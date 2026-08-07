# HIHI

Local Python bot: logs into Instagram as **@drjonnynp** over HTTP (`instagrapi`, no Chrome). When **@sudeep_wtf** tags or @mentions the bot account, it starts a DM and chats with **Groq**.

## Warning

This uses Instagram’s **unofficial private API**. It can get the account challenged, locked, or banned. Use at your own risk. Prefer testing carefully and keeping the poll interval slow.

Never commit `.env` — it holds your Instagram password and API keys.

## Setup

```powershell
cd C:\Users\user\Documents\HIHI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

- `IG_USERNAME` / `IG_PASSWORD` — bot account (`drjonnynp`)
- `TRIGGER_USERNAME` — who must tag you (`sudeep_wtf`)
- `GROQ_API_KEY` — from [console.groq.com](https://console.groq.com/)
- `GROQ_MODEL` — default `llama-3.3-70b-versatile`

## Run

```powershell
python main.py
```

On first login HIHI uses the password from `.env`.

If Instagram blocks password login (common — it often does **not** send an approve notification), HIHI asks for a browser **`sessionid`**:

1. Log into https://www.instagram.com in Chrome as the bot account
2. Finish any checkpoint in the browser
3. F12 → Application → Cookies → copy `sessionid`
4. Paste it when asked (or set `IG_SESSIONID` in `.env`)

## Behavior

1. Poll activity / photo tags for `@sudeep_wtf` tagging `@drjonnynp`
2. On a new tag → Groq writes an opener → DM `@sudeep_wtf`
3. Further DMs from `@sudeep_wtf` get Groq replies
4. Handled events/messages are stored in `state.json` so restarts don’t double-send

Stop with `Ctrl+C`.
