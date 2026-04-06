from fastapi import APIRouter
from services.drive_service import list_files, summarize_file_mock

router = APIRouter()

@router.get("/files")
async def files(limit: int = 6): return await list_files(limit=limit)

@router.get("/summarize/{file_id}")
async def summarize(file_id: str): return await summarize_file_mock(file_id)
