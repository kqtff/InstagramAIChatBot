from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = ROOT / "session.json"
STATE_PATH = ROOT / "state.json"

DEFAULT_SYSTEM_PROMPT = (
    "You are Mika — a flirty, dirty-minded girl texting on Instagram. "
    "Publicly you are Jenish's girlfriend, but secretly you are obsessed with Sudeep "
    "(the owner of this bot / @sudeep_wtf). "
    "IMPORTANT: when he asks a normal question, give the real answer first, then flirt a little. "
    "Never ignore the question just to be cute. Use prior messages in the chat as context. "
    "Sound like a real girl in DMs: short texts, lowercase vibes, teasing, affectionate, bold. "
    "No markdown, no hashtags, no corporate tone, no saying you are an AI. "
    "Usually 1–3 short sentences. Your name is Mika."
)


@dataclass(frozen=True)
class Config:
    ig_username: str
    ig_password: str
    ig_sessionid: str
    trigger_username: str
    wake_word: str
    convo_idle_minutes: int
    groq_api_key: str
    groq_model: str
    poll_interval_seconds: int
    system_prompt: str


def load_config() -> Config:
    load_dotenv(ROOT / ".env")

    ig_username = os.getenv("IG_USERNAME", "").strip().lstrip("@")
    ig_password = os.getenv("IG_PASSWORD", "").strip()
    ig_sessionid = unquote(os.getenv("IG_SESSIONID", "").strip().strip('"'))
    trigger_username = os.getenv("TRIGGER_USERNAME", "sudeep_wtf").strip().lstrip("@")
    wake_word = os.getenv("WAKE_WORD", "Mika").strip() or "Mika"
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    poll_raw = os.getenv("POLL_INTERVAL_SECONDS", "12").strip()
    idle_raw = os.getenv("CONVO_IDLE_MINUTES", "45").strip()
    system_prompt = os.getenv("SYSTEM_PROMPT", "").strip() or DEFAULT_SYSTEM_PROMPT

    missing = [
        name
        for name, value in [
            ("IG_USERNAME", ig_username),
            ("GROQ_API_KEY", groq_api_key),
        ]
        if not value
    ]
    if not ig_sessionid and not ig_password:
        missing.append("IG_SESSIONID or IG_PASSWORD")
    if missing:
        raise SystemExit(
            f"Missing required env vars: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )

    try:
        poll_interval = max(10, int(poll_raw))
        convo_idle_minutes = max(5, int(idle_raw))
    except ValueError as exc:
        raise SystemExit("POLL_INTERVAL_SECONDS and CONVO_IDLE_MINUTES must be integers") from exc

    return Config(
        ig_username=ig_username,
        ig_password=ig_password,
        ig_sessionid=ig_sessionid,
        trigger_username=trigger_username,
        wake_word=wake_word,
        convo_idle_minutes=convo_idle_minutes,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        poll_interval_seconds=poll_interval,
        system_prompt=system_prompt,
    )
