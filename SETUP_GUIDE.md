# Setup Guide

## Product Setup Context

This setup is for a developer and student workflow assistant. Configure only the integrations that support technical productivity use cases.

Recommended first integrations:
1. GitHub
2. Gmail
3. Google Calendar
4. Google Drive / Docs

Optional later integrations:
1. Slack or Discord
2. Notion or Linear
3. Jira

## Telegram Setup

Telegram is the best first mobile surface for this project because it lets you reuse the existing backend instead of building a dedicated mobile app.

### 1. Create a Bot

In Telegram:
1. Open `@BotFather`
2. Run `/newbot`
3. Choose a bot name and username
4. Copy the bot token

### 2. Add Backend Environment Variables

In `backend/.env` add:

```bash
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_WEBHOOK_SECRET=choose-a-long-random-secret
TELEGRAM_WEBHOOK_BASE_URL=https://your-public-domain
TELEGRAM_ALLOWED_CHAT_IDS=
```

`TELEGRAM_ALLOWED_CHAT_IDS` is optional but recommended while testing. Add your own Telegram chat id to limit access.

### 3. Start The Backend

```bash
cd agentic-ai/backend
python main.py
```

### 4. Expose Your Local Backend

Telegram needs a public HTTPS URL for webhooks. During development, use a tunnel such as `ngrok` or `cloudflared`.

Example with ngrok:

```bash
ngrok http 8000
```

Then set:

```bash
TELEGRAM_WEBHOOK_BASE_URL=https://your-ngrok-domain.ngrok-free.app
```

### 5. Register The Webhook

Call:

```bash
POST /integrations/telegram/set-webhook
```

This configures Telegram to send chat messages to:

```text
/integrations/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}
```

### 6. Use The Bot

Supported commands:
- `/help`
- `/plan review my github issues`
- `/status`
- `/run`
- `/cancel`

Plain text messages also generate a plan first.

## Security Expectations

Before using real accounts:
- keep OAuth credentials out of version control
- keep token files out of version control
- use the minimum scopes required
- prefer per-user secure token storage over shared local files

Current repo note:
- local token-based development is convenient for prototyping
- it is not sufficient as the long-term trust model for real users

## Backend Environment

Create `backend/.env`:

```bash
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=agentic_assistant

LLM_PROVIDER=groq
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-20b

GITHUB_TOKEN=your-github-token

GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_OAUTH_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/drive.metadata.readonly,https://www.googleapis.com/auth/drive.file
GOOGLE_TOKEN_PATH=google_token.json
GOOGLE_STATE_PATH=google_oauth_state.json
GOOGLE_REDIRECT_URI=http://localhost:8000/integrations/google/callback
FRONTEND_BASE_URL=http://localhost:5173
```

## Recommended Scope Boundary

Keep the app read-first wherever possible.

Recommended defaults:
- Gmail: readonly
- Calendar: readonly plus `calendar.events` when meeting creation is part of the approved workflow
- Drive: metadata/read access for summarization plus `drive.file` when Telegram upload/create actions are enabled
- GitHub: repo metadata and notifications first

Avoid adding broad write scopes until the approval model is stronger.

## Running The App

### Backend

```bash
cd agentic-ai/backend
pip install -r requirements.txt
python main.py
```

### Frontend

```bash
cd agentic-ai/frontend
npm install
npm run dev
```

## Setup Priorities For This Product Direction

If you are validating the product as a student/developer assistant, test in this order:
1. GitHub summaries
2. Gmail summaries
3. Calendar briefings
4. Drive/doc summarization
5. Task drafting from the above

That order keeps the product focused on one clear story instead of turning into a general assistant too early.
