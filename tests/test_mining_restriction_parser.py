import json
from pathlib import Path

import pytest

from app.parsers.mining_restriction_parser import MiningRestrictionParser


FIXTURE = Path(__file__).parent / "fixtures" / "mining_restrictions.geojson"


def test_fixture_rejections_are_visible_and_missing_metadata_is_preserved():
    result = MiningRestrictionParser(FIXTURE).parse()

    assert result.read_count == 6
    assert len(result.accepted) == 3
    assert {row["fixture_case"] for row in result.rejected} == {
        "null_geometry", "invalid_polygon", "missing_source_id"
    }
    assert all(row["reason"] for row in result.rejected)
    unknown = result.accepted.set_index("source_id").loc["fixture-sn-003"]
    assert unknown["hazard_classification"] is None
    assert unknown["status"] is None
    assert unknown["source_updated_at"] is None


def test_coordinates_are_transformed_and_geometry_types_are_preserved():
    result = MiningRestrictionParser(FIXTURE).parse()
    assert result.accepted.crs.to_epsg() == 25832
    assert set(result.accepted.geometry.geom_type) == {"Point", "Polygon"}
    assert result.accepted.geometry.is_valid.all()

    point = result.accepted.set_index("source_id").loc["fixture-sn-002"].geometry
    # Projected coordinates must be in metres, not just relabelled lon/lat.
    assert 800_000 < point.x < 900_000
    assert 5_600_000 < point.y < 5_700_000
    original = result.accepted.to_crs("EPSG:4326")
    original_point = original.set_index("source_id").loc["fixture-sn-002"].geometry
    assert original_point.x == pytest.approx(13.701, abs=1e-7)
    assert original_point.y == pytest.approx(51.001, abs=1e-7)


def test_wrong_region_and_empty_valid_result(tmp_path):
    data = json.loads(FIXTURE.read_text())
    feature = data["features"][0]
    feature["properties"]["state"] = "NW"
    data["features"] = [feature]
    file = tmp_path / "wrong_region.geojson"
    file.write_text(json.dumps(data))

    result = MiningRestrictionParser(file).parse()
    assert result.accepted.empty
    assert result.accepted.crs.to_epsg() == 25832
    assert len(result.rejected) == 1
    assert "Saxony" in result.rejected[0]["reason"]


@pytest.mark.parametrize("geometry", ["broken", [], 42, {"type": []}])
def test_malformed_geometry_is_rejected_without_stopping_other_records(tmp_path, geometry):
    data = json.loads(FIXTURE.read_text())
    data["features"] = data["features"][:2]
    data["features"][0]["geometry"] = geometry
    file = tmp_path / "malformed.geojson"
    file.write_text(json.dumps(data))
    result = MiningRestrictionParser(file).parse()
    assert len(result.accepted) == 1
    assert result.accepted.iloc[0]["source_id"] == "fixture-sn-002"
    assert len(result.rejected) == 1
    assert "geometry" in result.rejected[0]["reason"].lower()


def test_three_dimensional_geometry_is_rejected_before_database_loading(tmp_path):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][1]]
    data["features"][0]["geometry"]["coordinates"].append(100)
    file = tmp_path / "three_dimensional.geojson"
    file.write_text(json.dumps(data))
    result = MiningRestrictionParser(file).parse()
    assert result.accepted.empty
    assert "two-dimensional" in result.rejected[0]["reason"]


@pytest.mark.parametrize("field, value", [
    ("status", {}), ("status", 42),
    ("hazard_classification", []), ("hazard_classification", True),
])
def test_non_text_metadata_is_rejected(tmp_path, field, value):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][0]]
    data["features"][0]["properties"][field] = value
    file = tmp_path / "metadata.geojson"
    file.write_text(json.dumps(data))
    result = MiningRestrictionParser(file).parse()
    assert result.accepted.empty
    assert field in result.rejected[0]["reason"]


@pytest.mark.parametrize("field, value", [
    ("source_url", "https://example.invalid/other-source"),
    ("source_layer", "other_layer"),
])
def test_wrong_source_reference_is_rejected(tmp_path, field, value):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][0]]
    data["features"][0]["properties"][field] = value
    file = tmp_path / "wrong_source.geojson"
    file.write_text(json.dumps(data))
    result = MiningRestrictionParser(file).parse()
    assert result.accepted.empty
    assert "source URL and layer" in result.rejected[0]["reason"]


@pytest.mark.parametrize("coordinates", [[200, 51], [13.7, 151]])
def test_out_of_range_longitude_or_latitude_is_rejected(tmp_path, coordinates):
    data = json.loads(FIXTURE.read_text())
    data["features"] = [data["features"][1]]
    data["features"][0]["geometry"]["coordinates"] = coordinates
    file = tmp_path / "out_of_range.geojson"
    file.write_text(json.dumps(data))
    result = MiningRestrictionParser(file).parse()
    assert result.accepted.empty
    assert "longitude/latitude" in result.rejected[0]["reason"]


def test_invalid_source_crs_fails_as_configuration_error():
    with pytest.raises(ValueError, match="source CRS configuration"):
        MiningRestrictionParser(FIXTURE, source_crs="not-a-crs")
