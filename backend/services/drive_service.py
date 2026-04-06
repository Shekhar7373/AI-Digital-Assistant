"""
Google Drive Service.
"""
import asyncio
import io

from googleapiclient.http import MediaIoBaseDownload

from services.google_auth_service import build_google_service

MOCK_FILES = [
    {"id": "file_001", "name": "Q4 Report.docx",   "type": "document",     "size_kb": 245, "modified": "2024-01-20"},
    {"id": "file_002", "name": "Budget 2024.xlsx",  "type": "spreadsheet",  "size_kb": 98,  "modified": "2024-01-18"},
    {"id": "file_003", "name": "Product Roadmap.pdf","type": "pdf",         "size_kb": 512, "modified": "2024-01-15"},
    {"id": "file_004", "name": "Meeting Notes.txt",  "type": "text",        "size_kb": 12,  "modified": "2024-01-22"},
]

MOCK_FILE_CONTENT = {
    "file_001": (
        "Q4 Performance Report: Revenue increased 18% YoY to $2.4M. "
        "Customer acquisition cost dropped by 12%. Churn rate was 3.2%, down from 4.1% in Q3. "
        "Engineering shipped 24 features. Support ticket volume decreased by 30%."
    ),
    "file_002": (
        "Budget 2024: Total allocated budget is $5.2M. Engineering: $2.1M, Marketing: $1.3M, "
        "Operations: $800K, R&D: $700K, Contingency: $300K."
    ),
    "file_003": (
        "Product Roadmap 2024: Q1 — Authentication revamp, API v2 launch. "
        "Q2 — Mobile app beta, Integrations marketplace. Q3 — AI features, Analytics dashboard. "
        "Q4 — Enterprise tier, SOC2 compliance."
    ),
    "file_004": (
        "Meeting Notes Jan 22: Discussed deployment pipeline improvements. "
        "Action items: Bob to set up CI/CD for staging. Carol to write runbook. "
        "Next meeting: Feb 5."
    ),
}


def _mime_type_label(mime_type: str) -> str:
    mapping = {
        "application/vnd.google-apps.document": "document",
        "application/vnd.google-apps.spreadsheet": "spreadsheet",
        "application/vnd.google-apps.presentation": "presentation",
        "application/pdf": "pdf",
        "text/plain": "text",
    }
    return mapping.get(mime_type, mime_type or "unknown")


def _list_files_sync(page_size: int = 6) -> list[dict]:
    service = build_google_service("drive", "v3")
    response = (
        service.files()
        .list(
            pageSize=page_size,
            fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    files = []
    for item in response.get("files", []):
        size_raw = item.get("size")
        size_kb = round(int(size_raw) / 1024, 2) if size_raw and size_raw.isdigit() else None
        files.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": _mime_type_label(item.get("mimeType", "")),
                "mimeType": item.get("mimeType", ""),
                "size_kb": size_kb,
                "modified": item.get("modifiedTime", ""),
                "url": item.get("webViewLink", ""),
                "source": "google_drive",
            }
        )
    return files


def _download_drive_text_sync(file_id: str, mime_type: str) -> str:
    service = build_google_service("drive", "v3")
    buffer = io.BytesIO()
    if mime_type == "application/vnd.google-apps.document":
        request = service.files().export_media(fileId=file_id, mimeType="text/plain")
    elif mime_type == "text/plain":
        request = service.files().get_media(fileId=file_id)
    else:
        return ""

    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="ignore")


async def list_files(limit: int = 6) -> list[dict]:
    """Return live Drive files when authorized, otherwise use local fallback data."""
    page_size = max(1, min(limit or 6, 8))
    try:
        return await asyncio.to_thread(_list_files_sync, page_size)
    except Exception as error:
        print(f"[DriveService] Drive list failed, using fallback data: {error}")
        return MOCK_FILES[:page_size]


async def summarize_file_mock(file_id: str) -> dict:
    """
    Summarize a Drive file using live Drive content when available, otherwise use local fallback content.
    """
    file_listing = await list_files()
    file_meta = next((f for f in file_listing if f["id"] == file_id), None)
    content = ""
    if file_meta:
        try:
            content = await asyncio.to_thread(
                _download_drive_text_sync,
                file_id,
                file_meta.get("mimeType", ""),
            )
        except Exception as error:
            print(f"[DriveService] Drive download failed, using fallback data: {error}")

    if not content:
        content = MOCK_FILE_CONTENT.get(file_id, "")
    if not file_meta:
        file_meta = next((f for f in MOCK_FILES if f["id"] == file_id), {})
    if not content:
        return {"error": f"File {file_id} not found."}

    system = (
        "You are a document summarization assistant. "
        "Summarize the following document content in 3-5 bullet points, "
        "highlighting key metrics, decisions, or action items."
    )
    try:
        from llm.router import llm_chat

        summary = await llm_chat(system, content)
    except Exception as error:
        print(f"[DriveService] LLM summary failed: {error}")
        summary = content[:180] + ("..." if len(content) > 180 else "")

    return {
        "file_id": file_id,
        "file_name": file_meta.get("name", "Unknown"),
        "summary": summary,
    }
