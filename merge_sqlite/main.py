#!/usr/bin/env python

import os

# import sys
from argparse import ArgumentParser, Namespace
from logging import DEBUG, INFO, Logger, basicConfig, getLogger
from pathlib import Path
from subprocess import check_output
from typing import IO, List


def allow_create_fail(sql_path: str) -> str:
    create_notfail_file = "create_notfail.sql"
    with open(create_notfail_file, "w") as create_notfail_open, open(
        sql_path, "r"
    ) as sql_open:
        for line in sql_open:
            if line.startswith("CREATE"):
                if "NOT EXISTS" in line:
                    create_notfail_open.write(line)
                else:
                    if "TABLE" in line:
                        newline = line.replace("TABLE", "TABLE IF NOT EXISTS")
                    elif "INDEX" in line:
                        newline = line.replace("INDEX", "INDEX IF NOT EXISTS")
                    create_notfail_open.write(newline)
            else:
                create_notfail_open.write(line)
    return create_notfail_file


# def get_table_column_list(f_open: IO, alter_sql_open: IO, logger: Logger) -> List[str]:
#    table_column_list: List[str] = list()
#    for line in f_open:
#        logger.info("line=%s" % line)
#        if line.startswith(");"):
#            alter_sql_open.write(line)
#            return table_column_list
#        else:
#            alter_sql_open.write(line)
#            line = line.strip().strip("\n").lstrip().rstrip(",")
#            line_split = line.split()
#            column_name = " ".join(line_split[:-1])
#            table_column_list.append(column_name)
#    sys.exit(f"failed on file: {f_open}")
def get_table_column_list(f_open: IO, alter_sql_open: IO, logger: Logger) -> List[str]:
    table_column_list: List[str] = []
    for line in f_open:
        logger.info("line=%s" % line)
        alter_sql_open.write(line)
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("--"):
            continue  # skip empty lines and comments
        if line_stripped.startswith(");"):
            # End of CREATE TABLE block
            return table_column_list
        # Remove trailing comma if present
        if line_stripped.endswith(","):
            line_stripped = line_stripped[:-1]
        # Skip lines that don't look like column definitions
        if " " not in line_stripped:
            continue
        line_split = line_stripped.split()
        column_name = line_split[0]  # just the column name
        table_column_list.append(column_name)
    return table_column_list  # fallback


# def alter_insert(sql_path: str, logger: Logger) -> str:
#    specific_insert_file = "specific_insert.sql"
#    alter_sql_open = open(specific_insert_file, "w")
#    with open(sql_path, "r") as f_open:
#        for line in f_open:
#            if line.startswith("CREATE TABLE"):
#                alter_sql_open.write(line)
#                table_column_list = get_table_column_list(
#                    f_open, alter_sql_open, logger
#                )
#            elif line.startswith("INSERT INTO"):
#                line = line.strip("\n")
#                specific_columns = "(" + ",".join(table_column_list) + ")"
#                logger.info("specific_columns=%s" % specific_columns)
#                line_split = line.split()
#                line_split.insert(3, specific_columns)
#                new_line = " ".join(line_split) + "\n"
#               alter_sql_open.write(new_line)
#           else:
#                alter_sql_open.write(line)
#    alter_sql_open.close()
#    return specific_insert_file
def alter_insert(sql_path: str, logger: Logger) -> str:
    specific_insert_file = "specific_insert.sql"
    with open(specific_insert_file, "w") as alter_sql_open, open(
        sql_path, "r"
    ) as f_open:
        table_column_list = []
        for line in f_open:
            if line.startswith("CREATE TABLE"):
                alter_sql_open.write(line)
                table_column_list = get_table_column_list(
                    f_open, alter_sql_open, logger
                )
                continue

            if line.startswith("INSERT INTO") or line.startswith(
                "INSERT OR IGNORE INTO"
            ):
                line = line.strip()

                # force OR IGNORE
                line = line.replace("INSERT INTO", "INSERT OR IGNORE INTO")

                # extract table name
                parts = line.split()
                table_name = parts[4]

                specific_columns = "(" + ",".join(table_column_list) + ")"
                logger.info(f"specific_columns={specific_columns}")

                # rewrite cleanly
                if "VALUES" not in line:
                    raise ValueError(f"Unexpected INSERT syntax: {line}")

                vals = line.split("VALUES", 1)[1]
                new_line = f"INSERT OR IGNORE INTO {table_name} {specific_columns} VALUES{vals}\n"
                alter_sql_open.write(new_line)
                continue

            # otherwise just copy
            alter_sql_open.write(line)

    return specific_insert_file


# def specific_column_insert(sql_path: str, logger: Logger) -> str:
#    specific_insert_file = alter_insert(sql_path, logger)
#    return specific_insert_file
def specific_column_insert(sql_path: str, logger: Logger) -> str:
    specific_insert_file = alter_insert(sql_path, logger)
    with open(specific_insert_file, "r") as f:
        data = f.read()

    data = data.replace("INSERT INTO", "INSERT OR IGNORE INTO")

    with open(specific_insert_file, "w") as f:
        f.write(data)

    return specific_insert_file


def setup_logging(args: Namespace, job_uuid: str) -> Logger:
    basicConfig(
        filename=os.path.join(job_uuid + ".log"),
        level=args.level,
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d_%H:%M:%S_%Z",
    )
    getLogger("sqlalchemy.engine").setLevel(INFO)
    logger = getLogger(__name__)
    return logger


def main() -> int:
    parser = ArgumentParser("merge an arbitrary number of sqlite files")
    # Logging flags.
    parser.add_argument(
        "-d",
        "--debug",
        action="store_const",
        const=DEBUG,
        dest="level",
        help="Enable debug logging.",
    )
    parser.set_defaults(level=INFO)

    parser.add_argument("-s", "--source_sqlite", action="append", required=False)
    parser.add_argument("-u", "--job_uuid", required=True)
    args = parser.parse_args()

    source_sqlite_list = args.source_sqlite
    job_uuid = args.job_uuid

    logger = setup_logging(args, job_uuid)

    if source_sqlite_list is None:
        logger.info("empty set, create 0 byte file")
        db = Path(f"{job_uuid}.db")
        db.touch()
    else:
        for source_sqlite_path in source_sqlite_list:
            logger.info(f"{source_sqlite_path=}")
            source_sqlite_name = os.path.splitext(os.path.basename(source_sqlite_path))[
                0
            ]

            # dump
            source_dump_path = f"{source_sqlite_name}.sql"
            cmd = ["sqlite3", source_sqlite_path, ".dump"]
            dump = check_output(cmd)
            with open(source_dump_path, "wb") as f:
                f.write(dump)
            #            shell_cmd = shlex.split(cmd)
            # check_output(cmd, shell=True)

            # alter text create table/index
            create_notfail_file = allow_create_fail(source_dump_path)

            # specific column insert
            specific_insert_file = specific_column_insert(create_notfail_file, logger)

            # load
            destination_sqlite_path = f"{job_uuid}.db"
            cmd = ["sqlite3", destination_sqlite_path]
            with open(specific_insert_file, "rb") as f:
                check_output(cmd, input=f.read())
            # cmd = f"sqlite3 {destination_sqlite_path} < {specific_insert_file}"
            #            shell_cmd = shlex.split(cmd)
            # check_output(cmd, shell=True)
    return 0


if __name__ == "__main__":
    main()
