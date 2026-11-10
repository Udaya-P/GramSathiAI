# GramSathi AI

**Multilingual Gram Sabha Meeting Intelligence System**

GramSathi AI is an AI-powered application designed to digitize and streamline Gram Sabha meetings through multilingual speech transcription, speaker diarization, automated meeting minutes, decision tracking, and evidence-based human verification.

The system supports **English, Telugu, Kannada, Hindi, and code-mixed speech**, enabling structured documentation of discussions conducted in multiple Indian languages.

## Key Features

- **Multilingual Speech-to-Text:** Integrates Gnani Prisma v3.0 Batch API to transcribe English, Telugu, Kannada, Hindi, and code-mixed meeting recordings.
- **Speaker Diarization:** Automatically distinguishes anonymous speakers within meeting recordings.
- **AI-Generated Meeting Minutes:** Uses Groq-hosted LLMs to generate structured meeting summaries from transcripts.
- **Decision & Action Tracking:** Extracts decisions, budget allocations, assigned responsibilities, deadlines, and unresolved issues.
- **Evidence-Grounded Intelligence:** Links generated claims to original transcript segments and timestamps for traceability.
- **Integrity Validation:** Detects potentially unsupported decisions, budget inconsistencies, missing evidence, and ambiguous claims.
- **Human-in-the-Loop Verification:** Allows meeting owners to review, correct, approve, or reject generated minutes.
- **Audio Evidence Playback:** Enables playback of original recordings and timestamp-linked transcript segments.
- **PDF Export:** Generates downloadable PDFs of verified meeting minutes.
- **Secure Meeting Management:** Provides JWT authentication, meeting ownership controls, and persistent storage.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Frontend | Streamlit |
| Database | PostgreSQL, SQLAlchemy |
| Speech-to-Text | Gnani Prisma v3.0 |
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
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── app.py
│   ├── components.py
│   ├── styles.py
│   └── requirements.txt
├── sample_audio/
└── README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/GramSathiAI.git
cd GramSathiAI
```

### 2. Set Up the Backend

Requires Python 3.11+ and PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

On Windows:

```powershell
.venv\Scripts\activate
```

Create `backend/.env` and configure the required environment variables.

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/gramsathi
JWT_SECRET=your_secure_random_secret
CORS_ORIGINS=["http://localhost:8501"]

GNANI_API_KEY=your_gnani_api_key
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

Use a supported Groq model available to your account. Never commit real API keys or credentials.

Apply database migrations and start FastAPI:

```bash
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

API documentation: `http://localhost:8000/docs`

### 3. Start the Transcription Worker

In a separate terminal, activate the virtual environment and run:

```bash
cd backend
python -m app.worker --allow-live
```

**Note:** This enables live Gnani API requests, which may incur usage charges. Start the worker only when live transcription is intended.

### 4. Run the Frontend

In another terminal, from the repository root:

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Configure `frontend/.env` with:

```env
API_BASE_URL=http://localhost:8000
```

The application is available at `http://localhost:8501`.

## Application Workflow

1. **Create Meeting:** Register, log in, and create a Gram Sabha meeting.
2. **Upload Audio:** Upload an M4A recording containing supported Indian languages.
3. **Transcribe:** Gnani Prisma generates timestamped, speaker-diarized transcripts.
4. **Generate Minutes:** The configured Groq model extracts summaries, decisions, action items, and unresolved issues.
5. **Validate Evidence:** Integrity checks flag potentially unsupported or inconsistent claims.
6. **Review & Verify:** The meeting owner reviews evidence, corrects the draft, and explicitly confirms the minutes.
7. **Export:** Download verified minutes as a PDF.

## Sample Recordings

The project includes four sample multilingual meeting recordings.

| Recording | Languages |
|---|---|
| Meeting 01 | English + Telugu |
| Meeting 02 | English + Kannada |
| Meeting 03 | English + Hindi |
| Meeting 04 | English + Telugu + Kannada + Hindi |

These recordings demonstrate multilingual and code-mixed Gram Sabha discussions.

## Security & Reliability

- JWT-based authentication and meeting-level access control.
- PostgreSQL-backed transcription queue with duplicate upload protection.
- Worker restart recovery and controlled API retries.
- Evidence-linked claims with integrity warnings.
- Revision history and human verification audit trail.
- Original recording access restricted to meeting owners.
- Verified minutes protected against further modification.

## Current Limitations

- Live Gnani Evon reasoning integration is not yet implemented; Groq is used for AI-generated minutes.
- Speaker diarization identifies anonymous speakers rather than real-world identities.
- Transcript segment editing and Timbre voice playback are not yet supported.
- Multilingual semantic integrity checks are conservative and require human review.
- Verification is a prototype confirmation workflow, not legally authenticated government approval.

## Future Enhancements

- Integration with Gnani Evon for meeting intelligence.
- Improved multilingual semantic reasoning and claim verification.
- Speaker identification and voice-based transcript playback.
- Expanded transcript editing and meeting analytics.

## Disclaimer

GramSathi AI is a prototype intended to demonstrate AI-assisted multilingual meeting documentation. Generated meeting minutes require human review and verification before use. The system does not provide legally authenticated government records.
