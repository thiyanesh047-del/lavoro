"""Filtering and scoring jobs against your profile."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel

from . import llm, regions
from .config import has_claude, read_profile
from .sources import fill_description


def _has_any(text: str, words: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(rf"(?<![a-zåäö]){re.escape(w.lower())}(?![a-zåäö])", t) for w in words)


def _age_ok(posted: str | None, max_days: int) -> bool:
    if not posted:
        return True
    try:
        d = datetime.fromisoformat(posted.replace("Z", "+00:00").replace(" UTC", "+00:00"))
    except ValueError:
        return True
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d >= datetime.now(timezone.utc) - timedelta(days=max_days)


def passes_filter(job, s: dict, region: dict | None = None) -> bool:
    """`region` is regions.resolve(cfg): the places and remote wording that count. None = the plain config lists."""
    if region is None:
        region = {"places": s.get("locations_include") or [], "remote": s.get("remote_regions") or [], "any_place": False}
    title = job["title"] or ""
    if s.get("titles_include") and not _has_any(title, s["titles_include"]):
        return False
    if _has_any(title, s.get("titles_exclude") or []):
        return False
    if _has_any(job["company"] or "", s.get("companies_exclude") or []):
        return False
    loc = (job["location"] or "").lower()
    loc_ok = region.get("any_place") or _has_any(loc, region["places"])
    if not loc_ok and s.get("remote_ok") and (job["remote"] or "remote" in loc):
        # Remote with no region named, or a region we accept (e.g. "Remote - EMEA").
        loc_ok = (not re.sub(r"[^a-z]", "", loc.replace("remote", ""))) or _has_any(loc, region["remote"])
    if not loc_ok:
        return False
    return _age_ok(job["posted_at"], s.get("max_age_days", 30))


AGGREGATORS = ("jobtech", "arbeitnow", "hn", "web")   # feeds that repeat ads from companies' own boards


def _norm(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def mark_duplicates(con) -> int:
    """The same ad from a feed (Platsbanken, web search...) and from the company's own board: keep the board's copy.
    Same title, and one company name starts with the first word of the other ("Volvo Group" / "Volvo Business Services")."""
    q = ",".join("?" * len(AGGREGATORS))
    feed = con.execute(f"SELECT key, title, company FROM jobs WHERE source IN ({q}) "
                       "AND status IN ('new','scored','looked_up','no_contact')", AGGREGATORS).fetchall()
    if not feed:
        return 0
    boards: dict[str, list[str]] = {}
    for r in con.execute(f"SELECT title, company FROM jobs WHERE source NOT IN ({q}) AND status <> 'closed'", AGGREGATORS):
        boards.setdefault(_norm(r["title"]), []).append(r["company"] or "")
    n = 0
    for r in feed:
        for other in boards.get(_norm(r["title"]), []):
            a, b = _norm(r["company"]), _norm(other)
            wa, wb = _norm((r["company"] or "").split()[0] if r["company"] else ""), _norm(other.split()[0] if other else "")
            if a and b and ((len(wb) >= 2 and a.startswith(wb)) or (len(wa) >= 2 and b.startswith(wa))):
                con.execute("UPDATE jobs SET status='duplicate' WHERE key=?", (r["key"],))
                n += 1
                break
    con.commit()
    return n


def apply_filter(con, cfg) -> int:
    mark_duplicates(con)
    s = cfg.get("search", {})
    region = regions.resolve(cfg)
    rows = con.execute("SELECT key, title, company, location, remote, posted_at FROM jobs WHERE status='new'").fetchall()
    n = 0
    for r in rows:
        ok = passes_filter(r, s, region)
        con.execute("UPDATE jobs SET passed_filter=?, status=? WHERE key=?",
                    (int(ok), "new" if ok else "skipped", r["key"]))
        n += ok
    con.commit()
    return n


class AiCheck(BaseModel):
    ok: bool
    word: str


class JobScore(BaseModel):
    score: int                      # 0-10 fit
    reason: str                     # one or two sentences
    hiring_team: str                # team/function that would manage this hire, e.g. "Data Science", "Founders"
    language: Literal["en", "sv"]   # language the ad is written in
    red_flags: list[str]            # e.g. "requires 5+ years", "Swedish fluency required", "security clearance"


SCORE_SYSTEM = """You screen job ads for one candidate. Score fit from 0 to 10:
10 = the candidate is an obvious strong match and would likely get an interview;
7 = solid match worth a personal email; 4 = stretch; 0 = clearly wrong (seniority, field, language, location, visa).
Be strict about hard requirements (years of experience, required languages, citizenship/clearance).
Use only facts in the candidate profile. Return the JSON object only.

CANDIDATE PROFILE:
{profile}"""


def _heuristic(profile: str, desc: str) -> int:
    words = {w for w in re.findall(r"[a-zåäö+#]{4,}", profile.lower())}
    hits = {w for w in re.findall(r"[a-zåäö+#]{4,}", (desc or "").lower())} & words
    return min(10, 3 + len(hits) // 8)


def score_jobs(con, cfg) -> int:
    lc = cfg.get("llm", {})
    rows = con.execute(
        "SELECT * FROM jobs WHERE passed_filter=1 AND score IS NULL AND status='new' ORDER BY first_seen DESC LIMIT ?",
        (lc.get("max_jobs_to_score_per_run", 40),),
    ).fetchall()
    profile = read_profile(cfg)
    if not rows:
        return 0
    if not has_claude():
        for r in rows:
            con.execute("UPDATE jobs SET score=?, score_reason=?, status='scored' WHERE key=?",
                        (_heuristic(profile, r["description"]), "rough keyword score (Claude was not available)", r["key"]))
        con.commit()
        return len(rows)

    system = SCORE_SYSTEM.format(profile=profile)

    def work(r):
        # Some boards (Workday, SmartRecruiters) list jobs without the ad text; fetch it now so the score is fair.
        filled = "" if r["description"] else fill_description(r)
        desc = r["description"] or filled
        user = (f"JOB: {r['title']}\nCOMPANY: {r['company']}\nLOCATION: {r['location']} (remote={bool(r['remote'])})\n"
                f"DEPARTMENT: {r['department'] or '-'}\nSALARY: {r['salary'] or '-'}\n\nAD TEXT:\n{desc}")
        try:
            return r["key"], llm.parse(effort=lc.get("score_effort", "low"), system=system, user=user,
                                       schema=JobScore, max_tokens=4000), filled
        except Exception as e:  # keep the run going; the job is retried next time
            print(f"  ! scoring failed for {r['title']} @ {r['company']}: {e}")
            return r["key"], "error", filled

    n = 0
    with ThreadPoolExecutor(3) as ex:
        for key, s, filled in ex.map(work, rows):
            if filled:
                con.execute("UPDATE jobs SET description=? WHERE key=?", (filled, key))
            if s == "error" or (s is None and llm._stop.is_set()):
                continue  # retried on the next run
            if s is None:
                con.execute("UPDATE jobs SET score=0, score_reason='model declined', status='scored' WHERE key=?", (key,))
            else:
                reason = s.reason + (f" Red flags: {'; '.join(s.red_flags)}" if s.red_flags else "")
                con.execute("UPDATE jobs SET score=?, score_reason=?, hiring_team=?, language=?, status='scored' WHERE key=?",
                            (max(0, min(10, s.score)), reason, s.hiring_team, s.language, key))
            n += 1
    con.commit()
    return n
