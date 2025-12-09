#!/usr/bin/env python

import os
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from logging import DEBUG, INFO, Logger, basicConfig, getLogger
from pathlib import Path
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


def get_table_column_list(f_open: IO, alter_sql_open: IO, logger: Logger) -> List[str]:
    table_column_list: List[str] = list()
    for line in f_open:
        logger.info("line=%s" % line)
        stripped_line = line.strip()
        alter_sql_open.write(line)
        if stripped_line.startswith(");"):
            return table_column_list
        if not stripped_line:
            continue
        line_split = stripped_line.rstrip(",").split()
        if len(line_split) < 2:
            continue
        column_name = " ".join(line_split[:-1])
        table_column_list.append(column_name)
    return table_column_list


def alter_insert(sql_path: str, logger: Logger) -> str:
    specific_insert_file = "specific_insert.sql"
    with open(sql_path, "r") as f_open, open(
        specific_insert_file, "w"
    ) as alter_sql_open:
        table_column_list = []
        for line in f_open:
            if line.startswith("CREATE TABLE"):
                alter_sql_open.write(line)
                table_column_list = get_table_column_list(
                    f_open, alter_sql_open, logger
                )
            elif line.startswith("INSERT INTO"):
                line_split = line.strip().split()
                specific_columns = "(" + ",".join(table_column_list) + ")"
                logger.info("specific_columns=%s" % specific_columns)
                # Use INSERT OR IGNORE to avoid UNIQUE constraint errors
                line_split[0] = "INSERT"
                line_split.insert(1, "OR IGNORE")
                line_split.insert(3, specific_columns)
                alter_sql_open.write(" ".join(line_split) + "\n")
            else:
                alter_sql_open.write(line)
    return specific_insert_file


def specific_column_insert(sql_path: str, logger: Logger) -> str:
    return alter_insert(sql_path, logger)


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
    destination_sqlite_path = os.path.abspath(f"{job_uuid}.db")

    # Ensure destination DB exists
    Path(destination_sqlite_path).touch(exist_ok=True)

    if not source_sqlite_list:
        logger.info(
            "No source databases provided, created empty DB: %s",
            destination_sqlite_path,
        )
        return 0

    for source_sqlite_path in source_sqlite_list:
        source_sqlite_path = os.path.abspath(source_sqlite_path)
        source_sqlite_name = os.path.splitext(os.path.basename(source_sqlite_path))[0]
        source_dump_path = os.path.abspath(f"{source_sqlite_name}.sql")

        # Dump SQLite database safely
        with open(source_dump_path, "wb") as f:
            subprocess.run(
                ["sqlite3", source_sqlite_path, ".dump"], stdout=f, check=True
            )

        # Convert CREATE statements to IF NOT EXISTS
        create_notfail_file = allow_create_fail(source_dump_path)

        # Rewrite INSERT statements with specific columns and OR IGNORE
        specific_insert_file = specific_column_insert(create_notfail_file, logger)

        # Load into destination DB
        with open(specific_insert_file, "rb") as f:
            subprocess.run(["sqlite3", destination_sqlite_path], stdin=f, check=True)

        logger.info("Merged %s into %s", source_sqlite_path, destination_sqlite_path)

    logger.info("All databases merged successfully into %s", destination_sqlite_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
