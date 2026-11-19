"""SQLite storage. One file: data/lavoro.db"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

DB_PATH = ROOT / "data" / "lavoro.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    website     TEXT,
    domain      TEXT,
    ats         TEXT,            -- greenhouse | lever | ashby | workable | recruitee | teamtailor | smartrecruiters | none
    slug        TEXT,
    source      TEXT,            -- yc | manual | probe | jobtech
    info        TEXT,            -- one-liner, team size, batch...
    checked_at  TEXT,
    UNIQUE(ats, slug)
);
CREATE INDEX IF NOT EXISTS ix_companies_domain ON companies(domain);

CREATE TABLE IF NOT EXISTS jobs (
    key          TEXT PRIMARY KEY,  -- source:company:id
    source       TEXT NOT NULL,
    company_id   INTEGER,
    company      TEXT,
    domain       TEXT,
    title        TEXT,
    location     TEXT,
    remote       INTEGER DEFAULT 0,
    department   TEXT,
    url          TEXT,
    salary       TEXT,
    description  TEXT,
    posted_at    TEXT,
    first_seen   TEXT,
    last_seen    TEXT,
    ad_contacts  TEXT,              -- JSON list from the ad itself (JobTech)
    passed_filter INTEGER DEFAULT 0,
    score        REAL,
    score_reason TEXT,
    hiring_team  TEXT,
    language     TEXT,
    status       TEXT DEFAULT 'new' -- new | scored | looked_up | drafted | sent | skipped | closed
);
CREATE INDEX IF NOT EXISTS ix_jobs_score ON jobs(score);
CREATE INDEX IF NOT EXISTS ix_jobs_company ON jobs(company_id, status);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY,
    job_key      TEXT,
    name         TEXT,
    title        TEXT,
    email        TEXT,
    email_status TEXT,   -- listed_in_ad | verified | likely | guessed | none
    source       TEXT,   -- jobtech | hunter | web_search | pattern
    source_url   TEXT,
    note         TEXT,
    created_at   TEXT,
    UNIQUE(job_key, name, email)
);

CREATE TABLE IF NOT EXISTS drafts (
    job_key      TEXT,
    contact_id   INTEGER,
    to_email     TEXT,
    subject      TEXT,
    body         TEXT,
    gmail_draft_id TEXT,
    created_at   TEXT,
    PRIMARY KEY(job_key, contact_id)
);

-- Companies that announced a funding round recently (found by Claude web search). They tend to hire next.
CREATE TABLE IF NOT EXISTS funding (
    id           INTEGER PRIMARY KEY,
    company_id   INTEGER,
    name         TEXT NOT NULL,
    amount       TEXT,
    round        TEXT,
    announced    TEXT,
    summary      TEXT,
    source_url   TEXT,
    found_at     TEXT,
    UNIQUE(name, round)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The site reads while a run writes: WAL lets them overlap, and the timeout waits out short write locks.
    con = sqlite3.connect(path, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    con.executescript(SCHEMA)
    try:  # added later: companies you follow
        con.execute("ALTER TABLE companies ADD COLUMN starred INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    return con


class RunLock:
    """Only one `lavoro run` at a time. The OS releases the lock if the process dies."""

    def __init__(self):
        self.path = DB_PATH.parent / "run.lock"
        self.f = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            self.f = None
            raise RuntimeError("Another Lavoro run is already going. Wait for it to finish.")
        return self

    def __exit__(self, *exc):
        if self.f:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.f.close()


def upsert_company(con, *, name, website=None, domain=None, ats=None, slug=None, source=None, info=None) -> int:
    if ats and slug:
        row = con.execute("SELECT id FROM companies WHERE ats=? AND slug=?", (ats, slug)).fetchone()
        if row:
            return row["id"]
    if domain:
        row = con.execute("SELECT id, ats FROM companies WHERE domain=?", (domain,)).fetchone()
        if row:
            if ats and not row["ats"]:
                con.execute("UPDATE companies SET ats=?, slug=? WHERE id=?", (ats, slug, row["id"]))
            return row["id"]
    # Same name, and one side is missing what the other has (e.g. a probed board vs. a YC entry): one company.
    row = con.execute("SELECT * FROM companies WHERE lower(name)=lower(?) AND (domain IS NULL OR ? IS NULL OR domain=?)",
                      (name, domain, domain)).fetchone()
    if row:
        con.execute("""UPDATE companies SET website=coalesce(website,?), domain=coalesce(domain,?), info=coalesce(info,?),
                       ats=CASE WHEN ats IS NULL OR ats='none' THEN coalesce(?, ats) ELSE ats END,
                       slug=CASE WHEN ats IS NULL OR ats='none' THEN coalesce(?, slug) ELSE slug END WHERE id=?""",
                    (website, domain, info, ats, slug, row["id"]))
        return row["id"]
    cur = con.execute(
        "INSERT INTO companies(name, website, domain, ats, slug, source, info) VALUES (?,?,?,?,?,?,?)",
        (name, website, domain, ats, slug, source, info),
    )
    return cur.lastrowid


def merge_duplicate_companies(con) -> int:
    """Fold same-name companies into one when they don't conflict (same or missing domain). Returns rows removed."""
    removed = 0
    for (n,) in con.execute("SELECT lower(name) FROM companies GROUP BY lower(name) HAVING count(*) > 1").fetchall():
        rows = con.execute("""SELECT * FROM companies WHERE lower(name)=?
                              ORDER BY (ats IS NOT NULL AND ats<>'none') DESC, (info IS NOT NULL) DESC, id""", (n,)).fetchall()
        keep = rows[0]
        for r in rows[1:]:
            if keep["domain"] and r["domain"] and keep["domain"] != r["domain"]:
                continue  # really two different companies
            con.execute("UPDATE companies SET website=coalesce(website,?), domain=coalesce(domain,?), info=coalesce(info,?) WHERE id=?",
                        (r["website"], r["domain"], r["info"], keep["id"]))
            con.execute("UPDATE jobs SET company_id=? WHERE company_id=?", (keep["id"], r["id"]))
            con.execute("DELETE FROM companies WHERE id=?", (r["id"],))
            removed += 1
    con.commit()
    return removed


def upsert_job(con, job: dict) -> bool:
    """Insert or refresh a job. Returns True if it is new."""
    ts = now()
    row = con.execute("SELECT key FROM jobs WHERE key=?", (job["key"],)).fetchone()
    if row:
        con.execute("UPDATE jobs SET last_seen=?, status=CASE WHEN status='closed' THEN 'new' ELSE status END WHERE key=?",
                    (ts, job["key"]))
        return False
    con.execute(
        """INSERT INTO jobs(key, source, company_id, company, domain, title, location, remote, department, url,
                            salary, description, posted_at, first_seen, last_seen, ad_contacts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (job["key"], job["source"], job.get("company_id"), job.get("company"), job.get("domain"), job.get("title"),
         job.get("location"), int(bool(job.get("remote"))), job.get("department"), job.get("url"), job.get("salary"),
         job.get("description"), job.get("posted_at"), ts, ts, json.dumps(job.get("ad_contacts") or [], ensure_ascii=False)),
    )
    return True
