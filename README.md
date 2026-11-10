# GramSathi AI 

GramSathi AI is a multilingual Gram Sabha meeting intelligence application built using FastAPI, Streamlit, PostgreSQL, and Gnani Prisma STT.

The system supports meeting management, English/Telugu/Kannada/Hindi transcription, speaker diarization, evidence-linked meeting minutes, decision tracking, action items, and human verification.

Meeting minutes remain drafts until explicitly verified by the meeting owner. Verification is prototype confirmation, not legally authenticated government approval.

Python 3.11+, FastAPI, Pydantic v2, PostgreSQL, synchronous SQLAlchemy 2, Alembic, psycopg, Argon2/pwdlib and signed JWTs. Streamlit will be deployed separately.

```text
GramSathiAI/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   └── meetings.py
│   │   ├── services/
│   │   │   ├── meeting_service.py
│   │   │   ├── transcription_service.py
│   │   │   ├── prisma.py
│   │   │   ├── evon.py
│   │   │   └── integrity.py
│   │   └── worker.py
│   ├── alembic/
│   │   └── versions/
│   │       ├── 0001_initial.py
│   │       ├── 0002_transcription_jobs.py
│   │       ├── 0003_meeting_intelligence.py
│   │       └── 0004_generation_model.py
│   ├── tests/
│   │   └── test_backend.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app.py
│   ├── components.py
│   ├── styles.py
│   ├── requirements.txt
│   └── .env.example
├── sample_audio/
├── README.md
└── .gitignore
```

## Setup and run

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
# Create backend/.env if missing; configure the keys described below.
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

GramSathi AI currently includes:

- **Backend:** FastAPI REST APIs with JWT authentication and PostgreSQL persistence.
- **Frontend:** Streamlit interface for meeting creation, audio upload, transcript viewing, meeting minutes, and verification.
- **Speech-to-Text:** Gnani Prisma v3.0 Batch transcription supporting English, Telugu, Kannada, Hindi, and code-mixed speech.
- **Speaker Diarization:** Anonymous speaker identification based on audio.
- **Meeting Intelligence:** Evidence-grounded structured decisions, action items, unresolved issues, and integrity warnings.
- **Human Verification:** Draft review, correction, approval, and audit history.

### Current Limitations

- Live Gnani Evon reasoning is not yet integrated; development-only mock fixtures are supported.
- Groq draft generation requires an API key and model access.
- Timbre voice playback and transcript segment editing are not yet implemented.
- Human verification represents prototype confirmation, not legally authenticated government approval.

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

## Groq minutes generation

The default `POST /api/v1/meetings/{meeting_id}/minutes/generate` uses Groq. Set the following in the backend environment and apply `python -m alembic upgrade head` from `backend/`. Revision `0004` adds a nullable model label to minutes.

```dotenv
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Groq lists Llama 3.3 70B as Enterprise and publishes a shutdown date for the deprecated offering. If your account lacks access, explicitly set `GROQ_MODEL=openai/gpt-oss-120b`, a documented replacement with JSON Object Mode. The backend uses the configured model and displays the model reported by the provider. [Supported models](https://console.groq.com/docs/models) · [Deprecations](https://console.groq.com/docs/deprecations)

Restart FastAPI, open a meeting with a transcript and no minutes, and select **Draft with AI**. This sends the meeting's transcript text and segment metadata to Groq and uses your Groq account's quota. A successful request saves a draft with citations and integrity warnings. Inspect the evidence, edit if needed, then acknowledge the warnings on the Verification page.

The integration sends one request for the full transcript, up to 100,000 UTF-8 bytes of serialized segment data. Provider limits may be lower. The SDK allows one retry for transient HTTP or connection failures. The application validates JSON against `MinutesCreate` and checks citations before saving. Semantic support still requires a human review. Use `{"provider":"evon"}` to select the reserved Evon adapter, which returns 501. The development fixture path is explicitly selected with `provider: "mock"`.

## Streamlit frontend

The frontend lives in `frontend/` and talks to FastAPI only over HTTP (it never touches the database or Gnani).

```bash
pip install -r frontend/requirements.txt
cp frontend/.env.example frontend/.env   # set API_BASE_URL to your FastAPI URL
streamlit run frontend/app.py            # run from the repo root so .streamlit/config.toml (theme) is used
```

Pages: Dashboard, All Meetings, Create New Meeting, Audio & Transcripts (M4A upload, job status, transcript), Meeting Minutes (read and edit, suggestion vs approved resolution, evidence), and Verification (prototype human confirmation, not government approval). Shared styling is in `frontend/styles.py` and reusable pieces in `frontend/components.py`.

Editing or deleting existing transcript segments and Timbre voice playback are unavailable. Audio jobs only progress while the backend worker is running. Sessions are kept in memory, so a browser refresh requires logging in again.

### Original recording and evidence playback

In **Audio & Transcripts**, select **Play original recording** on a job or **Play segment** beside a transcript entry. In **Meeting Minutes** and **Verification**, open a supporting transcript citation and select **Play evidence**. Clips start at the cited timestamp and pause near the end. Check **Continue past the segment end** to listen further. If the browser blocks autoplay, press Play in the player.

The API retains each validated original M4A (up to 10 MiB) separately from the worker's temporary queue bytes. Set `AUDIO_STORAGE_DIR` in the backend environment to a private, writable persistent volume in deployment. All API replicas must see the same directory. Locally it defaults to `backend/.recordings`. Exclude it from public/static serving. Budget storage and backups for retained originals. Files do not expire automatically, and meeting deletion revokes access but leaves the archived file for operator-managed cleanup.

The owner-only `GET /api/v1/meetings/{meeting_id}/transcriptions/{job_id}/audio` requires a bearer token and supports HTTP byte ranges. Streamlit requests the capped file server-side and plays it in the requesting browser session. For older jobs without a retained copy, choose the identical M4A and language selection in the same meeting and click **Start transcription**. The API recognizes the duplicate and restores playback under the existing job ID, keeping existing transcript IDs. Manually entered segments have no recording link. Playback and duplicate restoration do not require the worker or a provider API key.

## Export verified minutes as a PDF

Install the updated backend requirements and restart FastAPI and Streamlit. On **Verification**, open verified minutes and click **Prepare PDF**, then **Download PDF**. The API endpoint is `GET /api/v1/meetings/{meeting_id}/minutes/pdf`, using the existing bearer token. Only the meeting owner can export, and draft minutes return `409`.

The PDF includes the meeting details, draft origin, human verification, decisions and budgets, action items, unresolved issues, and cited transcript quotes or excerpts. It is labeled as a prototype-generated meeting record. Embedded [Noto fonts](https://github.com/notofonts/noto-fonts) cover English, Hindi, Telugu, and Kannada. The bundled fonts ship with their SIL Open Font License under `backend/app/assets/fonts/`.

## Phase 3: evidence-grounded meeting intelligence

Groq and development fixtures use the same provider-independent `ReasoningProvider` contract. `MockEvonAdapter` returns a caller-supplied fixture for testing the grounding and review workflow.

Apply migration **`0003`** with `alembic upgrade head`. It adds optional amount/classification/deadline/quote fields, summary citations, and versioned draft/review history. Existing transcript/job tables and IDs are untouched. Verified legacy minutes remain verified. Before deploying to Neon, test the migration on an isolated branch and run Alembic using its direct (non-pooled) connection; the changes here were tested on disposable local PostgreSQL.

For development fixture mode only, set these in `backend/.env`, then restart Uvicorn:

```dotenv
APP_ENVIRONMENT=development
ENABLE_MOCK_REASONING=true
```

Defaults are `production` and `false`. Even with the flag enabled, production rejects mock requests with 403. No Gnani key or transcription worker is needed for this pipeline. Keep existing `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` and optional `GNANI_API_KEY` settings; never share their values. If creating a fresh `.env`, those first two keys are required.

### Swagger: generate, inspect, correct, review

1. Open `/docs`, log in and **Authorize**. Use the UUID of your meeting with persisted transcript data. **GET `/api/v1/meetings/{meeting_id}/transcript`** gives the real integer IDs and original evidence. Do not add synthetic segments to the real recording.
2. In **POST `/api/v1/meetings/{meeting_id}/minutes/generate`**, select **Try it out**. Set `provider` to `mock` and supply `fixture` matching the minutes schema. Copy actual IDs from step 1. The template below uses **E, P, A, C as placeholders**, not fabricated IDs: replace them with the persisted estimate, proposal, approval and coordination/progress-update segment IDs. They may be the same ID if several statements share a segment. Quote the relevant original excerpts through optional `evidence_quotes` when needed.

   ```text
   {
     "provider": "mock",
     "fixture": {
       "summary": "Pipeline repair has a ₹17,000 estimate and a ₹15,000 approved allocation. Coordination and a progress update are required.",
       "summary_evidence_segment_ids": [E, P, A, C],
       "decisions": [{
         "description": "Allocate funds for pipeline repair",
         "status": "APPROVED",
         "estimated_amount": 17000,
         "proposed_amount": 15000,
         "approved_amount": 15000,
         "currency": "INR",
         "evidence_segment_ids": [E, P, A]
       }],
       "action_items": [
         {"task": "Coordinate pipeline repair", "assigned_to": "Panchayat Secretary", "deadline": null, "evidence_segment_ids": [C]},
         {"task": "Provide progress update", "assigned_to": null, "deadline": null, "deadline_text": "within seven days", "evidence_segment_ids": [C]}
       ],
       "unresolved_issues": []
     }
   }
   ```

   This is Meeting 1's **expected fixture interpretation**, not live extraction. Attribute the progress update to a person only if its actual evidence assigns that responsibility. No calendar deadline is inferred. Money is serialized as decimal strings. Inspect and correct the fixture against the transcript; do not trust it merely because it matches this example.
3. The response must say `status=draft`, `generation_source=mock_fixture`. Read **GET `/minutes`**, **GET `/decisions`**, **GET `/action-items`**, **GET `/minutes/integrity`**, and **GET `/minutes/evidence`** under the same meeting prefix. Evidence includes untouched text, start/end times, language and actual speaker IDs. No extra speakers or dialogue roles are fabricated.
4. To correct a draft, **POST `/minutes`** using the editable request fields, actual evidence IDs and `expected_revision` from the latest GET. Change amounts, statuses, `assigned_to`, `deadline_text` or `deadline` as needed. Do not copy response-only fields such as document `status`, `revision`, history or verification metadata into this request. Warnings are recalculated, and the original generated draft remains preserved.
5. To reject, **POST `/minutes/review`** with `{"decision":"reject","reviewer_name":"Secretary","expected_revision":R,"comment":"Correct the allocation."}` (replace R with the current revision). It remains a draft with `review_state=rejected`; edit/regenerate before approval.
6. To approve, **POST `/minutes/verify`** with `{"verifier_name":"Secretary","confirmed":true,"acknowledge_warnings":true,"expected_revision":R}`. Alternatively `/minutes/review` accepts `decision=approve`, `reviewer_name`, `confirmed=true`, warning acknowledgement and the revision. Generated drafts require explicit warning acknowledgement. Stale revisions, unauthorized reviewers and repeated verification are rejected. This is prototype owner confirmation, not government approval.
7. **GET `/minutes/history`** returns the immutable first generated snapshot plus ordered generation, edit, rejection and approval snapshots, reviewer metadata, warnings and evidence. Verification acknowledges warnings rather than deleting them. Legacy manually authored requests remain valid; new fields are optional. Verified documents stay immutable.

### Integrity checks and limits

Missing/foreign citations, empty evidence on material claims, or non-exact quoted evidence fail with 422 and save nothing. Generated summaries also need `summary_evidence_segment_ids` or cited `summary_claims` (`text`, `evidence_segment_ids`, optional quotes). Prose claims cannot be supplied as evidence for themselves.

Narrow deterministic checks compare amounts/currencies with cited clauses and distinguish estimates, proposals and explicit approval, including negation/conditional guards. They check assignment/commitment wording, relative-deadline scope, calendar-date support, contradictory budgets/statuses, and quotes against their surrounding context. **Segment-ID validity is not treated as semantic proof.** `APPROVED`, `PROPOSED`, `REJECTED`, `DEFERRED`, `UNCLEAR` are accepted case-insensitively. Existing lowercase `status` values remain compatible; deferred/unclear map to legacy `proposed` with the precise new `classification` preserved. Unknown amounts, assignees and deadlines stay null.

Warnings include `UNSUPPORTED_APPROVAL`, `UNSUPPORTED_REJECTION`, `UNSUPPORTED_BUDGET`, `CONFLICTING_AMOUNTS`, `UNSUPPORTED_DEADLINE`, `UNSUPPORTED_ASSIGNEE`, `INVALID_EVIDENCE_REFERENCE`, `AMBIGUOUS_DECISION_STATUS`, `INSUFFICIENT_EVIDENCE` and `CLAIM_SUPPORT_UNVERIFIED`. Each identifies the affected claim, explanation, evidence IDs, severity and human-review requirement. Questionable output is retained only as a flagged draft; invalid references never persist.

The checker is intentionally conservative: currency matching covers INR/USD/EUR, and lexical/number rules cover common English forms plus a limited set of native-script forms. It does not provide comprehensive multilingual semantic entailment, translation or reliable coreference. Original Telugu, Kannada, Hindi and code-mixed evidence survives intact; uncertain wording is flagged for human review. A suggested deadline is not automatically a commitment; seven days for an update is not seven days to complete the repair. Even a matching claim retains `CLAIM_SUPPORT_UNVERIFIED`. Review flags are aids, not an automated correctness certificate.

To activate live Evon, supply its **official endpoint/base URL, authentication, model identifier, request/response and citation schemas, limits, timeout/retry policy and sync/async job lifecycle**. Only the provider adapter should change; grounding, storage, audit history and owner review stay shared. No live Evon support is claimed.
