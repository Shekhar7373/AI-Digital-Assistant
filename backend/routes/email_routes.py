from fastapi import APIRouter
from services.email_service import fetch_emails, process_emails, summarize_emails

router = APIRouter()

@router.post("/fetch")
async def fetch(refresh: bool = False, limit: int = 8): return await fetch_emails(refresh=refresh, limit=limit)

@router.post("/process")
async def process(): return await process_emails()

@router.post("/summarize")
async def summarize(): return await summarize_emails()
