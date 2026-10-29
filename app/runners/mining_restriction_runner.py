from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.commands.load_mining_restrictions_command import LoadMiningRestrictionsCommand


def task_database_url(env_file: Path | str) -> URL:
    settings = dotenv_values(env_file)
    value = os.environ.get("IRIS_DATABASE_URL") or settings.get("IRIS_DATABASE_URL")
    if not value:
        raise ValueError("Set IRIS_DATABASE_URL in the environment or task env file.")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg2" or url.database != "iris_geo_sn" or (url.host, url.port) not in {
        ("127.0.0.1", 4000), ("localhost", 4000), ("staging-db", 5432)
    }:
        raise ValueError("Only the isolated local iris_geo_sn database is supported.")
    return url


def main():
    cli = argparse.ArgumentParser(description="Load simulated mining records into local staging.")
    cli.add_argument("fixture", type=Path)
    cli.add_argument("--env-file", type=Path, default=Path(".env.iris"))
    cli.add_argument("--report", type=Path, default=Path("reports/mining_restrictions.json"))
    cli.add_argument("--source-crs", default="EPSG:4326")
    args = cli.parse_args()

    engine = None
    try:
        url = task_database_url(args.env_file)
        engine = create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)
        with Session(engine) as session:
            report = LoadMiningRestrictionsCommand(
                session, args.fixture, report_file=args.report, source_crs=args.source_crs
            ).execute()
    except SQLAlchemyError:
        cli.exit(1, "Database load failed. Check the local database and report; credentials are not printed.\n")
    except (OSError, ValueError) as error:
        cli.exit(1, f"Load failed: {error}\n")
    finally:
        if engine is not None:
            engine.dispose()

    print("Mode:     fixture (simulated data)")
    print(f"Read:     {report['read']}")
    print(f"Accepted: {report['accepted']}")
    print(f"Rejected: {report['rejected_count']}")
    print(f"Upserted: {report['upserted']} distinct source keys")
    print(f"Database: {report['database_status']}")
    print(f"Report:   {args.report}")
    for rejected in report["rejected"]:
        print(f"Rejected {rejected['source_id'] or 'missing source ID'}: {rejected['reason']}")


if __name__ == "__main__":
    main()
