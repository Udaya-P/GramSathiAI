"""Private originals on an API-host volume, separate from the worker's queue."""
import os
from stat import S_ISREG
from tempfile import NamedTemporaryFile

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings


def _path(job):
    return get_settings().audio_storage_dir / str(job.meeting_id) / f"{job.id}.m4a"


def retain(job, audio: bytes):
    path = _path(job)
    temporary = None
    try:
        if path.is_file():
            return
        path.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = output.name
            output.write(audio)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise HTTPException(503, "Recording storage is temporarily unavailable") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def playback(job):
    path = _path(job)
    try:
        metadata = path.stat()
    except FileNotFoundError:
        raise HTTPException(404, "Original recording is unavailable",
                            headers={"Cache-Control": "private, no-store"}) from None
    except OSError:
        raise HTTPException(503, "Recording storage is temporarily unavailable") from None
    if not S_ISREG(metadata.st_mode):
        raise HTTPException(503, "Recording storage is temporarily unavailable")
    return FileResponse(path, stat_result=metadata, media_type="audio/mp4",
                        headers={"Cache-Control": "private, no-store"})
