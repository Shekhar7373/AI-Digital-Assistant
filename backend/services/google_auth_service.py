import json
import os
import secrets
import hashlib
import base64
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

load_dotenv()

CALENDAR_WRITE_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DRIVE_WRITE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _credentials_path() -> Path:
    raw_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def _token_path() -> Path:
    raw_path = os.getenv("GOOGLE_TOKEN_PATH", "google_token.json")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def _state_path() -> Path:
    raw_path = os.getenv("GOOGLE_STATE_PATH", "google_oauth_state.json")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def get_google_scopes() -> list[str]:
    return [scope.strip() for scope in os.getenv("GOOGLE_OAUTH_SCOPES", "").split(",") if scope.strip()]


def get_missing_google_scopes(required_scopes: list[str]) -> list[str]:
    credentials = load_google_credentials()
    if credentials is None:
        return list(required_scopes)

    granted_scopes = set(credentials.scopes or [])
    return [scope for scope in required_scopes if scope not in granted_scopes]


def google_action_error(action_name: str, required_scopes: list[str]) -> str:
    missing_scopes = get_missing_google_scopes(required_scopes)
    if not missing_scopes:
        return ""

    if load_google_credentials() is None:
        return (
            f"Google authorization is required to {action_name}. "
            "Connect Google again and approve the write scopes before retrying."
        )

    missing_text = ", ".join(missing_scopes)
    return (
        f"Google is connected, but missing scopes required to {action_name}: {missing_text}. "
        "Reconnect Google and approve the expanded write scopes before retrying."
    )


def _read_client_config() -> dict:
    path = _credentials_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("installed") or payload.get("web") or {}


def _resolved_redirect_uri(client_config: dict | None = None, override: str | None = None) -> str:
    if override:
        return override

    env_redirect = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if env_redirect:
        return env_redirect

    config = client_config or _read_client_config()
    redirect_uris = config.get("redirect_uris") or []
    if not redirect_uris:
        raise ValueError("No redirect URIs found in Google credentials.")
    return redirect_uris[0]


def _load_state_store() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state_store(store: dict):
    _state_path().write_text(json.dumps(store, indent=2), encoding="utf-8")


def _create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def get_google_credentials_status() -> dict:
    path = _credentials_path()
    if not path.exists():
        return {
            "configured": False,
            "authorized": False,
            "path": str(path),
            "error": "Credentials file not found.",
        }

    try:
        installed = _read_client_config()
    except Exception as error:
        return {
            "configured": False,
            "authorized": False,
            "path": str(path),
            "error": f"Credentials file is not valid JSON: {error}",
        }

    scopes = get_google_scopes()
    missing = [
        field
        for field in ["client_id", "client_secret", "auth_uri", "token_uri"]
        if not installed.get(field)
    ]

    redirect_uri = ""
    redirect_error = ""
    try:
        redirect_uri = _resolved_redirect_uri(installed)
    except Exception as error:
        redirect_error = str(error)

    credentials = load_google_credentials()
    calendar_write_missing = get_missing_google_scopes(CALENDAR_WRITE_SCOPES)
    drive_write_missing = get_missing_google_scopes(DRIVE_WRITE_SCOPES)
    return {
        "configured": len(missing) == 0,
        "authorized": credentials is not None and credentials.valid,
        "path": str(path),
        "token_path": str(_token_path()),
        "project_id": installed.get("project_id", ""),
        "client_id_present": bool(installed.get("client_id")),
        "client_secret_present": bool(installed.get("client_secret")),
        "redirect_uris": installed.get("redirect_uris", []),
        "active_redirect_uri": redirect_uri,
        "redirect_error": redirect_error,
        "scopes": scopes,
        "missing_fields": missing,
        "write_capabilities": {
            "calendar_event_create": {
                "required_scopes": CALENDAR_WRITE_SCOPES,
                "authorized": len(calendar_write_missing) == 0,
                "missing_scopes": calendar_write_missing,
            },
            "drive_file_create": {
                "required_scopes": DRIVE_WRITE_SCOPES,
                "authorized": len(drive_write_missing) == 0,
                "missing_scopes": drive_write_missing,
            },
        },
    }


def create_google_auth_url(redirect_uri: str | None = None) -> dict:
    credentials_path = _credentials_path()
    if not credentials_path.exists():
        raise FileNotFoundError(f"Google credentials file not found at {credentials_path}")

    client_config = _read_client_config()
    resolved_redirect_uri = _resolved_redirect_uri(client_config, redirect_uri)
    scopes = get_google_scopes()
    flow = Flow.from_client_secrets_file(
        str(credentials_path),
        scopes=scopes,
        redirect_uri=resolved_redirect_uri,
    )
    state = secrets.token_urlsafe(24)
    code_verifier, code_challenge = _create_pkce_pair()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    store = _load_state_store()
    store[state] = {
        "redirect_uri": resolved_redirect_uri,
        "code_verifier": code_verifier,
    }
    _save_state_store(store)

    return {
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": resolved_redirect_uri,
        "instructions": (
            "Open the auth_url in a browser. After approval, if the redirect URI is plain "
            "http://localhost, copy the code from the browser URL and send it to "
            "/integrations/google/exchange-code."
        ),
    }


def exchange_google_code(code: str, state: str | None = None, redirect_uri: str | None = None) -> dict:
    credentials_path = _credentials_path()
    if not credentials_path.exists():
        raise FileNotFoundError(f"Google credentials file not found at {credentials_path}")

    store = _load_state_store()
    stored_redirect = store.get(state or "", {}).get("redirect_uri")
    stored_verifier = store.get(state or "", {}).get("code_verifier")
    resolved_redirect_uri = _resolved_redirect_uri(override=redirect_uri or stored_redirect)

    flow = Flow.from_client_secrets_file(
        str(credentials_path),
        scopes=get_google_scopes(),
        redirect_uri=resolved_redirect_uri,
    )
    if stored_verifier:
        flow.code_verifier = stored_verifier
    flow.fetch_token(code=code)

    credentials = flow.credentials
    _token_path().write_text(credentials.to_json(), encoding="utf-8")

    if state and state in store:
        del store[state]
        _save_state_store(store)

    return {
        "authorized": True,
        "redirect_uri": resolved_redirect_uri,
        "scopes": credentials.scopes,
        "token_path": str(_token_path()),
    }


def disconnect_google_account() -> dict:
    removed_files: list[str] = []
    for path in [_token_path(), _state_path()]:
        try:
            if path.exists():
                path.unlink()
                removed_files.append(str(path))
        except Exception as error:
            raise RuntimeError(f"Failed to remove Google auth file at {path}: {error}") from error

    return {
        "authorized": False,
        "removed_files": removed_files,
        "message": "Local Google OAuth token and state were cleared.",
    }


def load_google_credentials() -> Credentials | None:
    token_path = _token_path()
    if not token_path.exists():
        return None

    try:
        credentials = Credentials.from_authorized_user_file(str(token_path), scopes=get_google_scopes())
    except Exception as error:
        print(f"[GoogleAuth] Failed to load token: {error}")
        return None

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            token_path.write_text(credentials.to_json(), encoding="utf-8")
        except Exception as error:
            print(f"[GoogleAuth] Failed to refresh token: {error}")
            return None

    if not credentials.valid:
        return None
    return credentials


def build_google_service(api_name: str, version: str):
    credentials = load_google_credentials()
    if credentials is None:
        raise RuntimeError("Google account is not authorized yet.")
    return build(api_name, version, credentials=credentials, cache_discovery=False)
