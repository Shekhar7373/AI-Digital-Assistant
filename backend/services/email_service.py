"""
Email Service.

Dependency chain: fetch_emails → process_emails → summarize_emails
"""

import asyncio
import base64
import json
import html
import re
from datetime import datetime, timedelta

from agent.prompt import EMAIL_SUMMARY_SYSTEM
from db.mongodb import get_db
from services.google_auth_service import build_google_service

EMAIL_CACHE_LIMIT = 10
EMAIL_RESPONSE_LIMIT = 8

# ── Mock Email Data ────────────────────────────────────────────────────────────

MOCK_EMAILS = [
    {
        "id": "email_001",
        "from": "boss@company.com",
        "subject": "Q4 Performance Review Deadline",
        "body": (
            "Hi, just a reminder that Q4 performance reviews are due by Friday. "
            "Please ensure all self-assessments are submitted through the HR portal. "
            "This is critical for the annual bonus calculations."
        ),
        "date": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "read": False,
    },
    {
        "id": "email_002",
        "from": "github-notifications@github.com",
        "subject": "[urgent] Security vulnerability in dependency",
        "body": (
            "Dependabot has found a critical security vulnerability in lodash@4.17.15 "
            "used in your project my-app. Please update to lodash>=4.17.21 immediately."
        ),
        "date": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
        "read": False,
    },
    {
        "id": "email_003",
        "from": "team@slack.com",
        "subject": "Weekly team standup notes",
        "body": (
            "Team standup summary: Alice completed the authentication module. "
            "Bob is blocked on the payment gateway integration — needs API keys. "
            "Carol will deploy the staging environment by EOD."
        ),
        "date": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "read": True,
    },
    {
        "id": "email_004",
        "from": "newsletter@techcrunch.com",
        "subject": "This week in AI: GPT-5 rumours and open-source gains",
        "body": "Newsletter content about AI trends...",
        "date": (datetime.utcnow() - timedelta(days=2)).isoformat(),
        "read": True,
    },
]

EMAIL_CACHE: list[dict] = []


def _extract_header(headers: list[dict], name: str) -> str:
    lowered = name.lower()
    for header in headers:
        if header.get("name", "").lower() == lowered:
            return header.get("value", "")
    return ""


def _decode_message_data(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _clean_email_text(raw: str) -> str:
    if not raw:
        return ""

    text = raw
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</div>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _extract_body(payload: dict) -> str:
    data = payload.get("body", {}).get("data")
    if data:
        return _decode_message_data(data)

    plain_text = ""
    html_text = ""

    for part in payload.get("parts", []) or []:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            text = _extract_body(part)
            if text:
                plain_text = text
        elif mime_type == "text/html":
            text = _extract_body(part)
            if text:
                html_text = text
        elif part.get("parts"):
            text = _extract_body(part)
            if text and not plain_text:
                plain_text = text

    return plain_text or html_text or ""


def _fetch_gmail_emails_sync(max_results: int = EMAIL_CACHE_LIMIT) -> list[dict]:
    service = build_google_service("gmail", "v1")
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results, q="newer_than:7d")
        .execute()
    )
    messages = response.get("messages", [])
    emails = []
    for item in messages:
        detail = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
        payload = detail.get("payload", {})
        headers = payload.get("headers", [])
        labels = detail.get("labelIds", [])
        cleaned_body = _clean_email_text(_extract_body(payload) or detail.get("snippet", ""))
        emails.append(
            {
                "id": detail.get("id"),
                "from": _extract_header(headers, "From") or "Unknown sender",
                "subject": _extract_header(headers, "Subject") or "(No subject)",
                "body": cleaned_body or detail.get("snippet", ""),
                "preview": (cleaned_body or detail.get("snippet", ""))[:280],
                "date": _extract_header(headers, "Date") or datetime.utcnow().isoformat(),
                "read": "UNREAD" not in labels,
                "source": "gmail",
                "url": f"https://mail.google.com/mail/u/0/#inbox/{detail.get('id')}",
            }
        )
    return emails


async def _safe_store_emails(emails: list[dict]):
    db = get_db()
    if db is None:
        return
    try:
        payload = [{k: v for k, v in email.items() if k != "_id"} for email in emails]
        await db.emails.delete_many({})
        await db.emails.insert_many(payload)
    except Exception as error:
        print(f"[EmailService] Failed to persist emails: {error}")


async def _safe_load_emails() -> list[dict]:
    db = get_db()
    if db is None:
        return []
    try:
        return await db.emails.find({}, {"_id": 0}).to_list(length=100)
    except Exception as error:
        print(f"[EmailService] Failed to load emails from DB: {error}")
        return []


async def _safe_cache_summary(summary_text: str, summaries: list[dict]):
    db = get_db()
    if db is None:
        return
    try:
        await db.agent_context.replace_one(
            {"key": "last_email_summary"},
            {"key": "last_email_summary", "value": summary_text, "summaries": summaries},
            upsert=True,
        )
    except Exception as error:
        print(f"[EmailService] Failed to cache summary: {error}")


async def fetch_emails(refresh: bool = False, limit: int = EMAIL_RESPONSE_LIMIT) -> list[dict]:
    """
    Fetch emails from Gmail when OAuth is available, otherwise use local fallback data.
    """
    global EMAIL_CACHE
    normalized_limit = max(1, min(limit or EMAIL_RESPONSE_LIMIT, EMAIL_CACHE_LIMIT))

    if not refresh:
        cached = await _safe_load_emails()
        if cached:
            EMAIL_CACHE = cached[:EMAIL_CACHE_LIMIT]
            return EMAIL_CACHE[:normalized_limit]
        if EMAIL_CACHE:
            return EMAIL_CACHE[:normalized_limit]

    try:
        EMAIL_CACHE = await asyncio.to_thread(_fetch_gmail_emails_sync, EMAIL_CACHE_LIMIT)
    except Exception as error:
        print(f"[EmailService] Gmail fetch failed, using fallback data: {error}")
        EMAIL_CACHE = [
            {
                **dict(email),
                "preview": dict(email).get("body", "")[:280],
            }
            for email in MOCK_EMAILS[:EMAIL_CACHE_LIMIT]
        ]
    await _safe_store_emails(EMAIL_CACHE[:EMAIL_CACHE_LIMIT])
    return EMAIL_CACHE[:normalized_limit]


async def process_emails(emails: list[dict] = None) -> list[dict]:
    """
    Process raw emails:
    - Strips newsletter/low-priority items
    - Flags unread emails as higher priority
    - Returns cleaned email list
    """
    if emails is None:
        emails = await _safe_load_emails()
        if not emails:
            emails = EMAIL_CACHE or [dict(email) for email in MOCK_EMAILS]

    processed = []
    for email in emails:
        # Simple priority scoring
        subject_lower = email.get("subject", "").lower()
        priority = "low"
        if any(kw in subject_lower for kw in ["urgent", "critical", "deadline", "security"]):
            priority = "high"
        elif not email.get("read", True):
            priority = "medium"

        processed.append({
            **email,
            "priority": priority,
            "processed": True,
        })

    return processed


async def summarize_emails(emails: list[dict] = None) -> dict:
    """
    Summarize emails using the LLM.
    Depends on processed emails (calls process_emails if needed).
    """
    if not emails:
        emails = await process_emails()

    if not emails:
        return {"summary": "No emails to summarize.", "summaries": []}

    # Build a compact representation for the LLM
    email_text = "\n\n".join(
        f"From: {e['from']}\nSubject: {e['subject']}\nPriority: {e.get('priority','?')}\nBody: {e['body'][:300]}"
        for e in emails
    )

    try:
        from llm.router import llm_chat

        summary_text = await llm_chat(EMAIL_SUMMARY_SYSTEM, email_text)
    except Exception as error:
        print(f"[EmailService] LLM summary failed: {error}")
        lines = [
            f"- [{e.get('priority', 'medium').upper()}] {e['subject']} — From {e['from']}"
            for e in emails
        ]
        summary_text = "\n".join(lines)

    # Also build structured list for task extraction
    summaries = [
        {"subject": e["subject"], "from": e["from"], "priority": e.get("priority", "medium")}
        for e in emails
    ]

    await _safe_cache_summary(summary_text, summaries)

    return {"summary": summary_text, "summaries": summaries, "total": len(emails)}
