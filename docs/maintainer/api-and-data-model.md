# API and data model

## `models.py` is the contract

[../../hub/models.py](../../hub/models.py) is the shared request/response contract for:

- FastAPI validation
- collector payload shape
- UI/session JSON shape
- Copilot context assembly
- tests that assert stored bundle structure

Changing a field there usually requires coordinated updates in:

- [../../hub/db.py](../../hub/db.py) schema/JSON handling
- [../../hub/service.py](../../hub/service.py) serialization/merge logic
- templates and [../../hub/static/app.js](../../hub/static/app.js)
- collector parsers and/or posting code
- tests

Two important update semantics differ:

- `SessionUpdate` is explicit-field patching for the session row.
- `SessionObservationPatch` is merge-only for selected observation fields and intentionally fills blanks rather than overwriting existing evidence.

## Schema and migrations

There is no external migration framework. [../../hub/db.py](../../hub/db.py) owns both:

- `SCHEMA` — full `CREATE TABLE IF NOT EXISTS ...` DDL
- `SESSION_COLUMN_MIGRATIONS` — additive `ALTER TABLE sessions ADD COLUMN ...` support for older DBs

When you add storage:

1. Update `SCHEMA` and any needed indexes.
2. If the change is a new `sessions` column, add it to `SESSION_COLUMN_MIGRATIONS`.
3. If the change is JSON-backed session data, update `SESSION_JSON_COLUMNS`/`JSON_COLUMNS`.
4. Add/extend tests that cover existing-DB initialization when needed.

`db.init_db()` must stay idempotent.

## JSON-backed columns

These values are stored as TEXT in SQLite and decoded by `row_to_dict`:

- session JSON columns: `encoder_settings`, `requested_settings`, `hdr_details`, `visual_assessment`
- log metadata column: `log_chunks.meta`

Maintenance consequences:

- write JSON through `service.py` helpers instead of open-coded `json.dumps` scattered around the app
- treat missing/blank JSON as `{}` on reads
- if you add a new JSON session column, update storage, decoding, and tests together

## Surface map

| Surface | Endpoint(s) | Input model / shape | Storage | Notes |
|---|---|---|---|---|
| Session lifecycle | `/api/sessions`, `/api/sessions/{id}`, `/stop`, `/observations`, `/comparisons/{label}` | `SessionCreate`, `SessionUpdate`, `SessionObservationPatch` | `sessions` | Session is the root row and comparison identity source. |
| Logs | `/api/sessions/{id}/logs` | `LogChunkIn` | `log_chunks` | Host/client source plus role, machine, content, JSON `meta`. |
| Link samples | `/api/sessions/{id}/links` | `LinkSampleBatch` / `LinkSampleIn` | `link_samples` | Ordered by `sampled_at`, then `id`; feeds roam/RSSI UI and Copilot signals. |
| Display samples | `/api/sessions/{id}/displays` | `DisplaySampleBatch` / `DisplaySampleIn` | `display_samples` | Host-only contract (`source="host"`); used by `display_validation`. |
| Net tests | `/api/sessions/{id}/nettests` | `NetTestIn` | `net_tests` | Usually `iperf3`; raw output is stored for debugging. |
| Manual artifacts | `/api/sessions/{id}/artifacts` | multipart (`file`, `kind`, `caption`) | `artifacts` + artifact file on disk | Router writes the file under `ASL_ARTIFACTS_DIR`, then stores the DB row. |
| Screenshot requests | `/api/sessions/{id}/screenshot-requests`, `/pending`, `/{request_id}/complete`, `/{request_id}/fail` | `ScreenshotRequestIn`, `ScreenshotRequestFailIn`, multipart completion form | `screenshot_requests` and optionally `artifacts` | Request rows move `pending` → `completed`/`failed`; completion is source-bound and creates a `requested_{source}_screenshot` artifact. |
| Analysis/chat | `/api/sessions/{id}/analyze`, `/api/sessions/{id}/chat` | `ChatIn` for chat POST | `sessions.diagnosis`, `chat_messages` | Copilot works from the stored bundle, not ad-hoc request state. |

## SQLite discipline

- Use `db.db()` for one connection per call; it enables foreign keys and commits on exit.
- Keep raw SQL in `service.py`/`db.py`; do not spread SQL into routers, templates, or JS.
- Preserve stable ordering for child evidence (`sampled_at`/`id` or `id ASC`) so pages, tests, and Copilot see deterministic bundles.
- Treat filesystem writes and DB rows as one logical feature. Artifact-related changes must consider both the stored row and the file under `ASL_ARTIFACTS_DIR`.
- Prefer additive migrations and backward-compatible defaults; the app initializes existing databases in place.
