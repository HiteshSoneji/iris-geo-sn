-- Read-only examples using fictional parcels and simulated hazard records.
-- A missing match is not a safe classification.

-- 1. Parcel inside fixture-sn-001, containing the shaft fixture-sn-002.
-- Intersects includes containment and boundary contact. Points have zero area.
WITH parcel AS (
    SELECT ST_Transform(ST_GeomFromText(
        'POLYGON ((13.7005 51.0005, 13.7015 51.0005, 13.7015 51.0015, 13.7005 51.0015, 13.7005 51.0005))',
        4326
    ), 25832) AS geometry
)
SELECT hazard.source_id, hazard.hazard_type, hazard.hazard_classification,
       hazard.source_url, hazard.source_layer, hazard.is_fixture,
       ST_Area(ST_Intersection(hazard.geometry, parcel.geometry)) AS intersection_area_m2
FROM iris_staging.mining_restrictions AS hazard CROSS JOIN parcel
WHERE hazard.is_fixture AND ST_Intersects(hazard.geometry, parcel.geometry)
ORDER BY hazard.source_id;

-- 2. A nearby parcel east of fixture-sn-001, with a 25 metre threshold.
-- Both geometries use EPSG:25832. Intersections would count as distance zero.
WITH parcel AS (
    SELECT ST_Transform(ST_GeomFromText(
        'POLYGON ((13.7022 51.0005, 13.7025 51.0005, 13.7025 51.0015, 13.7022 51.0015, 13.7022 51.0005))',
        4326
    ), 25832) AS geometry
)
SELECT hazard.source_id, hazard.hazard_type, hazard.hazard_classification,
       hazard.source_url, hazard.source_layer, hazard.is_fixture,
       ST_Distance(hazard.geometry, parcel.geometry) AS distance_m
FROM iris_staging.mining_restrictions AS hazard CROSS JOIN parcel
WHERE hazard.is_fixture AND ST_DWithin(hazard.geometry, parcel.geometry, 25.0)
ORDER BY distance_m, hazard.source_id;
