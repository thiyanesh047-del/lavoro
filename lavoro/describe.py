"""One line about each company, for its card on the Companies page.

Tried in order, first answer wins:
  1. the intro a Greenhouse job board publishes about the company;
  2. the company's own website: its meta description;
  3. Wikipedia's summary, only when the article is clearly about that company (big employers like H&M or PwC).
Nothing is invented: a company with no source keeps no line, and its card shows where it is hiring instead.
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .net import get, get_json, html_to_text

_META = [re.compile(r'<meta[^>]+(?:name|property)=["\'](?:og:description|description|twitter:description)["\'][^>]*content=["\']([^"\']{30,400})', re.I),
         re.compile(r'<meta[^>]+content=["\']([^"\']{30,400})["\'][^>]*(?:name|property)=["\'](?:og:description|description)["\']', re.I)]
_COMPANYISH = re.compile(r"\b(company|companies|corporation|firm|business|startup|group|bank|manufacturer|retailer|"
                         r"consultancy|consulting|provider|platform|developer|maker|multinational|conglomerate|"
                         r"brand|agency|organisation|organization|subsidiary|enterprise|operator|producer|network)\b", re.I)
_BAD = re.compile(r"cookie|javascript|enable js|access denied|just a moment|captcha|404|page not found|log ?in", re.I)


def _key(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def _first_word_key(name: str) -> str:
    return _key((re.sub(r"\s*\(.*\)$", "", name).split() or [""])[0])  # "H&M Group" -> "hm"


# A careers site's own tagline is not a description of the company.
_CAREERS_TALK = re.compile(r"\b(jobs?|careers?|vacanc|join (us|our)|open positions|apply|recruit|work with us|hiring)\b", re.I)
# Wikipedia pages that share a company's name but are something else.
_NOT_A_COMPANY = re.compile(r"\b(video game|game|toy|film|album|song|band|novel|television|tv series|character|"
                            r"magazine|river|town|village|city|municipality|surname|given name|genus|species|software library)\b", re.I)


def _sentence(text: str, limit: int = 170) -> str:
    text = " ".join(html.unescape(text or "").split())
    m = re.match(rf"(.{{30,{limit}}}?[.!?])(\s|$)", text)
    if m:
        return m.group(1)
    return text[:limit].rsplit(" ", 1)[0] + "…" if len(text) > limit else text


def from_greenhouse(slug: str, name: str) -> str:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}", timeout=15) or {}
    text = html_to_text(data.get("content") or "")
    if len(text) < 40 or _BAD.search(text[:200]) or _first_word_key(name) not in _key(text[:400]):
        return ""
    return _sentence(text)


def from_website(url: str) -> str:
    if not url:
        return ""
    r = get(url if "://" in url else "https://" + url, timeout=15)
    if r is None or r.status_code >= 400:
        return ""
    for pat in _META:
        m = pat.search(r.text[:200_000])
        if m and not _BAD.search(m.group(1)) and not _CAREERS_TALK.search(m.group(1)):
            return _sentence(m.group(1))
    return ""


# Wikipedia asks automated tools to name themselves instead of posing as a browser.
WIKI_UA = "Lavoro/0.1 (open-source personal job-search tool)"


def _wiki_json(url: str) -> dict:
    r = get(url, timeout=15, headers={"User-Agent": WIKI_UA, "Accept": "application/json"})
    if r is not None and r.status_code == 429:  # too fast: wait once, then try again
        time.sleep(4)
        r = get(url, timeout=15, headers={"User-Agent": WIKI_UA, "Accept": "application/json"})
    if r is None or r.status_code != 200:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


_wiki_lock = threading.Lock()
_SUFFIX = re.compile(r"\s+(group|ab|ab \(publ\)|inc\.?|ltd\.?|gmbh|plc|se|nv|sa|as|oy|aktiebolag|technologies|labs?)$", re.I)


def from_wikipedia(name: str) -> str:
    """Look up the page with the company's name (and without "Group", "AB"...). Accept it only when the summary
    names the company and reads like a company, so a town or a band with the same name is never used."""
    base = re.sub(r"\s*\(.*\)$", "", name).strip()
    tries = [base] + ([_SUFFIX.sub("", base)] if _SUFFIX.search(base) else [])
    key = _first_word_key(base)
    for title in tries:
        with _wiki_lock:  # one request at a time, and a short pause: Wikipedia's rate limits are strict
            s = _wiki_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"), safe=""))
            time.sleep(0.5)
        if s.get("type") != "standard":
            continue
        extract, short = s.get("extract") or "", s.get("description") or ""
        if not key or key not in _key(s.get("title", "") + extract[:150]):
            continue
        if not _COMPANYISH.search(short) or _NOT_A_COMPANY.search(short):
            continue
        return _sentence(extract)
    return ""


def describe_one(c) -> tuple[int, str, str]:
    info = json.loads(c["info"] or "{}") if c["info"] else {}
    if info.get("one_liner"):
        return c["id"], "", ""
    line, src = "", ""
    if c["ats"] == "greenhouse" and c["slug"]:
        line, src = from_greenhouse(c["slug"], c["name"]), "job board"
    if not line:
        line, src = from_wikipedia(c["name"]), "Wikipedia"
    if not line and (c["website"] or c["domain"]):
        line, src = from_website(c["website"] or c["domain"]), "website"
    return c["id"], line, src if line else ""


def describe_companies(con, limit: int = 400) -> int:
    """Fill a one-line description for hiring companies that have none. Returns how many got one."""
    rows = con.execute(
        "SELECT c.*, (SELECT count(*) FROM jobs j WHERE j.company_id=c.id AND j.status NOT IN ('closed','duplicate')) AS roles "
        "FROM companies c ORDER BY roles DESC").fetchall()

    def todo(r):
        info = json.loads(r["info"] or "{}") if r["info"] else {}
        return r["roles"] > 0 and not info.get("one_liner") and not info.get("described")
    rows = [r for r in rows if todo(r)][:limit]
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(describe_one, rows))
    n = 0
    for (cid, line, src), r in zip(results, rows):
        info = json.loads(r["info"] or "{}") if r["info"] else {}
        info["described"] = True          # tried once; the weekly refresh does not ask again
        if line:
            info["one_liner"], info["one_liner_source"] = line, src
            n += 1
        con.execute("UPDATE companies SET info=? WHERE id=?", (json.dumps(info, ensure_ascii=False), cid))
    con.commit()
    return n
