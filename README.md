# InPY

Local Python bot: logs into Instagram as **@BOT** over HTTP (`instagrapi`, no Chrome). When **@HOST** tags or @mentions the bot account, it starts a DM and chats with **Groq**.

## Warning

This uses Instagram’s **unofficial private API**. Use at your own risk. Prefer testing carefully and keeping the poll interval slow.

Never commit `.env` — it holds your Instagram session cookie and API keys.

## Star goals

| Stars | Unlock |
|------:|--------|
| **50 ⭐** | Reels React |
| **100 ⭐** | Photo and video support |

Hit the goal → it ships.

## Setup

```powershell
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

- `IG_USERNAME` — bot account (`BOT`)
- `IG_SESSIONID` — browser `sessionid` cookie (**required**)
- `TRIGGER_USERNAME` — who must tag you (`HOST`)
- `GROQ_API_KEY` — from [console.groq.com](https://console.groq.com/)
- `GROQ_MODEL` — default `llama-3.3-70b-versatile`

### Get `IG_SESSIONID`

1. Log into https://www.instagram.com in Chrome as the bot account  
2. Finish any checkpoint in the browser  
3. F12 → Application → Cookies → `https://www.instagram.com` → copy `sessionid`  
4. Paste into `.env` as `IG_SESSIONID=...`

When the cookie expires, refresh it the same way and update `.env`.

## Run

```powershell
python main.py
```

## Behavior

1. Poll activity / photo tags for `@HOST` tagging `@BOT`
2. On a new tag → Groq writes an opener → DM `@HOST`
3. Further DMs from `@HOST` get Groq replies
4. Handled events/messages are stored in `state.json` so restarts don’t double-send

Stop with `Ctrl+C`.


YouTubr :- https://www.youtube.com/watch?v=fFDGgvPuVxc
