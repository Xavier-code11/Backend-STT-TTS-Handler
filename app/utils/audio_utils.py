import io
import os
import subprocess
import tempfile
import uuid
from typing import Optional
from app.core.config import settings


_MIME_EXT = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}


def _ext_for_mime(mime: Optional[str]) -> str:
    if not mime:
        return ".bin"
    return _MIME_EXT.get(mime.split(";")[0].strip().lower(), ".bin")


def _get_ffmpeg_bin() -> str:
    """Resolve ffmpeg executable path from environment variables or PATH."""
    # Prefer app settings from .env
    for val in (settings.FFMPEG_PATH, settings.FFMPEG_BIN):
        if val and val.strip():
            return val.strip().strip('"')
    # Fallback explicit env vars if provided
    for key in ("FFMPEG_PATH", "FFMPEG_BIN"):
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip().strip('"')
    # Fallback to system PATH
    return "ffmpeg"


def _sniff_mime(data: bytes) -> Optional[str]:
    """Best-effort container/format sniffing from magic bytes.
    Returns one of: 'audio/wav', 'audio/ogg', 'audio/mpeg', 'audio/webm', or None.
    """
    if not data or len(data) < 4:
        return None
    head4 = data[:4]
    head3 = data[:3]
    # WAV/RIFF
    if head4 == b"RIFF":
        return "audio/wav"
    # OGG
    if head4 == b"OggS":
        return "audio/ogg"
    # MP3 (ID3) or frame sync
    if head3 == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    # WebM/Matroska EBML signature
    if head4 == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        return "audio/webm"
    return None


def convert_to_wav(
    audio_bytes: bytes,
    input_mime: Optional[str] = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> bytes:
    """
    Convert arbitrary audio bytes (e.g., webm/ogg/mp3) to WAV using ffmpeg.
    Requires ffmpeg binary available in PATH. Raises RuntimeError on failure.
    """
    if not audio_bytes:
        raise RuntimeError("Empty audio bytes")

    # If caller already knows it's WAV, just return as-is
    if input_mime and input_mime.split(";")[0].strip().lower() in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return audio_bytes

    # Prefer sniffed mime if provided value seems wrong or missing
    sniffed = _sniff_mime(audio_bytes)
    if sniffed and (not input_mime or sniffed.split(";")[0].lower() != input_mime.split(";")[0].lower()):
        input_mime = sniffed

    in_ext = _ext_for_mime(input_mime)
    # Write input to a temp file and close it (Windows requires closed handle for external processes)
    with tempfile.NamedTemporaryFile(delete=False, suffix=in_ext) as f_in:
        f_in.write(audio_bytes)
        in_path = f_in.name

    # Create a unique output path without pre-creating the file to avoid Windows locking issues
    out_path = os.path.join(tempfile.gettempdir(), f"aud_{uuid.uuid4().hex}.wav")
    try:
        def run_ffmpeg(force_fmt: Optional[str] = None) -> subprocess.CompletedProcess:
            cmd = [
                _get_ffmpeg_bin(),
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
            ]
            if force_fmt:
                cmd += ["-f", force_fmt]
            cmd += [
                "-i", in_path,
                "-vn",
                "-ac", str(channels),
                "-ar", str(sample_rate),
                "-f", "wav",
                out_path,
            ]
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Try sequence: sniffed format first, then common fallbacks, then auto-detect
        fmt_map = {
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
        }
        tries = []
        if input_mime and input_mime in fmt_map:
            tries.append(fmt_map[input_mime])
        # Add common fallbacks
        for f in ("webm", "ogg", "mp3"):
            if f not in tries:
                tries.append(f)

        proc = None
        for f in tries:
            proc = run_ffmpeg(force_fmt=f)
            if proc.returncode == 0 and os.path.exists(out_path):
                break
        if not proc or proc.returncode != 0 or (not os.path.exists(out_path)):
            # Final retry with auto-detect (no forced format)
            proc = run_ffmpeg(force_fmt=None)
        if proc.returncode != 0 or (not os.path.exists(out_path)):
            raise RuntimeError(
                f"ffmpeg failed: code={proc.returncode}, stderr={(proc.stderr or b'').decode(errors='ignore')[:800]}"
            )

        # Read the produced WAV bytes
        with open(out_path, "rb") as f:
            data = f.read()
        if not data:
            raise RuntimeError("ffmpeg produced empty output")
        return data
    finally:
        try:
            os.remove(in_path)
        except Exception:
            pass
        if out_path and os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
