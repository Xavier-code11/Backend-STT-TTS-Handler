from typing import Optional, Tuple
import httpx
from fastapi import HTTPException
from app.core.config import settings


_TYPE_TO_VOICE_ENV = {
    "empathic": "VOICE_ID_EMPATHIC",
    "neutral": "VOICE_ID_NEUTRAL",
    "alert": "VOICE_ID_ALERT",
    "crisis": "VOICE_ID_CRISIS",
}


def _voice_for_type(response_type: Optional[str]) -> str:
    """Pick voice_id from settings based on response type; fallback to DEFAULT_VOICE_ID."""
    if response_type:
        key = _TYPE_TO_VOICE_ENV.get(response_type.lower())
        if key:
            voice_id = getattr(settings, key, "")
            if voice_id:
                return voice_id
    return settings.DEFAULT_VOICE_ID


def _media_type_for_format(fmt: str) -> str:
    fmt = (fmt or "").lower()
    if fmt.startswith("mp3_") or fmt == "mp3":
        return "audio/mpeg"
    if fmt.startswith("ogg_") or fmt == "ogg":
        return "audio/ogg"
    if fmt.startswith("wav_") or fmt == "wav":
        return "audio/wav"
    # default
    return "audio/mpeg"


async def text_to_speech(
    http: httpx.AsyncClient,
    text: str,
    response_type: Optional[str] = None,
    voice_id: Optional[str] = None,
    output_format: Optional[str] = None,
) -> Tuple[bytes, str]:
    if not settings.XI_API_KEY:
        raise HTTPException(500, "XI_API_KEY not set")
    if not text or not text.strip():
        raise HTTPException(400, "Text is empty")

    chosen_voice = (voice_id or _voice_for_type(response_type) or settings.DEFAULT_VOICE_ID).strip()
    if not chosen_voice:
        raise HTTPException(500, "No voice_id available (DEFAULT_VOICE_ID not set)")
    fmt = (output_format or settings.DEFAULT_TTS_FORMAT or "mp3_44100_128").strip()
    url_base = settings.ELEVEN_TTS_URL_TMPL.format(voice_id=chosen_voice)
    url = f"{url_base}/stream"

    headers = {
        "xi-api-key": settings.XI_API_KEY,
        "accept": "*/*",
    }
    params = {"output_format": fmt}
    json_body = {
        "text": text,
        "model_id": settings.ELEVEN_TTS_MODEL_ID,
    }

    resp = await http.post(url, headers=headers, params=params, json=json_body)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)

    audio_bytes = resp.content
    media_type = _media_type_for_format(fmt)
    return audio_bytes, media_type


async def stream_text_to_speech(
    http: httpx.AsyncClient,
    text: str,
    response_type: Optional[str] = None,
    voice_id: Optional[str] = None,
    output_format: Optional[str] = None,
):
    """
    Stream audio bytes from ElevenLabs TTS so the client can start playback earlier.

    Returns: (async iterator of bytes, media_type)
    """
    if not settings.XI_API_KEY:
        raise HTTPException(500, "XI_API_KEY not set")
    if not text or not text.strip():
        raise HTTPException(400, "Text is empty")

    chosen_voice = (voice_id or _voice_for_type(response_type) or settings.DEFAULT_VOICE_ID).strip()
    if not chosen_voice:
        raise HTTPException(500, "No voice_id available (DEFAULT_VOICE_ID not set)")
    fmt = (output_format or settings.DEFAULT_TTS_FORMAT or "mp3_44100_128").strip()

    url_base = settings.ELEVEN_TTS_URL_TMPL.format(voice_id=chosen_voice)
    url = f"{url_base}/stream"

    headers = {
        "xi-api-key": settings.XI_API_KEY,
        "accept": "*/*",
    }
    params = {"output_format": fmt}
    json_body = {
        "text": text,
        "model_id": settings.ELEVEN_TTS_MODEL_ID,
    }

    async def _aiter():
        # Open streaming response within generator so the response context stays alive
        async with http.stream("POST", url, headers=headers, params=params, json=json_body) as resp:
            if resp.status_code >= 400:
                detail = await resp.aread()
                raise HTTPException(resp.status_code, detail.decode(errors="ignore"))
            async for chunk in resp.aiter_bytes():
                yield chunk

    media_type = _media_type_for_format(fmt)
    return _aiter(), media_type
