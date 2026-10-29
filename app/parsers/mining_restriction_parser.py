from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from pyproj.exceptions import ProjError
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.validation import explain_validity


@dataclass
class ParseResult:
    read_count: int
    accepted: gpd.GeoDataFrame
    rejected: list[dict]


class MiningRestrictionParser:
    """Validate GeoJSON records and project accepted geometries to EPSG:25832.

    Field names and hazard types follow our documented fixture assumptions,
    not a verified live WFS schema. No database connection is made here.
    """

    TARGET_CRS = "EPSG:25832"
    SOURCE_URL = "https://geoportal.sachsen.de/wfs/altbergbau"
    SOURCE_LAYER = "sn_salka_hohlraeume"
    HAZARD_TYPES = {
        "underground_cavity",
        "shaft",
        "legacy_mining_area",
        "contaminated_land",
        "mine_right",
    }
    GEOMETRY_TYPES = {"Point", "MultiPoint", "Polygon", "MultiPolygon"}
    FIELDS = (
        "source_id", "state", "hazard_type", "status",
        "hazard_classification", "source_url", "source_layer",
        "source_updated_at", "is_fixture", "fixture_case",
    )

    def __init__(self, file: Path | str, source_crs: str = "EPSG:4326"):
        self.file = Path(file)
        try:
            self.source_crs = CRS.from_user_input(source_crs)
        except (ProjError, TypeError, ValueError) as error:
            raise ValueError("Invalid source CRS configuration.") from error

    def parse(self) -> ParseResult:
        with self.file.open(encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            raise ValueError("Expected a GeoJSON FeatureCollection.")
        features = data.get("features")
        if not isinstance(features, list):
            raise ValueError("FeatureCollection.features must be a list.")

        accepted = []
        rejected = []
        fetched_at = datetime.now(timezone.utc)

        for index, feature in enumerate(features, start=1):
            properties = {}
            try:
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ValueError("Expected a GeoJSON Feature.")
                properties = feature.get("properties")
                if not isinstance(properties, dict):
                    properties = {}
                    raise ValueError("Missing or invalid properties.")

                record = {
                    field: self._clean_value(properties.get(field))
                    for field in self.FIELDS
                }
                for field in ("source_id", "state", "hazard_type", "source_url", "source_layer"):
                    if not isinstance(record[field], str) or not record[field]:
                        raise ValueError(f"Missing or invalid {field}.")
                if record["state"] != "SN":
                    raise ValueError("Expected state SN (Saxony).")
                if record["source_url"] != self.SOURCE_URL or record["source_layer"] != self.SOURCE_LAYER:
                    raise ValueError("Expected the assignment's source URL and layer reference.")
                if record["hazard_type"] not in self.HAZARD_TYPES:
                    raise ValueError("Unsupported hazard_type for this demonstrator.")
                for field in ("status", "hazard_classification"):
                    if record[field] is not None and not isinstance(record[field], str):
                        raise ValueError(f"{field} must be text or null.")

                geometry_data = feature.get("geometry")
                if geometry_data is None:
                    raise ValueError("Null geometry.")
                if not isinstance(geometry_data, dict):
                    raise ValueError("Geometry must be a GeoJSON geometry object.")
                geometry_type = geometry_data.get("type")
                if not isinstance(geometry_type, str) or geometry_type not in self.GEOMETRY_TYPES:
                    raise ValueError("Unsupported or missing geometry type.")
                geometry = shape(geometry_data)
                if geometry.is_empty:
                    raise ValueError("Empty geometry.")
                if not geometry.is_valid:
                    raise ValueError(f"Invalid geometry: {explain_validity(geometry)}.")
                if geometry.has_z:
                    raise ValueError("Only two-dimensional geometry is supported.")
                if self.source_crs.to_epsg() == 4326:
                    min_x, min_y, max_x, max_y = geometry.bounds
                    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
                        raise ValueError("Coordinates outside valid EPSG:4326 longitude/latitude ranges.")

                projected = gpd.GeoSeries(
                    [geometry], crs=self.source_crs
                ).to_crs(self.TARGET_CRS).iloc[0]
                if projected.is_empty or not projected.is_valid:
                    raise ValueError("Invalid geometry after coordinate transformation.")

                record["geometry"] = projected
                record["fetched_at"] = fetched_at
                accepted.append(record)

            except (ValueError, TypeError, KeyError, IndexError, ShapelyError, ProjError) as error:
                rejected.append({
                    "feature_index": index,
                    "source_id": properties.get("source_id"),
                    "fixture_case": properties.get("fixture_case"),
                    "source_url": properties.get("source_url"),
                    "source_layer": properties.get("source_layer"),
                    "reason": str(error),
                })

        columns = [*self.FIELDS, "fetched_at", "geometry"]
        records = gpd.GeoDataFrame(
            accepted, columns=columns, geometry="geometry", crs=self.TARGET_CRS
        )
        # Pandas may infer string columns with NaN; keep optional fields as None.
        for field in ("status", "hazard_classification", "source_updated_at"):
            records[field] = records[field].astype(object).where(records[field].notna(), None)
        return ParseResult(len(features), records, rejected)

    @staticmethod
    def _clean_value(value):
        if isinstance(value, str):
            return value.strip() or None
        return value


def main():
    cli = argparse.ArgumentParser(description="Validate mining-hazard GeoJSON; no database writes.")
    cli.add_argument("file", type=Path, help="GeoJSON file; coordinates default to EPSG:4326.")
    cli.add_argument("--source-crs", default="EPSG:4326")
    args = cli.parse_args()

    result = MiningRestrictionParser(args.file, source_crs=args.source_crs).parse()
    print(f"Input:    {args.file}")
    print(f"Read:     {result.read_count}")
    print(f"Accepted: {len(result.accepted)}")
    print(f"Rejected: {len(result.rejected)}")
    print(f"CRS:      {result.accepted.crs}")
    if not result.accepted.empty and result.accepted["is_fixture"].eq(True).all():
        print("Data:     Simulated fixture records; not official hazard data.")
    for rejected in result.rejected:
        label = rejected["source_id"] or f"feature {rejected['feature_index']}"
        print(f"Rejected {label}: {rejected['reason']}")


if __name__ == "__main__":
    main()
