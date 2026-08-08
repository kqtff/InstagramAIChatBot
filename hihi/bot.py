from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from hihi.config import Config, STATE_PATH
from hihi.groq_client import GroqClient
from hihi.instagram import InstagramSession, TagEvent

log = logging.getLogger("hihi.bot")


class StateStore:
    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        self.data: dict[str, Any] = {
            "handled_events": [],
            "handled_messages": [],
            "active_threads": {},  # thread_id -> last_activity_unix
        }
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
                self.data.setdefault("handled_events", [])
                self.data.setdefault("handled_messages", [])
                self.data.setdefault("active_threads", {})
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read state file (%s); starting fresh", exc)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def seen_event(self, event_id: str) -> bool:
        return event_id in self.data.get("handled_events", [])

    def mark_event(self, event_id: str) -> None:
        handled = list(self.data.get("handled_events", []))
        if event_id not in handled:
            handled.append(event_id)
        self.data["handled_events"] = handled[-500:]
        self.save()

    def seen_message(self, message_id: str) -> bool:
        return message_id in self.data.get("handled_messages", [])

    def mark_message(self, message_id: str) -> None:
        handled = list(self.data.get("handled_messages", []))
        if message_id not in handled:
            handled.append(message_id)
        self.data["handled_messages"] = handled[-1000:]
        self.save()

    def touch_thread(self, thread_id: str) -> None:
        active = dict(self.data.get("active_threads") or {})
        active[thread_id] = time.time()
        self.data["active_threads"] = active
        self.save()

    def is_thread_active(self, thread_id: str, idle_minutes: int) -> bool:
        active = self.data.get("active_threads") or {}
        last = active.get(thread_id)
        if last is None:
            return False
        return (time.time() - float(last)) <= idle_minutes * 60


class Bot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.ig = InstagramSession(
            username=config.ig_username,
            trigger_username=config.trigger_username,
            sessionid=config.ig_sessionid,
        )
        self.llm = GroqClient(
            api_key=config.groq_api_key,
            model=config.groq_model,
            system_prompt=config.system_prompt,
        )
        self.state = StateStore()
        self._wake_re = re.compile(
            rf"\b{re.escape(config.wake_word)}\b",
            re.IGNORECASE,
        )

    def start(self) -> None:
        self.ig.login()
        self._bootstrap_seen()
        log.info(
            "Watching for wake word '%s' from @%s (poll every %ss, convo idle %s min)",
            self.config.wake_word,
            self.config.trigger_username,
            self.config.poll_interval_seconds,
            self.config.convo_idle_minutes,
        )
        while True:
            started = time.monotonic()
            try:
                self.tick()
            except KeyboardInterrupt:
                log.info("Stopped by user")
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("Tick failed: %s", exc)
            elapsed = time.monotonic() - started
            sleep_for = max(0.0, self.config.poll_interval_seconds - elapsed)
            time.sleep(sleep_for)

    def _contains_wake_word(self, text: str) -> bool:
        return bool(self._wake_re.search(text or ""))

    def _bootstrap_seen(self) -> None:
        """Mark old noise as seen; leave pending wake-word / active-thread msgs."""
        for event in self.ig.find_tag_events():
            self.state.mark_event(event.event_id)

        pending = 0
        for msg in self.ig.fetch_trigger_dms():
            wake = self._contains_wake_word(msg.text)
            active = self.state.is_thread_active(
                msg.thread_id, self.config.convo_idle_minutes
            )
            if wake or active:
                pending += 1
                continue
            self.state.mark_message(msg.message_id)

        log.info(
            "Bootstrapped (%s tag events seen, %s pending wake/active DMs)",
            len(self.state.data.get("handled_events", [])),
            pending,
        )

    def tick(self) -> None:
        self._handle_new_tags()
        self._handle_dms()

    def _handle_new_tags(self) -> None:
        # Photo/activity tags still open a chat (rare if accounts have no posts)
        events = self.ig.find_tag_events()
        for event in events:
            if self.state.seen_event(event.event_id):
                continue
            self._send_tag_reply(event.event_id, event.preview, kind=event.kind)

    def _handle_dms(self) -> None:
        """
        Reply when:
        - message contains wake word 'Mika', OR
        - thread is already an active conversation (follow-ups keep context)
        """
        for msg in reversed(self.ig.fetch_trigger_dms()):
            if self.state.seen_message(msg.message_id):
                continue

            text = msg.text or ""
            wake = self._contains_wake_word(text)
            active = self.state.is_thread_active(
                msg.thread_id, self.config.convo_idle_minutes
            )

            if not wake and not active:
                self.state.mark_message(msg.message_id)
                continue

            reason = "wake" if wake else "follow-up"
            log.info("DM (%s) %s: %s", reason, msg.message_id, text[:80])
            try:
                history = self._history_for_prompt(msg.thread_id, msg.message_id)
                reply = self.llm.reply(
                    self.config.trigger_username,
                    text,
                    history=history,
                )
                self.ig.reply_dm(msg.thread_id, reply)
                self.state.mark_message(msg.message_id)
                self.state.touch_thread(msg.thread_id)
                log.info("Replied (%s) with %s history msgs", reason, len(history))
            except Exception:
                log.exception("Failed to reply to DM %s", msg.message_id)
                raise

    def _history_for_prompt(
        self, thread_id: str, current_message_id: str
    ) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for item in self.ig.fetch_thread_history(thread_id, amount=30):
            if item.message_id == current_message_id:
                # Current message is passed separately as latest
                continue
            history.append(
                {
                    "role": "assistant" if item.is_from_me else "user",
                    "text": item.text,
                }
            )
        return history

    def _send_tag_reply(self, event_id: str, preview: str, *, kind: str) -> None:
        log.info("Trigger %s: %s", event_id, preview)
        try:
            reply = self.llm.reply(self.config.trigger_username, preview, history=None)
            self.ig.start_dm(reply)
            self.state.mark_event(event_id)
            log.info("Sent tag reply (%s)", kind)
        except Exception:
            log.exception("Failed to reply to tag %s", event_id)
            raise
