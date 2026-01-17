# SerenityAI — Speech AI Bridge

This repository provides a FastAPI backend that bridges realtime speech-to-text (STT) and text-to-speech (TTS) with an n8n orchestration webhook. It accepts audio via WebSocket or HTTP, transcribes it using ElevenLabs (XI) STT, forwards the text to an n8n webhook for orchestration, and returns TTS audio (or sends crisis UI events).

Contents
- `server.py` — FastAPI app bootstrap and router mounting
- `app/routes` — HTTP and WebSocket routes (STT, TTS, realtime)
- `app/service` — STT/TTS wrappers and orchestration helpers
- `app/utils` — audio conversion (ffmpeg) and text cleaning helpers
- `.env` — runtime configuration (supply API keys and paths)

Requirements
- Python 3.11+ / 3.12 recommended
- Poetry or pip for dependency install (requirements listed in `req.txt`)
- FFmpeg executable available on PATH or configured via `FFMPEG_PATH` in `.env`
- Public/Private hosting for backend with support for persistent WebSockets if you need realtime WS (serverless platforms like Vercel functions do NOT support persistent WS)

Tools you will need
- Python and pip (or a virtualenv)
- FFmpeg (to convert webm/ogg to WAV for STT)
- An ElevenLabs / XI API key (used for STT and TTS)
- n8n running and reachable (or another webhook endpoint that accepts `POST { session_id, text }`)

Environment (.env)
Place a `.env` file at the project root (a template is included). Important variables:
- XI_API_KEY — ElevenLabs API key used for STT/TTS
- ELEVEN_STT_URL — ElevenLabs STT endpoint (default provided)
- ELEVEN_STT_MODEL_ID — STT model id (default: `scribe_v2`)
- ELEVEN_TTS_URL_TMPL — TTS endpoint template (provided)
- ELEVEN_TTS_MODEL_ID — TTS model id (default set)
- DEFAULT_VOICE_ID — fallback voice id for TTS
- N8N_WEBHOOK_URL — n8n webhook URL (e.g., `http://localhost:5678/webhook/serenity/input`)
- N8N_INTERNAL_TOKEN — optional header token for n8n
- FFMPEG_PATH — optional full path to ffmpeg executable if not on PATH
- FFMPEG_BIN — optional alternative env var for ffmpeg path
- CORS_ORIGINS — comma-separated list of allowed origins (frontend)
- MAX_UPLOAD_MB — restrict upload size

Install & run (development)
1. Create and activate a virtualenv (Windows example):

```powershell
python -m venv env
env\Scripts\activate
pip install -r req.txt
```

2. Fill `.env` with your XI API key, n8n URL, and optionally `FFMPEG_PATH`.
3. Start the app with Uvicorn:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

If using Windows and ffmpeg isn't on PATH, set `FFMPEG_PATH=C:\\path\\to\\ffmpeg.exe` in `.env`.

FFmpeg installation notes
- Windows: download a static build from https://ffmpeg.org/download.html or via chocolatey/scoop. Add `ffmpeg.exe` to PATH or set `FFMPEG_PATH`.
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg` (or use your distro's package manager)

WebSocket realtime protocol (quick)
- Endpoint: `wss://<HOST>/api/v1/rt/chat` (use `wss` on HTTPS pages)
- Client protocol:
  1. Send: `{"type": "start", "session_id": "<id>", "content_type": "audio/webm", "language": "id"}`
  2. Send binary frames (Blob chunks) in chronological order (the server will append in order).
  3. Send: `{"type": "stop"}` to indicate end of utterance.
- Server events (JSON text frames):
  - `{"event":"ready"}` — server ready for audio
  - `{"event":"audio_start","media_type":"audio/mpeg","type":"chat"}` — TTS audio incoming
  - binary frames for audio
  - `{"event":"audio_end"}` — TTS finished
  - `{"event":"crisis","type":"crisis","text":"...","meta":{...}}` — UI-only crisis event (no TTS)
  - `{"event":"error","detail":"..."}` — errors
  - `{"event":"debug","transcript":...,"n8n_result":...}` — debug info (on no_text)

HTTP endpoints (main)
- POST `/api/v1/stt` — upload `audio` file (multipart) to transcribe
- POST `/api/v1/stt-chat` — upload `audio` + `session_id` to STT → n8n → respond with JSON chat shape
- POST `/api/v1/tts/...` — several tts endpoints under `/api/v1/tts` for combined STT→chat→TTS and streaming variants
- Health endpoints under `/api/v1/health` (see `app/routes/healthRoutes.py`)

n8n integration notes
- The server forwards `POST { session_id, text }` to `N8N_WEBHOOK_URL` and expects a structured response. Common n8n shapes handled by the server:
  - Direct dict with keys `text`, `type`, `crisis_flag`, and `meta`.
  - `[{ "json": { ... } }]` (n8n execution array) — server will extract `json`.
  - `keepOnlySet/values` shaped responses — server normalizes to a flat dict.

Troubleshooting
- Mixed content / invalid WS: if frontend is on HTTPS (e.g., Vercel), use `wss://` and ensure backend has a valid TLS certificate. Browsers block `ws://` from `https://` pages.
- Partial/corrupt audio: ensure client sends chunks in chronological order and sends a final `stop` only after the last chunk is appended. Add a small delay (30–100ms) after last chunk if needed.
- FFmpeg missing: server will report conversion failure; install ffmpeg and/or populate `FFMPEG_PATH`.

Testing
- To test STT-only via HTTP:
```bash
curl -F "audio=@path/to/file.webm" -F "language=id" http://localhost:8000/api/v1/stt # or postman
```
- To test n8n webhook mapping, `curl` a sample payload to `N8N_WEBHOOK_URL` and inspect the output shape.
- Use `wscat` to test the websocket endpoint:
```bash
npm i -g wscat
wscat -c "wss://your.backend.domain/api/v1/rt/chat"
```

Development notes
- Shared `httpx.AsyncClient` is attached to `app.state.http_client` during the FastAPI lifespan. WebSocket handlers access it via `ws.app.state.http_client`.
- Logs are helpful: watch for "WS utterance bytes", "WS transcript chars", and "n8n result" messages.

Security
- Never commit real API keys to the repository. Use environment variables or a secrets manager in production.
- If exposing the n8n webhook publicly, protect it with `N8N_INTERNAL_TOKEN` or other auth in n8n.

If you want, I can also:
- Add a minimal example frontend (`index.html`) that implements the WS protocol (start/chunk/stop) and the `crisis` modal handler.
- Provide an nginx TLS + ws proxy example for deployment.

---
README generated by the project assistant. If you want a shorter quickstart or extra deployment guides (Docker, systemd, nginx), tell me which target and I will add it.