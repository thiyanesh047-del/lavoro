"""Optional: save drafts into your Gmail Drafts folder. Never sends anything.

Setup (once): `pip install -r requirements-gmail.txt`, then in the Google Cloud console → new project → enable "Gmail API" → OAuth consent screen (External, add
yourself as test user) → Credentials → OAuth client ID → "Desktop app" → download JSON as credentials.json
into this folder. The first run opens a browser to approve; the token is stored in token.json.
Scope used: gmail.compose (create drafts; cannot read your inbox).
"""
from __future__ import annotations

import base64
from email.message import EmailMessage

from .config import ROOT

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token, creds_file = ROOT / "token.json", ROOT / "credentials.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_file.exists():
                raise FileNotFoundError("credentials.json not found — see lavoro/gmail.py for setup")
            creds = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def create_draft(svc, sender: str, to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"], msg["Subject"] = to, subject
    if sender and sender != "me":
        msg["From"] = sender
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    d = svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return d["id"]
