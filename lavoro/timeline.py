"""What the welcome page's live timeline shows: real numbers from the database while a run goes on."""
from __future__ import annotations

import json
import re

from . import db, regions
from .config import min_score

SOURCE_LABEL = {
    "greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "workable": "Workable", "recruitee": "Recruitee",
    "teamtailor": "Teamtailor", "smartrecruiters": "SmartRecruiters", "workday": "Workday",
    "successfactors": "SuccessFactors", "jobtech": "Platsbanken", "hn": "Hacker News", "arbeitnow": "Arbeitnow",
    "web": "Web search",
}


def _profile_bits(cfg) -> dict:
    """Name, headline and a few chips from profile.md (employers/projects and skills)."""
    from .config import read_profile
    md = read_profile(cfg)
    m = re.search(r"^## Headline\s*\n+(.+?)(?:\n\s*\n|\n#|\Z)", md, re.M | re.S)
    head = " ".join(m.group(1).split()) if m else ""
    if len(head) > 170:  # first sentence, or a clean cut at a word
        first = re.match(r"(.{40,170}?[.!?])\s", head + " ")
        head = first.group(1) if first else head[:170].rsplit(" ", 1)[0] + "…"
    orgs = re.findall(r"^### ([^\n:(]+)", md, re.M)
    skills_block = re.search(r"^## Skills\s*\n(.*?)(?=^## |\Z)", md, re.M | re.S)
    skills = []
    if skills_block:
        for part in re.split(r"[,;\n•]", re.sub(r"\*\*[^*]+:\*\*", "", skills_block.group(1))):
            part = part.strip(" -*.")
            if 2 < len(part) <= 32 and part not in skills:
                skills.append(part)
    return {"name": cfg.get("me", {}).get("name", ""), "headline": head,
            "orgs": [o.strip() for o in orgs][:6], "skills": skills[:8]}


def data(cfg, started: str | None) -> dict:
    con = db.connect()
    try:
        s = cfg.get("search", {})
        floor = min_score(cfg)
        sources = con.execute(
            "SELECT coalesce(nullif(c.ats,'none'), j.source) AS src, count(*) AS n FROM jobs j "
            "LEFT JOIN companies c ON c.id = j.company_id WHERE j.status NOT IN ('closed','duplicate') GROUP BY src ORDER BY n DESC").fetchall()
        boards = con.execute("SELECT count(*) FROM companies WHERE ats IS NOT NULL AND ats <> 'none'").fetchone()[0]
        good = con.execute(
            "SELECT key, title, company, company_id, location, score, url, posted_at, first_seen FROM jobs "
            "WHERE score >= ? AND status NOT IN ('closed','skipped','sent','duplicate') ORDER BY score DESC, first_seen DESC", (floor,)).fetchall()
        people = con.execute(
            "SELECT c.name, c.title, c.email, c.email_status, j.company FROM contacts c JOIN jobs j ON j.key = c.job_key "
            "WHERE j.status NOT IN ('closed','skipped') AND c.email IS NOT NULL AND c.email <> '' "
            "ORDER BY CASE WHEN c.name IS NULL OR c.name = '' THEN 1 ELSE 0 END, "
            "CASE c.email_status WHEN 'listed_in_ad' THEN 0 WHEN 'published' THEN 1 WHEN 'verified' THEN 2 "
            "WHEN 'likely' THEN 3 ELSE 4 END, c.created_at DESC").fetchall()
        seen, best = set(), []          # one person per company: a named one before an ad's bare address
        for p in people:
            if p["company"] not in seen:
                seen.add(p["company"])
                best.append(p)
        people = best
        drafts = con.execute(
            "SELECT d.subject, d.to_email, j.company, j.title FROM drafts d JOIN jobs j ON j.key = d.job_key "
            "WHERE j.status = 'drafted' ORDER BY d.created_at DESC").fetchall()
        raises = con.execute(
            "SELECT f.name, f.amount, f.round, f.summary, f.company_id, "
            "(SELECT count(*) FROM jobs j WHERE j.company_id = f.company_id AND j.status NOT IN ('closed','duplicate')) AS roles "
            "FROM funding f ORDER BY f.found_at DESC, f.announced DESC LIMIT 8").fetchall()
        reg = regions.resolve(cfg)
        return {
            "profile": _profile_bits(cfg),
            "prefs": {"titles": s.get("titles_include", [])[:6], "region": regions.LABELS[reg["name"]],
                      "places": (reg["places"] or [])[:4], "remote": bool(s.get("remote_ok", True)),
                      "more_titles": max(0, len(s.get("titles_include", [])) - 6)},
            "sources": [{"name": SOURCE_LABEL.get(r["src"], r["src"].title()), "n": r["n"]} for r in sources],
            "total": sum(r["n"] for r in sources), "boards": boards,
            "jobs": [dict(r) for r in good[:12]], "jobs_count": len(good), "min_score": floor,
            "people": [dict(r) for r in people[:5]], "people_count": len(people), "people_companies": len(people),
            "raises": [dict(r) for r in raises],
            "drafts": [dict(r) for r in drafts[:4]], "drafts_count": len(drafts),
            "started": started,
        }
    finally:
        con.close()
