# GramSathi AI — Backend

A multi-user FastAPI backend for manual, multilingual Gram Sabha transcripts and evidence-linked meeting minutes. Each meeting belongs to one user. Minutes stay drafts until explicit owner confirmation; this is **prototype confirmation, not legally authenticated government approval**.

Python 3.11+, FastAPI, Pydantic v2, PostgreSQL, synchronous SQLAlchemy 2, Alembic, psycopg, Argon2/pwdlib and signed JWTs. Streamlit will be deployed separately.

```text
backend/
  app/
    main.py, config.py, database.py, models.py, schemas.py, security.py
    routes/auth.py, routes/meetings.py
    services/meeting_service.py
  alembic/env.py, alembic/script.py.mako, alembic/versions/0001_initial.py
  tests/test_backend.py
  data/sample_meeting.json
  alembic.ini, requirements.txt, .env.example
```

## Setup and run

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Provision a PostgreSQL database and a dedicated application login with schema migration privileges. Set `DATABASE_URL` in `backend/.env` to `postgresql+psycopg://USERNAME:PASSWORD@HOST:5432/gramsathi` (URL-encode special characters in credentials; use your provider's required SSL options, e.g. `?sslmode=require`). Set `JWT_SECRET` to the generated value. No secrets are provided. `JWT_ALGORITHM=HS256` is fixed by configuration validation and token verification; tokens expire after 30 minutes (configurable 1–60).

Set `CORS_ORIGINS` to a JSON list of exact frontend origins such as `["https://your-frontend.example"]`, without trailing slashes. An empty list disables browser cross-origin access. Wildcards are rejected. Environment variables override `.env` values.

```bash
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

For development add `--reload` instead of `--workers 2`. Use HTTPS through your hosting provider and configure its health probe to `/health`. The health endpoint is liveness only. Apply migrations once before starting workers; the application never auto-creates tables. Pool limits are 5 persistent + 5 overflow connections **per worker**; choose workers to fit PostgreSQL's connection budget. Configure your provider to avoid logging Authorization headers or request bodies and to limit abusive authentication traffic.

Swagger: [local API docs](http://127.0.0.1:8000/docs). Register and log in with JSON email/password, then use Swagger's **Authorize** button with the returned bearer token. Registration requires a password of 12–128 characters. Responses never contain password hashes.

## API and sample

- `GET /health`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `POST/GET /api/v1/meetings` (listing uses `offset` and `limit`, default 50, maximum 100)
- `GET/DELETE /api/v1/meetings/{meeting_id}`
- `POST/GET /api/v1/meetings/{meeting_id}/transcript`
- `POST/GET /api/v1/meetings/{meeting_id}/minutes`
- `POST /api/v1/meetings/{meeting_id}/minutes/verify`

Meeting routes require bearer authentication; inaccessible meetings return 404. Transcript POST appends a validated batch atomically and returns the appended segments ordered by start time, end time, then ID; GET returns the complete ordered transcript. Original text is preserved. Minutes POST creates or replaces a draft atomically. All structured entries require evidence from the same meeting. Verified minutes cannot be replaced or verified again; the owner can still delete the entire meeting and its associated data.

`backend/data/sample_meeting.json` contains eight synthetic segments in Hindi, Telugu, Kannada, English and mixed language. POST its `meeting` and `transcript` objects separately. Replace the `minutes_template` illustrative evidence IDs with actual returned segment IDs before submission. The wrapper itself is not an API request.

## Tests

Create a **separate PostgreSQL database** (for example `gramsathi_test`) and set `TEST_DATABASE_URL` in `backend/.env` or the environment. Its database name must differ from `DATABASE_URL`, even if credentials or hostnames differ. Use a dedicated test login with permission to create schemas; never point it at a shared application database.

```bash
# From backend/, with the virtual environment active:
pytest -q tests/test_backend.py
```

The tests require both URLs and fail safely when the test URL is missing or uses the application database name. They run Alembic in a random private test schema, then drop only that schema. Existing schemas/tables are untouched. All provider HTTP requests are blocked in tests; SDK calls use mocks and no live API key is required. PostgreSQL must be reachable; SQLite is not supported.

For future schema changes: `alembic revision --autogenerate -m "describe change"`, inspect the migration, then `alembic upgrade head`.

## Scope

Manual transcript/minutes APIs remain compatible. Recorded meetings now support queued Prisma v3.0 Batch transcription. No frontend, translation, voice output or PDF export is implemented. Evon reasoning remains disabled until its official API contract is available. Keep Gnani credentials exclusively on the backend.


## Prisma v3.0 Batch transcription

Read and verified against the official [Batch overview](https://docs.gnani.ai/api/STTBatch/Introduction.md), [Prisma v3.0](https://docs.gnani.ai/api/STT/models/prisma-v3.md), [Python Batch SDK](https://docs.gnani.ai/python-sdk/speech-to-text-batch.md), [transcript schema](https://docs.gnani.ai/api/STTBatch/Get_Job_Files.md) and installed `gnani-vachana==0.9.0` signatures. That version exposes `model`, `format`, `diarization` and `start` on `create_job()`; no HTTP fallback is needed. Every job explicitly uses `model="prisma-v3.0"`, `format="codemix"`, `diarization=True`. No speaker names are supplied.

After installing updated requirements, apply `alembic upgrade head` (revision `0002`). It adds `transcription_jobs`, transcript provenance columns and minutes `review_flags`; existing segment IDs/data remain intact. Set **`GNANI_API_KEY`** in `backend/.env` or the environment. It is optional for starting FastAPI and safely queueing uploads, but required by the live worker. Do not put it in Streamlit or Swagger.

| Recording in `sample_audio/` | `language_code` form field | Duration |
| --- | --- | --- |
| `meeting_01_en_te.m4a` | `en-IN,te-IN` | 58.364 s |
| `meeting_02_en_kn.m4a` | `en-IN,kn-IN` | 68.604 s |
| `meeting_03_en_hi.m4a` | `en-IN,hi-IN` | 73.980 s |
| `meeting_04_en_te_kn_hi.m4a` | `en-IN,te-IN,kn-IN,hi-IN` | 84.220 s |

Durations were inspected locally; audio was not sent to Gnani. All recordings use Batch (including any future clip under 30 seconds). M4A is uploaded directly, without conversion. One file per job, maximum **10 MiB / 10,485,760 bytes**, matching the SDK constant. The server reads at most that limit plus one byte and checks the `.m4a` extension/container header. Configure your hosting proxy with an approximately 11 MiB total request-body cap as well, since multipart parsing precedes endpoint validation. Gnani enforces its separate 4-hour duration limit.

The PostgreSQL queue stores uploaded bytes durably until its provider job ID commits, then clears the bytes. Raw result JSON is retained when downloaded, including silence entries. Nonblank segments are atomically appended to the existing transcript table. Text and timestamps are preserved; raw `detected_language` and `provider_speaker_id` accompany the normalized language and anonymous, job-scoped speaker ID. A detected language outside the original four (or a missing tag) uses `mixed` as a compatibility fallback with a job warning; the raw tag is retained without guessing. Batch labels describe anonymous speakers, not identified people.

### Swagger walkthrough

1. Start FastAPI and open `/docs`. Register, log in, then **Authorize** using the returned token.
2. Create one meeting per recording with `POST /api/v1/meetings`. Include its primary language in `supported_languages` (short codes `en`, `te`, `kn`, `hi`). Copy its UUID.
3. Open **POST `/api/v1/meetings/{meeting_id}/transcriptions`**, click **Try it out**, enter the UUID, select the M4A in `audio`, and enter the exact `language_code` from the table. Execute: **202** returns a local job UUID with `status="queued"`. This request makes **no Gnani call**. Identical bytes/options return the same job with **200**; different options for the same audio return **409**.
4. **GET `/api/v1/meetings/{meeting_id}/transcriptions`** lists local jobs. **GET `/api/v1/meetings/{meeting_id}/transcriptions/{job_id}`** reads local status/progress/provider ID without polling Gnani. With the worker stopped, jobs safely remain queued.
5. **Only after explicit approval for live, billable Gnani calls**, start the separate worker in another terminal with the same environment/database:

   ```bash
   source .venv/bin/activate
   cd backend
   python -m app.worker --allow-live
   ```

   The command processes all due queued jobs in that database, not just one meeting. Manage it as a persistent process with your hosting provider. `python -m app.worker` refuses live calls without the flag; `--once --allow-live` performs at most one due step. FastAPI never starts the worker itself.
6. Refresh local job status until `completed`, then **GET `/api/v1/meetings/{meeting_id}/transcript`**. Stable integer IDs are the evidence references for minutes. Terminal problems expose safe `error_code` values; provider error bodies/secrets are not returned. A `failed` job must be inspected; it is never automatically resubmitted.
7. Submit manual structured minutes using those IDs to the existing **POST `/minutes`**. Retrieve with **GET `/minutes`**; status stays `draft`. Only **POST `/minutes/verify`** with `{"verifier_name":"Secretary","confirmed":true}` verifies the document. Verified minutes cannot be overwritten.

### Worker recovery and duplicate protection

The worker uses a PostgreSQL advisory lock to serialize processing across worker processes. It performs bounded SDK create/get/start/files calls and polls no more frequently than every 10 seconds; it never invokes the SDK's blocking `wait()`/`transcribe()` helpers. Temporary status/download errors keep the provider ID and retry with backoff. Restarting the worker reattaches with `get_job(provider_job_id)`.

A unique `(meeting_id, audio_sha256)` prevents duplicate uploads. A unique `(transcription_job_id, source_index)` and atomic import/completion transaction prevent duplicate segments on restart; provider `segment_id` is not assumed unique.

There is no documented idempotency guarantee for a provider create request. The local state is committed as `submitting` before uploading with `start=False`; the returned provider ID commits **before** `/start`. A crash/timeout during creation therefore changes to `needs_reconciliation` rather than submitting again. Find the real provider job in the Gnani dashboard/logs by the opaque upload name **`<local-job-UUID>.m4a`** (also used as its request trace ID). Then use **POST `/api/v1/meetings/{meeting_id}/transcriptions/{job_id}/resume`** with `{"provider_job_id":"<actual Gnani UUID>"}`. This API only updates local state. The approved worker validates the remote filename, model, languages, codemix and diarization settings before starting/importing it. Never attach an unrelated provider job. If no provider job exists, operator investigation is required; there is deliberately no blind automatic re-upload of an ambiguous submission.

Deleting a meeting cascades its local jobs, raw results and segments. It does not cancel an already submitted provider job; provider-side retention/cancellation is a separate operation.

## Evon adapter status

**POST `/api/v1/meetings/{meeting_id}/minutes/generate`** is an authenticated extension point and returns **501** after a transcript exists. No real or simulated AI-generated content is returned. Official Evon documentation is still needed for its endpoint/base URL, authentication, model, request/response schema, evidence/citation format, limits and job lifecycle. No Evon endpoint was guessed.

`MockEvonAdapter` accepts an explicit test fixture; it is only injected by tests. All generated entries require nonempty stable segment citations. Missing/foreign IDs are rejected with 422 and unsupported-evidence flags, without saving. Valid references establish provenance, not semantic support: every generated decision, action and issue carries `claim_support_unverified` in persisted `review_flags` until human confirmation. The existing manual minutes API remains available; no automated entailment check is claimed.
