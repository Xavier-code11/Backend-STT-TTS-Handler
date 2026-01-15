from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    XI_API_KEY: str = Field(default="", description="ElevenLabs API key")
    ELEVEN_STT_URL: str = Field(default="https://api.elevenlabs.io/v1/speech-to-text")
    ELEVEN_STT_MODEL_ID: str = Field(default="scribe_v2", description="ElevenLabs STT model id (e.g., scribe_v2 or scribe_v2_multilingual)")
    ELEVEN_TTS_URL_TMPL: str = Field(default="https://api.elevenlabs.io/v1/text-to-speech/{voice_id}")
    ELEVEN_TTS_MODEL_ID: str = Field(default="eleven_multilingual_v2")
    # Optional voice mappings by response type
    VOICE_ID_EMPATHIC: str = Field(default="", description="Voice ID for empathic responses")
    VOICE_ID_NEUTRAL: str = Field(default="", description="Voice ID for neutral responses")
    VOICE_ID_ALERT: str = Field(default="", description="Voice ID for alert/urgent responses")
    VOICE_ID_CRISIS: str = Field(default="", description="Voice ID for crisis assistance responses")
    N8N_WEBHOOK_URL: str = Field(default="", description="n8n webhook URL")
    N8N_INTERNAL_TOKEN: str = Field(default="", description="Internal header for n8n (optional)")
    HTTP_TIMEOUT_S: float = Field(default=30.0)
    DEFAULT_VOICE_ID: str = Field(default="YOUR_DEFAULT_VOICE_ID")
    DEFAULT_TTS_FORMAT: str = Field(default="mp3_44100_128")
    MAX_UPLOAD_MB: int = Field(default=10, description="Max upload size in megabytes")
    CORS_ORIGINS: List[str] = []

    # Optional: FFmpeg path/binary override for audio conversion
    FFMPEG_PATH: str = Field(default="", description="Absolute path to ffmpeg executable (e.g., C\\ffmpeg\\bin\\ffmpeg.exe)")
    FFMPEG_BIN: str = Field(default="", description="Alternative env name for ffmpeg executable path")

    # pydantic v2 uses SettingsConfigDict for settings configuration
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()