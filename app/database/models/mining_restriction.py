from __future__ import annotations

from datetime import date, datetime

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Index, Integer, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.entity import BaseEntity


class MiningRestriction(BaseEntity):
    """Staging record for the assumed IRIS-GEO-SN fixture schema."""

    __tablename__ = "mining_restrictions"
    __table_args__ = (
        UniqueConstraint(
            "state", "source_layer", "source_id",
            name="uq_mining_restrictions_source",
        ),
        CheckConstraint("state = 'SN'", name="ck_mining_restrictions_state"),
        CheckConstraint(
            "ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry) "
            # Array containment avoids PostGIS inferring a single fixed type.
            "AND ARRAY['POINT', 'MULTIPOINT', 'POLYGON', 'MULTIPOLYGON'] "
            "@> ARRAY[GeometryType(geometry)]",
            name="ck_mining_restrictions_geometry",
        ),
        Index(
            "idx_mining_restrictions_geometry", "geometry",
            postgresql_using="gist",
        ),
        {"schema": "iris_staging"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The unique source key identifies a record across repeated loads.
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    source_layer: Mapped[str] = mapped_column(Text, nullable=False)

    hazard_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    hazard_classification: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Require the loader to explicitly identify simulated records.
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False)

    geometry: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=25832, spatial_index=False),
        nullable=False,
    )
