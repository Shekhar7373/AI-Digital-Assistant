from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException

from services.telegram_service import process_telegram_update, set_telegram_webhook, telegram_status

router = APIRouter()


@router.get("/status")
async def get_telegram_status():
    return telegram_status()


@router.post("/set-webhook")
async def telegram_set_webhook():
    try:
        return await set_telegram_webhook()
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/webhook/{secret}")
async def telegram_webhook(secret: str, update: dict, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    status = telegram_status()
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not status["configured"]:
        raise HTTPException(status_code=400, detail="Telegram bot token is not configured.")
    if not status["webhook_secret_present"]:
        raise HTTPException(status_code=400, detail="Telegram webhook secret is not configured.")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")
    if x_telegram_bot_api_secret_token and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram secret token header.")
    return await process_telegram_update(update)
