"""Small HTTP helpers: one shared session, polite headers, HTML to text."""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en,sv;q=0.8"})


def get(url: str, timeout: float = 20, **kw) -> requests.Response | None:
    try:
        return _session.get(url, timeout=timeout, **kw)
    except requests.RequestException:
        return None


def get_json(url: str, timeout: float = 20, **kw):
    r = get(url, timeout=timeout, headers={"Accept": "application/json"}, **kw)
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def post_json(url: str, body: dict, timeout: float = 20):
    """POST a JSON body and return the JSON reply, or None on any failure."""
    try:
        r = _session.post(url, json=body, timeout=timeout, headers={"Accept": "application/json"})
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)  # some feeds double-escape
    s = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    s = _NL.sub("\n\n", s)
    return s.strip()


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host
