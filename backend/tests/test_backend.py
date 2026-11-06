"""Six PostgreSQL integration tests; migrations run in a disposable random schema."""
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")


@pytest.fixture(scope="session")
def api():
    test_url = os.getenv("TEST_DATABASE_URL")
    if not test_url:
        pytest.fail("TEST_DATABASE_URL is required; use a dedicated PostgreSQL test database")
    test = make_url(test_url)
    app_url = os.getenv("DATABASE_URL")
    if test.drivername != "postgresql+psycopg" or not test.database:
        pytest.fail("TEST_DATABASE_URL must identify a PostgreSQL database using psycopg")
    # Ignore user/password/query so different credentials cannot bypass the guard.
    # Requiring different database names also catches hostname aliases to the same DB.
    if app_url and make_url(app_url).database == test.database:
        pytest.fail("Test database name must differ from the application database name")
    if not app_url:
        pytest.fail("DATABASE_URL is required for the test database isolation safety check")
    original_env = {key: os.environ.get(key) for key in ("DATABASE_URL", "JWT_SECRET", "CORS_ORIGINS", "APP_ENVIRONMENT", "ENABLE_MOCK_REASONING")}
    os.environ.update(DATABASE_URL=test_url, JWT_SECRET=secrets.token_urlsafe(48), CORS_ORIGINS="[]", APP_ENVIRONMENT="test", ENABLE_MOCK_REASONING="true")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.database import get_db, engine as app_engine
    from app.main import app

    schema = "test_" + uuid4().hex
    admin = create_engine(test_url, hide_parameters=True, connect_args={"connect_timeout": 5})
    test_engine = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        test_engine = create_engine(test_url, hide_parameters=True,
                                    connect_args={"options": f"-csearch_path={schema},pg_catalog", "connect_timeout": 5})
        cfg = Config(str(BACKEND / "alembic.ini"))
        with test_engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        factory = sessionmaker(test_engine, expire_on_commit=False)
        app.state.test_session_factory = factory
        app.state.test_engine = test_engine

        def override_db():
            with factory() as session:
                try:
                    yield session
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        if test_engine:
            test_engine.dispose()
        app_engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def account(api):
    email = f"{uuid4().hex}@example.com"
    body = {"name": "Test Owner", "email": email, "password": secrets.token_urlsafe(20)}
    result = api.post("/api/v1/auth/register", json=body)
    assert result.status_code == 201, result.text
    login = api.post("/api/v1/auth/login", json={"email": email, "password": body["password"]})
    assert login.status_code == 200
    return {"Authorization": "Bearer " + login.json()["access_token"]}, body, result.json()


def meeting(api, headers):
    payload = json.loads((BACKEND / "data/sample_meeting.json").read_text())["meeting"]
    response = api.post("/api/v1/meetings", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return "/api/v1/meetings/" + response.json()["id"]


def segment(text_value="Pipeline inspection", start=0, end=4, language="en"):
    return {"speaker_id": "speaker_1", "language": language, "text": text_value, "start_time": start, "end_time": end}


def minutes(segment_id):
    return {"summary": "Water supply discussion", "summary_evidence_segment_ids": [segment_id], "decisions": [{"description": "Repair pipeline", "status": "approved", "evidence_segment_ids": [segment_id]}],
            "action_items": [{"task": "Inspect pipeline", "assigned_to": "Secretary", "deadline": None, "evidence_segment_ids": [segment_id]}],
            "unresolved_issues": [{"description": "Funding pending", "evidence_segment_ids": [segment_id]}]}


def test_health(api):
    assert api.get("/health").json() == {"status": "ok", "service": "GramSathi AI", "version": "0.1.0"}
    assert api.get("/docs").status_code == 200


def test_authentication(api):
    headers, body, user = account(api)
    assert "password_hash" not in user and "password" not in user
    assert api.get("/api/v1/auth/me", headers=headers).json() == user
    assert api.post("/api/v1/auth/register", json=body).status_code == 409
    assert api.post("/api/v1/auth/login", json={"email": body["email"], "password": "incorrect"}).status_code == 401
    assert api.get("/api/v1/meetings").status_code == 401
    from app.config import get_settings
    now = datetime.now(timezone.utc)
    claims = {"sub": user["id"], "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1), "type": "access"}
    expired = jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), algorithm="HS256")
    wrong_signature = jwt.encode({**claims, "exp": now + timedelta(minutes=1)}, secrets.token_urlsafe(48), algorithm="HS256")
    unsigned = jwt.encode({**claims, "exp": now + timedelta(minutes=1)}, key="", algorithm="none")
    for token in ("malformed", expired, wrong_signature, unsigned):
        assert api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_meetings_and_owner_isolation(api):
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path = meeting(api, owner)
    assert api.get(path, headers=owner).status_code == 200
    assert path.rsplit("/", 1)[1] in [m["id"] for m in api.get("/api/v1/meetings", headers=owner).json()]
    assert api.get("/api/v1/meetings", headers=other).json() == []
    for suffix in ("", "/transcript", "/minutes"):
        assert api.get(path + suffix, headers=other).status_code == 404
    assert api.post(path + "/transcript", headers=other, json={"segments": [segment()]}).status_code == 404
    assert api.post(path + "/minutes", headers=other, json=minutes(1)).status_code == 404
    assert api.delete(path, headers=other).status_code == 404
    assert api.delete(path, headers=owner).status_code == 204
    assert api.get(path, headers=owner).status_code == 404
    invalid = {"title": "Meeting", "village_name": "Village", "district": "District", "state": "State", "meeting_date": "2026-10-01", "primary_language": "te", "supported_languages": ["en"]}
    assert api.post("/api/v1/meetings", headers=owner, json=invalid).status_code == 422


def test_multilingual_transcripts(api):
    owner, _, _ = account(api)
    path = meeting(api, owner) + "/transcript"
    data = json.loads((BACKEND / "data/sample_meeting.json").read_text())["transcript"]
    data["segments"][0]["text"] = "  " + data["segments"][0]["text"] + "\n"
    result = api.post(path, headers=owner, json={"segments": list(reversed(data["segments"]))})
    assert result.status_code == 201, result.text
    saved = result.json()
    assert [s["text"] for s in saved] == [s["text"] for s in data["segments"]]
    assert len({s["id"] for s in saved}) == len(saved)
    for invalid in (segment(start=-1), segment(start=4, end=4), segment(text_value=" \n ")):
        assert api.post(path, headers=owner, json={"segments": [segment(), invalid]}).status_code == 422
    assert api.get(path, headers=owner).json() == saved  # Invalid batches added nothing.
    extra = api.post(path, headers=owner, json={"segments": [segment(start=0, end=2, language="mixed")]}).json()[0]
    fetched = api.get(path, headers=owner).json()
    assert fetched[0]["id"] == extra["id"]
    assert {s["id"] for s in saved}.issubset({s["id"] for s in fetched})


def test_minutes_and_evidence(api):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    sid = api.post(path + "/transcript", headers=owner, json={"segments": [segment()]}).json()[0]["id"]
    body = minutes(sid)
    result = api.post(path + "/minutes", headers=owner, json=body)
    assert result.status_code == 200, result.text
    original = result.json()
    assert original["status"] == "draft" and original["verified_at"] is None
    foreign = meeting(api, owner)
    foreign_id = api.post(foreign + "/transcript", headers=owner, json={"segments": [segment()]}).json()[0]["id"]
    for evidence in ([], [999999999], [foreign_id]):
        body["decisions"][0]["evidence_segment_ids"] = evidence
        assert api.post(path + "/minutes", headers=owner, json=body).status_code == 422
        assert api.get(path + "/minutes", headers=owner).json() == original
    body = minutes(sid)
    assert api.post(path + "/minutes", headers=owner, json={**body, "status": "verified"}).status_code == 422
    body["summary"] = "Revised summary"
    assert api.post(path + "/minutes", headers=owner, json=body).json()["summary"] == "Revised summary"


def test_explicit_verification(api):
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path = meeting(api, owner)
    sid = api.post(path + "/transcript", headers=owner, json={"segments": [segment()]}).json()[0]["id"]
    assert api.post(path + "/minutes", headers=owner, json=minutes(sid)).status_code == 200
    verification = {"verifier_name": "Panchayat Secretary", "confirmed": True}
    assert api.post(path + "/minutes/verify", json=verification).status_code == 401
    assert api.post(path + "/minutes/verify", headers=other, json=verification).status_code == 404
    for invalid in ({**verification, "confirmed": False}, {**verification, "verifier_name": "  "}):
        assert api.post(path + "/minutes/verify", headers=owner, json=invalid).status_code == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: api.post(path + "/minutes/verify", headers=owner, json=verification), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    result = next(r for r in responses if r.status_code == 200)
    assert result.json()["status"] == "verified" and result.json()["verified_at"]
    assert result.json()["verifier_name"] == verification["verifier_name"]
    assert api.post(path + "/minutes/verify", headers=owner, json=verification).status_code == 409
    assert api.post(path + "/minutes", headers=owner, json=minutes(sid)).status_code == 409
    assert api.get(path + "/minutes", headers=owner).json() == result.json()
    assert api.delete(path, headers=owner).status_code == 204
    assert api.get(path + "/transcript", headers=owner).status_code == 404


@pytest.fixture(autouse=True)
def block_live_provider_calls(monkeypatch):
    """Even an accidental real SDK invocation must never reach Gnani in tests."""
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError("Live HTTP calls are forbidden in tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    import httpx
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


def queue_upload(api, owner, path, audio=None, code="en-IN,te-IN", filename="meeting.m4a"):
    if audio is None:
        audio = b"\x00\x00\x00\x18ftypM4A " + secrets.token_bytes(16)
    return api.post(path + "/transcriptions", headers=owner,
                    files={"audio": (filename, audio, "audio/mp4")}, data={"language_code": code})


def fake_provider(job_id, provider_id=None):
    from unittest.mock import Mock
    from gnani.stt import GnaniSTTBatchClient
    from gnani.stt.batch import BatchFile, BatchJob
    provider_id = provider_id or str(uuid4())
    document = {"job_id": provider_id, "model": "prisma-v3.0", "segments": [
        {"segment_id": 0, "start_time": 0, "end_time": 3, "text": "  Water pipeline సమస్య ఉంది.\n", "speaker_id": 0, "language_detected": "te-IN"},
        {"segment_id": 0, "start_time": 3.2, "end_time": 6, "text": "ನಾಳೆ ಪರಿಶೀಲನೆ ಮಾಡೋಣ.", "speaker_id": 1, "language_detected": "kn-IN"},
        {"segment_id": 2, "start_time": 6.1, "end_time": 8, "text": "मरम्मत की ज़रूरत है।", "speaker_id": 0, "language_detected": "hi-IN"},
        {"segment_id": 3, "start_time": 8.2, "end_time": 12, "text": "We need an estimate.", "speaker_id": 2, "language_detected": "en-IN"},
        {"segment_id": 4, "start_time": 12.1, "end_time": 13, "text": "", "speaker_id": -1, "language_detected": None},
    ]}
    file = BatchFile(file_id=str(uuid4()), name=f"{job_id}.m4a", status="COMPLETED", _transcript=document)
    remote = BatchJob(id=provider_id, status="CREATED", config={"model": "prisma-v3.0", "format": "codemix", "with_diarization": True, "language_code": "en-IN,te-IN"})
    remote.files = Mock(return_value=[file])
    def start():
        remote.status = "STARTING"
        return remote
    remote.start = Mock(side_effect=start)
    client = Mock(spec=GnaniSTTBatchClient)
    client.create_job.return_value = remote
    client.get_job.return_value = remote
    return client, remote, document


def worker_tick(api, client, job_id):
    from sqlalchemy import update
    from app.models import TranscriptionJob
    from app.worker import run_once
    factory = api.app.state.test_session_factory
    with factory.begin() as db:
        # Other tests' queued audio must not be picked up by this test's worker.
        db.execute(update(TranscriptionJob).values(next_poll_at=datetime.now(timezone.utc) + timedelta(days=1)))
        db.execute(update(TranscriptionJob).where(TranscriptionJob.id == UUID(job_id))
                   .values(next_poll_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    return run_once(client, db_engine=api.app.state.test_engine, factory=factory)


@pytest.mark.parametrize("filename,codes", [
    ("meeting_01_en_te.m4a", "en-IN,te-IN"),
    ("meeting_02_en_kn.m4a", "en-IN,kn-IN"),
    ("meeting_03_en_hi.m4a", "en-IN,hi-IN"),
    ("meeting_04_en_te_kn_hi.m4a", "en-IN,te-IN,kn-IN,hi-IN"),
])
def test_recording_profiles_queue_without_gnani(api, filename, codes):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    audio = (BACKEND.parent / "sample_audio" / filename).read_bytes()
    response = queue_upload(api, owner, path, audio, codes, filename)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["language_codes"] == codes.split(",")
    assert body["model"] == "prisma-v3.0" and body["output_format"] == "codemix"
    assert body["status"] == "queued" and body["provider_job_id"] is None
    assert "audio_data" not in body and "result_json" not in body


def test_upload_validation_ownership_and_concurrent_dedup(api):
    from app.services.prisma import MAX_AUDIO_BYTES
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path = meeting(api, owner)
    assert queue_upload(api, {}, path).status_code == 401
    assert queue_upload(api, other, path).status_code == 404
    assert queue_upload(api, owner, path, audio=b"").status_code == 415
    assert queue_upload(api, owner, path, filename="audio.wav").status_code == 415
    assert queue_upload(api, owner, path, code="en-IN,en-IN").status_code == 422
    assert queue_upload(api, owner, path, code="not-a-language").status_code == 422
    assert queue_upload(api, owner, path, audio=b"x" * (MAX_AUDIO_BYTES + 1)).status_code == 413
    audio = b"\x00\x00\x00\x18ftypM4A " + secrets.token_bytes(24)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: queue_upload(api, owner, path, audio=audio), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 202]
    job_id = responses[0].json()["id"]
    assert responses[1].json()["id"] == job_id
    assert queue_upload(api, owner, path, audio=audio, code="en-IN,hi-IN").status_code == 409
    assert len(api.get(path + "/transcriptions", headers=owner).json()) == 1
    assert api.get(path + "/transcriptions/" + job_id, headers=other).status_code == 404
    assert api.get(path + "/transcriptions", headers=other).status_code == 404


def test_worker_sdk_options_restart_and_atomic_import(api):
    from unittest.mock import Mock
    from gnani.stt import GnaniSTTBatchClient
    from app.models import TranscriptionJob
    owner, _, _ = account(api)
    path = meeting(api, owner)
    queued = queue_upload(api, owner, path).json()
    client, remote, document = fake_provider(queued["id"])
    assert worker_tick(api, client, queued["id"])
    args, options = client.create_job.call_args
    assert args[0][0] == queued["id"] + ".m4a" and isinstance(args[0][1], bytes)
    assert options == {"language_code": "en-IN,te-IN", "model": "prisma-v3.0", "format": "codemix", "diarization": True, "start": False, "request_id": queued["id"]}
    assert remote.start.call_count == 0  # Provider ID must commit before start.
    status_path = path + "/transcriptions/" + queued["id"]
    assert api.get(status_path, headers=owner).json()["provider_job_id"] == remote.id
    with api.app.state.test_session_factory() as db:
        assert db.get(TranscriptionJob, UUID(queued["id"])).audio_data is None
    # A new client/process reattaches by persisted ID instead of uploading again.
    restarted = Mock(spec=GnaniSTTBatchClient)
    restarted.get_job.return_value = remote
    assert worker_tick(api, restarted, queued["id"])
    restarted.create_job.assert_not_called()
    remote.start.assert_called_once()
    remote.status = "IN_PROGRESS"
    worker_tick(api, restarted, queued["id"])
    assert api.get(path + "/transcript", headers=owner).json() == []
    remote.status = "COMPLETED"
    worker_tick(api, restarted, queued["id"])
    saved = api.get(path + "/transcript", headers=owner).json()
    assert len(saved) == 4
    assert [s["text"] for s in saved] == [s["text"] for s in document["segments"][:4]]
    assert [s["language"] for s in saved] == ["te", "kn", "hi", "en"]
    assert [s["detected_language"] for s in saved] == ["te-IN", "kn-IN", "hi-IN", "en-IN"]
    assert [s["provider_speaker_id"] for s in saved] == [0, 1, 0, 2]
    assert [s["start_time"] for s in saved] == [0, 3.2, 6.1, 8.2]
    assert [s["end_time"] for s in saved] == [3, 6, 8, 12]
    assert all(s["speaker_id"].startswith("gnani_" + queued["id"] + "_speaker_") for s in saved)
    assert api.get(status_path, headers=owner).json()["status"] == "completed"
    assert not worker_tick(api, restarted, queued["id"])
    assert api.get(path + "/transcript", headers=owner).json() == saved


def test_worker_uncertain_submission_requires_reconciliation(api):
    from unittest.mock import Mock
    from gnani.stt import GnaniSTTBatchClient
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path = meeting(api, owner)
    job = queue_upload(api, owner, path).json()
    client = Mock(spec=GnaniSTTBatchClient)
    client.create_job.side_effect = TimeoutError("secret provider body must never be exposed")
    worker_tick(api, client, job["id"])
    status_path = path + "/transcriptions/" + job["id"]
    status = api.get(status_path, headers=owner).json()
    assert status["status"] == "needs_reconciliation"
    assert status["error_code"] == "submission_outcome_unknown"
    assert "secret provider body" not in str(status)
    assert not worker_tick(api, client, job["id"])
    assert client.create_job.call_count == 1
    resumed, remote, _ = fake_provider(job["id"])
    body = {"provider_job_id": remote.id}
    assert api.post(status_path + "/resume", headers=other, json=body).status_code == 404
    assert api.post(status_path + "/resume", headers=owner, json=body).status_code == 200
    worker_tick(api, resumed, job["id"])
    resumed.create_job.assert_not_called()
    remote.status = "COMPLETED"
    worker_tick(api, resumed, job["id"])
    assert api.get(status_path, headers=owner).json()["status"] == "completed"
    assert api.post(status_path + "/resume", headers=owner, json=body).status_code == 409


def test_worker_crash_state_and_wrong_provider_file(api):
    from app.models import TranscriptionJob
    owner, _, _ = account(api)
    path = meeting(api, owner)
    job = queue_upload(api, owner, path).json()
    with api.app.state.test_session_factory.begin() as db:
        db.get(TranscriptionJob, UUID(job["id"])).status = "submitting"
    client, remote, _ = fake_provider(job["id"])
    worker_tick(api, client, job["id"])
    client.create_job.assert_not_called()
    status_path = path + "/transcriptions/" + job["id"]
    assert api.post(status_path + "/resume", headers=owner, json={"provider_job_id": remote.id}).status_code == 200
    remote.files.return_value[0].name = "another-owners-file.m4a"
    worker_tick(api, client, job["id"])
    assert api.get(status_path, headers=owner).json()["error_code"] == "provider_contract_invalid"
    remote.start.assert_not_called()
    assert api.get(path + "/transcript", headers=owner).json() == []


def test_worker_bad_result_rolls_back_and_transient_poll_recovers(api):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    job = queue_upload(api, owner, path).json()
    client, remote, document = fake_provider(job["id"])
    worker_tick(api, client, job["id"])
    client.get_job.side_effect = TimeoutError("not returned")
    worker_tick(api, client, job["id"])
    status_path = path + "/transcriptions/" + job["id"]
    status = api.get(status_path, headers=owner).json()
    assert status["attempts"] == 1 and status["provider_job_id"] == remote.id
    client.get_job.side_effect = None
    remote.status = "COMPLETED"
    document["segments"][1]["end_time"] = 0  # First valid segment must not be partially inserted.
    worker_tick(api, client, job["id"])
    assert api.get(status_path, headers=owner).json()["status"] == "failed"
    assert api.get(path + "/transcript", headers=owner).json() == []
    assert client.create_job.call_count == 1


def test_evon_disabled_mock_citations_and_human_review(api):
    from app.services.evon import MockEvonAdapter, get_evon_adapter
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path = meeting(api, owner)
    sid = api.post(path + "/transcript", headers=owner, json={"segments": [segment()]}).json()[0]["id"]
    assert api.post(path + "/minutes/generate", headers=other).status_code == 404
    assert api.post(path + "/minutes/generate", headers=owner).status_code == 501
    try:
        api.app.dependency_overrides[get_evon_adapter] = lambda: MockEvonAdapter(minutes(sid + 999999))
        invalid = api.post(path + "/minutes/generate", headers=owner)
        assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "unsupported_claims"
        assert api.get(path + "/minutes", headers=owner).status_code == 404
        fixture = minutes(sid)
        fixture["decisions"][0]["evidence_segment_ids"] = []
        api.app.dependency_overrides[get_evon_adapter] = lambda: MockEvonAdapter(fixture)
        assert api.post(path + "/minutes/generate", headers=owner).status_code == 422
        api.app.dependency_overrides[get_evon_adapter] = lambda: MockEvonAdapter(minutes(sid))
        result = api.post(path + "/minutes/generate", headers=owner)
        assert result.status_code == 200, result.text
        draft = result.json()
        assert draft["status"] == "draft" and draft["generation_source"] == "mock_fixture"
        assert any(f["code"] == "CLAIM_SUPPORT_UNVERIFIED" for f in draft["review_flags"])
        verified = api.post(path + "/minutes/verify", headers=owner, json={"confirmed": True, "verifier_name": "Secretary", "acknowledge_warnings": True})
        assert verified.json()["status"] == "verified" and all(f["acknowledged"] for f in verified.json()["review_flags"])
        assert api.post(path + "/minutes/generate", headers=owner).status_code == 409
    finally:
        api.app.dependency_overrides.pop(get_evon_adapter, None)


def test_worker_recovers_lost_commit_acknowledgement(api, monkeypatch):
    from app import worker
    owner, _, _ = account(api)
    path = meeting(api, owner)
    job = queue_upload(api, owner, path).json()
    client, remote, _ = fake_provider(job["id"])
    original_update = worker._update
    def lost_ack(factory, job_id, **values):
        result = original_update(factory, job_id, **values)
        if "provider_job_id" in values:
            raise ConnectionError("simulated lost commit acknowledgement")
        return result
    monkeypatch.setattr(worker, "_update", lost_ack)
    worker_tick(api, client, job["id"])
    state = api.get(path + "/transcriptions/" + job["id"], headers=owner).json()
    assert state["status"] == "submitted" and state["provider_job_id"] == remote.id
    assert client.create_job.call_count == 1
    monkeypatch.setattr(worker, "_update", original_update)
    worker_tick(api, client, job["id"])
    remote.start.assert_called_once()
    assert client.create_job.call_count == 1


def phase3_fixture(api, owner):
    """Synthetic Meeting 1 semantics, persisted before IDs are used as citations."""
    path = meeting(api, owner)
    texts = [
        "మన గ్రామంలో నీటి సమస్య ఉంది. Estimated pipeline repair cost is approximately ₹17,000.",
        "We propose an allocation of ₹15,000 for the pipeline repair.",
        "The proposal is approved.",
        "Panchayat Secretary must coordinate the repair and provide a progress update within seven days.",
        "The additional borewell proposal is deferred pending a funding decision.",
    ]
    response = api.post(path + "/transcript", headers=owner, json={"segments": [
        segment(text_value=text, start=index * 6, end=index * 6 + 5, language="mixed")
        for index, text in enumerate(texts)]})
    assert response.status_code == 201, response.text
    saved = response.json()
    ids = [s["id"] for s in saved]
    fixture = {
        "summary": "Village water supply needs pipeline repair, with a ₹17,000 estimate and a ₹15,000 approved allocation. Coordination and a progress update are required.",
        "summary_evidence_segment_ids": ids[:4],
        "summary_claims": [
            {"text": "The repair estimate is ₹17,000.", "evidence_segment_ids": [ids[0]]},
            {"text": "The proposal for ₹15,000 is approved.", "evidence_segment_ids": ids[1:3]},
        ],
        "decisions": [
            {"description": "Allocate funds for pipeline repair", "status": "APPROVED", "estimated_amount": 17000,
             "proposed_amount": 15000, "approved_amount": 15000, "currency": "INR", "evidence_segment_ids": ids[:3],
             "evidence_quotes": [{"segment_id": ids[1], "quote": texts[1]}, {"segment_id": ids[2], "quote": texts[2]},
                                 {"segment_id": ids[0], "quote": texts[0]}]},
            {"description": "Additional borewell funding remains pending", "status": "DEFERRED", "evidence_segment_ids": [ids[4]]},
        ],
        "action_items": [
            {"task": "Coordinate pipeline repair", "assigned_to": "Panchayat Secretary", "deadline": None, "evidence_segment_ids": [ids[3]]},
            {"task": "Provide progress update", "assigned_to": "Panchayat Secretary", "deadline": None,
             "deadline_text": "within seven days", "evidence_segment_ids": [ids[3]]},
        ],
        "unresolved_issues": [{"description": "Additional borewell funding is not yet decided", "evidence_segment_ids": [ids[4]]}],
    }
    return path, saved, fixture


def generate_fixture(api, owner, path, fixture):
    return api.post(path + "/minutes/generate", headers=owner, json={"provider": "mock", "fixture": fixture})


def test_phase3_meeting_one_grounding_and_review_history(api):
    from copy import deepcopy
    from decimal import Decimal
    owner, _, _ = account(api)
    other, _, _ = account(api)
    path, source, fixture = phase3_fixture(api, owner)
    result = generate_fixture(api, owner, path, fixture)
    assert result.status_code == 200, result.text
    draft = result.json()
    decision = draft["decisions"][0]
    assert decision["status"] == decision["classification"] == "approved"
    assert Decimal(decision["approved_amount"]) == 15000
    assert Decimal(decision["estimated_amount"]) == 17000
    assert draft["decisions"][1]["status"] == "proposed" and draft["decisions"][1]["classification"] == "deferred"
    assert draft["action_items"][0]["deadline"] is None and draft["action_items"][0]["deadline_text"] is None
    assert draft["action_items"][1]["deadline"] is None and draft["action_items"][1]["deadline_text"] == "within seven days"
    assert not any(w["code"] in {"UNSUPPORTED_BUDGET", "UNSUPPORTED_APPROVAL", "UNSUPPORTED_ASSIGNEE", "UNSUPPORTED_DEADLINE", "CONFLICTING_AMOUNTS"} for w in draft["review_flags"])
    assert draft["status"] == "draft" and draft["generation_source"] == "mock_fixture"
    assert all(w["requires_human_review"] for w in draft["review_flags"])
    evidence = api.get(path + "/minutes/evidence", headers=owner).json()
    assert evidence["segments"] == source  # Original text, timestamps and speaker IDs survive.
    assert len({s["speaker_id"] for s in evidence["segments"]}) == 1
    for suffix in ("/decisions", "/action-items", "/minutes/evidence", "/minutes/integrity", "/minutes/history"):
        assert api.get(path + suffix, headers=owner).status_code == 200
        assert api.get(path + suffix, headers=other).status_code == 404
    original = api.get(path + "/minutes/history", headers=owner).json()["generated_original"]
    edit = deepcopy(fixture)
    edit["expected_revision"] = draft["revision"]
    edit["decisions"][0]["approved_amount"] = 14000
    changed = api.post(path + "/minutes", headers=owner, json=edit)
    assert changed.status_code == 200, changed.text
    assert any(w["code"] == "UNSUPPORTED_BUDGET" for w in changed.json()["review_flags"])
    rejection = {"decision": "reject", "reviewer_name": "Secretary", "expected_revision": changed.json()["revision"], "comment": "Correct the approved allocation."}
    assert api.post(path + "/minutes/review", headers=other, json=rejection).status_code == 404
    rejected = api.post(path + "/minutes/review", headers=owner, json=rejection)
    assert rejected.status_code == 200 and rejected.json()["review_state"] == "rejected"
    assert rejected.json()["status"] == "draft"
    confirmation = {"confirmed": True, "verifier_name": "Secretary", "acknowledge_warnings": True}
    assert api.post(path + "/minutes/verify", headers=owner, json=confirmation).status_code == 409
    edit["decisions"][0]["approved_amount"] = 15000
    edit["expected_revision"] = rejected.json()["revision"]
    corrected = api.post(path + "/minutes", headers=owner, json=edit).json()
    assert api.post(path + "/minutes", headers=owner, json=edit).status_code == 409  # stale revision
    assert api.post(path + "/minutes/verify", headers=owner, json={"confirmed": True, "verifier_name": "Secretary"}).status_code == 409
    assert api.post(path + "/minutes/verify", headers=other, json=confirmation).status_code == 404
    review = {"decision": "approve", "reviewer_name": "Secretary", "expected_revision": corrected["revision"],
              "confirmed": True, "acknowledge_warnings": True, "comment": "Reviewed original evidence."}
    assert api.post(path + "/minutes/review", headers=owner, json={**review, "confirmed": False}).status_code == 422
    verified = api.post(path + "/minutes/review", headers=owner, json=review)
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified" and verified.json()["review_state"] == "accepted"
    history = api.get(path + "/minutes/history", headers=owner).json()
    assert history["generated_original"] == original
    assert history["history"][-1]["comment"] == "Reviewed original evidence."
    assert [h["event"] for h in history["history"]] == ["generated", "manual_edit", "rejected", "manual_edit", "approved"]
    assert any(Decimal(h["document"]["decisions"][0]["approved_amount"]) == 14000 for h in history["history"])
    assert api.get(path + "/transcript", headers=owner).json() == source
    assert generate_fixture(api, owner, path, fixture).status_code == 409


@pytest.mark.parametrize("text,status,expected,absent", [
    ("We propose an allocation of ₹15,000.", "PROPOSED", None, "UNSUPPORTED_APPROVAL"),
    ("We propose an allocation of ₹15,000.", "APPROVED", "UNSUPPORTED_APPROVAL", None),
    ("The budget of ₹15,000 is rejected.", "REJECTED", None, "UNSUPPORTED_REJECTION"),
    ("The proposal of ₹15,000 is not approved.", "APPROVED", "UNSUPPORTED_APPROVAL", None),
    ("Everyone agreed the repair would be useful. Should we approve ₹15,000?", "APPROVED", "UNSUPPORTED_APPROVAL", None),
    ("The proposal of ₹15,000 is not rejected; it remains pending.", "REJECTED", "UNSUPPORTED_REJECTION", None),
    ("The proposal of ₹15,000 is unclear.", "UNCLEAR", "AMBIGUOUS_DECISION_STATUS", None),
])
def test_phase3_status_distinctions(api, text, status, expected, absent):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    sid = api.post(path + "/transcript", headers=owner, json={"segments": [segment(text_value=text)]}).json()[0]["id"]
    fixture = {"summary": "Budget discussion.", "summary_evidence_segment_ids": [sid],
               "decisions": [{"description": "Budget allocation", "status": status, "evidence_segment_ids": [sid]}]}
    response = generate_fixture(api, owner, path, fixture)
    assert response.status_code == 200, response.text
    codes = {w["code"] for w in response.json()["review_flags"]}
    if expected:
        assert expected in codes
    if absent:
        assert absent not in codes
    assert response.json()["status"] == "draft"
    assert response.json()["decisions"][0]["approved_amount"] is None


def test_phase3_unsupported_budget_assignee_and_deadline(api):
    owner, _, _ = account(api)
    path, _, fixture = phase3_fixture(api, owner)
    fixture["decisions"][0]["approved_amount"] = 17000  # Estimate is not the allocation.
    fixture["action_items"][0].update(deadline="2026-10-22", deadline_text="within seven days", assigned_to="Village Engineer")
    fixture["action_items"][1]["assigned_to"] = None
    response = generate_fixture(api, owner, path, fixture)
    assert response.status_code == 200, response.text
    flags = response.json()["review_flags"]
    assert {"UNSUPPORTED_BUDGET", "CONFLICTING_AMOUNTS", "UNSUPPORTED_ASSIGNEE", "UNSUPPORTED_DEADLINE", "INSUFFICIENT_EVIDENCE"}.issubset({w["code"] for w in flags})
    assert response.json()["action_items"][1]["assigned_to"] is None
    assert any(w["entity"] == "action_items[0]" and w["code"] == "UNSUPPORTED_DEADLINE" for w in flags)
    assert all({"code", "entity", "explanation", "evidence_segment_ids", "requires_human_review"} <= w.keys() for w in flags)


def test_phase3_invalid_cross_meeting_and_empty_evidence(api):
    from copy import deepcopy
    owner, _, _ = account(api)
    path, _, fixture = phase3_fixture(api, owner)
    other_path = meeting(api, owner)
    foreign_id = api.post(other_path + "/transcript", headers=owner, json={"segments": [segment()]}).json()[0]["id"]
    for bad_id in (foreign_id, 2147483647):
        invalid = deepcopy(fixture)
        invalid["decisions"][0]["evidence_segment_ids"] = [bad_id]
        response = generate_fixture(api, owner, path, invalid)
        assert response.status_code == 422, response.text
        assert any(w["code"] == "INVALID_EVIDENCE_REFERENCE" for w in response.json()["detail"]["review_flags"])
        assert api.get(path + "/minutes", headers=owner).status_code == 404
    invalid = deepcopy(fixture)
    invalid["action_items"][0]["evidence_segment_ids"] = []
    assert generate_fixture(api, owner, path, invalid).status_code == 422
    invalid = deepcopy(fixture)
    invalid["summary_evidence_segment_ids"] = []
    invalid["summary_claims"] = []
    response = generate_fixture(api, owner, path, invalid)
    assert response.status_code == 422
    assert any(w["entity"] == "summary" and w["code"] == "INSUFFICIENT_EVIDENCE" for w in response.json()["detail"]["review_flags"])
    invalid = deepcopy(fixture)
    invalid["decisions"][0]["evidence_quotes"][0]["quote"] = "The budget is ₹99,999 and approved."
    response = generate_fixture(api, owner, path, invalid)
    assert response.status_code == 422
    assert any(w["code"] == "INSUFFICIENT_EVIDENCE" for w in response.json()["detail"]["review_flags"])


def test_phase3_conflicts_and_native_evidence_remain_reviewable(api):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    texts = ["ప్రతిపాదనను చర్చిద్దాం. ₹15,000 అవసరం. ಅಂದಾಜು ವೆಚ್ಚವನ್ನು ಪರಿಶೀಲಿಸೋಣ. प्रस्ताव पर चर्चा लंबित है।",
             "The budget of ₹15,000 is approved. The budget of ₹17,000 is rejected."]
    source = api.post(path + "/transcript", headers=owner, json={"segments": [segment(text_value=t, start=i*5, end=i*5+4, language="mixed") for i,t in enumerate(texts)]}).json()
    ids = [s["id"] for s in source]
    fixture = {"summary": texts[0], "summary_evidence_segment_ids": ids,
               "decisions": [{"description": "Allocation", "status": "approved", "approved_amount": 15000, "currency": "INR", "evidence_segment_ids": [ids[1]]},
                             {"description": "Allocation", "status": "rejected", "approved_amount": 17000, "currency": "INR", "evidence_segment_ids": [ids[1]]}]}
    result = generate_fixture(api, owner, path, fixture)
    assert result.status_code == 200, result.text
    assert {"CONFLICTING_AMOUNTS", "AMBIGUOUS_DECISION_STATUS"} <= {w["code"] for w in result.json()["review_flags"]}
    assert result.json()["summary"] == texts[0]
    assert api.get(path + "/minutes/evidence", headers=owner).json()["segments"] == source


def test_phase3_mock_gate_and_live_evon_stays_disabled(api, monkeypatch):
    from app.config import get_settings
    owner, _, _ = account(api)
    path, _, fixture = phase3_fixture(api, owner)
    assert api.post(path + "/minutes/generate", headers=owner).status_code == 501
    assert api.post(path + "/minutes/generate", headers=owner, json={"provider": "evon"}).status_code == 501
    monkeypatch.setattr(get_settings(), "app_environment", "production")
    assert generate_fixture(api, owner, path, fixture).status_code == 403
    monkeypatch.setattr(get_settings(), "app_environment", "development")
    monkeypatch.setattr(get_settings(), "enable_mock_reasoning", False)
    assert generate_fixture(api, owner, path, fixture).status_code == 403
    assert api.get(path + "/minutes", headers=owner).status_code == 404


def test_phase3_quotes_cannot_hide_condition_or_reverse_chronology(api):
    owner, _, _ = account(api)
    path = meeting(api, owner)
    text_value = "We propose an allocation of ₹15,000. If the proposal is approved, we can proceed."
    sid = api.post(path + "/transcript", headers=owner, json={"segments": [segment(text_value=text_value)]}).json()[0]["id"]
    fixture = {"summary": "Allocation discussion.", "summary_evidence_segment_ids": [sid], "decisions": [
        {"description": "Pipeline allocation", "status": "approved", "approved_amount": 15000, "currency": "INR", "evidence_segment_ids": [sid],
         "evidence_quotes": [{"segment_id": sid, "quote": "the proposal is approved"},
                             {"segment_id": sid, "quote": "We propose an allocation of ₹15,000."}]}]}
    response = generate_fixture(api, owner, path, fixture)
    assert response.status_code == 200, response.text
    assert {"UNSUPPORTED_APPROVAL", "UNSUPPORTED_BUDGET"} <= {w["code"] for w in response.json()["review_flags"]}


def test_phase3_currency_and_omitted_contradiction(api):
    owner, _, _ = account(api)
    path, _, fixture = phase3_fixture(api, owner)
    extra = api.post(path + "/transcript", headers=owner, json={"segments": [segment(
        text_value="The budget of ₹15,000 is not approved after the funding review.", start=40, end=45)]}).json()[0]
    fixture["decisions"][0]["currency"] = "USD"
    wrong_currency = generate_fixture(api, owner, path, fixture)
    assert any(w["code"] == "UNSUPPORTED_BUDGET" for w in wrong_currency.json()["review_flags"])
    fixture["decisions"][0]["currency"] = "INR"
    contradicted = generate_fixture(api, owner, path, fixture)
    assert any(w["code"] == "AMBIGUOUS_DECISION_STATUS" and extra["id"] in w["evidence_segment_ids"] for w in contradicted.json()["review_flags"])


def test_phase3_migration_preserves_legacy_transcripts_and_verified_minutes(api):
    """Upgrade populated 0002 in a second transaction-scoped disposable schema."""
    schema = "migration_" + uuid4().hex
    user_id, meeting_id = uuid4(), uuid4()
    cfg = Config(str(BACKEND / "alembic.ini"))
    with api.app.state.test_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'SET LOCAL search_path TO "{schema}", pg_catalog'))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0002")
        conn.execute(text("INSERT INTO users(id,name,email,password_hash) VALUES (:u,'Legacy owner','legacy@example.com','synthetic-unused-hash')"), {"u": user_id})
        conn.execute(text("INSERT INTO meetings(id,owner_id,title,village_name,district,state,meeting_date,primary_language,supported_languages) VALUES (:m,:u,'Legacy','Village','District','State','2026-10-15','te','[\"te\",\"en\"]'::jsonb)"), {"m": meeting_id, "u": user_id})
        conn.execute(text("INSERT INTO transcript_segments(id,meeting_id,speaker_id,language,text,start_time,end_time) VALUES (401,:m,'speaker_1','mixed',:t,0.25,5.75)"), {"m": meeting_id, "t": "నీటి సమస్య — original Unicode ₹15,000."})
        conn.execute(text("INSERT INTO meeting_minutes(id,meeting_id,summary,status,verifier_name,verified_at) VALUES (21,:m,'Legacy verified minutes','verified','Secretary',now())"), {"m": meeting_id})
        conn.execute(text("INSERT INTO decisions(minutes_id,description,status,evidence_segment_ids) VALUES (21,'Allocation','approved','[401]'::jsonb)"))
        before = dict(conn.execute(text("SELECT * FROM transcript_segments WHERE id=401")).mappings().one())
        command.upgrade(cfg, "head")
        after = dict(conn.execute(text("SELECT * FROM transcript_segments WHERE id=401")).mappings().one())
        assert before == after
        preserved = conn.execute(text("SELECT status,verifier_name,review_state FROM meeting_minutes WHERE id=21")).one()
        assert tuple(preserved) == ("verified", "Secretary", "accepted")
        assert conn.scalar(text("SELECT classification FROM decisions WHERE minutes_id=21")) == "approved"
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
