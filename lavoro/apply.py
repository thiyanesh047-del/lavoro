"""Help for a role you are going for, written by Claude from your profile and the ad:

  kit       — for roles you apply to through a careers portal: a cover letter, which of your CV points to put first,
              words from the ad worth mirroring, and what the ad asks for that your profile does not show.
  followup  — a short, friendly follow-up to an email or application that has had no answer for a week.

Both use only facts from profile.md. Nothing is sent; you copy the text where it needs to go.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from . import db, llm
from .config import has_claude, read_profile
from .draft import CLOSINGS, GREETINGS, _strip_signoff, signature
from .sources import fill_description

SCHEMA = """
CREATE TABLE IF NOT EXISTS writings (
    pipeline_id  INTEGER,
    kind         TEXT,          -- kit | followup
    body         TEXT,          -- JSON
    created_at   TEXT,
    PRIMARY KEY(pipeline_id, kind)
);
"""


class CvPoint(BaseModel):
    point: str     # copied or closely paraphrased from the profile, never new
    why: str       # which part of the ad it answers


class Kit(BaseModel):
    cover_letter: str
    cv_points: list[CvPoint]
    keywords: list[str]   # words and phrases from the ad that are true of the person
    gaps: list[str]       # what the ad asks for that the profile does not show; honest, short


class FollowUp(BaseModel):
    subject: str
    body: str


KIT_SYSTEM = """You help one person apply for one role through the employer's own application form.
Write, from the candidate's profile and the job ad:
1. cover_letter: one page at most (250-350 words), first person, plain and specific. Open with why this role and
   company, connect two or three concrete things from the profile to what the ad asks for, end with one line on
   what they would bring. No "I am writing to apply", no "passionate", no em dashes. Start with a greeting line
   ("Dear hiring team," or the local equivalent) and end without a signature: the name is added after your text.
2. cv_points: the 4-6 points from the profile that this ad cares about most, best first, each with the part of the
   ad it answers. Copy them from the profile; you may shorten, never add.
3. keywords: 6-12 words or phrases from the ad that are genuinely true of this person, to mirror in the CV.
4. gaps: up to 4 things the ad asks for that the profile does not show, said plainly, so the person can prepare.
Rules: use ONLY facts written in the profile. Never invent experience, numbers, tools, languages or dates, and never
state a graduation date, start date, availability or work permit unless the profile says it in those words.
Language: {language} (the cover letter and everything else).

CANDIDATE PROFILE:
{profile}"""

FOLLOW_SYSTEM = """You write a short follow-up email from a job seeker who has had no answer for about {days} days.
Rules:
- 50-90 words. Warm, brief, no guilt-tripping, no "just following up" or "circling back", no em dashes.
- Start with a greeting using the recipient's first name if known ("Hi Anna," / "Hej Anna,").
- Mention the role once, add ONE new, useful thing from the profile that the first message did not say (a project
  or a result), and end with one easy question.
- Use ONLY facts written in the profile. Never state a graduation date, start date, availability, notice period or
  work permit unless the profile says it in those words. Do NOT write a sign-off, name or links; a signature is
  added after your text.
- Subject: reuse the first subject with "Re: " if one is given, else under 8 words.
- Language: {language}.

CANDIDATE PROFILE:
{profile}"""


def ensure(con) -> None:
    con.executescript(SCHEMA)


def get(con, rid: int) -> dict:
    ensure(con)
    return {r["kind"]: {**json.loads(r["body"]), "created_at": r["created_at"]}
            for r in con.execute("SELECT * FROM writings WHERE pipeline_id=?", (rid,))}


def _save(con, rid: int, kind: str, data: dict) -> dict:
    con.execute("INSERT OR REPLACE INTO writings(pipeline_id, kind, body, created_at) VALUES (?,?,?,?)",
                (rid, kind, json.dumps(data, ensure_ascii=False), db.now()))
    con.commit()
    return {**data, "created_at": db.now()}


def _context(con, rid: int) -> tuple:
    p = con.execute("SELECT * FROM pipeline WHERE id=?", (rid,)).fetchone()
    if p is None:
        raise KeyError(rid)
    job = con.execute("SELECT * FROM jobs WHERE key=?", (p["job_key"],)).fetchone() if p["job_key"] else None
    ad = ""
    if job is not None:
        ad = job["description"] or ""
        if not ad:
            ad = fill_description(job)
            if ad:
                con.execute("UPDATE jobs SET description=? WHERE key=?", (ad, job["key"]))
    return p, job, ad


def _language(cfg, job) -> str:
    want = cfg.get("email", {}).get("language", "auto")
    if want != "auto":
        return want
    return "Swedish" if job is not None and job["language"] == "sv" else "English"


def make_kit(con, cfg, rid: int) -> dict:
    if not has_claude():
        raise RuntimeError("Claude isn't available, so Lavoro can't write the kit.")
    ensure(con)
    p, job, ad = _context(con, rid)
    lang = _language(cfg, job)
    user = (f"ROLE: {p['title'] or '(no title given)'} at {p['company']}\n"
            f"{('LOCATION: ' + job['location']) if job is not None and job['location'] else ''}\n"
            f"MY NOTES: {p['notes'] or '-'}\n\nJOB AD:\n{ad[:12000] or '(no ad text: write from the role title and company only)'}")
    k = llm.parse(effort=cfg.get("llm", {}).get("draft_effort", "medium"),
                  system=KIT_SYSTEM.format(language=lang, profile=read_profile(cfg) + f"\n\nName: {cfg.get('me', {}).get('name')}"),
                  user=user, schema=Kit, max_tokens=8000)
    if k is None:
        raise RuntimeError("Claude didn't return a kit this time. Try again in a minute.")
    letter = _strip_signoff(k.cover_letter, cfg) + "\n\n" + CLOSINGS.get(lang.lower(), "Kind regards,") + "\n" + \
        (cfg.get("me", {}).get("name") or "")
    return _save(con, rid, "kit", {"cover_letter": letter, "cv_points": [c.model_dump() for c in k.cv_points],
                                   "keywords": k.keywords, "gaps": k.gaps, "language": lang})


def make_followup(con, cfg, rid: int) -> dict:
    if not has_claude():
        raise RuntimeError("Claude isn't available, so Lavoro can't write the follow-up.")
    ensure(con)
    p, job, ad = _context(con, rid)
    lang = _language(cfg, job)
    first = con.execute("SELECT subject, body FROM drafts WHERE job_key=?", (p["job_key"],)).fetchone() if p["job_key"] else None
    days = 7
    if p["applied_at"]:
        from datetime import date
        try:
            days = max(1, (date.today() - date.fromisoformat(p["applied_at"][:10])).days)
        except ValueError:
            pass
    who = p["contact"] or "(name unknown)"
    user = (f"RECIPIENT: {who} <{p['email'] or 'no email on file'}>\nROLE: {p['title'] or ''} at {p['company']}\n"
            f"STAGE: {p['stage']} on {p['applied_at'] or 'unknown date'}\n"
            f"FIRST MESSAGE SUBJECT: {first['subject'] if first else '(applied through the careers site, no email)'}\n"
            f"FIRST MESSAGE:\n{first['body'] if first else '-'}\n\nJOB AD (short):\n{ad[:3000]}")
    f = llm.parse(effort="low", system=FOLLOW_SYSTEM.format(days=days, language=lang,
                                                              profile=read_profile(cfg)), user=user, schema=FollowUp,
                  max_tokens=4000)
    if f is None:
        raise RuntimeError("Claude didn't return a follow-up this time. Try again in a minute.")
    body = _strip_signoff(f.body, cfg)
    if not any(body.lower().startswith(g.lower()) for g in ["hi", "hello", "dear", *GREETINGS.values()]):
        name = (p["contact"] or "").split(" ")[0]
        body = f"{GREETINGS.get(lang.lower(), 'Hi')}{' ' + name if name else ''},\n\n{body}"
    return _save(con, rid, "followup", {"subject": f.subject, "body": body + "\n\n" + signature(cfg, lang),
                                        "to": p["email"] or "", "language": lang})
