"""Who to write to at a company, team by team, and the "Find who hires" button behind it.

For one role, on request: find the hiring lead (from the ad, then Claude web search, then Hunter if set up),
and draft a short email to them from profile.md. Nothing is ever sent: the result is a draft with links that
open it in Gmail or the mail app, where the user reads it and decides.
"""
from __future__ import annotations

import threading
from urllib.parse import quote

from . import contacts, draft
from .config import has_claude
from .sources import fill_description

TRUST = {"listed_in_ad": "In the ad", "published": "Published online", "verified": "Verified", "likely": "Likely",
         "guessed": "Guessed, check first", "none": "No email"}
_busy: set[str] = set()
_lock = threading.Lock()


class ReachError(RuntimeError):
    """A plain-language reason the lookup could not run."""


def best_for(con, keys: list[str]):
    """The best contact Lavoro already holds for any of these roles, with its draft if there is one, or None."""
    if not keys:
        return None
    q = ",".join("?" * len(keys))
    rows = con.execute(
        f"""SELECT c.*, j.title AS job_title, j.key AS jkey, d.subject, d.body, d.to_email
            FROM contacts c JOIN jobs j ON j.key = c.job_key
            LEFT JOIN drafts d ON d.job_key = c.job_key AND d.contact_id = c.id
            WHERE c.job_key IN ({q}) AND coalesce(c.name, '') <> ''""", keys).fetchall()
    rows = [x for x in rows if contacts.clean_name(x["name"])]  # older rows can hold '""' as a name
    if not rows:
        return None
    return min(rows, key=lambda r: (r["subject"] is None, draft.STATUS_RANK.get(r["email_status"] or "none", 5)))


def as_dict(r) -> dict:
    """What the page needs to show a contact and its draft."""
    out = {"name": r["name"], "title": r["title"] or "", "email": r["email"] or "", "status": r["email_status"] or "none",
           "trust": TRUST.get(r["email_status"] or "none", ""), "job": r["job_title"], "key": r["jkey"],
           "subject": r["subject"] or "", "body": r["body"] or ""}
    if out["subject"]:
        to = r["to_email"] or out["email"]
        out["gmail"] = ("https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(to) + "&su=" + quote(out["subject"])
                        + "&body=" + quote(out["body"]))
        out["mailto"] = f"mailto:{quote(to)}?subject={quote(out['subject'])}&body={quote(out['body'])}"
    return out


def reach(con, cfg, key: str) -> dict:
    """Find who hires for this role and draft an email to them. Returns {"found": bool, ...as_dict}."""
    job = con.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
    if job is None:
        raise KeyError(key)
    have = best_for(con, [key])
    if have is not None and have["subject"]:
        return {"found": True, **as_dict(have)}
    with _lock:
        if key in _busy:
            raise ReachError("Lavoro is already looking this one up. Give it a minute.")
        _busy.add(key)
    try:
        if not (job["description"] or "").strip():
            desc = fill_description(job)
            if desc:
                con.execute("UPDATE jobs SET description=? WHERE key=?", (desc, key))
                con.commit()
        if have is None:
            no_ad_contacts = (job["ad_contacts"] or "[]") == "[]"
            if not has_claude() and no_ad_contacts:
                raise ReachError("Finding who hires needs Claude. Run `claude` once in a terminal to sign in, then try again.")
            contacts.find_contacts(con, cfg, keys=[key])
        if draft._best_contact(con, key) is None:
            found = best_for(con, [key])
            if found is None:
                return {"found": False, "job": job["title"],
                        "message": "No one with a public name and email turned up for this role. Try another role on this team, "
                                   "or apply through the job board."}
            return {"found": True, **as_dict(found)}  # a name but no email: show who, without a draft
        draft.write_drafts(con, cfg, keys=[key])
        return {"found": True, **as_dict(best_for(con, [key]))}
    finally:
        with _lock:
            _busy.discard(key)
