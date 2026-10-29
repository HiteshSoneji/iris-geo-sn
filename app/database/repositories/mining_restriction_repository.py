from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models.mining_restriction import MiningRestriction
from app.database.repositories.base_repository import BaseRepository


class MiningRestrictionRepository(BaseRepository[MiningRestriction]):
    """Write staging records; the caller controls commit and rollback."""

    KEY_FIELDS = ("state", "source_layer", "source_id")
    UPDATE_FIELDS = (
        "hazard_type", "status", "hazard_classification", "source_url",
        "source_updated_at", "fetched_at", "is_fixture", "geometry",
    )

    def __init__(self, session: Session):
        super().__init__(session, MiningRestriction)

    def upsert_many(self, records: Sequence[Mapping[str, Any]]) -> int:
        """Insert or update records and return the number of distinct keys.

        Values must be database-ready (dates, timestamps and PostGIS geometry).
        For duplicate keys in one batch, the last record wins. Internal IDs and
        creation timestamps are never replaced. This method does not commit.
        """
        unique_records = {}
        for record in records:
            key = tuple(record.get(field) for field in self.KEY_FIELDS)
            if any(not isinstance(value, str) or not value.strip() for value in key):
                raise ValueError("Each record needs state, source_layer and source_id.")
            unique_records[key] = {
                field: record.get(field)
                for field in (*self.KEY_FIELDS, *self.UPDATE_FIELDS)
            }

        rows = list(unique_records.values())
        for offset in range(0, len(rows), 500):
            statement = insert(self.model).values(rows[offset:offset + 500])
            updates = {
                field: getattr(statement.excluded, field)
                for field in self.UPDATE_FIELDS
            }
            # ON CONFLICT does not apply the ORM's onupdate setting itself.
            updates["updated_at"] = func.now()
            self.session.execute(statement.on_conflict_do_update(
                constraint="uq_mining_restrictions_source",
                set_=updates,
            ))

        return len(rows)

    def find_intersections(self, parcel: WKBElement) -> list[dict]:
        """Find parcel intersections, including containment and boundary contact.

        Point matches and boundary-only contact have zero intersection area.
        An empty result does not establish that a parcel is safe.
        """
        self._validate_parcel(parcel)
        statement = select(
            *self._spatial_columns(),
            func.ST_Area(
                func.ST_Intersection(self.model.geometry, parcel)
            ).label("intersection_area_m2"),
        ).where(
            func.ST_Intersects(self.model.geometry, parcel)
        ).order_by(self.model.state, self.model.source_layer, self.model.source_id)
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def find_within_distance(self, parcel: WKBElement, distance_m: float) -> list[dict]:
        """Find hazards at or within a distance in projected metres.

        Intersecting features have distance zero and are included.
        """
        self._validate_parcel(parcel)
        if (
            isinstance(distance_m, bool)
            or not isinstance(distance_m, Real)
            or not math.isfinite(distance_m)
            or distance_m < 0
        ):
            raise ValueError("distance_m must be a finite, non-negative number.")
        distance = func.ST_Distance(self.model.geometry, parcel).label("distance_m")
        statement = select(
            *self._spatial_columns(), distance,
        ).where(
            func.ST_DWithin(self.model.geometry, parcel, float(distance_m))
        ).order_by(distance, self.model.state, self.model.source_layer, self.model.source_id)
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def _spatial_columns(self):
        return (
            self.model.state, self.model.source_id, self.model.source_layer,
            self.model.source_url, self.model.hazard_type, self.model.status,
            self.model.hazard_classification, self.model.is_fixture,
        )

    @staticmethod
    def _validate_parcel(parcel: WKBElement) -> None:
        if not isinstance(parcel, WKBElement) or parcel.srid != 25832:
            raise ValueError("Parcel must be a PostGIS geometry in EPSG:25832.")
        geometry = to_shape(parcel)
        if (
            geometry.geom_type not in {"Polygon", "MultiPolygon"}
            or geometry.is_empty
            or not geometry.is_valid
        ):
            raise ValueError("Parcel must be a valid, non-empty polygon or multipolygon.")
