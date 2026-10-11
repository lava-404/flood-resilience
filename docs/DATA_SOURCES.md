# Data sources: what is actually implemented

| Source | Adapter | Status |
|---|---|---|
| Synthetic replay fixture | `FixtureAdapter` | Works. **Fictional station, rain and official statuses.** Every record carries `provenance=synthetic_reconstruction`. |
| CWC, Nepal DHM, NASA IMERG, GloFAS | `CwcAdapter`, `DhmAdapter`, `ImergAdapter`, `GlofasAdapter` | **Not implemented.** They return `source_unavailable` (visible in source health). SRS 9: no verified machine-readable endpoint, so none was invented. |
| SRTM, Sentinel-1, OSM | none | Not started. `/v1/flood-extent` returns `available:false`. |
| Shelters | `data/fixtures/shelters_DEMO.json` | Fictional demo shelters (`provenance=synthetic_demo`). |

To add a real source: implement `fetch(now) -> RawSnapshot` and `normalize(raw, received_at) -> (stations, observations)` in `services/ingest/ingest/adapters.py`, register it in `REGISTRY`, set Terraform `ingest_adapter`. Add per-source timeouts and retry/backoff in `fetch` (not yet present). Respect each source's terms; store credentials in Secrets Manager.
