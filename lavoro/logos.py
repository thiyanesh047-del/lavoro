"""Company logos, fetched once from each company's own website and kept in data/logos/.

Where the company's address comes from, in this order:
  1. the website saved for the company;
  2. a job ad hosted on the company's own site (careers.hellofresh.com → hellofresh.com);
  3. the company's name or job-board name as a web address (pwc.com, astrazeneca.se...), used only when
     that site's own title names the company.
The logo is the site's own icon: its apple-touch-icon, or the largest icon it lists, or /favicon.ico. If the
site serves none, Google's public favicon service is asked for the same address. A company with no logo keeps
its letter. A miss is remembered for 30 days so pages never wait on it twice.

    python -m lavoro logos            fetch logos for every company that is hiring
    python -m lavoro logos --all      every company Lavoro watches
"""
from __future__ import annotations

import html
import re
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from .db import DB_PATH
from .net import _session, domain_of

DIR = DB_PATH.parent / "logos"
EXTS = ("png", "svg", "ico", "jpg", "webp", "gif")
MISS_DAYS = 30
MAX_BYTES = 1_000_000
TYPES = {"png": "image/png", "svg": "image/svg+xml", "ico": "image/x-icon", "jpg": "image/jpeg",
         "webp": "image/webp", "gif": "image/gif"}
# Hosts that belong to job boards, not to the company.
BOARD_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "teamtailor.com",
               "smartrecruiters.com", "myworkdayjobs.com", "successfactors", "contactrh.com", "jobylon", "arbetsformedlingen",
               "jobtechdev", "linkedin.", "indeed.", "ycombinator.com", "workatastartup", "wellfound", "breezy.hr",
               "bamboohr", "personio", "jobvite", "icims", "taleo", "oraclecloud", "dover.", "rippling", "gem.com",
               "hn.algolia", "news.ycombinator", "arbeitnow", "join.com", "homerun.co", "pinpointhq", "jobs.eu.lever")
PREFIXES = {"www", "jobs", "careers", "career", "job", "work", "join", "apply", "karriere", "karriar", "jobb",
            "team", "people", "talent", "en", "global", "hire", "recruiting", "candidate", "life", "about"}
NAME_STOP = {"group", "ab", "inc", "ltd", "llc", "gmbh", "as", "asa", "oy", "aktiebolag", "the", "and", "company",
             "graduates", "graduate", "careers", "sverige", "sweden", "international", "holding", "plc", "co", "se"}
TLDS = ("com", "se", "io", "ai", "co", "eu", "de", "app", "tech")
_busy: set[int] = set()
_lock = threading.Lock()


# ---------------------------------------------------------------- the cache
def path(cid: int) -> Path | None:
    for ext in EXTS:
        p = DIR / f"{cid}.{ext}"
        if p.exists():
            return p
    return None


def state(cid: int) -> str:
    """'have', 'miss' (looked recently, none found) or 'unknown'."""
    if path(cid):
        return "have"
    m = DIR / f"{cid}.miss"
    if m.exists() and time.time() - m.stat().st_mtime < MISS_DAYS * 86400:
        return "miss"
    return "unknown"


def tile(cid: int | None, name: str, cls: str = "mono") -> str:
    """The company's logo over its first letter; if the logo can't load, the letter shows."""
    from .digest import e
    letter = e((name or "?").strip()[:1].upper() or "?")
    img = ""
    if cid and state(cid) != "miss":
        # One retry after a moment (the site may have been restarting), then the letter shows.
        img = (f'<img src="/logo/{cid}" alt="" loading="lazy" decoding="async" onload="this.parentNode.classList.add(\'has\');if(this.naturalWidth&lt;72)this.parentNode.classList.add(\'lo\')" '
               f'onerror="if(this.dataset.r)this.remove();else{{this.dataset.r=1;setTimeout(()=>this.src=\'/logo/{cid}?r=1\',1500)}}">')
    return f'<span class="logo-t {cls}" aria-hidden="true">{letter}{img}</span>'


# ---------------------------------------------------------------- finding the company's site
def _site(host: str) -> str:
    """'careers.hellofresh.com' → 'hellofresh.com'; 'jobs.example.co.uk' → 'example.co.uk'."""
    labels = [x for x in (host or "").lower().split(".") if x]
    while len(labels) > 2 and labels[0] in PREFIXES:
        labels = labels[1:]
    if len(labels) >= 3 and labels[-2] in ("co", "com", "ac", "org", "net") and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _name_tokens(name: str) -> list[str]:
    plain = re.sub(r"\([^)]*\)", " ", name or "")
    words = [_fold(w) for w in re.split(r"[\s/,&+.-]+", plain)]
    words = [w for w in words if w and w not in NAME_STOP]
    joined = "".join(words)
    out = [w for w in words if len(w) >= 3]
    if joined and joined not in out:
        out.append(joined)
    return out


def _from_jobs(con, cid: int) -> str:
    hosts = Counter()
    for (url,) in con.execute("SELECT url FROM jobs WHERE company_id = ? AND url IS NOT NULL LIMIT 80", (cid,)):
        host = domain_of(url)
        if host and not any(b in host for b in BOARD_HOSTS):
            hosts[_site(host)] += 1
    return hosts.most_common(1)[0][0] if hosts else ""


def _bases(c) -> list[str]:
    """Names to try as web addresses: the job-board name (pwc from pwc.wd3.myworkdayjobs.com) and the company name."""
    out = []
    slug = (c["slug"] or "").lower()
    if slug:
        first = slug.split("/")[0]
        first = first.split(".")[0] if "." in first else first
        out.append(re.sub(r"[^a-z0-9-]", "", first))
    toks = _name_tokens(c["name"])
    if toks:
        out.append(toks[-1])  # all words joined
        out.append(toks[0])
    seen, bases = set(), []
    for b in out:
        if b and len(b) >= 2 and b not in seen:
            seen.add(b)
            bases.append(b)
    return bases[:3]


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_SITE_NAME = re.compile(r'<meta[^>]+property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)', re.I)


def _names_company(page: str, name: str) -> bool:
    found = " ".join(_TITLE.findall(page[:200_000])[:1] + _SITE_NAME.findall(page[:200_000])[:1])
    folded = _fold(html.unescape(found))
    return bool(folded) and any(t in folded for t in _name_tokens(name))


_PARKED = re.compile(r"resources and information|resurser och information|domain (name )?(is )?for sale|buy this domain|"
                     r"this domain (may be|is) for sale|parked (free|domain)|sedoparking|afternic|hugedomains|dan\.com/|"
                     r"domain has expired|godaddy\.com/domains", re.I)


def _links_board(page: str, c) -> bool:
    """Does this page link to the job board Lavoro reads for the company?"""
    slug = (c["slug"] or "").split("/")[0].lower()
    if not slug or not page:
        return False
    low = page.lower()
    return any(f"{host}/{slug}" in low or (host in low and slug in low) for host in
               ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "teamtailor.com",
                "smartrecruiters.com")) or slug in low and "myworkdayjobs.com" in low


def _probe(domain: str):
    """(status, final_domain, final_url, html) for the site's home page, or None if nothing answers."""
    try:
        r = _session.get(f"https://{domain}/", timeout=8, allow_redirects=True)
    except Exception:
        return None
    text = r.text[:300_000] if "html" in (r.headers.get("Content-Type") or "html") else ""
    return r.status_code, _site(domain_of(r.url) or domain), r.url, text


def _home(domain: str):
    """(final_domain, final_url, html) for a site that answers, or None."""
    p = _probe(domain)
    return (p[1], p[2], p[3]) if p and p[0] < 400 else None


def find_site(con, c):
    """(domain, home_url, html or '') for this company, or None. html is '' when the home page could not be read."""
    if c["domain"] or c["website"]:
        dom = _site(c["domain"] or domain_of(c["website"]))
        return _home(dom) or (dom, f"https://{dom}/", "")
    dom = _from_jobs(con, c["id"])
    if dom:
        return _home(dom) or (dom, f"https://{dom}/", "")
    exact = (_name_tokens(c["name"]) or [""])[-1]  # the whole name, folded: "pwc", "astrazeneca"
    for base in _bases(c):
        for tld in TLDS:
            p = _probe(f"{base}.{tld}")
            if not p:
                continue
            status, final, url, page = p
            if not any(t in _fold(final) for t in _name_tokens(c["name"]) + [base]):
                continue  # redirected to some other site, such as a domain marketplace
            # A short, common name ("Linear", "Flink") is shared by many sites: trust it only as the exact .com,
            # or when the site links to the company's own job board.
            sure = (tld == "com" and base == exact) or len(exact) >= 8 or _links_board(page, c)
            if status < 400 and sure and not _PARKED.search(page) and _names_company(page, c["name"]):
                return final, url, page
            # Big companies often refuse robots (403). Trust only the exact name as a .com address.
            if tld == "com" and base == exact and status in (401, 403, 429, 503) and not _PARKED.search(page):
                return final, url, ""
    return None


# ---------------------------------------------------------------- picking the icon
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z-]+)\s*=\s*["\']([^"\']*)["\']')


def _icons(page: str, base_url: str) -> list[tuple[int, str]]:
    """(rough pixel size, absolute url) for each icon the page lists, biggest first."""
    out = []
    for tag in _LINK.findall(page or ""):
        a = {k.lower(): v for k, v in _ATTR.findall(tag)}
        rel = a.get("rel", "").lower()
        href = html.unescape(a.get("href", "")).strip()
        if "icon" not in rel or "mask-icon" in rel or not href or href.startswith("data:"):
            continue
        sizes = [int(x) for x in re.findall(r"(\d+)x\d+", a.get("sizes", ""))]
        if sizes:
            px = max(sizes)
        elif href.lower().split("?")[0].endswith(".svg") or "svg" in a.get("type", ""):
            px = 256
        elif "apple-touch-icon" in rel:
            px = 180
        else:
            px = 32
        out.append((min(px, 512), urljoin(base_url, href)))
    out.sort(key=lambda t: -t[0])
    return out


def _kind(data: bytes) -> str | None:
    head = data[:600].lstrip()
    if data.startswith(b"\x89PNG"):
        return "png"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"GIF8":
        return "gif"
    if b"<svg" in head.lower():
        return "svg"
    return None


def _pixels(data: bytes, kind: str) -> int:
    try:
        if kind == "png":
            return int.from_bytes(data[16:20], "big")
        if kind == "ico":
            n = int.from_bytes(data[4:6], "little")
            return max((data[6 + 16 * i] or 256) for i in range(min(n, 20)))
        if kind == "gif":
            return int.from_bytes(data[6:8], "little")
    except (IndexError, ValueError):
        return 0
    return 256 if kind == "svg" else 96  # jpg/webp: assume a usable size


def _get_image(url: str):
    try:
        r = _session.get(url, timeout=8, allow_redirects=True, stream=True)
        if r.status_code != 200:
            return None
        data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    except Exception:
        return None
    if not data or len(data) > MAX_BYTES or len(data) < 70:
        return None
    kind = _kind(data)
    return (kind, data, _pixels(data, kind)) if kind else None


def _best_icon(domain: str, home_url: str, page: str):
    cands = [u for _, u in _icons(page, home_url)]
    cands += [f"https://{domain}/apple-touch-icon.png", f"https://{domain}/favicon.ico"]
    best = None
    seen = set()
    for url in cands:
        if url in seen:
            continue
        seen.add(url)
        got = _get_image(url)
        if not got:
            continue
        if got[2] >= 64:
            return got
        if best is None or got[2] > best[2]:
            best = got
    if best is None or best[2] < 64:
        got = _get_image(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")
        if got and got[2] >= 32 and (best is None or got[2] > best[2]):
            best = got
    return best if best and best[2] >= 16 else None


# ---------------------------------------------------------------- fetch and save
def fetch(con, cid: int, force: bool = False) -> Path | None:
    """Find and save this company's logo. Returns its file, or None (and remembers the miss)."""
    if not force and state(cid) != "unknown":
        return path(cid)
    with _lock:
        if cid in _busy:
            return None
        _busy.add(cid)
    try:
        c = con.execute("SELECT id, name, domain, website, ats, slug FROM companies WHERE id = ?", (cid,)).fetchone()
        if c is None:
            return None
        DIR.mkdir(parents=True, exist_ok=True)
        site = find_site(con, c)
        got = _best_icon(*site) if site else None
        for ext in EXTS:
            (DIR / f"{cid}.{ext}").unlink(missing_ok=True)
        if not got:
            (DIR / f"{cid}.miss").write_text(site[0] if site else "", encoding="utf-8")
            return None
        (DIR / f"{cid}.miss").unlink(missing_ok=True)
        out = DIR / f"{cid}.{got[0]}"
        out.write_bytes(got[1])
        (DIR / f"{cid}.site").write_text(site[0], encoding="utf-8")  # which address the logo came from
        return out
    finally:
        with _lock:
            _busy.discard(cid)


def fetch_all(con, everyone: bool = False, force: bool = False, workers: int = 8) -> tuple[int, int, int]:
    """Fetch missing logos. Returns (found, not found, already had)."""
    from . import db
    sql = ("SELECT id FROM companies" if everyone else
           "SELECT DISTINCT company_id FROM jobs WHERE company_id IS NOT NULL AND status NOT IN ('closed','duplicate')")
    ids = [r[0] for r in con.execute(sql)]
    todo = [i for i in ids if force or state(i) == "unknown"]
    had = len(ids) - len(todo)

    def one(cid):
        c2 = db.connect()  # one connection per thread
        try:
            return fetch(c2, cid, force=True) is not None
        finally:
            c2.close()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(one, todo))
    return sum(results), len(results) - sum(results), had
