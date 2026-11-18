from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit

from .core import valid_phone


@dataclass(frozen=True)
class Settings:
    api_token: str
    public_url: str
    account_sid: str
    auth_token: str
    from_number: str
    test_number: str
    allowed_origins: tuple[str, ...]
    database: str = "data/happysmile.sqlite3"
    ollama_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = "qwen2.5:7b"
    whisper_model: str = "base"
    enabled: bool = False
    max_seconds: int = 180
    daily_limit: int = 10
    staff_number: str = ""
    amd: bool = True

    @classmethod
    def from_env(cls):
        value = cls(
            api_token=os.environ.get("VOICE_API_TOKEN", ""),
            public_url=os.environ.get("VOICE_PUBLIC_URL", "").rstrip("/"),
            account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
            from_number=os.environ.get("TWILIO_FROM_NUMBER", ""),
            test_number=os.environ.get("DEMO_TO_NUMBER", ""),
            allowed_origins=tuple(x.strip().rstrip("/") for x in os.environ.get("VOICE_ALLOWED_ORIGINS", "").split(",") if x.strip()),
            database=os.environ.get("VOICE_DATABASE", "data/happysmile.sqlite3"),
            ollama_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
            whisper_model=os.environ.get("WHISPER_MODEL", "base"),
            enabled=os.environ.get("LIVE_CALLS_ENABLED", "false").lower() == "true",
            max_seconds=int(os.environ.get("MAX_CALL_SECONDS", "180")),
            daily_limit=int(os.environ.get("MAX_DAILY_CALLS", "10")),
            staff_number=os.environ.get("STAFF_PHONE_NUMBER", ""),
            amd=os.environ.get("TWILIO_AMD_ENABLED", "true").lower() == "true",
        )
        if len(value.api_token) < 32:
            raise ValueError("Set VOICE_API_TOKEN to a random secret of at least 32 characters.")
        if not 30 <= value.max_seconds <= 300 or not 1 <= value.daily_limit <= 30:
            raise ValueError("Use 30–300 seconds per call and 1–30 test calls per day.")
        if value.enabled:
            public = urlsplit(value.public_url)
            if public.scheme != "https" or not public.netloc or public.path not in {"", "/"} or public.query or public.fragment or public.username or public.password:
                raise ValueError("VOICE_PUBLIC_URL must be the public HTTPS origin of this backend.")
            if not re.fullmatch(r"AC[0-9a-fA-F]{32}", value.account_sid) or not value.auth_token:
                raise ValueError("Configure the Twilio account SID and auth token.")
            if not all(valid_phone(p) for p in (value.from_number, value.test_number)):
                raise ValueError("Configure the caller and your own test number in E.164 format.")
            if value.staff_number and not valid_phone(value.staff_number):
                raise ValueError("STAFF_PHONE_NUMBER must be E.164 or empty.")
            if value.staff_number in {value.test_number, value.from_number}:
                raise ValueError("The staff destination must differ from both test and caller numbers.")
            if not value.allowed_origins:
                raise ValueError("Configure the frontend origin in VOICE_ALLOWED_ORIGINS.")
        return value
