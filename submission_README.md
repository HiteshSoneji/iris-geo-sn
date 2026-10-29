# IRIS-GEO-SN submission

## Run with Docker

Requires Docker with Compose v2 and host Python 3 for the small setup script. Run from the repo root:

```bash
python3 scripts/setup_iris_env.py
docker compose --env-file .env.iris -f docker-compose.yml build harvester
docker compose --env-file .env.iris -f docker-compose.yml up -d --wait staging-db
docker compose --env-file .env.iris -f docker-compose.yml run --rm harvester
docker compose --env-file .env.iris -f docker-compose.yml run --rm harvester python -m pytest tests/ -q
```

The setup script creates an ignored `.env.iris` with a generated password. Existing credentials are kept. UID/GID settings let the container write reports on the host. `.env.iris.example` shows the configuration. Credentials are not copied into the image.

The application uses Python 3.11.18. Base images and Python dependencies are pinned. The PostGIS image uses amd64 emulation on Apple Silicon. The application was built and tested on Linux arm64 through Docker Desktop.

The database is `iris_geo_sn`, user `hitesh_soneji`, at `127.0.0.1:4000` locally or `staging-db:5432` inside Compose. It has its own volume. The task runner accepts only these isolated endpoints and database name. The root Compose file defines only the isolated task services. The original application pipeline is not run. `docker-compose.iris.yml` remains a compatibility alias for earlier commands.

Stop without deleting data:

```bash
docker compose --env-file .env.iris -f docker-compose.yml down
```

## Source and fixture

On 28 October 2026, this capabilities request returned HTTP 404 and HTML:

`https://geoportal.sachsen.de/wfs/altbergbau?service=WFS&request=GetCapabilities`

Rechecked on 29 October 2026: still HTTP 404 with HTML. See `reports/source_access.json`.

The requested layer is `sn_salka_hohlraeume`. Its actual schema, permissions, licence and data currency could not be verified. This uses the fixture fallback allowed in the assignment. No access restrictions were bypassed.

`tests/fixtures/mining_restrictions.geojson` has six fictional Saxony records in EPSG:4326. Three pass: a polygon, a shaft point and a polygon with missing metadata. Three are rejected: null geometry, a self-intersecting polygon and a missing source ID. All records are labelled `is_fixture`. The URL and layer are assignment references, not the origin of this data. Dates, field names, statuses and classifications are assumed.

## Processing and schema

The task follows runner -> command -> loader -> parser/repository, reusing `BaseEntity` and `BaseRepository`. Geometry structure, topology, 2D coordinates and source references are validated before transformation to EPSG:25832. Invalid geometry is rejected rather than repaired. Missing classification stays null, not safe.

The destination is only `iris_staging.mining_restrictions`:

| Fields | Meaning |
|---|---|
| `state`, `source_layer`, `source_id` | Unique source key for upserts; state must be SN. |
| `hazard_type`, `status`, `hazard_classification` | Source attributes; status and classification can be null. |
| `source_url`, `source_updated_at` | Source reference and nullable source date. |
| `fetched_at` | Collection timestamp, separate from source currency. |
| `is_fixture` | Required simulated-data marker. |
| `geometry` | Valid, non-empty point/multipoint/polygon/multipolygon in EPSG:25832, with GiST index. |
| `id`, `created_at`, `updated_at` | Internal ID and audit timestamps. |

Fixture fields map to the same column names. `fixture_case` is a test label and is not stored. `docker/iris/01-staging.sql` creates the table on first volume initialisation; keep it in sync with the model if fields change.

Upserts update source attributes and `updated_at`, preserving `id` and `created_at`. The last record wins for duplicate keys within a batch. The loader commits the batch or rolls it back on a database error. `upserted` means distinct keys processed, not newly inserted rows.

## Parcel queries

Run the read-only examples after loading:

```bash
docker compose --env-file .env.iris -f docker-compose.yml exec -T staging-db psql -X -U hitesh_soneji -d iris_geo_sn -v ON_ERROR_STOP=1 < examples/parcel_queries.sql
```

`find_intersections()` uses `ST_Intersects`, including containment and boundary contact. Point matches and boundary-only contact have zero intersection area. `find_within_distance()` uses `ST_DWithin`, including intersections at distance zero. Parcel input must be a valid polygon/multipolygon converted with `from_shape(..., srid=25832)`. Thresholds are finite, non-negative metres. No match does not establish safety.

The example parcel intersects `fixture-sn-001` and `fixture-sn-002`. The nearby parcel is about 14.05 metres from `fixture-sn-001`, within 25 metres.

## Checks, reports and limits

- `reports/mining_restrictions.json`: counts, rejected records, reasons, source references and access/currency notes. Each load replaces this file.
- `reports/spatial_queries.json`: checked parcel-query results.
- `reports/docker_validation.json`: fresh Docker setup, repeated loads and test evidence.
- `reports/source_access.json`: latest check of the supplied WFS endpoint.
- `reports/quality_report.md`: short quality/error report and acceptance summary.

Checked on 29 October 2026: fresh database rows went 0 -> 3 -> 3. IDs and creation timestamps were preserved. All 43 tests passed in Docker with no skips. Tests cover unknown metadata, malformed/3D geometry, bad coordinates/dates, wrong source references, repeat loads, updates, rollback, containment, boundary contact and distance thresholds. Test records are rolled back. No `iris_core` schema was created. The report path is checked so it cannot overwrite the input fixture.

The report file and database are not one atomic transaction. If the final report write fails after commit, records remain committed; repeating the load is safe. This demonstrates the assumed fixture schema, not a verified live integration.

## Local Python option

Use Python 3.11 and `python -m pip install -r requirements.txt`, not the full application's Python 3.12 project configuration. Start the task database, then run:

```bash
python -m app.runners.mining_restriction_runner tests/fixtures/mining_restrictions.geojson
```

The runner reads `IRIS_DATABASE_URL` from the environment or `.env.iris`. Database-backed tests need `IRIS_TEST_DATABASE_URL` set to that isolated database; otherwise those tests skip. Docker sets it automatically.
