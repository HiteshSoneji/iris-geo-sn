from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

from app.database.repositories.mining_restriction_repository import MiningRestrictionRepository
from app.parsers.mining_restriction_parser import MiningRestrictionParser


class MiningRestrictionLoader:
    """Parse simulated records, upsert a batch and save its rejection report.

    This loader owns commit/rollback for the supplied task session.
    """

    def __init__(
        self,
        session: Session,
        file: Path | str,
        report_file: Path | str = "reports/mining_restrictions.json",
        source_crs: str = "EPSG:4326",
    ):
        self.session = session
        self.parser = MiningRestrictionParser(file, source_crs=source_crs)
        self.repository = MiningRestrictionRepository(session)
        self.report_file = Path(report_file)
        if self.report_file.resolve() == self.parser.file.resolve():
            raise ValueError("Report path must differ from the input fixture path.")

    def execute(self) -> dict:
        parsed = self.parser.parse()
        rejected = list(parsed.rejected)
        records = []

        for record in parsed.accepted.to_dict("records"):
            try:
                if record["is_fixture"] is not True:
                    raise ValueError("Fixture mode requires is_fixture=true.")
                source_date = record["source_updated_at"]
                if source_date is not None:
                    source_date = date.fromisoformat(source_date)
                converted = dict(record)
                converted.pop("fixture_case", None)
                converted["source_updated_at"] = source_date
                converted["geometry"] = from_shape(record["geometry"], srid=25832)
                records.append(converted)
            except (TypeError, ValueError) as error:
                rejected.append({
                    "source_id": record["source_id"],
                    "fixture_case": record["fixture_case"],
                    "source_url": record["source_url"],
                    "source_layer": record["source_layer"],
                    "reason": str(error),
                })

        report = {
            "mode": "fixture",
            "input_file": str(self.parser.file),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "source_crs": str(self.parser.source_crs),
            "target_crs": self.parser.TARGET_CRS,
            "destination": "iris_staging.mining_restrictions",
            "source_urls": sorted({row["source_url"] for row in records}),
            "source_layers": sorted({row["source_layer"] for row in records}),
            "access_note": "Live permissions, licence and schema are unverified. These records are simulated.",
            "currency_note": "Fixture dates are fictional; they do not establish live data currency.",
            "read": parsed.read_count,
            "accepted": len(records),
            "rejected_count": len(rejected),
            "rejected": rejected,
            "unknown_classification_ids": [
                row["source_id"] for row in records if row["hazard_classification"] is None
            ],
            "upserted": 0,
            "database_status": "pending",
        }
        # Save validation evidence before attempting database writes.
        self._write_report(report)
        try:
            processed = self.repository.upsert_many(records)
            self.session.commit()
        except Exception as error:
            self.session.rollback()
            report["database_status"] = "rolled_back"
            # Do not copy connection details or SQL parameters into the report.
            report["database_error_type"] = type(error).__name__
            self._write_report(report)
            raise

        report["upserted"] = processed
        report["database_status"] = "committed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._write_report(report)
        return report

    def _write_report(self, report: dict) -> None:
        self.report_file.parent.mkdir(parents=True, exist_ok=True)
        self.report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
