import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.loaders.mining_restriction_loader import MiningRestrictionLoader
from app.runners.mining_restriction_runner import task_database_url


FIXTURE = Path(__file__).parent / "fixtures" / "mining_restrictions.geojson"


def test_invalid_date_is_reported_before_database_write(tmp_path):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][0]]
    data["features"][0]["properties"]["source_updated_at"] = "not-a-date"
    file = tmp_path / "invalid_date.geojson"
    file.write_text(json.dumps(data))
    loader = MiningRestrictionLoader(Mock(), file, report_file=tmp_path / "report.json")
    loader.repository = Mock()
    loader.repository.upsert_many.return_value = 0
    report = loader.execute()

    assert report["read"] == 1
    assert report["accepted"] == 0
    assert report["rejected_count"] == 1
    assert "date" in report["rejected"][0]["reason"]
    loader.repository.upsert_many.assert_called_once_with([])


def test_failure_rolls_back_and_keeps_rejection_report(tmp_path):
    session = Mock()
    report_file = tmp_path / "report.json"
    loader = MiningRestrictionLoader(session, FIXTURE, report_file=report_file)
    loader.repository = Mock()
    loader.repository.upsert_many.side_effect = RuntimeError("test database failure")
    with pytest.raises(RuntimeError):
        loader.execute()

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    report = json.loads(report_file.read_text())
    assert report["database_status"] == "rolled_back"
    assert report["upserted"] == 0
    assert report["rejected_count"] == 3
    assert report["database_error_type"] == "RuntimeError"


def test_non_fixture_record_is_rejected(tmp_path):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][0]]
    data["features"][0]["properties"]["is_fixture"] = False
    file = tmp_path / "unlabelled.geojson"
    file.write_text(json.dumps(data))
    loader = MiningRestrictionLoader(Mock(), file, report_file=tmp_path / "report.json")
    loader.repository = Mock()
    loader.repository.upsert_many.return_value = 0
    report = loader.execute()
    assert report["accepted"] == 0
    assert report["rejected_count"] == 1
    assert "is_fixture=true" in report["rejected"][0]["reason"]


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://example.invalid:5432/iris_geo_sn",
    "postgresql+psycopg2://127.0.0.1:4000/iris_core",
    "sqlite:///iris_geo_sn",
])
def test_runner_refuses_other_databases(monkeypatch, tmp_path, url):
    monkeypatch.setenv("IRIS_DATABASE_URL", url)
    with pytest.raises(ValueError, match="isolated local"):
        task_database_url(tmp_path / "unused.env")


def test_report_cannot_overwrite_input_fixture(tmp_path):
    file = tmp_path / "fixture.geojson"
    original = FIXTURE.read_text()
    file.write_text(original)
    with pytest.raises(ValueError, match="Report path must differ"):
        MiningRestrictionLoader(Mock(), file, report_file=file)
    assert file.read_text() == original
