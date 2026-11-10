# GramSathi AI

**Multilingual Gram Sabha Meeting Intelligence System**

GramSathi AI is an AI-powered application designed to digitize and streamline Gram Sabha meetings through multilingual speech transcription, speaker diarization, automated meeting minutes, decision tracking, and evidence-based human verification.

The system supports **English, Telugu, Kannada, Hindi, and code-mixed speech**, enabling structured documentation of discussions conducted in multiple Indian languages.

## Key Features

- **Multilingual Speech-to-Text:** Integrates the Gnani Prisma v3.0 Batch API to transcribe English, Telugu, Kannada, Hindi, and code-mixed meeting recordings.
- **Speaker Diarization:** Automatically distinguishes anonymous speakers within meeting recordings.
- **AI-Generated Meeting Minutes:** Uses Groq-hosted LLMs to generate structured meeting summaries from transcripts.
- **Decision & Action Tracking:** Extracts decisions, budget allocations, assigned responsibilities, deadlines, and unresolved issues.
- **Evidence-Grounded Intelligence:** Links generated claims to original transcript segments and timestamps for traceability.
- **Integrity Validation:** Flags potentially unsupported decisions, budget inconsistencies, missing evidence, and ambiguous claims.
- **Human-in-the-Loop Verification:** Allows meeting owners to review and edit draft minutes, then confirm them before exporting a PDF.
- **Audio Evidence Playback:** Enables playback of original recordings and timestamp-linked transcript segments.
- **PDF Export:** Generates downloadable PDFs of verified meeting minutes.
- **Secure Meeting Management:** Provides JWT authentication, meeting ownership controls, and persistent storage.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Frontend | Streamlit |
| Database | PostgreSQL, SQLAlchemy |
| Speech-to-Text | Gnani Prisma v3.0 Batch |
| Speaker Diarization | Gnani Prisma |
| AI Reasoning | Groq LLM API |
| Authentication | JWT, Argon2 |
| Database Migrations | Alembic |
| Testing | Pytest |

## System Architecture

```text
                 Gram Sabha Meeting
                    (M4A Audio)
                         |
                         v
                 Streamlit Frontend
                         |
                         v
                    FastAPI
                         |
                         v
                PostgreSQL Job Queue
                         |
                         v
                 Background Worker
                         |
                         v
                 Gnani Prisma v3.0
               (STT + Diarization)
                         |
                         v
                Timestamped Transcript
                         |
                         v
                   Groq LLM
                         |
                         v
              Structured Meeting Minutes
                         |
                         v
               Evidence & Integrity Checks
                         |
                         v
                 Human Verification
                         |
                         v
                 Verified Minutes
                   + PDF Export
```

## Project Structure

```text
GramSathiAI/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── worker.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── main.py
│   ├── alembic/
│   ├── data/
│   │   └── sample_meeting.json
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── app.py
│   ├── components.py
│   ├── styles.py
│   └── requirements.txt
└── README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Udaya-P/GramSathiAI.git
cd GramSathiAI
```

### 2. Set Up the Backend

Use Python 3.11+ and a running PostgreSQL instance. Create a `gramsathi` database or use an existing development database.

```bash
python -m venv .venv
```

Activate the virtual environment on macOS or Linux.

```bash
source .venv/bin/activate
```

In Windows PowerShell, use the following command.

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies.

```bash
python -m pip install -r backend/requirements.txt
```

Copy [`backend/.env.example`](backend/.env.example) to `backend/.env`. Generate a secret for `JWT_SECRET` with the following command.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the database URL and paste the generated value into `JWT_SECRET`. Set `GNANI_API_KEY` for live transcription and `GROQ_API_KEY` for AI drafting. Keep real credentials in your local `.env` file.

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/gramsathi
JWT_SECRET=PASTE_GENERATED_SECRET_HERE
CORS_ORIGINS=[]
GNANI_API_KEY=
GROQ_API_KEY=
```

To override the default Groq model, set `GROQ_MODEL` to a model available to your account.

Apply database migrations and start FastAPI.

```bash
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Open the [FastAPI documentation](http://127.0.0.1:8000/docs).

### 3. Start the Transcription Worker

Open a separate terminal at the repository root and activate the same virtual environment. Run the worker when you want to make live Gnani API requests, which use your API credits.

```bash
cd backend
python -m app.worker --allow-live
```

### 4. Run the Frontend

Open another terminal at the repository root and activate the same virtual environment.

```bash
python -m pip install -r frontend/requirements.txt
python -m streamlit run frontend/app.py
```

Open the [Streamlit app](http://localhost:8501). The frontend defaults to `http://127.0.0.1:8000`. If your API runs at a different address, set `API_BASE_URL` in `frontend/.env`.

## Application Workflow

1. **Create a meeting.** Register, sign in, and enter the meeting details.
2. **Upload audio.** Upload an M4A recording up to 10 MiB and select the languages spoken.
3. **Transcribe.** Gnani Prisma generates a timestamped transcript with anonymous speaker labels.
4. **Generate minutes.** Select **Draft with AI** to use Groq to draft a summary, decisions, action items, and unresolved issues.
5. **Check the evidence.** Open the cited transcript segments and play the corresponding audio where available. Integrity checks flag potentially unsupported or inconsistent claims.
6. **Review and verify.** The meeting owner edits the draft as needed and confirms it.
7. **Export.** Download the verified minutes as a PDF.

## Try the Synthetic Meeting

The repository includes a [synthetic Gram Sabha transcript](backend/data/sample_meeting.json) about a fictional pipeline repair. It includes English, Telugu, Kannada, Hindi, and a code-mixed turn.

With the backend and frontend running, create a meeting and use **Add a segment by hand** in **Audio & Transcripts** to enter the sample turns. Then use **Write minutes** to link draft items to the saved transcript segments and try verification and PDF export. This workflow runs without provider API keys or the transcription worker.

For a live Prisma demo, upload your own synthetic M4A recording up to 10 MiB.

## Security & Reliability

- JWT-based authentication and meeting-level access control.
- PostgreSQL-backed transcription queue with duplicate upload protection.
- Worker restart recovery and controlled API retries.
- Evidence-linked claims with integrity warnings.
- Revision history and a human verification audit trail.
- Original recording access restricted to meeting owners.
- Verified minutes protected against further modification.

## Current Limitations

- Groq powers live minutes drafting. Gnani Evon integration is planned.
- Speaker diarization labels speakers anonymously.
- Existing transcript segments are read-only. Users can add segments by hand.
- Multilingual integrity checks flag possible issues for human review.
- Verification records the meeting owner's confirmation within the prototype. Official approval follows the applicable government process.

## Future Enhancements

- Gnani Evon integration for meeting intelligence.
- Improved multilingual reasoning and claim verification.
- Speaker identification and voice playback with Gnani Timbre.
- Transcript editing and meeting analytics.
