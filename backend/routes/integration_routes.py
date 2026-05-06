from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from routes.dashboard_routes import reset_dashboard_state
from services.google_auth_service import (
    create_google_auth_url,
    disconnect_google_account,
    exchange_google_code,
    get_google_credentials_status,
)

router = APIRouter()


class GoogleExchangeRequest(BaseModel):
    code: str
    state: str | None = None
    redirect_uri: str | None = None


@router.get("/google/status")
async def google_status():
    return get_google_credentials_status()


@router.get("/google/auth-url")
async def google_auth_url(redirect_uri: str | None = None):
    try:
        return create_google_auth_url(redirect_uri)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/google/exchange-code")
async def google_exchange_code(body: GoogleExchangeRequest):
    try:
        return exchange_google_code(body.code, body.state, body.redirect_uri)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/google/logout")
async def google_logout():
    try:
        result = disconnect_google_account()
        dashboard = await reset_dashboard_state()
        return {**result, "dashboard": dashboard}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(code: str, state: str | None = None):
    try:
        result = exchange_google_code(code, state)
    except Exception as error:
        message = str(error).replace("'", "\\'")
        html = f"""
<!doctype html>
<html>
  <body style="font-family: sans-serif; background: #091224; color: #eef5ff; display: grid; place-items: center; min-height: 100vh;">
    <div>
      <h2>Google connection failed</h2>
      <p>{message}</p>
      <script>
        if (window.opener) {{
          window.opener.postMessage({{ type: 'google-oauth-error', message: '{message}' }}, 'http://localhost:5173');
        }}
      </script>
    </div>
  </body>
</html>
"""
        return HTMLResponse(content=html, status_code=400)

    html = """
<!doctype html>
<html>
  <body style="font-family: sans-serif; background: #091224; color: #eef5ff; display: grid; place-items: center; min-height: 100vh;">
    <div>
      <h2>Google connected</h2>
      <p>You can close this window now.</p>
      <script>
        if (window.opener) {
          window.opener.postMessage({ type: 'google-oauth-success' }, 'http://localhost:5173');
          window.close();
        }
      </script>
    </div>
  </body>
</html>
"""
    return HTMLResponse(content=html)
