from typing import Optional
import time
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Response, Request
from app.service.sttServices import stt_bytes_to_text
from app.service.orchSerenityAi import forward_to_n8n
from app.service.ttsServices import text_to_speech, stream_text_to_speech
from fastapi.responses import StreamingResponse
from app.utils.text_utils import clean_for_tts

router = APIRouter(prefix="/tts", tags=["tts"])


def _normalize_n8n_result(data):
    """Normalize various n8n response shapes into a dict with keys: text, type, crisis_flag, meta.
    Accepts direct dict, {json: {...}}, {body: {...}}, or a list wrapping those.
    """
    import re

    # Unwrap list
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        if "json" in data and isinstance(data["json"], dict):
            data = data["json"]
        elif "body" in data and isinstance(data["body"], dict):
            data = data["body"]

    result = {"text": None, "type": None, "crisis_flag": None, "meta": {}}
    if isinstance(data, dict):
        result["text"] = data.get("text") or data.get("output") or data.get("response")
        result["type"] = data.get("type")
        result["crisis_flag"] = data.get("crisis_flag")
        meta = data.get("meta")
        if isinstance(meta, dict):
            result["meta"] = meta
    elif isinstance(data, str):
        result["text"] = data

    # Fallback: parse [[type:...]] tag from text
    if result["text"] and not result["type"]:
        m = re.search(r"\[\[type:([a-zA-Z0-9_\-]+)\]\]", result["text"]) 
        if m:
            result["type"] = m.group(1)
            result["text"] = re.sub(r"\[\[type:[a-zA-Z0-9_\-]+\]\]", "", result["text"]).strip()

    return result


@router.post("/stt-chat-tts")
async def stt_chat_tts(
    request: Request,
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    language: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
):
    http = request.app.state.http_client

    t0 = time.perf_counter()
    # STT
    upload = file or audio
    if upload is None:
        raise HTTPException(422, "Missing file upload: provide 'file' or 'audio' field")
    text = await stt_bytes_to_text(http, upload, language)
    t_stt = time.perf_counter()

    # Forward to n8n for chat orchestration
    if not session_id:
        raise HTTPException(400, "session_id is required")
    n8n_result = await forward_to_n8n(http, session_id=session_id, text=text)
    t_chat = time.perf_counter()

    # Normalize n8n result into common shape
    normalized = _normalize_n8n_result(n8n_result)
    response_type = normalized.get("type")
    response_text = normalized.get("text")
    crisis_flag = normalized.get("crisis_flag")

    # Clean text for TTS (remove markdown, tags, tidy punctuation)
    if response_text:
        response_text = clean_for_tts(response_text)

    if not response_text:
        raise HTTPException(502, "n8n did not return text")

    # TTS
    audio_bytes, media_type = await text_to_speech(
        http=http,
        text=response_text,
        response_type=response_type,
    )
    t_tts = time.perf_counter()

    # Add simple timing headers
    headers = {
        "X-Perf-STT-ms": str(int((t_stt - t0) * 1000)),
        "X-Perf-CHAT-ms": str(int((t_chat - t_stt) * 1000)),
        "X-Perf-TTS-ms": str(int((t_tts - t_chat) * 1000)),
        "X-Chat-Type": (response_type or "unknown"),
        "X-Chat-Crisis": str(bool(crisis_flag)),
        "X-Chat-Text-Len": str(len(response_text or "")),
    }

    return Response(content=audio_bytes, media_type=media_type, headers=headers)


@router.post("/stt-chat-tts-stream")
async def stt_chat_tts_stream(
    request: Request,
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    language: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
):
    """
    Streaming variant: STT -> n8n -> stream TTS audio to client.
    Use when you want the audio to start playing sooner.
    """
    http = request.app.state.http_client

    # STT
    upload = file or audio
    if upload is None:
        raise HTTPException(422, "Missing file upload: provide 'file' or 'audio' field")
    text = await stt_bytes_to_text(http, upload, language)

    # Forward to n8n
    if not session_id:
        raise HTTPException(400, "session_id is required")
    n8n_result = await forward_to_n8n(http, session_id=session_id, text=text)

    # Normalize and clean text
    normalized = _normalize_n8n_result(n8n_result)
    response_type = normalized.get("type")
    response_text = normalized.get("text")
    if not response_text:
        raise HTTPException(502, "n8n did not return text")
    response_text = clean_for_tts(response_text)

    # Stream TTS audio
    aiter, media_type = await stream_text_to_speech(
        http=http,
        text=response_text,
        response_type=response_type,
    )

    return StreamingResponse(aiter, media_type=media_type)
