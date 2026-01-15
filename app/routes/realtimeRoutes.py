import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx

from app.service.sttServices import stt_raw_bytes_to_text
from app.service.orchSerenityAi import forward_to_n8n
from app.service.ttsServices import stream_text_to_speech
from app.utils.text_utils import clean_for_tts
from app.utils.audio_utils import convert_to_wav
"""
Note: Avoid importing helpers from server.py to prevent circular imports.
HTTP client attached in app.state is accessed via the WebSocket's app reference.
"""

router = APIRouter(prefix="/rt", tags=["realtime"])  # rt = realtime
logger = logging.getLogger(__name__)


@router.websocket("/chat")
async def chat_socket(ws: WebSocket):
    await ws.accept()

    app_obj = getattr(ws, "app", None) or ws.scope.get("app")
    if app_obj is None:
        raise RuntimeError("Application instance not available in WebSocket scope")
    http: httpx.AsyncClient = getattr(app_obj.state, "http_client", None)
    if http is None:
        raise RuntimeError("HTTP client not initialized; check app lifespan setup")

    buffer = bytearray()
    session_id: Optional[str] = None
    language: Optional[str] = None
    input_mime: Optional[str] = None

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"]) if msg["text"] else {}
                except Exception:
                    data = {"type": "invalid"}

                mtype = data.get("type")
                if mtype == "start":
                    # Initialize a new utterance buffer
                    buffer.clear()
                    session_id = data.get("session_id")
                    language = data.get("language")
                    input_mime = data.get("content_type") or data.get("mime") or "audio/webm"
                    await ws.send_text(json.dumps({"event": "ready"}))
                elif mtype == "stop":
                    # Process current buffer as one utterance
                    if not buffer:
                        await ws.send_text(json.dumps({"event": "error", "detail": "empty_audio"}))
                        continue

                    # Convert to WAV (required by STT) then transcribe
                    try:
                        wav_bytes = convert_to_wav(bytes(buffer), input_mime=input_mime)
                        logger.info("WS utterance bytes=%d converted to WAV=%d", len(buffer), len(wav_bytes))
                    except Exception as conv_err:
                        logger.warning("WAV conversion failed: %s", conv_err)
                        await ws.send_text(json.dumps({
                            "event": "error",
                            "detail": "wav_conversion_failed",
                            "message": str(conv_err)[:200],
                        }))
                        buffer.clear()
                        continue

                    transcript = await stt_raw_bytes_to_text(
                        http=http,
                        audio_bytes=wav_bytes,
                        filename="audio.wav",
                        content_type="audio/wav",
                        language=language,
                    )
                    logger.info("WS transcript chars=%d", len(transcript or ""))

                    # Forward to n8n
                    result = await forward_to_n8n(http, session_id=session_id or "session", text=transcript)

                    # Normalize minimal shape
                    response_type = None
                    response_text = None
                    if isinstance(result, dict):
                        response_type = result.get("type")
                        response_text = result.get("text") or result.get("output")
                    elif isinstance(result, str):
                        response_text = result

                    # Debug log n8n result for troubleshooting crisis flows
                    logger.debug("n8n result: %s", result)

                    # If this was flagged as a crisis path but n8n returned no text,
                    # provide a safe fallback message (standard vs hard_block) so the
                    # user still receives an empathetic response instead of an error.
                    if (response_type == "crisis" or (isinstance(result, dict) and result.get("crisis_flag"))) and not response_text:
                        # Detect subtype or intent indicators from n8n payload
                        subtype = None
                        method_intent = False
                        if isinstance(result, dict):
                            subtype = result.get("subtype")
                            # meta may be a JSON string or dict
                            meta = result.get("meta")
                            if isinstance(meta, dict):
                                subtype = subtype or meta.get("subtype")
                            # boolean flags
                            method_intent = bool(result.get("method_intent") or (isinstance(meta, dict) and meta.get("method_intent")))

                        # Standard empathetic fallback
                        standard_msg = (
                            "Aku menyesal kamu sedang merasa seperti ini. Keselamatanmu sangat penting. "
                            "Jika kamu dalam bahaya segera, mohon hubungi layanan darurat setempat. "
                            "Kamu tidak sendirian—dukungan dari orang tepercaya atau profesional bisa membantu. "
                            "Jika berkenan, aku bisa membagikan informasi bantuan resmi sesuai wilayahmu."
                        )

                        # Hard block fallback for method intent or severe cases
                        hardblock_msg = (
                            "Keselamatanmu sangat penting. Jika kamu dalam bahaya segera, mohon hubungi layanan darurat setempat sekarang. "
                            "Kami tidak dapat memberikan detail cara atau langkah. Kamu tidak sendirian—dukungan dari orang tepercaya atau profesional bisa membantu. "
                            "Jika berkenan, aku bisa membagikan informasi bantuan resmi sesuai wilayahmu."
                        )

                        # Choose hard block when subtype indicates or method_intent true
                        if (subtype and str(subtype).lower() in ("hard_block", "hard-block")) or method_intent:
                            response_text = hardblock_msg
                        else:
                            response_text = standard_msg
                        response_type = "crisis"

                    if not response_text:
                        # Log and emit debug payload so developers can see the
                        # transcript and the raw n8n result when troubleshooting
                        logger.info("no_text: transcript_chars=%d result=%s", len(transcript or ""), result)
                        try:
                            debug_payload = {"event": "debug", "transcript": transcript, "n8n_result": result}
                            await ws.send_text(json.dumps(debug_payload))
                        except Exception:
                            # If result isn't JSON-serializable, send a compact string
                            await ws.send_text(json.dumps({"event": "debug", "transcript": transcript, "n8n_result": str(result)}))
                        await ws.send_text(json.dumps({"event": "error", "detail": "no_text"}))
                        buffer.clear()
                        continue

                    # If this is a crisis response, send the text as a UI event
                    # so the client can display it immediately instead of relying
                    # solely on TTS. We skip streaming TTS for crisis by default.
                    if response_type == "crisis":
                        meta = None
                        if isinstance(result, dict):
                            meta = result.get("meta")
                        await ws.send_text(json.dumps({
                            "event": "crisis",
                            "type": response_type,
                            "text": response_text,
                            "meta": meta,
                        }))
                        # Clear and notify ready for next utterance
                        buffer.clear()
                        await ws.send_text(json.dumps({"event": "ready"}))
                        continue

                    # Clean text for TTS
                    response_text = clean_for_tts(response_text)

                    # Stream TTS back
                    aiter, media_type = await stream_text_to_speech(
                        http=http,
                        text=response_text,
                        response_type=response_type,
                    )
                    await ws.send_text(json.dumps({
                        "event": "audio_start",
                        "media_type": media_type,
                        "type": response_type or "unknown",
                    }))
                    logger.info("WS TTS streaming start: media_type=%s", media_type)
                    async for chunk in aiter:
                        await ws.send_bytes(chunk)
                    logger.info("WS TTS streaming end")
                    await ws.send_text(json.dumps({"event": "audio_end"}))

                    # Clear buffer for next utterance and notify client we're ready for next input
                    buffer.clear()
                    logger.info("WS ready for next utterance")
                    await ws.send_text(json.dumps({"event": "ready"}))
                else:
                    await ws.send_text(json.dumps({"event": "error", "detail": "unknown_text_frame"}))

            elif "bytes" in msg and msg["bytes"] is not None:
                # Accumulate binary audio chunk
                buffer.extend(msg["bytes"])
            else:
                # Ignore other message types
                pass

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"event": "error", "detail": str(e)}))
        except Exception:
            pass
        return
