from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi import HTTPException
from app.schema.schema import STTResponse, ChatResponse
from app.service.sttServices import stt_bytes_to_text
from app.service.orchSerenityAi import forward_to_n8n

router = APIRouter(tags=["stt"])

@router.post("/stt", response_model=STTResponse)
async def stt_only(request: Request, audio: UploadFile = File(...), language: str | None = Form(None)):
    http = request.app.state.http_client
    transcript = await stt_bytes_to_text(http, audio, language)
    return STTResponse(transcript=transcript)

@router.post("/stt-chat", response_model=ChatResponse)
async def stt_then_chat(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    language: str | None = Form(None),
):
    http = request.app.state.http_client
    transcript = await stt_bytes_to_text(http, audio, language)
    result = await forward_to_n8n(http, session_id, transcript)
    if "type" in result and "text" in result:
        return ChatResponse(
            type=result["type"],
            text=result["text"],
            crisis_flag=result.get("crisis_flag"),
            meta=result.get("meta"),
        )
    if isinstance(result, dict) and "output" in result and isinstance(result["output"], str):
        raw = result["output"]
        parsed_type = "chat"
        text = raw
        import re
        m = re.search(r"\[\[type:([a-zA-Z0-9_\-]+)\]\]", raw)
        if m:
            parsed_type = m.group(1)
            text = re.sub(r"\[\[type:[a-zA-Z0-9_\-]+\]\]", "", raw).strip()
        return ChatResponse(
            type=parsed_type,
            text=text,
            crisis_flag=result.get("crisis_flag"),
            meta=result.get("meta"),
        )
    # If shape differs, bubble raw for debugging
    raise HTTPException(502, f"Unexpected n8n response shape: {result}")