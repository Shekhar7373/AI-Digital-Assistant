"""
Notification service.

Currently supports sending summary emails through the user's authorized Gmail account.
"""

from __future__ import annotations

import asyncio
import base64
import html
from datetime import datetime
from email.message import EmailMessage

from services.google_auth_service import build_google_service


def _normalize_subject(subject: str, context: dict | None = None) -> str:
    subject = (subject or "").strip()
    if subject:
        return subject
    query = (context or {}).get("query", "").strip()
    if query:
        return f"Briefing: {query}"
    return "Agentic AI Briefing"


def _build_professional_email(body: str, context: dict | None = None) -> tuple[str, str]:
    context = context or {}
    query = context.get("query", "").strip()
    summary = (context.get("summary") or body or "").strip()
    items = context.get("items") or []
    generated_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    intro = "Here is the requested briefing from Agentic AI."
    if query:
        intro = f"Here is the requested briefing for: {query}."

    text_lines = [
        intro,
        "",
        "Executive Summary",
        summary or "No summary was generated.",
    ]

    if items:
        text_lines.extend(["", "Key References"])
        for index, item in enumerate(items[:5], start=1):
            title = item.get("title", f"Source {index}")
            item_summary = item.get("summary", "").strip()
            url = item.get("url", "").strip()
            text_lines.append(f"{index}. {title}")
            if item_summary:
                text_lines.append(f"   {item_summary}")
            if url:
                text_lines.append(f"   {url}")

    text_lines.extend(
        [
            "",
            f"Generated on {generated_at}",
            "",
            "Regards,",
            "Agentic AI",
        ]
    )
    text_body = "\n".join(text_lines)

    safe_intro = html.escape(intro)
    safe_summary = html.escape(summary or "No summary was generated.").replace("\n", "<br />")
    html_sections = [
        "<html><body style=\"margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Arial,sans-serif;color:#1f2937;\">",
        "<div style=\"max-width:700px;margin:32px auto;padding:0 16px;\">",
        "<div style=\"background:#ffffff;border:1px solid #dbe4f0;border-radius:18px;overflow:hidden;box-shadow:0 10px 30px rgba(15,23,42,0.08);\">",
        "<div style=\"padding:24px 28px;background:linear-gradient(135deg,#122033,#1d4f91);color:#f8fafc;\">",
        "<div style=\"font-size:12px;letter-spacing:0.1em;text-transform:uppercase;opacity:0.8;\">Agentic AI Briefing</div>",
        f"<h1 style=\"margin:10px 0 0;font-size:24px;line-height:1.3;\">{html.escape(query) if query else 'Requested Summary'}</h1>",
        "</div>",
        "<div style=\"padding:28px;\">",
        f"<p style=\"margin:0 0 16px;font-size:15px;line-height:1.7;\">{safe_intro}</p>",
        "<div style=\"margin:0 0 20px;padding:18px 20px;background:#f8fbff;border:1px solid #dbeafe;border-radius:14px;\">",
        "<div style=\"font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#3b82f6;margin-bottom:10px;\">Executive Summary</div>",
        f"<div style=\"font-size:15px;line-height:1.75;color:#334155;\">{safe_summary}</div>",
        "</div>",
    ]

    if items:
        html_sections.append("<div style=\"margin-top:22px;\">")
        html_sections.append("<div style=\"font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;margin-bottom:12px;\">Key References</div>")
        for item in items[:5]:
            title = html.escape(item.get("title", "Source"))
            item_summary = html.escape(item.get("summary", "").strip())
            url = html.escape(item.get("url", "").strip())
            html_sections.append("<div style=\"padding:14px 16px;border:1px solid #e2e8f0;border-radius:12px;margin-bottom:10px;\">")
            html_sections.append(f"<div style=\"font-weight:600;color:#0f172a;margin-bottom:6px;\">{title}</div>")
            if item_summary:
                html_sections.append(f"<div style=\"font-size:14px;line-height:1.6;color:#475569;margin-bottom:8px;\">{item_summary}</div>")
            if url:
                html_sections.append(f"<a href=\"{url}\" style=\"font-size:13px;color:#2563eb;text-decoration:none;\">Open source</a>")
            html_sections.append("</div>")
        html_sections.append("</div>")

    html_sections.extend(
        [
            f"<div style=\"margin-top:24px;font-size:12px;color:#64748b;\">Generated on {html.escape(generated_at)}</div>",
            "<div style=\"margin-top:18px;font-size:14px;color:#475569;\">Regards,<br />Agentic AI</div>",
            "</div></div></div></body></html>",
        ]
    )
    html_body = "".join(html_sections)

    return text_body, html_body


def _send_email_sync(to_email: str, subject: str, body: str, context: dict | None = None) -> dict:
    service = build_google_service("gmail", "v1")
    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = _normalize_subject(subject, context)
    text_body, html_body = _build_professional_email(body, context)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
    return {
        "id": sent.get("id"),
        "to": to_email,
        "subject": subject,
        "status": "sent",
        "source": "gmail",
    }


async def send_summary_email(to_email: str, subject: str, body: str, context: dict | None = None) -> dict:
    if not to_email:
        return {"error": "A recipient email address is required to send mail."}
    if not body.strip():
        return {"error": "Email body is empty."}

    try:
        return await asyncio.to_thread(_send_email_sync, to_email, subject, body, context)
    except Exception as error:
        message = str(error)
        if "insufficient authentication scopes" in message.lower() or "insufficientpermissions" in message.lower():
            return {
                "error": (
                    "Gmail send permission is missing. Add "
                    "'https://www.googleapis.com/auth/gmail.send' to GOOGLE_OAUTH_SCOPES, "
                    "delete google_token.json, reconnect Google, and try again."
                )
            }
        return {"error": f"Unable to send email: {error}"}
