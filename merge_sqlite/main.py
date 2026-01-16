#!/usr/bin/env python

# import os
from argparse import ArgumentParser, Namespace
from logging import DEBUG, INFO, Logger, basicConfig, getLogger
from pathlib import Path
from subprocess import check_output
from typing import IO, List


def allow_create_fail(sql_path: str) -> str:
    """
    Rewrite CREATE TABLE / INDEX statements to use IF NOT EXISTS.
    """
    create_notfail_file = "create_notfail.sql"
    with open(create_notfail_file, "w") as out_f, open(sql_path, "r") as in_f:
        for line in in_f:
            if line.startswith("CREATE"):
                if "NOT EXISTS" in line:
                    out_f.write(line)
                else:
                    if "TABLE" in line:
                        out_f.write(line.replace("TABLE", "TABLE IF NOT EXISTS"))
                    elif "INDEX" in line:
                        out_f.write(line.replace("INDEX", "INDEX IF NOT EXISTS"))
                    else:
                        out_f.write(line)
            else:
                out_f.write(line)
    return create_notfail_file


def get_table_column_list(f_open: IO, alter_sql_open: IO, logger: Logger) -> List[str]:
    table_column_list: List[str] = []

    for line in f_open:
        alter_sql_open.write(line)
        stripped = line.strip()

        if not stripped or stripped.startswith("--"):
            continue

        if stripped.startswith(");"):
            return table_column_list

        # remove trailing comma
        if stripped.endswith(","):
            stripped = stripped[:-1]

        # quoted column name
        if stripped.startswith('"'):
            end = stripped.find('"', 1)
            if end == -1:
                raise ValueError(f"Unterminated quoted column: {line}")
            column_name = stripped[: end + 1]

        # unquoted column name
        else:
            column_name = stripped.split()[0]

        logger.info("parsed column: %s", column_name)
        table_column_list.append(column_name)

    raise ValueError("CREATE TABLE block did not terminate correctly")


def alter_insert(sql_path: str, logger: Logger) -> str:
    """
    Rewrite INSERT statements to include explicit column lists
    and force INSERT OR IGNORE.
    """
    specific_insert_file = "specific_insert.sql"

    with open(specific_insert_file, "w") as out_f, open(sql_path, "r") as in_f:
        table_column_list: List[str] = []

        for line in in_f:
            if line.startswith("CREATE TABLE"):
                out_f.write(line)
                table_column_list = get_table_column_list(in_f, out_f, logger)
                continue

            if line.startswith("INSERT INTO") or line.startswith(
                "INSERT OR IGNORE INTO"
            ):
                line = line.strip()
                line = line.replace("INSERT INTO", "INSERT OR IGNORE INTO")

                if "VALUES" not in line:
                    raise ValueError(f"Unexpected INSERT syntax: {line}")

                parts = line.split()
                table_name = parts[4]
                columns = "(" + ",".join(table_column_list) + ")"
                values = line.split("VALUES", 1)[1]

                new_line = (
                    f"INSERT OR IGNORE INTO {table_name} {columns} VALUES{values}\n"
                )
                logger.info("specific_columns=%s", columns)
                out_f.write(new_line)
                continue

            out_f.write(line)

    return specific_insert_file


def specific_column_insert(sql_path: str, logger: Logger) -> str:
    """
    Wrapper for alter_insert (kept for API compatibility).
    """
    return alter_insert(sql_path, logger)


def setup_logging(args: Namespace, job_uuid: str) -> Logger:
    basicConfig(
        filename=f"{job_uuid}.log",
        level=args.level,
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d_%H:%M:%S_%Z",
    )
    getLogger("sqlalchemy.engine").setLevel(INFO)
    return getLogger(__name__)


def main() -> int:
    parser = ArgumentParser("merge an arbitrary number of sqlite files")

    parser.add_argument(
        "-d",
        "--debug",
        action="store_const",
        const=DEBUG,
        dest="level",
        help="Enable debug logging",
    )
    parser.set_defaults(level=INFO)

    parser.add_argument("-s", "--source_sqlite", action="append", required=False)
    parser.add_argument("-u", "--job_uuid", required=True)

    args = parser.parse_args()

    logger = setup_logging(args, args.job_uuid)
    destination_db = Path(f"{args.job_uuid}.db")

    if not args.source_sqlite:
        logger.info("No source databases provided; creating empty db")
        destination_db.touch()
        return 0

    for source_sqlite_path in args.source_sqlite:
        logger.info("Processing %s", source_sqlite_path)
        source_name = Path(source_sqlite_path).stem
        dump_path = f"{source_name}.sql"

        dump = check_output(["sqlite3", source_sqlite_path, ".dump"])
        with open(dump_path, "wb") as f:
            f.write(dump)

        create_safe_sql = allow_create_fail(dump_path)
        insert_safe_sql = specific_column_insert(create_safe_sql, logger)

        with open(insert_safe_sql, "rb") as f:
            check_output(["sqlite3", str(destination_db)], input=f.read())

    return 0


if __name__ == "__main__":
    main()
