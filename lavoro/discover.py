"""Building the company list: YC seed, the bundled startup list, ATS detection from a website, slug probing."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import db
from .net import domain_of, get, get_json
from .sources import ATS_FETCHERS

ATS_PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_.-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)")),
    ("workable", re.compile(r"//([A-Za-z0-9-]+)\.workable\.com")),
    ("recruitee", re.compile(r"//([A-Za-z0-9-]+)\.recruitee\.com")),
    ("teamtailor", re.compile(r"//([A-Za-z0-9-]+)\.teamtailor\.com")),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    # Workday: the slug keeps host and site, e.g. astrazeneca.wd3.myworkdayjobs.com/Careers (a locale like en-US is skipped)
    ("workday", re.compile(r"([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?!wday\b)[A-Za-z0-9_-]+)")),
]
BAD_SLUGS = {"embed", "v1", "jobs", "api", "www", "apply", "careers", "app", "j", "static", "assets", "js", "widget", "career"}
CAREER_LINK = re.compile(r"""href=["']([^"']*(?:career|jobs|job-openings|join|karriar|karriär|jobba|work-with-us|hiring|openings)[^"']*)["']""", re.I)


def find_ats_in_html(html: str) -> tuple[str, str] | None:
    for ats, pat in ATS_PATTERNS:
        for m in pat.finditer(html):
            if ats == "workday":
                host, *rest = m.group(1).split("/")
                return ats, f"{host.lower()}/{rest[-1]}"
            slug = m.group(1).strip("/").split("/")[0].split("?")[0]
            if slug and slug.lower() not in BAD_SLUGS:
                return ats, slug
    return None


def detect_ats(website: str) -> tuple[str, str] | None:
    """Look at the homepage and up to 3 careers-looking pages for a known ATS link."""
    if not website:
        return None
    if "://" not in website:
        website = "https://" + website
    r = get(website, timeout=15)
    if r is None or r.status_code >= 400:
        return None
    html = r.text
    # A SuccessFactors career site (jobs.volvogroup.com and the like) loads the "j2w" script. Check it first:
    # such sites often link to a subsidiary's board elsewhere on the page.
    if "j2w" in html:
        host = urlparse(r.url).hostname
        if host and ATS_FETCHERS["successfactors"](host):
            return "successfactors", host
    hit = find_ats_in_html(r.url) or find_ats_in_html(html)
    if hit:
        return hit
    seen, pages = set(), []
    for href in CAREER_LINK.findall(html):
        u = urljoin(r.url, href)
        if u not in seen and urlparse(u).scheme in ("http", "https"):
            seen.add(u)
            pages.append(u)
    for u in pages[:3]:
        p = get(u, timeout=15)
        if p is None or p.status_code >= 400:
            continue
        hit = find_ats_in_html(p.text) or find_ats_in_html(p.url)
        if hit:
            return hit
        # Teamtailor career sites on a custom domain still serve /jobs.rss
        if "teamtailor" in p.text.lower():
            host = urlparse(p.url).hostname
            if host and ATS_FETCHERS["teamtailor"](host):
                return "teamtailor", host
    if "teamtailor" in html.lower():
        host = urlparse(r.url).hostname
        if host and ATS_FETCHERS["teamtailor"](host):
            return "teamtailor", host
    return None


def slug_candidates(name: str, domain: str = "") -> list[str]:
    base = re.sub(r"\b(ab|inc|ltd|gmbh|as|oy|aps|labs?|technologies|technology|ai)\b\.?", "", name.lower()).strip()
    c = [re.sub(r"[^a-z0-9]", "", base), re.sub(r"[^a-z0-9]+", "-", base).strip("-"),
         re.sub(r"[^a-z0-9]", "", name.lower())]
    if domain:
        c.append(domain.split(".")[0])
    out = []
    for s in c:
        if s and s not in out:
            out.append(s)
    return out


def probe(name: str, domain: str = "", ats_list: list[str] | None = None) -> tuple[str, str, int] | None:
    """Try likely slugs on every ATS. Returns (ats, slug, job_count) for the first board with jobs."""
    ats_list = ats_list or list(ATS_FETCHERS)
    tries = [(a, s) for s in slug_candidates(name, domain) for a in ats_list]

    def check(t):
        a, s = t
        try:
            jobs = ATS_FETCHERS[a](s, name)
        except Exception:
            jobs = []
        return a, s, len(jobs)

    with ThreadPoolExecutor(8) as ex:
        for a, s, n in ex.map(check, tries):
            if n:
                return a, s, n
    return None


def seed_yc(con, regions: list[str]) -> int:
    data = get_json("https://yc-oss.github.io/api/companies/hiring.json", timeout=60)
    if not data:
        print("Could not download the YC hiring list.")
        return 0
    want = {r.lower() for r in regions}
    n = 0
    for c in data:
        regs = {r.lower() for r in c.get("regions") or []}
        locs = (c.get("all_locations") or "").lower()
        if want and not (regs & want or any(w in locs for w in want)):
            continue
        if c.get("status") not in (None, "Active"):
            continue
        dom = domain_of(c.get("website"))
        exists = con.execute("SELECT 1 FROM companies WHERE domain=?", (dom,)).fetchone()
        info = json.dumps({"one_liner": c.get("one_liner"), "team_size": c.get("team_size"), "batch": c.get("batch"),
                           "locations": c.get("all_locations"), "yc_slug": c.get("slug"), "yc_url": c.get("url")},
                          ensure_ascii=False)
        db.upsert_company(con, name=c["name"], website=c.get("website"), domain=dom, source="yc", info=info)
        n += 0 if exists else 1
    con.commit()
    db.merge_duplicate_companies(con)
    return n


LISTS_DIR = Path(__file__).parent / "lists"


def seed_startups(con) -> int:
    """Add the bundled list of startups that are hiring, each with its job board (lavoro/lists/startups.csv:
    name, ats, slug). Returns how many companies are new."""
    path = LISTS_DIR / "startups.csv"
    if not path.exists():
        print("The bundled startup list is missing: lavoro/lists/startups.csv")
        return 0
    n = 0
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["ats"] not in ATS_FETCHERS or not row["slug"]:
                continue
            if con.execute("SELECT 1 FROM companies WHERE ats=? AND slug=?", (row["ats"], row["slug"])).fetchone():
                continue
            existed = con.execute("SELECT 1 FROM companies WHERE lower(name)=lower(?)", (row["name"],)).fetchone()
            try:
                db.upsert_company(con, name=row["name"], ats=row["ats"], slug=row["slug"], source="startups")
            except sqlite3.IntegrityError:  # a same-name company already holds this board under another row
                continue
            n += 0 if existed else 1
    con.commit()
    db.merge_duplicate_companies(con)
    return n


def detect_all(con, limit: int = 200) -> tuple[int, int]:
    """Find the ATS board for companies that don't have one yet."""
    rows = con.execute(
        "SELECT id, name, website, domain, info FROM companies WHERE ats IS NULL ORDER BY id LIMIT ?", (limit,)
    ).fetchall()

    def work(row):
        hit = detect_ats(row["website"])
        if not hit:
            yc_slug = (json.loads(row["info"] or "{}") or {}).get("yc_slug", "")
            p = probe(yc_slug or row["name"], row["domain"] or "", ["ashby", "greenhouse", "lever", "workable"])
            hit = (p[0], p[1]) if p else None
        return row["id"], hit

    found = 0
    with ThreadPoolExecutor(6) as ex:
        for cid, hit in ex.map(work, rows):
            if hit:
                clash = con.execute("SELECT id FROM companies WHERE ats=? AND slug=? AND id<>?", (hit[0], hit[1], cid)).fetchone()
                if clash:
                    con.execute("UPDATE companies SET ats='none', checked_at=? WHERE id=?", (db.now(), cid))
                else:
                    con.execute("UPDATE companies SET ats=?, slug=?, checked_at=? WHERE id=?", (hit[0], hit[1], db.now(), cid))
                    found += 1
            else:
                con.execute("UPDATE companies SET ats='none', checked_at=? WHERE id=?", (db.now(), cid))
    con.commit()
    return len(rows), found


ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "teamtailor.com", "smartrecruiters.com",
             "myworkdayjobs.com")
SUPPORTED = "Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, SmartRecruiters, Workday or SuccessFactors"


class AddError(Exception):
    """A message for the person adding the company, in plain words."""


def add_company(con, text: str, name: str | None = None) -> dict:
    """Add one company from its name, its website, or its job-board link, then fetch its open roles.

    Returns {"id", "name", "ats", "roles", "new", "existed"}. Raises AddError with a readable reason.
    """
    text = (text or "").strip()
    if not text:
        raise AddError("Type a company name or paste a link.")
    if len(text) > 300:
        raise AddError("That is too long for a company name or a link.")
    is_url = "://" in text or (" " not in text and re.search(r"\.[a-z]{2,}(/|$)", text, re.I))
    if is_url:
        url = text if "://" in text else "https://" + text
        if urlparse(url).scheme not in ("http", "https") or not urlparse(url).hostname:
            raise AddError("That link does not look right. Paste the full address, like https://example.com/careers.")
        dom = domain_of(url)
        if "linkedin." in dom:
            raise AddError("Lavoro does not read LinkedIn. Paste the company's own website, or type its name.")
        on_board = any(dom.endswith(h) for h in ATS_HOSTS)
        hit = find_ats_in_html(url) or detect_ats(url)
        if not name:
            if on_board and hit and "." not in hit[1]:
                name = hit[1].replace("-", " ").replace("_", " ").title()
            else:
                labels = [x for x in dom.split(".") if x not in ("www", "career", "careers", "jobs", "join", "work", "karriar")]
                name = labels[0].title() if labels else dom
        if not hit and not on_board:
            p = probe(name, dom)
            hit = (p[0], p[1]) if p else None
        website, domain = (None, None) if on_board else (url, dom)
    else:
        name = name or text
        # Already known with a board? Reuse it rather than probing again.
        row = con.execute("SELECT id, name, ats FROM companies WHERE lower(name)=lower(?) AND ats IS NOT NULL AND ats<>'none'",
                          (name,)).fetchone()
        if row:
            n = con.execute("SELECT count(*) FROM jobs WHERE company_id=? AND status NOT IN ('closed','duplicate')", (row["id"],)).fetchone()[0]
            return {"id": row["id"], "name": row["name"], "ats": row["ats"], "roles": n, "new": 0, "existed": True}
        p = probe(name)
        hit = (p[0], p[1]) if p else None
        website = domain = None
    if not hit:
        tip = "Try pasting the link to their careers page." if not is_url else f"Their jobs may be on a board Lavoro cannot read yet. It reads {SUPPORTED}."
        raise AddError(f"Could not find a job board for {name}. {tip}")

    existed = con.execute("SELECT id FROM companies WHERE ats=? AND slug=?", hit).fetchone() is not None
    cid = db.upsert_company(con, name=name, website=website, domain=domain, ats=hit[0], slug=hit[1],
                            source="manual")
    jobs = ATS_FETCHERS[hit[0]](hit[1], name) or []
    dom_row = con.execute("SELECT domain FROM companies WHERE id=?", (cid,)).fetchone()
    new = 0
    for j in jobs:
        j["company_id"], j["domain"] = cid, dom_row["domain"]
        new += db.upsert_job(con, j)
    con.execute("UPDATE companies SET checked_at=? WHERE id=?", (db.now(), cid))
    con.commit()
    real = con.execute("SELECT name FROM companies WHERE id=?", (cid,)).fetchone()["name"]
    return {"id": cid, "name": real, "ats": hit[0], "roles": len(jobs), "new": new, "existed": existed}
