"""Prisma v3 Batch adapter, verified against gnani-vachana 0.9.0.

No calls at import/construction. Never use transcribe()/wait() in a request.
Raw documented transcript fields are used rather than SDK convenience defaults.
"""
import inspect

from gnani.stt import GnaniSTTBatchClient

from app import schemas

MODEL = "prisma-v3.0"
OUTPUT_FORMAT = "codemix"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # Same bound as SDK BATCH_MAX_FILE_BYTES.
LANGUAGES = {"en-IN": "en", "te-IN": "te", "kn-IN": "kn", "hi-IN": "hi"}


class ProviderContractError(ValueError):
    pass


def make_client(api_key):
    required = {"model", "format", "diarization", "start"}
    if not required.issubset(inspect.signature(GnaniSTTBatchClient.create_job).parameters):
        raise RuntimeError("Unsupported SDK: required Prisma v3 Batch options are missing; install requirements.txt")
    return GnaniSTTBatchClient(api_key=api_key, timeout=30, upload_timeout=120)


def normalize_transcript(document, job_id, provider_job_id):
    """Keep provider data separately; do not guess timestamps or languages.

    Blank/silence entries stay in the raw document, not the nonblank transcript
    table. Non-core languages retain their exact tag alongside language=mixed.
    Source position, not provider segment_id (which may repeat), deduplicates.
    """
    if (document.get("model") != MODEL or document.get("job_id") != provider_job_id
            or not isinstance(document.get("segments"), list)):
        raise ProviderContractError("Unexpected transcript document")
    segments, warnings = [], []
    for index, item in enumerate(document["segments"]):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ProviderContractError("Missing segment text")
        if not item["text"].strip():
            warnings.append({"source_index": index, "code": "silence_not_imported"})
            continue
        detected = item.get("language_detected")
        speaker = item.get("speaker_id")
        if detected is not None and (not isinstance(detected, str) or len(detected) > 64):
            raise ProviderContractError("Invalid language tag")
        if speaker is not None and (type(speaker) is not int or not -(2**31) <= speaker < 2**31):
            raise ProviderContractError("Invalid speaker label")
        if detected not in LANGUAGES:
            warnings.append({"source_index": index, "code": "language_not_in_core_enum", "detected_language": detected})
        anonymous = f"speaker_{speaker}" if speaker is not None and speaker >= 0 else "speaker_unknown"
        validated = schemas.SegmentCreate(
            speaker_id=f"gnani_{job_id}_{anonymous}",
            language=LANGUAGES.get(detected, "mixed"),
            text=item["text"], start_time=item["start_time"], end_time=item["end_time"],
        )
        segments.append({**validated.model_dump(), "transcription_job_id": job_id,
                         "source_index": index, "detected_language": detected,
                         "provider_speaker_id": speaker})
    if not segments:
        raise ProviderContractError("No speech segments to import")
    return segments, warnings
