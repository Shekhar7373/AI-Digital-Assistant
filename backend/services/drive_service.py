"""
Google Drive Service.
"""

import asyncio
import io
from datetime import datetime

from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

from services.google_auth_service import DRIVE_WRITE_SCOPES, build_google_service, google_action_error


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
        size_kb = round(int(size_raw) / 1024, 2) if size_raw and str(size_raw).isdigit() else None
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


def _create_drive_text_file_sync(name: str, content: str) -> dict:
    service = build_google_service("drive", "v3")
    safe_name = name.strip() or f"Agentic AI Note {datetime.utcnow().strftime('%Y-%m-%d %H-%M')}.txt"
    if not safe_name.lower().endswith(".txt"):
        safe_name = f"{safe_name}.txt"

    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain", resumable=False)
    created = (
        service.files()
        .create(
            body={"name": safe_name, "mimeType": "text/plain"},
            media_body=media,
            fields="id,name,mimeType,webViewLink,modifiedTime,size",
        )
        .execute()
    )
    size_raw = created.get("size")
    size_kb = round(int(size_raw) / 1024, 2) if size_raw and str(size_raw).isdigit() else None
    return {
        "id": created.get("id"),
        "name": created.get("name"),
        "mimeType": created.get("mimeType", "text/plain"),
        "type": _mime_type_label(created.get("mimeType", "text/plain")),
        "size_kb": size_kb,
        "modified": created.get("modifiedTime", ""),
        "url": created.get("webViewLink", ""),
        "source": "google_drive",
    }


async def list_files(limit: int = 6) -> list[dict]:
    page_size = max(1, min(limit or 6, 8))
    try:
        return await asyncio.to_thread(_list_files_sync, page_size)
    except Exception as error:
        print(f"[DriveService] Drive list failed: {error}")
        return []


async def summarize_file_mock(file_id: str) -> dict:
    file_listing = await list_files()
    file_meta = next((f for f in file_listing if f["id"] == file_id), None)
    if not file_meta:
        return {"error": f"File {file_id} was not found in Google Drive."}

    try:
        content = await asyncio.to_thread(
            _download_drive_text_sync,
            file_id,
            file_meta.get("mimeType", ""),
        )
    except Exception as error:
        print(f"[DriveService] Drive download failed: {error}")
        return {"error": f"Unable to download Drive file content: {error}"}

    if not content:
        return {"error": "This Drive file type cannot be summarized as plain text yet."}

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


async def create_drive_text_file(params: dict) -> dict:
    auth_error = google_action_error("create a Drive file", DRIVE_WRITE_SCOPES)
    if auth_error:
        return {"error": auth_error}

    content = (params.get("drive_content") or params.get("content") or "").strip()
    if not content:
        return {"error": "Drive upload content is empty. Generate or provide text content before uploading."}

    title = (params.get("drive_file_name") or params.get("title") or "Agentic AI Note").strip()
    try:
        return await asyncio.to_thread(_create_drive_text_file_sync, title, content)
    except Exception as error:
        print(f"[DriveService] Drive create failed: {error}")
        return {"error": f"Drive file creation failed after authorization. Google returned: {error}"}
