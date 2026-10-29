import os
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, Polygon, box
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models.mining_restriction import MiningRestriction
from app.database.repositories.mining_restriction_repository import MiningRestrictionRepository
from app.parsers.mining_restriction_parser import MiningRestrictionParser


@pytest.fixture
def session():
    database_url = os.environ.get("IRIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set IRIS_TEST_DATABASE_URL to the isolated task database.")
    url = make_url(database_url)
    if url.database != "iris_geo_sn" or (url.host, url.port) not in {
        ("127.0.0.1", 4000), ("localhost", 4000), ("staging-db", 5432)
    }:
        pytest.fail("Repository tests require the isolated local iris_geo_sn database.")

    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db_session:
                yield db_session
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def records():
    file = Path(__file__).parent / "fixtures" / "mining_restrictions.geojson"
    parsed = MiningRestrictionParser(file).parse()
    prefix = "test-repo-" + uuid4().hex
    rows = []
    for index, record in enumerate(parsed.accepted.to_dict("records")):
        record.pop("fixture_case")
        record["source_id"] = f"{prefix}-{index}"
        if record["source_updated_at"] is not None:
            record["source_updated_at"] = date.fromisoformat(record["source_updated_at"])
        record["geometry"] = from_shape(record["geometry"], srid=25832)
        rows.append(record)
    return rows


def stored_record(session, record):
    table = MiningRestriction.__table__
    return session.execute(select(table).where(
        table.c.state == record["state"],
        table.c.source_layer == record["source_layer"],
        table.c.source_id == record["source_id"],
    )).mappings().one()


def test_duplicate_load_preserves_identity_and_unknown_metadata(session, records):
    repository = MiningRestrictionRepository(session)
    before = repository.count()
    assert repository.upsert_many(records) == 3
    first = stored_record(session, records[0])
    assert repository.upsert_many(records) == 3
    second = stored_record(session, records[0])

    assert repository.count() == before + 3
    assert second["id"] == first["id"]
    assert second["created_at"] == first["created_at"]
    unknown = stored_record(session, records[2])
    assert unknown["hazard_classification"] is None
    assert unknown["status"] is None
    assert unknown["source_updated_at"] is None
    assert unknown["is_fixture"] is True


def test_existing_record_updates_attributes_and_geometry(session, records):
    repository = MiningRestrictionRepository(session)
    repository.upsert_many([records[1]])
    first = stored_record(session, records[1])
    changed = dict(records[1])
    changed["status"] = "fixture_only_updated"
    changed["hazard_classification"] = None
    changed["fetched_at"] += timedelta(minutes=1)
    changed["geometry"] = from_shape(Point(830_000, 5_660_000), srid=25832)
    repository.upsert_many([changed])
    updated = stored_record(session, changed)

    assert updated["id"] == first["id"]
    assert updated["created_at"] == first["created_at"]
    assert updated["status"] == "fixture_only_updated"
    assert updated["hazard_classification"] is None
    assert updated["fetched_at"] > first["fetched_at"]
    assert to_shape(updated["geometry"]).equals(Point(830_000, 5_660_000))


def test_duplicate_keys_within_batch_use_last_record(session, records):
    repository = MiningRestrictionRepository(session)
    changed = {**records[0], "status": "fixture_only_last_in_batch"}
    assert repository.upsert_many([records[0], changed]) == 1
    assert stored_record(session, changed)["status"] == changed["status"]


def test_database_error_does_not_leave_a_partial_batch(session, records):
    repository = MiningRestrictionRepository(session)
    before = repository.count()
    wrong_state = {**records[1], "state": "NW"}
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            repository.upsert_many([records[0], wrong_state])
    assert repository.count() == before


def test_empty_batch_is_a_no_op(session):
    repository = MiningRestrictionRepository(session)
    before = repository.count()
    assert repository.upsert_many([]) == 0
    assert repository.count() == before


@pytest.fixture
def spatial_records(session, records):
    # Projected coordinates make distances and areas independently checkable.
    geometries = [
        box(850_000, 5_650_000, 850_010, 5_650_010),
        Point(850_030, 5_650_005),
        box(850_050, 5_650_000, 850_060, 5_650_010),
    ]
    for record, geometry in zip(records, geometries):
        record["geometry"] = from_shape(geometry, srid=25832)
    MiningRestrictionRepository(session).upsert_many(records)
    return records


def test_parcel_inside_hazard_is_an_intersection(session, spatial_records):
    parcel = from_shape(box(850_002, 5_650_002, 850_008, 5_650_008), srid=25832)
    matches = MiningRestrictionRepository(session).find_intersections(parcel)
    assert [row["source_id"] for row in matches] == [spatial_records[0]["source_id"]]
    assert matches[0]["intersection_area_m2"] == pytest.approx(36)
    assert matches[0]["source_url"] == spatial_records[0]["source_url"]


def test_parcel_contains_hazards_and_preserves_unknown_classification(session, spatial_records):
    parcel = from_shape(box(849_999, 5_649_999, 850_061, 5_650_011), srid=25832)
    matches = MiningRestrictionRepository(session).find_intersections(parcel)
    by_id = {row["source_id"]: row for row in matches}
    assert set(by_id) == {record["source_id"] for record in spatial_records}
    assert by_id[spatial_records[1]["source_id"]]["intersection_area_m2"] == 0
    assert by_id[spatial_records[2]["source_id"]]["hazard_classification"] is None


def test_boundary_contact_counts_as_intersection_and_zero_distance(session, spatial_records):
    parcel = from_shape(box(850_010, 5_650_002, 850_020, 5_650_008), srid=25832)
    repository = MiningRestrictionRepository(session)
    matches = repository.find_intersections(parcel)
    assert [row["source_id"] for row in matches] == [spatial_records[0]["source_id"]]
    assert matches[0]["intersection_area_m2"] == 0
    nearby = repository.find_within_distance(parcel, 0)
    assert [row["source_id"] for row in nearby] == [spatial_records[0]["source_id"]]
    assert nearby[0]["distance_m"] == 0


@pytest.mark.parametrize("threshold, expected_indexes", [
    (4.99, []), (5, [1]), (10, [1, 0]), (25, [1, 0, 2]),
])
def test_proximity_thresholds_in_metres(session, spatial_records, threshold, expected_indexes):
    parcel = from_shape(box(850_020, 5_650_002, 850_025, 5_650_008), srid=25832)
    repository = MiningRestrictionRepository(session)
    assert repository.find_intersections(parcel) == []
    matches = repository.find_within_distance(parcel, threshold)
    assert [row["source_id"] for row in matches] == [spatial_records[index]["source_id"] for index in expected_indexes]
    assert [row["distance_m"] for row in matches] == [5, 10, 25][:len(expected_indexes)]


@pytest.mark.parametrize("distance", [-1, float("nan"), float("inf"), True])
def test_invalid_distance_is_rejected(distance):
    repository = MiningRestrictionRepository(None)
    parcel = from_shape(box(850_000, 5_650_000, 850_010, 5_650_010), srid=25832)
    with pytest.raises(ValueError, match="non-negative"):
        repository.find_within_distance(parcel, distance)


@pytest.mark.parametrize("parcel", [
    from_shape(box(13.7, 51, 13.71, 51.01), srid=4326),
    from_shape(Point(850_000, 5_650_000), srid=25832),
    from_shape(Polygon(), srid=25832),
])
def test_wrong_crs_and_invalid_parcel_shapes_are_rejected(parcel):
    repository = MiningRestrictionRepository(None)
    with pytest.raises(ValueError, match="Parcel must"):
        repository.find_intersections(parcel)
