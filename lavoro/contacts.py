"""Finding the person who leads hiring for a role, and their work email.

Order of sources, best first:
  1. Contacts printed in the ad itself (JobTech/Platsbanken ads often list a name + email).
  2. Hunter.io (optional key): people at the domain + verified emails + the domain's email pattern.
  3. Claude with web search: who leads this team / founded this company (public pages only).
Then the email is taken from Hunter, or built from the domain's known pattern, and labelled honestly:
  listed_in_ad | verified | likely | guessed
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from . import db, llm
from .config import has_claude, min_score
from .net import get_json
from .sources import is_platform

PATTERNS = ["{first}.{last}", "{first}", "{f}{last}", "{first}{last}", "{first}_{last}", "{f}.{last}", "{first}{l}", "{last}"]


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def split_name(full: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    if not parts:
        return "", ""
    return _ascii(parts[0]), _ascii(parts[-1]) if len(parts) > 1 else ""


def render(pattern: str, first: str, last: str, domain: str) -> str | None:
    if not first or ("{last}" in pattern or "{l}" in pattern) and not last:
        return None
    local = pattern.format(first=first, last=last, f=first[:1], l=last[:1])
    return f"{local}@{domain}"


def learn_pattern(name: str, email: str) -> str | None:
    first, last = split_name(name)
    if not email or "@" not in email:
        return None
    domain = email.split("@")[1].lower()
    for p in PATTERNS:
        if render(p, first, last, domain) == email.lower():
            return p
    return None


def known_pattern(con, domain: str) -> str | None:
    """Email pattern for a domain, learned from any named contact we already have on it."""
    for r in con.execute("SELECT name, email FROM contacts WHERE email LIKE ? AND name IS NOT NULL", (f"%@{domain}",)):
        p = learn_pattern(r["name"], r["email"])
        if p:
            return p
    return None


# ---------------------------------------------------------------- Hunter.io (optional)
def _hunter_key(cfg) -> str | None:
    return os.environ.get(cfg.get("contacts", {}).get("hunter_api_key_env", "HUNTER_API_KEY"))


def hunter_domain(domain: str, key: str) -> dict:
    d = get_json("https://api.hunter.io/v2/domain-search", params={"domain": domain, "limit": 10, "api_key": key})
    return (d or {}).get("data") or {}


def hunter_find(domain: str, first: str, last: str, key: str) -> dict:
    d = get_json("https://api.hunter.io/v2/email-finder",
                 params={"domain": domain, "first_name": first, "last_name": last, "api_key": key})
    return (d or {}).get("data") or {}


def _best_hunter_person(people: list[dict], team: str) -> dict | None:
    team_words = [w for w in re.findall(r"[a-z]{3,}", (team or "").lower())]
    def rank(p):
        pos = (p.get("position") or "").lower()
        r = 0
        if any(w in pos for w in team_words):
            r += 3
        if re.search(r"\b(head|lead|director|vp|chief|cto|ceo|founder|manager)\b", pos):
            r += 2
        if p.get("seniority") in ("executive", "senior"):
            r += 1
        if (p.get("verification") or {}).get("status") == "valid":
            r += 1
        return r
    people = [p for p in people if p.get("value") and p.get("first_name")]
    return max(people, key=rank) if people else None


# ---------------------------------------------------------------- Claude + web search
class HiringLead(BaseModel):
    name: str                    # full name, or "" if not found
    title: str
    source_url: str              # public page where this was found
    company_domain: str          # the company's own website domain, e.g. "acme.com"
    published_email: str         # this person's work email exactly as printed on a public page you read, else ""
    confidence: Literal["high", "medium", "low"]
    why: str                     # one sentence: why this person would lead hiring for the role


LEAD_SYSTEM = """You find the single best person to email about a job opening: the person who leads the team the
role sits in (the future manager), not a recruiter or a generic careers inbox. At startups under ~50 people this is
usually a founder, the CEO or the CTO. Use web search on public pages only (company site, team page, press,
public profiles in search results). Never invent a name: if you cannot find one with reasonable confidence,
return an empty name and confidence "low". If a page you read (for example the job ad itself or a mirror of it)
prints this person's work email, copy it exactly into published_email; never construct or guess an email.
Return the JSON object only."""


def find_lead_web(cfg, job) -> HiringLead | None:
    user = (f"Company: {job['company']}\nCompany domain (may be empty): {job['domain'] or ''}\n"
            f"Role: {job['title']}\nTeam: {job['hiring_team'] or job['department'] or '-'}\n"
            f"Location: {job['location']}\nJob link: {job['url']}")
    return llm.parse(effort="medium", system=LEAD_SYSTEM, user=user, schema=HiringLead, web=True)


# ---------------------------------------------------------------- does the domain take email?
_mail_ok: dict[str, bool] = {}


def domain_takes_mail(domain: str) -> bool | None:
    """True if the domain has a mail server (MX record, or an address record as the fallback mail host).
    Asks a public DNS-over-HTTPS resolver; only the domain name is sent, never an address. None if the lookup failed."""
    domain = (domain or "").lower().strip(".")
    if not domain:
        return None
    if domain in _mail_ok:
        return _mail_ok[domain]
    mx = get_json(f"https://dns.google/resolve?name={domain}&type=MX", timeout=10)
    if mx is None:
        return None
    records = [a.get("data", "").strip() for a in mx.get("Answer") or [] if a.get("type") == 15]
    if records:
        ok = not all(r in ("0 .", "0") for r in records)   # "0 ." is a null MX: the domain takes no email
    else:  # no MX: mail goes to the domain's own address, if it has one
        a = get_json(f"https://dns.google/resolve?name={domain}&type=A", timeout=10)
        if a is None:
            return None
        ok = any(x.get("type") == 1 for x in a.get("Answer") or [])
    _mail_ok[domain] = bool(ok)
    return _mail_ok[domain]


def check_domain(email: str | None, status: str, note: str | None) -> tuple[str | None, str, str | None]:
    """Before an address built from a pattern or a guess is shown, make sure its domain takes email at all."""
    if not email or status not in ("likely", "guessed"):
        return email, status, note
    ok = domain_takes_mail(email.split("@")[-1])
    if ok is False:
        return None, "none", ((note + " | ") if note else "") + f"{email} not used: its domain does not take email"
    if ok is None:
        return email, status, note
    return email, status, ((note + " | ") if note else "") + "domain takes email"


# ---------------------------------------------------------------- main step
def _insert(con, job_key, name, title, email, status, source, url=None, note=None):
    email, status, note = check_domain(email, status, note)
    con.execute("""INSERT OR IGNORE INTO contacts(job_key, name, title, email, email_status, source, source_url, note, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (job_key, name, title, email, status, source, url, note, db.now()))


def find_contacts(con, cfg) -> int:
    cc = cfg.get("contacts", {})
    rows = con.execute(
        """SELECT j.*, c.domain AS c_domain FROM jobs j LEFT JOIN companies c ON c.id = j.company_id
           WHERE j.status='scored' AND j.score >= ?
           ORDER BY j.score DESC, j.first_seen DESC LIMIT ?""",
        (min_score(cfg), cc.get("max_jobs_per_run", 15)),
    ).fetchall()
    hunter_key = _hunter_key(cfg)
    use_web = cc.get("use_web_search", True) and has_claude()

    # 1. Contacts from the ad itself — free and the most reliable.
    for r in rows:
        for c in json.loads(r["ad_contacts"] or "[]"):
            _insert(con, r["key"], c.get("name"), c.get("title"), c.get("email"),
                    "listed_in_ad" if c.get("email") else "none", "ad")
    con.commit()

    # 2/3. Web search for the hiring lead (in parallel; network-bound).
    leads = {}
    todo = [r for r in rows if use_web and not any(c.get("email") and c.get("name") for c in json.loads(r["ad_contacts"] or "[]"))]

    def web(r):
        try:
            return r["key"], find_lead_web(cfg, r)
        except Exception as e:
            print(f"  ! web search failed for {r['company']}: {e}")
            return r["key"], None
    with ThreadPoolExecutor(3) as ex:
        leads = dict(ex.map(web, todo))

    n = 0
    for r in rows:
        domain = r["domain"] or r["c_domain"] or ""
        lead = leads.get(r["key"])
        if lead and lead.company_domain and (not domain or is_platform(domain)):
            domain = lead.company_domain.lower().removeprefix("www.")
        if domain and not r["domain"]:
            con.execute("UPDATE jobs SET domain=? WHERE key=?", (domain, r["key"]))

        hunter_people, pattern = [], None
        if hunter_key and domain and not is_platform(domain):
            hd = hunter_domain(domain, hunter_key)
            hunter_people, pattern = hd.get("emails") or [], hd.get("pattern")  # e.g. "{first}.{last}"
            if pattern and pattern not in PATTERNS:
                pattern = None

        if lead and lead.name:
            first, last = split_name(lead.name)
            email, status, note = None, "none", None
            pub = (lead.published_email or "").strip().lower()
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", pub):
                email, status = pub, "published"
                domain = domain or pub.split("@")[1]
            if not email and hunter_key and domain:
                f = hunter_find(domain, first, last, hunter_key)
                if f.get("email"):
                    v = (f.get("verification") or {}).get("status")
                    email, status = f["email"], "verified" if v == "valid" else "likely"
                    note = f"hunter score {f.get('score')}"
            if not email and domain:
                p = pattern or known_pattern(con, domain)
                if p:
                    email, status, note = render(p, first, last, domain), "likely", f"domain pattern {p}"
                else:
                    guesses = [g for g in (render(p, first, last, domain) for p in PATTERNS[:4]) if g]
                    email, status = (guesses[0] if guesses else None), "guessed"
                    note = "other guesses: " + ", ".join(guesses[1:]) if len(guesses) > 1 else None
            _insert(con, r["key"], lead.name, lead.title, email, status, "web_search", lead.source_url,
                    f"{lead.confidence} confidence. {lead.why}" + (f" | {note}" if note else ""))
            n += 1
        elif hunter_people:
            p = _best_hunter_person(hunter_people, r["hiring_team"] or r["department"] or "")
            if p:
                v = (p.get("verification") or {}).get("status")
                _insert(con, r["key"], f"{p.get('first_name')} {p.get('last_name') or ''}".strip(), p.get("position"),
                        p.get("value"), "verified" if v == "valid" else "likely", "hunter", None,
                        f"hunter confidence {p.get('confidence')}")
                n += 1
        else:
            n += bool(json.loads(r["ad_contacts"] or "[]"))
        con.execute("UPDATE jobs SET status='looked_up' WHERE key=?", (r["key"],))
    con.commit()
    return n
