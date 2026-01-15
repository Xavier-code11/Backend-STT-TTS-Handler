from fastapi import UploadFile, HTTPException
import httpx
from app.core.config import settings
from app.utils.audio_utils import convert_to_wav

async def stt_bytes_to_text(http: httpx.AsyncClient, audio: UploadFile, language: str | None) -> str:
    if not settings.XI_API_KEY:
        raise HTTPException(500, "XI_API_KEY not set")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio")
    max_bytes = int(settings.MAX_UPLOAD_MB * 1024 * 1024)
    if len(audio_bytes) > max_bytes:
        raise HTTPException(400, f"Audio exceeds max size of {settings.MAX_UPLOAD_MB} MB")
    # Convert to WAV if needed
    input_mime = (audio.content_type or "").split(";")[0].lower() if audio.content_type else None
    try:
        if input_mime not in {"audio/wav", "audio/x-wav", "audio/wave"}:
            audio_bytes = convert_to_wav(audio_bytes, input_mime)
            input_mime = "audio/wav"
    except Exception as e:
        raise HTTPException(400, f"WAV conversion failed: {e}")

    files = {
        "file": (audio.filename or "audio.wav", audio_bytes, input_mime or "audio/wav"),
    }
    data = {"model_id": settings.ELEVEN_STT_MODEL_ID}
    if language:
        data["language_code"] = language

    headers = {
        "xi-api-key": settings.XI_API_KEY,
        "accept": "application/json",
    }

    resp = await http.post(settings.ELEVEN_STT_URL, files=files, data=data, headers=headers)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)

    try:
        result = resp.json()
    except Exception:
        raise HTTPException(502, "Invalid STT provider response")

    transcript = result.get("text", "")
    if not transcript:
        raise HTTPException(400, "No transcript text produced")
    return transcript


async def stt_raw_bytes_to_text(
    http: httpx.AsyncClient,
    audio_bytes: bytes,
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
    language: str | None = None,
) -> str:
    """Transcribe raw bytes (for WebSocket or other binary sources)."""
    if not settings.XI_API_KEY:
        raise HTTPException(500, "XI_API_KEY not set")

    if not audio_bytes:
        raise HTTPException(400, "Empty audio")
    max_bytes = int(settings.MAX_UPLOAD_MB * 1024 * 1024)
    if len(audio_bytes) > max_bytes:
        raise HTTPException(400, f"Audio exceeds max size of {settings.MAX_UPLOAD_MB} MB")

    files = {
        "file": (filename, audio_bytes, content_type or "application/octet-stream"),
    }
    data = {"model_id": settings.ELEVEN_STT_MODEL_ID}
    if language:
        data["language_code"] = language

    headers = {
        "xi-api-key": settings.XI_API_KEY,
        "accept": "application/json",
    }

    resp = await http.post(settings.ELEVEN_STT_URL, files=files, data=data, headers=headers)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)

    try:
        result = resp.json()
    except Exception:
        raise HTTPException(502, "Invalid STT provider response")

    transcript = result.get("text", "")
    if not transcript:
        raise HTTPException(400, "No transcript text produced")
    return transcript