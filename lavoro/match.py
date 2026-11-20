"""Filtering and scoring jobs against your profile."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel

from . import llm, regions
from .config import has_claude, read_profile
from .sources import fill_description


def _has_any(text: str, words: list[str]) -> bool:
    # Hyphens count as spaces, so "UX-designer" (as Swedish ads write it) matches "ux designer".
    t = (text or "").lower().replace("-", " ")
    return any(re.search(rf"(?<![a-zåäö]){re.escape(w.lower().replace('-', ' '))}(?![a-zåäö])", t) for w in words)


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
    # Feeds keep stale ads, so they get the age limit. A role still listed on the company's own board is open,
    # however old its date: consultancies keep "always hiring" ads up for years. board_max_age_days: 0 = no limit.
    src = job["source"] if "source" in job.keys() else ""
    days = s.get("max_age_days", 30) if src in AGGREGATORS or not src else s.get("board_max_age_days", 0)
    return not days or _age_ok(job["posted_at"], days)


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


def _title_ok(job, s: dict) -> bool:
    title = job["title"] or ""
    return (not s.get("titles_include") or _has_any(title, s["titles_include"])) and \
        not _has_any(title, s.get("titles_exclude") or [])


_LOC_PATTERNS = [
    re.compile(r"job\s+location\s*:?\s*\n?\s*(.{3,200})", re.I),                                   # a "Job location" heading
    re.compile(r"(?:^|\n)\s*(?:location|locations|ort|arbetsort|placering)\s*:\s*(.{3,160})", re.I),  # "Location: Lund"
]


def _location_from_ad(con, r):
    """Some boards list jobs without a place (e.g. SAP's newer career sites). Read it from the ad, once, and save it.
    Only called for titles that already pass the filter, so few pages are fetched."""
    desc = r["description"] or fill_description(r)
    where = ""
    for pat in _LOC_PATTERNS:
        m = pat.search(desc or "")
        if m:
            where = m.group(1)
            break
    if not where:  # "... Graduate Programme - UK", "... 2027 - Qingdao"
        m = re.search(r"\s[-–|]\s*([^-–|]{2,40})$", r["title"] or "")
        where = m.group(1) if m else ""
    if not where:
        return r
    where = " ".join(where.split())[:200]
    con.execute("UPDATE jobs SET location=?, description=coalesce(nullif(description,''), ?) WHERE key=?",
                (f"{where} (from the ad)", desc or "", r["key"]))
    return {**dict(r), "location": f"{where} (from the ad)", "description": desc}


def reopen_skipped(con) -> int:
    """Send jobs the filter skipped back through it, e.g. after titles or locations changed in config.yaml.
    Jobs the user turned down ("Not for me") were scored first, so they stay skipped. Returns how many."""
    cur = con.execute("UPDATE jobs SET status='new', passed_filter=0 WHERE status='skipped' AND score IS NULL")
    con.commit()
    return cur.rowcount


def apply_filter(con, cfg) -> int:
    mark_duplicates(con)
    s = cfg.get("search", {})
    region = regions.resolve(cfg)
    rows = con.execute("SELECT key, source, title, company, location, remote, posted_at, url, description "
                       "FROM jobs WHERE status='new'").fetchall()
    n = 0
    for r in rows:
        if not (r["location"] or "").strip() and _title_ok(r, s):
            r = _location_from_ad(con, r)
        ok = passes_filter(r, s, region)
        con.execute("UPDATE jobs SET passed_filter=?, status=? WHERE key=?",
                    (int(ok), "new" if ok else "skipped", r["key"]))
        n += ok
    con.commit()
    return n


class AiCheck(BaseModel):
    ok: bool
    word: str


class FitDetail(BaseModel):
    reason: str                     # one sentence: the overall verdict
    fits: list[str]                 # what in the profile matches the ad, e.g. "Figma and design systems"
    missing: list[str]              # what the ad asks for that the profile does not show, e.g. "iOS/Android patterns"
    red_flags: list[str]            # hard blockers, e.g. "requires 5+ years", "Swedish fluency required", "security clearance"


class JobScore(FitDetail):
    score: int                      # 0-10 fit
    hiring_team: str                # team/function that would manage this hire, e.g. "Data Science", "Founders"
    language: Literal["en", "sv"]   # language the ad is written in


FIT_RULES = """Explain the fit in short lists, each item a phrase of at most 8 words, no full sentences:
- reason: one sentence with the overall verdict.
- fits: up to 4 things in the profile that match what the ad asks for.
- missing: up to 4 things the ad asks for that the profile does not show.
- red_flags: hard blockers only (required language, years of experience, location, visa, clearance). Often empty."""

SCORE_SYSTEM = """You screen job ads for one candidate. Score fit from 0 to 10:
10 = the candidate is an obvious strong match and would likely get an interview;
7 = solid match worth a personal email; 4 = stretch; 0 = clearly wrong (seniority, field, language, location, visa).
Be strict about hard requirements (years of experience, required languages, citizenship/clearance).
Use only facts in the candidate profile. Return the JSON object only.

""" + FIT_RULES + """

CANDIDATE PROFILE:
{profile}"""

EXPLAIN_SYSTEM = """You explain why one job ad does or does not fit one candidate. Use only facts in the candidate profile.
Return the JSON object only.

""" + FIT_RULES + """

CANDIDATE PROFILE:
{profile}"""


def _detail_json(s: FitDetail) -> str:
    return json.dumps({"summary": s.reason, "fits": s.fits[:4], "missing": s.missing[:4], "red_flags": s.red_flags[:4]},
                      ensure_ascii=False)


def _job_prompt(r, desc: str) -> str:
    return (f"JOB: {r['title']}\nCOMPANY: {r['company']}\nLOCATION: {r['location']} (remote={bool(r['remote'])})\n"
            f"DEPARTMENT: {r['department'] or '-'}\nSALARY: {r['salary'] or '-'}\n\nAD TEXT:\n{desc}")


def explain_jobs(con, cfg, limit: int = 12) -> int:
    """Jobs scored before the fit was split into lists: fill in what fits, what is missing and the red flags, for the
    ones the site shows as cards (emails ready, good fit without an email). The score itself is kept."""
    if not has_claude() or "fit_detail" not in {c[1] for c in con.execute("PRAGMA table_info(jobs)")}:
        return 0  # the column is added on the next connect that is not blocked by a running write
    rows = con.execute("SELECT * FROM jobs WHERE fit_detail IS NULL AND score IS NOT NULL AND status IN ('drafted','no_contact') "
                       "ORDER BY score DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    system = EXPLAIN_SYSTEM.format(profile=read_profile(cfg))
    effort = cfg.get("llm", {}).get("score_effort", "low")

    def work(r):
        try:
            return r["key"], llm.parse(effort=effort, system=system, user=_job_prompt(r, r["description"] or ""),
                                       schema=FitDetail, max_tokens=3000)
        except Exception as e:  # noqa: BLE001  tried again next run
            print(f"  ! could not explain {r['title']} @ {r['company']}: {e}")
            return r["key"], None

    n = 0
    with ThreadPoolExecutor(3) as ex:
        for key, s in ex.map(work, rows):
            if s:
                con.execute("UPDATE jobs SET fit_detail=? WHERE key=?", (_detail_json(s), key))
                n += 1
    con.commit()
    return n


def _heuristic(profile: str, desc: str) -> int:
    words = {w for w in re.findall(r"[a-zåäö+#]{4,}", profile.lower())}
    hits = {w for w in re.findall(r"[a-zåäö+#]{4,}", (desc or "").lower())} & words
    return min(10, 3 + len(hits) // 8)


def score_jobs(con, cfg) -> int:
    """Score new jobs that passed the filter, newest first, up to llm.max_jobs_to_score_per_run."""
    rows = con.execute(
        "SELECT * FROM jobs WHERE passed_filter=1 AND score IS NULL AND status='new' ORDER BY first_seen DESC LIMIT ?",
        (cfg.get("llm", {}).get("max_jobs_to_score_per_run", 40),),
    ).fetchall()
    return _score_rows(con, cfg, rows, set_status=True)


def rescore_jobs(con, cfg, keys: list[str] | None = None, limit: int | None = None) -> int:
    """Score jobs again, for example after profile.md changed. With `keys`, exactly those jobs; otherwise the open
    jobs that were already scored, best first. A job keeps its stage (an email ready stays ready); only its score
    and fit lists change. A job that now scores high enough gets a contact and a draft on the next run."""
    if keys:
        rows = con.execute(f"SELECT * FROM jobs WHERE key IN ({','.join('?' * len(keys))})", keys).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM jobs WHERE passed_filter=1 AND score IS NOT NULL AND status IN ('scored','looked_up','no_contact','drafted') "
            "ORDER BY score DESC, first_seen DESC LIMIT ?",
            (limit or cfg.get("llm", {}).get("max_jobs_to_score_per_run", 40),)).fetchall()
    return _score_rows(con, cfg, rows, set_status=False)


def _score_rows(con, cfg, rows, set_status: bool) -> int:
    lc = cfg.get("llm", {})
    profile = read_profile(cfg)
    if not rows:
        return 0
    stage = ", status='scored'" if set_status else ""
    if not has_claude():
        for r in rows:
            con.execute(f"UPDATE jobs SET score=?, score_reason=?{stage} WHERE key=?",
                        (_heuristic(profile, r["description"]), "rough keyword score (Claude was not available)", r["key"]))
        con.commit()
        return len(rows)

    system = SCORE_SYSTEM.format(profile=profile)

    def work(r):
        # Some boards (Workday, SmartRecruiters) list jobs without the ad text; fetch it now so the score is fair.
        filled = "" if r["description"] else fill_description(r)
        desc = r["description"] or filled
        user = _job_prompt(r, desc)
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
                con.execute(f"UPDATE jobs SET score=0, score_reason='model declined'{stage} WHERE key=?", (key,))
            else:
                reason = s.reason + "".join(f" {label}: {'; '.join(items)}." for label, items in
                                            (("Fits", s.fits), ("Missing", s.missing), ("Red flags", s.red_flags)) if items)
                con.execute(f"UPDATE jobs SET score=?, score_reason=?, fit_detail=?, hiring_team=?, language=?{stage} "
                            "WHERE key=?", (max(0, min(10, s.score)), reason, _detail_json(s), s.hiring_team, s.language, key))
            n += 1
    con.commit()
    return n
