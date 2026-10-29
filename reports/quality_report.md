# IRIS-GEO-SN quality report

Reviewed on 29 October 2026. Fixture demonstrator only.

## Source limitation

The supplied GetCapabilities URL returned HTTP 404 on 28 October and again on 29 October. The live layer, schema, permissions, licence and data currency remain unverified. All fixture locations, dates and classifications are fictional. No alternative source or access bypass was used.

## Input results

| Record | Result |
|---|---|
| `fixture-sn-001` | Accepted polygon, EPSG:25832. |
| `fixture-sn-002` | Accepted shaft point, EPSG:25832. |
| `fixture-sn-003` | Accepted polygon; classification, status and source date remain null. |
| `fixture-sn-004` | Rejected: null geometry. |
| `fixture-sn-005` | Rejected: self-intersecting polygon. |
| Feature 6 | Rejected: missing source ID. |

## Acceptance evidence

- The simulated records are near Dresden in Saxony, marked `SN`, with explicit mining/cavity/shaft categories. Source URL, layer and ID are stored alongside `is_fixture=true`.
- Fresh Docker database: 0 -> 3 -> 3 rows across two loads. IDs and creation timestamps stayed unchanged.
- Business records are written only to `iris_staging.mining_restrictions`. The fresh test database had no `iris_core` schema.
- All 43 tests passed in Docker without skips. Tests cover updates, rollback, unknown metadata, malformed/3D geometry, bad coordinates, wrong source references and invalid dates.
- Spatial tests cover containment, boundary contact, non-matches and inclusive distance thresholds. The example intersection finds two records; the proximity example finds one at about 14.05 metres within 25 metres.
- Local credentials are ignored by Git and excluded from the image. The existing local database stayed at three records. Temporary review resources were removed.
- The database user is `hitesh_soneji`, with local port `4000` (container port `5432`). The renamed account kept database ownership and all three existing records. The fresh Docker checks also passed with these settings.

## Remaining assumptions

Only 2D point/multipoint/polygon/multipolygon geometry is supported. Invalid geometry is rejected, not repaired. Source fields and categories are an assumed contract, not a verified WFS schema. No classification or no spatial match does not mean safe. The database commit and report-file write are separate operations; a final report-write failure can occur after records are committed.

Details: `mining_restrictions.json`, `spatial_queries.json`, `docker_validation.json` and `source_access.json` in this folder. Run instructions and schema mapping are in `submission_README.md`.
