"""Writing one short, specific email per top job."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from . import db, llm
from .config import has_claude, min_score, read_profile

STATUS_RANK = {"listed_in_ad": 0, "published": 0, "verified": 1, "likely": 2, "guessed": 3, "none": 9}


class Email(BaseModel):
    subject: str
    body: str


DRAFT_SYSTEM = """You write one cold email from a job seeker to the person who leads hiring for a role.
Rules:
- Write in the candidate's own voice, first person, plain and human. Tone: {tone}.
- At most {max_words} words in the body. Short paragraphs. No bullet lists.
- Start with a short greeting using the recipient's first name (e.g. "Hi Anna," or "Hej Anna,"), then open with
  something specific about the role or company, not about yourself and not a pleasantry.
- Connect one or two concrete things from the candidate's profile to what the role needs.
- Use ONLY facts from the profile. Never invent experience, numbers, names or mutual contacts.
- Do not use: "I hope this email finds you well", "I am writing to", "passionate", "synergy", em dashes.
- End with one small, clear ask (a 15-minute call, or whether they would look at the CV or portfolio).
- Do NOT write a sign-off, name or links: a signature with the candidate's name{links_note} is added after your text.
  {portfolio_note}
- Language: {language}.
- Subject: under 8 words, specific to the role, no clickbait.
Return the JSON object only.

CANDIDATE PROFILE:
{profile}"""


def _best_contact(con, job_key):
    rows = con.execute("SELECT * FROM contacts WHERE job_key=? AND email IS NOT NULL AND email<>''", (job_key,)).fetchall()
    if not rows:
        return None
    # A named person beats the generic application inbox; then trust the email by its status.
    return sorted(rows, key=lambda c: (c["name"] is None, STATUS_RANK.get(c["email_status"], 5)))[0]


def greeting_name(contact) -> str:
    """First name for 'Hi …': the contact's name, else a first.last email address, else ''."""
    if contact["name"]:
        return contact["name"].split(" ")[0]
    local = (contact["email"] or "").split("@")[0]
    if re.fullmatch(r"[a-zA-Z]{2,}[._][a-zA-Z]{2,}", local):
        return re.split(r"[._]", local)[0].title()
    return ""


CLOSINGS = {"swedish": "Vänliga hälsningar,", "german": "Viele Grüße,", "french": "Bien cordialement,",
            "spanish": "Saludos cordiales,", "italian": "Cordiali saluti,", "danish": "Venlig hilsen,",
            "norwegian": "Vennlig hilsen,", "dutch": "Met vriendelijke groet,", "finnish": "Ystävällisin terveisin,"}


GREETINGS = {"swedish": "Hej", "german": "Hallo", "french": "Bonjour", "spanish": "Hola", "italian": "Ciao",
             "danish": "Hej", "norwegian": "Hei", "dutch": "Hoi", "finnish": "Hei"}
_GREETING_RE = re.compile(r"^\s*(hi|hello|hey|dear|hej|hejsan|hallo|bonjour|hola|ciao|hei|hoi|god\s?(morgon|dag))\b", re.I)


def with_greeting(body: str, contact, language: str) -> str:
    """Make sure the email opens with 'Hi <first name>,' in the email's language."""
    if _GREETING_RE.match(body or ""):
        return body
    word = GREETINGS.get(language.strip().lower(), "Hi")
    name = greeting_name(contact)
    return f"{word} {name},\n\n{body.lstrip()}" if name else f"{word},\n\n{body.lstrip()}"


def signature(cfg, language: str = "English") -> str:
    me = cfg.get("me", {})
    lines = [me.get("name") or ""]
    if me.get("portfolio"):
        lines.append(f"Portfolio: {me['portfolio']}")
    if me.get("linkedin"):
        lines.append(f"LinkedIn: {me['linkedin']}")
    return CLOSINGS.get(language.strip().lower(), "Best,") + "\n" + "\n".join(l for l in lines if l)


def _strip_signoff(body: str, cfg) -> str:
    """If the model added its own sign-off anyway, cut it before appending ours."""
    name = (cfg.get("me", {}).get("name") or "").split(" ")[0]
    lines = body.rstrip().splitlines()
    while lines and (re.fullmatch(r"\s*(best|regards|kind regards|best regards|thanks|cheers|vänliga hälsningar|mvh|hälsningar)[,!.]?\s*", lines[-1], re.I)
                     or (name and lines[-1].strip().startswith(name)) or "linkedin.com" in lines[-1] or not lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).rstrip()


def _template(cfg, job, contact) -> Email:
    first = greeting_name(contact) or "there"
    body = (f"Hi {first},\n\nI saw the {job['title']} opening at {job['company']} and wanted to reach out to you directly.\n\n"
            f"[One or two sentences linking your experience to this role.]\n\n"
            f"Would you be open to a 15-minute call, or to taking a look at my portfolio?")
    return Email(subject=f"{job['title']} at {job['company']}", body=body + "\n\n" + signature(cfg))


def write_drafts(con, cfg, gmail_service=None, keys: list[str] | None = None, note: str = "") -> int:
    """Draft an email for each looked-up top job, or, with `keys`, for exactly those jobs. With `note` (e.g. "make it
    shorter"), the current draft is rewritten to follow it."""
    lc, ec, me = cfg.get("llm", {}), cfg.get("email", {}), cfg.get("me", {})
    if keys:
        jobs = con.execute(f"SELECT * FROM jobs WHERE key IN ({','.join('?' * len(keys))})", keys).fetchall()
    else:
        jobs = con.execute(
            "SELECT * FROM jobs WHERE status='looked_up' AND score >= ? ORDER BY score DESC",
            (min_score(cfg),),
        ).fetchall()
    profile = read_profile(cfg)
    todo = []
    for j in jobs:
        c = _best_contact(con, j["key"])
        if c is None:
            con.execute("UPDATE jobs SET status='no_contact' WHERE key=?", (j["key"],))
            continue
        todo.append((j, c))
    con.commit()
    # With a note, the drafts being rewritten (read here: the connection belongs to this thread).
    current = {j["key"]: con.execute("SELECT subject, body FROM drafts WHERE job_key=? AND contact_id=?", (j["key"], c["id"])).fetchone()
               for j, c in todo} if note else {}

    def work(item):
        j, c = item
        if not has_claude():
            return j, c, _template(cfg, j, c)
        lang = ec.get("language", "auto")
        lang = ("Swedish" if j["language"] == "sv" else "English") if lang == "auto" else lang
        links = [x for x in ("portfolio" if me.get("portfolio") else "", "LinkedIn" if me.get("linkedin") else "") if x]
        system = DRAFT_SYSTEM.format(
            tone=ec.get("tone", "warm, direct"), max_words=ec.get("max_words", 140), language=lang,
            links_note=(" and links to their " + " and ".join(links)) if links else "",
            portfolio_note=("- You may point to the portfolio once (\"my portfolio is linked below\") when the role is design work."
                            if me.get("portfolio") else ""),
            profile=profile + f"\n\nName: {me.get('name')}")
        who = c["name"] or (f"probably {greeting_name(c)} (from the email address)" if greeting_name(c) else "(no name: the application inbox)")
        user = (f"RECIPIENT: {who} <{c['email']}> — {c['title'] or ''}\n"
                f"ROLE: {j['title']} at {j['company']} ({j['location']})\nWHY IT FITS (screening note): {j['score_reason'] or '-'}\n\n"
                f"JOB AD:\n{j['description']}")
        if note:
            old = current.get(j["key"])
            if old:
                user += f"\n\nCURRENT DRAFT (subject: {old['subject']}):\n{_strip_signoff(old['body'], cfg)}"
            user += f"\n\nREWRITE IT. THE CANDIDATE ASKS: {note}\nKeep every rule above; still use only facts from the profile."
        try:
            e = llm.parse(effort=lc.get("draft_effort", "medium"), system=system, user=user, schema=Email, max_tokens=8000)
        except Exception as ex:
            print(f"  ! drafting failed for {j['title']} @ {j['company']}: {ex}")
            e = None
        if e is None:
            return j, c, _template(cfg, j, c)
        body = with_greeting(_strip_signoff(e.body, cfg), c, lang)
        return j, c, Email(subject=e.subject, body=body + "\n\n" + signature(cfg, lang))

    n = 0
    with ThreadPoolExecutor(3) as ex:
        for j, c, e in ex.map(work, todo):
            gid = None
            if gmail_service is not None:
                try:
                    from .gmail import create_draft
                    gid = create_draft(gmail_service, me.get("email") or "me", c["email"], e.subject, e.body)
                except Exception as err:
                    print(f"  ! Gmail draft failed for {c['email']}: {err}")
            con.execute("""INSERT OR REPLACE INTO drafts(job_key, contact_id, to_email, subject, body, gmail_draft_id, created_at)
                           VALUES (?,?,?,?,?,?,?)""", (j["key"], c["id"], c["email"], e.subject, e.body, gid, db.now()))
            con.execute("UPDATE jobs SET status='drafted' WHERE key=?", (j["key"],))
            n += 1
    con.commit()
    return n
