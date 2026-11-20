"""First-run setup: turn a CV file or a portfolio link into profile.md, and save search preferences to config.yaml.

Everything stays on this computer. CVs are kept in data/uploads/ (gitignored). LinkedIn is never fetched: its terms
forbid scraping, so the user is asked for LinkedIn's "Save to PDF" export instead.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel

from . import llm
from .config import ROOT
from .net import domain_of, get, html_to_text

UPLOADS = ROOT / "data" / "uploads"
MAX_UPLOAD = 15 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}


class SetupError(Exception):
    """A problem the user can fix; the message is shown on the page."""


# ---------------------------------------------------------------- does this person still need setup?
def _strip_comments(s: str) -> str:
    return re.sub(r"<!--.*?-->", "", s, flags=re.S).strip()


def needs_setup(cfg) -> bool:
    p = ROOT / cfg.get("me", {}).get("profile_file", "profile.md")
    ex = ROOT / "profile.example.md"
    if not p.exists():
        return True
    body = _strip_comments(p.read_text(encoding="utf-8"))
    if ex.exists() and body == _strip_comments(ex.read_text(encoding="utf-8")):
        return True
    return len(body) < 200


# ---------------------------------------------------------------- reading the source
def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return unescape(re.sub(r"<[^>]+>", "", xml)).strip()


def save_upload(name: str, data: bytes) -> Path:
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise SetupError("Use a PDF, Word (.docx) or text file.")
    if len(data) > MAX_UPLOAD:
        raise SetupError("That file is over 15 MB. Export a smaller PDF.")
    if not data:
        raise SetupError("That file is empty.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:60] or "cv"
    path = UPLOADS / f"{datetime.now():%Y%m%d-%H%M%S}-{safe}{ext}"
    path.write_bytes(data)
    return path


def _is_linkedin(url: str) -> bool:
    return "linkedin.com" in domain_of(url)


def read_site(url: str, max_pages: int = 8, max_chars: int = 60_000) -> str:
    """Text of a public site: the page plus a few same-site pages (about, work, projects)."""
    if "://" not in url:
        url = "https://" + url
    if _is_linkedin(url):
        raise SetupError("LinkedIn doesn't allow other tools to read profiles. On your LinkedIn profile, "
                         "choose More → Save to PDF, then drop that PDF here.")
    first = get(url, timeout=20)
    if first is None or first.status_code >= 400:
        raise SetupError("Couldn't open that link. Check it opens in your browser, or drop your CV instead.")
    host = urlparse(first.url).hostname
    pages, seen, texts = [first.url], {first.url.rstrip("/")}, []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', first.text):
        u = urljoin(first.url, href)
        pu = urlparse(u)
        if pu.hostname != host or re.search(r"\.(png|jpe?g|gif|svg|webp|pdf|css|js|ico|xml|json)$", pu.path, re.I):
            continue
        key = u.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            pages.append(u)
    for u in pages[:max_pages]:
        r = first if u == first.url else get(u, timeout=20)
        if r is None or r.status_code >= 400:
            continue
        html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", r.text)
        t = html_to_text(html)
        # Sites built with page builders often repeat each block; collapse exact repeats.
        lines, out = [], set()
        for line in t.splitlines():
            if line.strip() and line.strip() not in out:
                out.add(line.strip())
                lines.append(line)
        texts.append(f"=== {u}\n" + "\n".join(lines))
        if sum(map(len, texts)) > max_chars:
            break
    text = "\n\n".join(texts)[:max_chars]
    # Profile links live in hrefs, not in the visible text. These are only recorded, never fetched.
    socials = sorted({h.split("?")[0].rstrip("/") + "/" for h in re.findall(r'href=["\'](https?://[^"\']+)["\']', first.text)
                      if re.search(r"(linkedin\.com/in/|github\.com/|dribbble\.com/|behance\.net/)", h)})
    if socials:
        text += "\n\nProfile links on the site: " + ", ".join(socials)
    if len(text) < 200:
        raise SetupError("That page has almost no readable text. Drop your CV instead.")
    return text


# ---------------------------------------------------------------- Claude turns it into a profile
class ProfileDraft(BaseModel):
    name: str                       # full name, or ""
    first_name: str
    headline: str                   # one line, in their words where possible
    location: str                   # city, country — or ""
    in_sweden: bool
    linkedin_url: str               # only if printed in the source, else ""
    portfolio_url: str              # only if printed in the source, else ""
    suggested_titles: list[str]     # 4–10 job-title phrases to search for, lowercase
    suggested_locations: list[str]  # single place names, lowercase, no commas or brackets: "stockholm", "sweden", "sverige"
    seniority: str                  # "student/graduate", "junior", "mid", "senior"
    markdown: str                   # the full profile.md


PROFILE_SYSTEM = """You turn a person's CV or portfolio into the profile file a job-search tool uses to score jobs
and draft emails for them. Rules:
- Use ONLY facts stated in the source. Never invent employers, dates, numbers, skills or languages.
- Keep concrete results and numbers exactly as written.
- Where something useful is missing (graduation date, languages, tools, work permit), write a line starting
  with "TODO:" so the person can fill it in.
- Markdown with these headings, in order: # My profile, ## Headline, ## Education, ## Experience and projects,
  ## Skills, ## Languages, ## What I want next, ## Links. Under projects, one ### heading per job or project.
- Do not include phone numbers, home addresses, ID numbers or dates of birth.
- suggested_titles: realistic job-title phrases this person should search for given their field and level.
- suggested_locations: single place names only (city, then country in English and the local language), e.g.
  "stockholm", "sweden", "sverige". No commas, no brackets, no "remote" (remote is a separate setting).
Return the JSON object only."""


def build_profile(*, path: Path | None = None, url: str | None = None) -> ProfileDraft:
    if not llm.backend():
        raise SetupError("Claude isn't available. Open a terminal, run `claude` once to sign in, then try again.")
    pdf, source = None, ""
    if path is not None:
        ext = path.suffix.lower()
        if ext == ".pdf":
            pdf = str(path)
            source = "SOURCE: the attached CV (cv.pdf)."
        elif ext == ".docx":
            source = "SOURCE (CV, Word):\n" + _docx_text(path)
        else:
            source = "SOURCE (CV, text):\n" + path.read_text(encoding="utf-8", errors="ignore")
    elif url:
        source = f"SOURCE (public portfolio site {url}):\n" + read_site(url)
        if "portfolio" not in source.lower():
            source += f"\n\nThe portfolio URL is {url}."
    else:
        raise SetupError("Drop a CV or paste a link.")
    draft = llm.parse(effort="medium", system=PROFILE_SYSTEM, user=source, schema=ProfileDraft, max_tokens=16000, pdf=pdf)
    if draft is None or len(draft.markdown) < 120:
        raise SetupError("Claude couldn't read that. Try a different file (a text-based PDF works best).")
    if url and not draft.portfolio_url and not _is_linkedin(url):
        draft.portfolio_url = url
    return _tidy(draft)


def _tidy(d: ProfileDraft) -> ProfileDraft:
    """Undo HTML escapes that leak through page text, and keep locations as plain place names."""
    for f in ("name", "first_name", "headline", "location", "markdown"):
        v = getattr(d, f)
        for _ in range(3):  # "&amp;amp;" needs more than one pass
            v2 = unescape(v)
            if v2 == v:
                break
            v = v2
        setattr(d, f, v)
    places = []
    for loc in d.suggested_locations:
        for part in re.split(r"[,/()]+", loc.lower()):
            part = part.strip()
            if part and part != "remote" and not part.startswith("remote ") and part not in places:
                places.append(part)
    d.suggested_locations = places[:12]
    return d


def save_profile(markdown: str, source_note: str) -> Path:
    p = ROOT / "profile.md"
    if p.exists():
        backup = ROOT / "data" / f"profile.backup-{datetime.now():%Y%m%d-%H%M%S}.md"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)
    header = (f"<!--\nPRIVATE: gitignored, never committed. Built by Lavoro from {source_note} on {datetime.now():%Y-%m-%d}.\n"
              "Only facts from that source. Fill in the TODO lines: Claude never invents them.\n-->\n\n")
    p.write_text(header + markdown.strip() + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- editing config.yaml without losing comments
def _flow(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)  # JSON is valid YAML, and keeps the rest of the file untouched


_KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):(.*)$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _content(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def set_yaml(text: str, path: list[str], value) -> str:
    """Replace the value at a nested key (e.g. ["search", "jobtech", "enabled"]), keeping comments and layout."""
    lines = text.splitlines()
    lo, hi = 0, len(lines)
    for depth, key in enumerate(path):
        keys = [(i, _KEY.match(lines[i])) for i in range(lo, hi) if _KEY.match(lines[i])]
        if not keys:
            raise KeyError(".".join(path))
        child = min(len(m.group(1)) for _, m in keys)  # indent of this level's keys
        hit = next(((i, m) for i, m in keys if len(m.group(1)) == child and m.group(2) == key), None)
        if hit is None:
            raise KeyError(".".join(path))
        i, m = hit
        end = i + 1  # this key's block: following lines indented deeper (blank lines and comments included)
        while end < hi and (not _content(lines[end]) or _indent(lines[end]) > child):
            end += 1
        while end > i + 1 and not _content(lines[end - 1]):  # leave trailing blanks/comments to the next key
            end -= 1
        if depth < len(path) - 1:
            lo, hi = i + 1, end
            continue
        old = re.match(r"""^\s*("[^"]*"|'[^']*'|\[[^\]]*\]|[^#]*?)(\s*#.*)?$""", m.group(3))
        comment = (old.group(2) or "") if old else ""
        new = f"{m.group(1)}{key}: {_flow(value)}"
        lines[i] = (new.ljust(len(lines[i]) - len(comment)) + comment) if comment else new
        del lines[i + 1:end]  # an old block list under the key
    return "\n".join(lines) + "\n"


class Preferences(BaseModel):
    name: str = ""
    portfolio: str = ""
    linkedin: str = ""
    titles: list[str] = []
    locations: list[str] = []
    remote_ok: bool = True
    in_sweden: bool = False
    keep_queries: bool = False      # the Profile page: leave hand-tuned Platsbanken searches alone


def _clean_list(xs: list[str], limit: int = 30) -> list[str]:
    out = []
    for x in xs:
        x = re.sub(r"\s+", " ", str(x)).strip().lower()[:60]
        if x and x not in out:
            out.append(x)
    return out[:limit]


def save_preferences(p: Preferences) -> None:
    cfg_path = ROOT / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    places = [part for loc in p.locations for part in re.split(r"[,/()]+", str(loc))]
    titles = _clean_list(p.titles, 100)
    locs = [x for x in _clean_list(places, 100) if x != "remote" and not x.startswith("remote ")]
    if not titles:
        raise SetupError("Add at least one role to search for.")
    if p.linkedin and not _is_linkedin(p.linkedin):
        raise SetupError("That LinkedIn link doesn't look like linkedin.com.")
    edits = [
        (["me", "name"], p.name.strip()),
        (["me", "portfolio"], p.portfolio.strip()),
        (["me", "linkedin"], p.linkedin.strip()),
        (["search", "titles_include"], titles),
        (["search", "locations_include"], locs or ["remote"]),
        (["search", "remote_ok"], bool(p.remote_ok)),
        (["search", "jobtech", "enabled"], bool(p.in_sweden)),
    ]
    if p.in_sweden:
        import yaml
        current = ((yaml.safe_load(text) or {}).get("search", {}).get("jobtech") or {}).get("queries")
        if not (p.keep_queries and current):  # setup starts them from the roles; later saves keep yours
            edits.append((["search", "jobtech", "queries"], titles[:8]))
    for path, value in edits:
        try:
            text = set_yaml(text, path, value)
        except KeyError:
            if path == ["me", "portfolio"]:  # older config without the portfolio key
                text = text.replace("\n  linkedin:", f"\n  portfolio: {_flow(value)}\n  linkedin:", 1)
            else:
                raise
    import yaml
    yaml.safe_load(text)  # never write a file the next run can't read
    (ROOT / "data").mkdir(exist_ok=True)
    shutil.copy2(cfg_path, ROOT / "data" / "config.backup.yaml")
    cfg_path.write_text(text, encoding="utf-8")


def set_region(con, name: str) -> int:
    """Save search.region in config.yaml and send jobs the old region skipped back through the filter.

    Returns how many earlier jobs will be checked again on the next run.
    """
    from . import regions
    if name not in regions.LABELS:
        raise SetupError(f"Unknown region. Choose one of: {', '.join(regions.LABELS)}.")
    cfg_path = ROOT / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    try:
        text = set_yaml(text, ["search", "region"], name)
    except KeyError:  # older config without the key: add it as the first line of the search section
        text = re.sub(r"(?m)^search:\s*$", "search:\n  region: " + _flow(name) +
                      "                 # sweden | nordics | europe | worldwide | custom (uses locations_include)", text, count=1)
    import yaml
    yaml.safe_load(text)
    cfg_path.write_text(text, encoding="utf-8")
    cur = con.execute("UPDATE jobs SET status='new', passed_filter=0 WHERE status='skipped' AND score IS NULL")
    con.commit()
    # New region, new companies: make the next run refresh the YC list for it instead of waiting for the weekly refresh.
    (ROOT / "data" / "last_discover.txt").unlink(missing_ok=True)
    return cur.rowcount
