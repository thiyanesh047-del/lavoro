"""Two searches Claude runs on the open web, on your Claude plan:

  search_jobs   — job postings the boards Lavoro reads directly might miss (company career pages, LinkedIn job
                  listings, local job sites). Claude only sees search results: it never opens a LinkedIn page,
                  and Lavoro keeps a LinkedIn result as a title, a company and a link for you to open yourself.
  find_raises   — companies in your region that announced a funding round in the last weeks. They tend to hire
                  next, often before posting the job. Lavoro then looks for their job board.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from pydantic import BaseModel

from . import db, llm, regions
from .config import has_claude, read_profile
from .net import domain_of, get


# ---------------------------------------------------------------- job postings
class WebJob(BaseModel):
    title: str
    company: str
    location: str        # as the result states it, or ""
    url: str             # exactly as it appears in the search results
    site: str            # the site that hosts the posting, e.g. "linkedin.com" or "careers.example.com"
    posted: str          # what the result says about the date ("3 days ago", "2026-11-12"), or ""
    summary: str         # one or two sentences from the result about the role; no invented detail


class WebJobs(BaseModel):
    jobs: list[WebJob]


JOBS_SYSTEM = """You look for open job postings on the public web for one person, using web search only.
Rules:
- Run several searches (up to 8): the person's target titles with their places, in English and, where it fits, in
  the local language. Include searches limited to LinkedIn job listings (site:linkedin.com/jobs/view) and searches
  that find company career pages.
- Use only what the search results show: their titles, snippets and URLs. Do not open or fetch any page.
- Return only single job postings that look open and recent (posted in the last 30 days when the result shows a date).
  Skip list pages, "top 10 jobs" articles, salary pages, course ads and duplicates of the same posting.
- Copy each URL exactly from the results. Never make up a posting, a company, a location or a URL.
- Prefer roles at the person's level; skip roles whose title says senior, lead, principal, staff, head or director.
- If nothing fits, return an empty list."""


# LinkedIn numbers job ads in order. Search engines keep old ads indexed long after they close, so an ad with a
# low number is an old one. 4,300,000,000 was reached around mid-2025; raise it over time (search.web.linkedin_min_id).
LINKEDIN_MIN_ID = 4_300_000_000
_LI_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*?-)?(\d{9,})")


def _looks_current(url: str, min_id: int) -> bool:
    """Drop old LinkedIn ads (by their number) and pages that no longer exist. LinkedIn itself is never opened."""
    m = _LI_ID.search(url)
    if "linkedin." in url:
        return bool(m) and int(m.group(1)) >= min_id
    r = get(url, timeout=15)
    return r is not None and r.status_code < 400


def _job_key(url: str) -> str:
    return "web:" + hashlib.sha1(url.strip().lower().encode()).hexdigest()[:16]


def search_jobs(con, cfg) -> tuple[int, int]:
    """Returns (postings found, new ones saved)."""
    s = cfg.get("search", {})
    w = s.get("web", {})
    if not w.get("enabled", True) or not has_claude():
        return 0, 0
    reg = regions.resolve(cfg)
    titles = [t for t in s.get("titles_include", []) if len(t) > 3][:10]
    places = reg["places"][:12] if reg["places"] else ["anywhere"]
    user = (f"TARGET TITLES: {', '.join(titles)}\n"
            f"PLACES: {', '.join(places)} (region: {regions.LABELS[reg['name']]})\n"
            f"REMOTE OK: {'yes, within ' + regions.LABELS[reg['name']] if s.get('remote_ok', True) else 'no'}\n"
            f"RETURN AT MOST: {int(w.get('max_results', 25))} postings\n\n"
            f"PERSON (for judging fit and level):\n{read_profile(cfg)[:3000]}")
    res = llm.parse(effort=w.get("effort", "low"), system=JOBS_SYSTEM, user=user, schema=WebJobs, web="search")
    if not res:
        return 0, 0
    new = 0
    for j in res.jobs[: int(w.get("max_results", 25))]:
        url = j.url.strip()
        if not url.startswith(("http://", "https://")) or not j.title.strip() or not j.company.strip():
            continue
        if not _looks_current(url, int(w.get("linkedin_min_id", LINKEDIN_MIN_ID))):
            continue
        # The same role may already be in from the company's own board.
        if con.execute("SELECT 1 FROM jobs WHERE lower(company)=lower(?) AND lower(title)=lower(?) AND status<>'closed'",
                       (j.company.strip(), j.title.strip())).fetchone():
            continue
        site = j.site or domain_of(url)
        desc = (f"{j.summary.strip()}\n\nFound by web search on {site}."
                + (f" Posted: {j.posted}." if j.posted else "")
                + (" Open the link to read the full ad." if "linkedin." in site else ""))
        new += db.upsert_job(con, dict(
            key=_job_key(url), source="web", company=j.company.strip(), title=j.title.strip(), location=j.location.strip(),
            remote="remote" in f"{j.location} {j.title}".lower(), department=None, url=url, salary=None,
            description=desc, posted_at=None, ad_contacts=[]))
    con.commit()
    return len(res.jobs), new


# ---------------------------------------------------------------- recently funded companies
class Raise(BaseModel):
    company: str
    website: str         # the company's own site, "" if the results do not show it
    amount: str          # e.g. "$3.1M", "€12M", "" if not stated
    round: str           # e.g. "Seed", "Series A", "" if not stated
    announced: str       # YYYY-MM-DD if shown, else ""
    what_they_do: str    # one short sentence
    source_url: str      # the article or announcement, copied exactly from the results


class Raises(BaseModel):
    raises: list[Raise]


RAISES_SYSTEM = """You find companies that announced a funding round recently, using web search.
Rules:
- Look for rounds announced in the last 30 days by companies based in, or hiring in, the given region.
  Search funding news (for example "raises seed round", "Series A", "tar in kapital" for Sweden) for the region.
- Prefer companies whose work fits the person's field (given below), so they are likely to hire someone like them.
- Use only facts the results show. Copy URLs exactly. Never invent a company, an amount, a date or a website.
- Return at most the number asked for. If you find none, return an empty list."""


def find_raises(con, cfg, force: bool = False) -> tuple[int, int]:
    """Returns (raises found, companies with a job board added). Runs once a week unless forced."""
    f = cfg.get("search", {}).get("funding", {})
    if not f.get("enabled", True) or not has_claude():
        return 0, 0
    stamp = db.DB_PATH.parent / "last_funding.txt"
    days = f.get("refresh_days", 7)
    if not force and stamp.exists() and time.time() - stamp.stat().st_mtime < days * 86400:
        return 0, 0
    reg = regions.resolve(cfg)
    titles = cfg.get("search", {}).get("titles_include", [])[:8]
    user = (f"REGION: {regions.LABELS[reg['name']]} ({', '.join((reg['places'] or ['anywhere'])[:10])})\n"
            f"PERSON'S FIELD: {', '.join(titles)}\n"
            f"RETURN AT MOST: {int(f.get('max', 8))} companies\n\n"
            f"PERSON:\n{read_profile(cfg)[:2000]}")
    res = llm.parse(effort=f.get("effort", "low"), system=RAISES_SYSTEM, user=user, schema=Raises, web="search")
    stamp.write_text(db.now(), encoding="utf-8")
    if not res:
        return 0, 0
    from . import discover
    boards = 0
    for r in res.raises[: int(f.get("max", 8))]:
        name = r.company.strip()
        if not name:
            continue
        cid = None
        site = r.website.strip()
        if site and "linkedin." not in site:
            try:
                got = discover.add_company(con, site, name)
                cid, boards = got["id"], boards + 1
            except Exception:
                pass
        if cid is None:
            cid = db.upsert_company(con, name=name, website=site or None, domain=domain_of(site) or None, source="funding",
                                    info=json.dumps({"one_liner": r.what_they_do}, ensure_ascii=False))
        con.execute("""INSERT INTO funding(company_id, name, amount, round, announced, summary, source_url, found_at)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(name, round) DO UPDATE SET company_id=excluded.company_id, amount=excluded.amount,
                         announced=excluded.announced, summary=excluded.summary, source_url=excluded.source_url""",
                    (cid, name, r.amount, r.round, r.announced, r.what_they_do, r.source_url, db.now()))
    con.commit()
    return len(res.raises), boards
