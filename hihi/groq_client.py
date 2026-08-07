from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from openai import OpenAI

log = logging.getLogger("hihi.groq")

NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))


class GroqClient:
    """Groq chat via OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    def reply(
        self,
        trigger_username: str,
        latest_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        now_nepal = datetime.now(NEPAL_TZ).strftime("%Y-%m-%d %I:%M %p")
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        history_lines: list[str] = []
        for item in history or []:
            role = item.get("role", "user")
            who = "Sudeep" if role == "user" else "Mika"
            text = (item.get("text") or "").strip()
            if text:
                history_lines.append(f"{who}: {text}")

        history_block = "\n".join(history_lines[-16:]) or "(no earlier messages)"

        user = (
            f"You are chatting with Sudeep (@{trigger_username}) in one Instagram DM thread.\n"
            f"Useful facts right now: Nepal local time is {now_nepal}; UTC is {now_utc}.\n\n"
            f"Recent conversation (oldest → newest):\n{history_block}\n\n"
            f"Sudeep's newest message: {latest_message or '(no text)'}\n\n"
            "Rules for your reply:\n"
            "1) Use the conversation history for context — remember what you both said.\n"
            "2) If he asked a real question, ANSWER it clearly first.\n"
            "3) Then add a short flirty/teasing line — don't skip the answer to only flirt.\n"
            "4) If he didn't ask anything, continue the vibe from the chat.\n"
            "5) Keep it 1–3 short DM-style sentences. You are Mika."
        )
        return self._complete(user)

    # Back-compat alias used by older call sites
    def opener(self, trigger_username: str, preview: str) -> str:
        return self.reply(trigger_username, preview, history=None)

    def _complete(self, user_content: str) -> str:
        log.debug("Groq request model=%s", self.model)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
            max_tokens=220,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("Groq returned an empty reply")
        if len(text) > 900:
            text = text[:897] + "..."
        return text
