-- Local assignment database only. Table definition follows MiningRestriction.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS iris_staging;

CREATE TABLE iris_staging.mining_restrictions (
    id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    state VARCHAR(2) NOT NULL,
    source_layer TEXT NOT NULL,
    hazard_type VARCHAR(80) NOT NULL,
    status TEXT,
    hazard_classification TEXT,
    source_url TEXT NOT NULL,
    source_updated_at DATE,
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_fixture BOOLEAN NOT NULL,
    geometry geometry(GEOMETRY,25832) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT uq_mining_restrictions_source UNIQUE (state, source_layer, source_id),
    CONSTRAINT ck_mining_restrictions_state CHECK (state = 'SN'),
    CONSTRAINT ck_mining_restrictions_geometry CHECK (
        ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry)
        AND ARRAY['POINT', 'MULTIPOINT', 'POLYGON', 'MULTIPOLYGON']
            @> ARRAY[GeometryType(geometry)]
    )
);

CREATE INDEX idx_mining_restrictions_geometry
    ON iris_staging.mining_restrictions USING gist (geometry);
