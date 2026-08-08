from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from instagrapi import Client

from hihi.config import SESSION_PATH

log = logging.getLogger("hihi.instagram")

MENTION_RE = re.compile(r"@([A-Za-z0-9._]+)")


@dataclass(frozen=True)
class TagEvent:
    """A detected tag/mention of the bot by the trigger user."""

    event_id: str
    kind: str  # usertag | mention | activity
    media_pk: str | None = None
    preview: str = ""


@dataclass(frozen=True)
class IncomingDM:
    thread_id: str
    message_id: str
    user_id: str
    text: str


@dataclass(frozen=True)
class ThreadMessage:
    message_id: str
    user_id: str
    text: str
    is_from_me: bool


class InstagramSession:
    def __init__(
        self,
        username: str,
        trigger_username: str,
        sessionid: str,
    ) -> None:
        self.username = username.lstrip("@").lower()
        self.trigger_username = trigger_username.lstrip("@").lower()
        self.sessionid = unquote(sessionid.strip().strip('"'))
        self.client = Client()
        self.client.delay_range = [0.5, 1.2]
        self.my_user_id: str | None = None
        self.trigger_user_id: str | None = None

    def login(self) -> None:
        if not self.sessionid:
            raise SystemExit("Set IG_SESSIONID in .env (browser cookie). Password login is disabled.")
        if len(self.sessionid) < 30:
            raise SystemExit("IG_SESSIONID looks too short. Copy the full sessionid cookie value.")

        log.info("Logging in with IG_SESSIONID from .env")
        self._sessionid_login(self.sessionid)

        self.client.dump_settings(SESSION_PATH)
        self.my_user_id = str(self.client.user_id)
        try:
            me = self.client.account_info()
            actual = str(getattr(me, "username", "") or "").lower()
            if actual and actual != self.username:
                log.warning(
                    "Session is logged in as @%s but IG_USERNAME is @%s — using session account",
                    actual,
                    self.username,
                )
                self.username = actual
        except Exception as exc:  # noqa: BLE001
            log.debug("account_info skipped: %s", exc)

        info = self.client.user_info_by_username(self.trigger_username)
        self.trigger_user_id = str(info.pk)
        log.info(
            "Ready — bot=@%s (%s), trigger=@%s (%s)",
            self.username,
            self.my_user_id,
            self.trigger_username,
            self.trigger_user_id,
        )

    def _save_device(self) -> None:
        try:
            self.client.dump_settings(SESSION_PATH)
            log.info("Saved device settings to %s", SESSION_PATH.name)
        except OSError as exc:
            log.warning("Could not save session settings: %s", exc)

    def _sessionid_login(self, sessionid: str) -> None:
        try:
            if SESSION_PATH.exists():
                try:
                    self.client.load_settings(SESSION_PATH)
                except Exception as exc:  # noqa: BLE001
                    log.debug("load_settings before sessionid skipped: %s", exc)
            self.client.login_by_sessionid(sessionid)
            # Timeline often 403s right after sessionid login; verify with account_info instead
            try:
                me = self.client.account_info()
                log.info(
                    "Logged in via sessionid as @%s",
                    getattr(me, "username", self.client.username),
                )
            except Exception:
                try:
                    self.client.get_timeline_feed()
                    log.info("Logged in via sessionid as @%s", self.client.username)
                except Exception as err:  # noqa: BLE001
                    if self.client.user_id:
                        log.warning(
                            "Timeline/account check failed (%s); continuing with session user_id=%s",
                            err,
                            self.client.user_id,
                        )
                    else:
                        raise
            self._save_device()
        except SystemExit:
            raise
        except Exception as err:  # noqa: BLE001
            raise SystemExit(
                f"sessionid login failed: {err}\n"
                "Log into Instagram in the browser again, copy a fresh sessionid into "
                "IG_SESSIONID in .env, then retry."
            ) from err

    def find_tag_events(self) -> list[TagEvent]:
        events: list[TagEvent] = []
        events.extend(self._events_from_usertags())
        events.extend(self._events_from_activity())
        return events

    def _events_from_usertags(self) -> list[TagEvent]:
        assert self.my_user_id is not None
        assert self.trigger_user_id is not None
        out: list[TagEvent] = []
        try:
            medias = self.client.usertag_medias(self.my_user_id, amount=12)
        except Exception as exc:  # noqa: BLE001
            log.warning("usertag_medias failed: %s", exc)
            return out

        for media in medias:
            user = getattr(media, "user", None)
            if user is None:
                continue
            author_id = str(getattr(user, "pk", "") or "")
            author_name = str(getattr(user, "username", "") or "").lower()
            if author_id != self.trigger_user_id and author_name != self.trigger_username:
                continue
            pk = str(media.pk)
            caption = (getattr(media, "caption_text", None) or "")[:120]
            out.append(
                TagEvent(
                    event_id=f"usertag:{pk}",
                    kind="usertag",
                    media_pk=pk,
                    preview=caption or f"photo/video tag by @{self.trigger_username}",
                )
            )
        return out

    def _events_from_activity(self) -> list[TagEvent]:
        out: list[TagEvent] = []
        try:
            inbox: dict[str, Any] = self.client.news_inbox_v1()
        except Exception as exc:  # noqa: BLE001
            log.warning("news_inbox_v1 failed: %s", exc)
            return out

        stories = list(inbox.get("new_stories") or []) + list(inbox.get("old_stories") or [])
        for story in stories:
            args = story.get("args") or {}
            if not self._activity_is_from_trigger(args):
                continue
            if not self._activity_looks_like_tag_or_mention(story, args):
                continue
            pk = str(story.get("pk") or args.get("tuuid") or args.get("timestamp") or "")
            if not pk:
                continue
            text = str(args.get("rich_text") or args.get("text") or "mention/tag")[:160]
            out.append(
                TagEvent(
                    event_id=f"activity:{pk}",
                    kind="activity",
                    media_pk=str(args.get("media_id") or args.get("media") or "") or None,
                    preview=text,
                )
            )
        return out

    def _activity_is_from_trigger(self, args: dict[str, Any]) -> bool:
        assert self.trigger_user_id is not None
        profile_id = str(args.get("profile_id") or args.get("user_id") or "")
        if profile_id and profile_id == self.trigger_user_id:
            return True

        links = args.get("links") or []
        for link in links:
            if str(link.get("id") or "") == self.trigger_user_id:
                return True

        blob = " ".join(
            [
                str(args.get("rich_text") or ""),
                str(args.get("text") or ""),
                str(args.get("comment_text") or ""),
            ]
        ).lower()
        return self.trigger_username in blob or f"@{self.trigger_username}" in blob

    def _activity_looks_like_tag_or_mention(
        self, story: dict[str, Any], args: dict[str, Any]
    ) -> bool:
        story_type = story.get("story_type")
        # Common Instagram activity types: usertag ~12, comment mention patterns vary.
        if story_type in {12, 13, 14, 60, 101}:
            pass

        text = " ".join(
            [
                str(args.get("rich_text") or ""),
                str(args.get("text") or ""),
                str(args.get("comment_text") or ""),
            ]
        ).lower()
        mentions = {m.lower() for m in MENTION_RE.findall(text)}
        if self.username in mentions:
            return True
        tag_phrases = ("tagged you", "mentioned you", "in a comment", "in their")
        return any(p in text for p in tag_phrases)

    def start_dm(self, text: str) -> None:
        assert self.trigger_user_id is not None
        self.client.direct_send(text, user_ids=[int(self.trigger_user_id)])
        log.info("Started DM with @%s", self.trigger_username)

    def fetch_trigger_dms(self, amount: int = 20) -> list[IncomingDM]:
        assert self.trigger_user_id is not None
        assert self.my_user_id is not None
        out: list[IncomingDM] = []
        try:
            threads = self.client.direct_threads(amount=amount)
        except Exception as exc:  # noqa: BLE001
            log.warning("direct_threads failed: %s", exc)
            return out

        for thread in threads:
            users = getattr(thread, "users", None) or []
            participant_ids = {str(getattr(u, "pk", "")) for u in users}
            if self.trigger_user_id not in participant_ids:
                continue
            thread_id = str(thread.id)
            messages = getattr(thread, "messages", None) or []
            for msg in messages:
                user_id = str(getattr(msg, "user_id", "") or "")
                if user_id != self.trigger_user_id:
                    continue
                text = (getattr(msg, "text", None) or "").strip()
                if not text:
                    continue
                msg_id = str(getattr(msg, "id", "") or getattr(msg, "pk", "") or "")
                if not msg_id:
                    continue
                out.append(
                    IncomingDM(
                        thread_id=thread_id,
                        message_id=msg_id,
                        user_id=user_id,
                        text=text,
                    )
                )
        return out

    def fetch_thread_history(self, thread_id: str, amount: int = 30) -> list[ThreadMessage]:
        """Return thread messages oldest → newest (text only)."""
        assert self.my_user_id is not None
        out: list[ThreadMessage] = []
        try:
            thread = self.client.direct_thread(int(thread_id), amount=amount)
        except Exception as exc:  # noqa: BLE001
            log.warning("direct_thread(%s) failed: %s", thread_id, exc)
            return out

        messages = list(getattr(thread, "messages", None) or [])
        # Instagram usually returns newest first
        messages.reverse()
        for msg in messages:
            text = (getattr(msg, "text", None) or "").strip()
            if not text:
                continue
            user_id = str(getattr(msg, "user_id", "") or "")
            msg_id = str(getattr(msg, "id", "") or getattr(msg, "pk", "") or "")
            if not msg_id:
                continue
            out.append(
                ThreadMessage(
                    message_id=msg_id,
                    user_id=user_id,
                    text=text,
                    is_from_me=user_id == self.my_user_id,
                )
            )
        return out

    def reply_dm(self, thread_id: str, text: str) -> None:
        self.client.direct_send(text, thread_ids=[int(thread_id)])
        log.info("Replied in thread %s", thread_id)
