"""The pipeline tracker: a spreadsheet of the roles and companies you are going for.

Each row is one role (or a company you want to approach without a posting). Stages run from "Interested" to "Offer".
Moving a row to Applied or Emailed sets a follow-up date a week later; the Today page shows follow-ups that are due.
Marking a drafted email as sent adds its role here by itself. The whole sheet downloads as a CSV file for Excel or Sheets.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from . import db
from .config import min_score
from .digest import ago, bar, e, head, icon, scene

STAGES = [
    ("interested", "Interested"), ("applying", "Will apply"), ("applied", "Applied"), ("emailed", "Emailed"),
    ("followed_up", "Followed up"), ("interview", "Interviewing"), ("offer", "Offer"), ("closed", "Not this time"),
]
STAGE_LABEL = dict(STAGES)
WAITING = ("applied", "emailed", "followed_up")       # stages where a follow-up date matters
FOLLOW_UP_DAYS = 7
EDITABLE = {"stage", "contact", "email", "applied_at", "follow_up", "notes", "title", "company", "url"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline (
    id          INTEGER PRIMARY KEY,
    job_key     TEXT UNIQUE,
    company_id  INTEGER,
    company     TEXT,
    title       TEXT,
    url         TEXT,
    stage       TEXT DEFAULT 'interested',
    contact     TEXT,
    email       TEXT,
    applied_at  TEXT,
    follow_up   TEXT,
    notes       TEXT,
    created_at  TEXT,
    updated_at  TEXT
);
"""


def ensure(con) -> None:
    con.executescript(SCHEMA)


def _today() -> str:
    return date.today().isoformat()


def _later(days: int = FOLLOW_UP_DAYS) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- changes
def track(con, job_key: str, stage: str = "interested") -> int:
    """Add a role to the tracker (or move it forward). Returns the row id."""
    ensure(con)
    j = con.execute("SELECT * FROM jobs WHERE key=?", (job_key,)).fetchone()
    if j is None:
        raise KeyError(job_key)
    # A named person first; an ad's bare "apply here" address only when there is no one else.
    c = con.execute("SELECT name, title, email FROM contacts WHERE job_key=? AND email IS NOT NULL ORDER BY "
                    "CASE WHEN name IS NULL OR name='' THEN 1 ELSE 0 END, "
                    "CASE email_status WHEN 'listed_in_ad' THEN 0 WHEN 'published' THEN 1 WHEN 'verified' THEN 2 ELSE 3 END",
                    (job_key,)).fetchone()
    d = con.execute("SELECT to_email FROM drafts WHERE job_key=?", (job_key,)).fetchone()
    row = con.execute("SELECT id, stage FROM pipeline WHERE job_key=?", (job_key,)).fetchone()
    now = db.now()
    if row is None:
        cur = con.execute(
            "INSERT INTO pipeline(job_key, company_id, company, title, url, stage, contact, email, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_key, j["company_id"], j["company"], j["title"], j["url"], "interested",
             (c["name"] or c["title"]) if c else None, (d["to_email"] if d else None) or (c["email"] if c else None), now, now))
        rid = cur.lastrowid
    else:
        rid = row["id"]
    if stage != "interested" or row is None:
        set_field(con, rid, "stage", stage)
    con.commit()
    return rid


def set_field(con, rid: int, field: str, value: str) -> dict:
    """Change one cell. Moving to Applied/Emailed/Followed up sets the dates that go with it."""
    ensure(con)
    if field not in EDITABLE:
        raise ValueError(f"{field} cannot be changed")
    value = (value or "").strip()[:2000]
    if field == "stage" and value not in STAGE_LABEL:
        raise ValueError("unknown stage")
    if field in ("applied_at", "follow_up") and value:
        date.fromisoformat(value)  # raises ValueError on a bad date
    row = con.execute("SELECT * FROM pipeline WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise KeyError(rid)
    changes = {field: value or None}
    if field == "stage":
        if value in ("applied", "emailed") and not row["applied_at"]:
            changes["applied_at"] = _today()
        if value in WAITING:
            changes["follow_up"] = _later() if value == "followed_up" or not row["follow_up"] else row["follow_up"]
        elif value in ("interview", "offer", "closed"):
            changes["follow_up"] = None
    sets = ", ".join(f"{k}=?" for k in changes)
    con.execute(f"UPDATE pipeline SET {sets}, updated_at=? WHERE id=?", (*changes.values(), db.now(), rid))
    con.commit()
    return dict(con.execute("SELECT * FROM pipeline WHERE id=?", (rid,)).fetchone())


def add_manual(con, company: str, title: str, url: str) -> int:
    ensure(con)
    if not company.strip():
        raise ValueError("Add at least a company name.")
    now = db.now()
    cur = con.execute("INSERT INTO pipeline(company, title, url, stage, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                      (company.strip()[:200], title.strip()[:300], url.strip()[:1000], "interested", now, now))
    con.commit()
    return cur.lastrowid


def remove(con, rid: int) -> None:
    ensure(con)
    con.execute("DELETE FROM pipeline WHERE id=?", (rid,))
    con.commit()


def on_sent(con, job_key: str) -> None:
    """A drafted email was marked as sent on Today: the role moves to Emailed, follow up in a week."""
    try:
        track(con, job_key, "emailed")
    except KeyError:
        pass


def due(con) -> list:
    ensure(con)
    q = ",".join("?" * len(WAITING))
    return con.execute(f"SELECT * FROM pipeline WHERE stage IN ({q}) AND follow_up IS NOT NULL AND follow_up <= ? "
                       "ORDER BY follow_up", (*WAITING, _today())).fetchall()


# ---------------------------------------------------------------- export
COLUMNS = [("company", "Company"), ("title", "Role"), ("stage", "Stage"), ("contact", "Contact"), ("email", "Email"),
           ("applied_at", "Applied"), ("follow_up", "Follow up"), ("notes", "Notes"), ("url", "Link")]


def to_csv(con) -> bytes:
    ensure(con)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([label for _, label in COLUMNS])
    for r in con.execute("SELECT * FROM pipeline ORDER BY updated_at DESC"):
        w.writerow([STAGE_LABEL.get(r[k], r[k]) if k == "stage" else (r[k] or "") for k, _ in COLUMNS])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # the BOM makes Excel read å, ä, ö correctly


# ---------------------------------------------------------------- page
CSS = r"""
body.browse .wrap{max-width:1180px}
header.hero.slim{min-height:auto;padding:9vh 0 44px}
header.hero.slim h1{font-size:clamp(44px,6.4vw,68px);max-width:none}
.count{margin:14px 0 0;font:500 16px/1.6 var(--sans);color:#1f1f1f;max-width:62ch;text-shadow:0 1px 18px rgba(255,252,248,.95)}
.stagebar{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.stagebar span{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 13px;border-radius:999px;background:rgba(255,255,255,.9);
  box-shadow:0 0 0 1px var(--line) inset;font:600 13px var(--sans)}
.stagebar b{font-variant-numeric:tabular-nums}
.sec{margin:34px 0 0}
.sec h2{font:400 34px/1.1 var(--serif);margin:0 0 6px;letter-spacing:-.01em}
.sec .lead{color:var(--ink-2);font-size:14px;margin:0 0 14px}
.sheetwrap{overflow-x:auto;border-radius:18px;background:#fff;box-shadow:0 0 0 1px var(--line) inset}
table.sheet{width:100%;border-collapse:collapse;font:500 14px var(--sans);min-width:980px}
.sheet th{text-align:left;font:600 12px var(--sans);text-transform:uppercase;letter-spacing:.04em;color:var(--mute);padding:12px 10px;
  border-bottom:1px solid var(--line);background:#fcfbf9;position:sticky;top:0}
.sheet td{padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
.sheet tr:last-child td{border-bottom:0}
.sheet tr.due td{background:#fffbeb}
.sheet .co{font-weight:650;white-space:nowrap}
.sheet .ro a{color:var(--ink);text-decoration:none}.sheet .ro a:hover{text-decoration:underline}
.sheet input,.sheet select{width:100%;height:34px;border:1px solid transparent;border-radius:8px;background:transparent;
  font:500 13.5px var(--sans);color:var(--ink);padding:0 8px}
.sheet input:hover,.sheet select:hover{border-color:var(--line)}
.sheet input:focus,.sheet select:focus{outline:0;border-color:rgba(225,29,72,.5);background:#fff;box-shadow:0 0 0 3px rgba(225,29,72,.1)}
.sheet input[type=date]{min-width:132px}
.sheet select{font-weight:600;cursor:pointer;min-width:132px}
.sheet td.x{width:40px}
.sheet td.op a{font:600 12.5px var(--sans);color:var(--rose-ink);text-decoration:none;white-space:nowrap}
.sheet td.op a:hover{text-decoration:underline}
.sheet .del{width:30px;height:30px;border:0;border-radius:8px;background:transparent;color:var(--mute);cursor:pointer;display:grid;place-items:center}
.sheet .del:hover{background:var(--rose-wash);color:var(--rose-ink)}.sheet .del svg{width:15px;height:15px}
.sheet .empty td{padding:26px 16px;color:var(--ink-2)}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:0 0 12px}
.addrow{display:flex;flex-wrap:wrap;gap:8px;flex:1 1 560px}
.addrow input{flex:1 1 150px;height:42px;border-radius:12px;border:1px solid var(--line);background:#fff;padding:0 12px;font:500 14px var(--sans)}
.addrow input:focus{outline:0;border-color:rgba(225,29,72,.5);box-shadow:0 0 0 3px rgba(225,29,72,.1)}
.btn2{display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 16px;border-radius:12px;border:0;cursor:pointer;
  font:600 14px var(--sans);text-decoration:none;white-space:nowrap}
.btn2.dark{background:var(--ink);color:#fff}.btn2.light{background:#fff;color:var(--ink);box-shadow:0 0 0 1px var(--line) inset}
.btn2 svg{width:16px;height:16px}
.duelist{display:grid;gap:10px}
.duec{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;padding:14px 18px;border-radius:16px;background:#fffbeb;
  box-shadow:0 0 0 1px var(--amber-ring) inset}
.duec .w{flex:1 1 280px}.duec b{display:block;font-size:15px}.duec small{color:var(--ink-2);font-size:13px}
.saved{font-size:12.5px;color:var(--mute);min-height:18px}
@media (max-width:640px){.stagebar span{height:30px}.sec h2{font-size:30px}}
"""

JS = r"""
const say2=m=>{try{say(m)}catch(e){}};
async function send(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Could not save');return d}
document.querySelectorAll('.sheet [data-f]').forEach(el=>el.addEventListener('change',async()=>{
  const tr=el.closest('tr');
  try{const d=await send('/api/pipeline',{id:+tr.dataset.id,field:el.dataset.f,value:el.value});
    if(el.dataset.f==='stage'){for(const k of ['applied_at','follow_up']){const i=tr.querySelector(`[data-f=${k}]`);if(i)i.value=d.row[k]||''}}
    tr.classList.toggle('due',!!d.row.follow_up&&d.row.follow_up<=new Date().toISOString().slice(0,10)&&['applied','emailed','followed_up'].includes(d.row.stage));
    say2('Saved.')}catch(e){say2(e.message)}}));
document.querySelectorAll('.sheet .del').forEach(b=>b.addEventListener('click',async()=>{
  const tr=b.closest('tr');if(!confirmRemove(tr))return;
  try{await send('/api/pipeline',{id:+tr.dataset.id,remove:true});tr.remove();say2('Removed from your tracker.')}catch(e){say2(e.message)}}));
function confirmRemove(tr){const b=tr.querySelector('.del');if(b.dataset.armed){return true}
  b.dataset.armed='1';b.style.background='var(--rose-wash)';b.title='Click again to remove';say2('Click again to remove this row.');
  setTimeout(()=>{delete b.dataset.armed;b.style.background=''},3000);return false}
const add=document.querySelector('#addrow');
if(add)add.addEventListener('submit',async ev=>{ev.preventDefault();const f=new FormData(add);
  try{await send('/api/pipeline',{add:true,company:f.get('company'),title:f.get('title'),url:f.get('url')});location.reload()}catch(e){say2(e.message)}});
document.querySelectorAll('[data-followed]').forEach(b=>b.addEventListener('click',async()=>{
  try{await send('/api/pipeline',{id:+b.dataset.followed,field:'stage',value:'followed_up'});b.closest('.duec').remove();say2('Next follow-up in a week.')}
  catch(e){say2(e.message)}}));
"""


BOOKMARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>'


DUE_CLASS = ' class="due"'  # kept out of the f-string: Python before 3.12 allows no backslash there


def track_btn(key: str, on: bool = False) -> str:
    """A small bookmark button. Its class is 'trackbtn' (not 'track', which the Roles page uses for its bars)."""
    tip = "In your tracker" if on else "Add to your tracker"
    return (f'<button class="trackbtn" type="button" data-track="{e(key)}" aria-pressed="{"true" if on else "false"}" '
            f'title="{tip}" aria-label="{tip}">{BOOKMARK}</button>')


# Shared by every page that shows job rows: the Track button.
TRACK_JS = r"""
document.querySelectorAll('[data-track]').forEach(b=>b.addEventListener('click',async ev=>{ev.preventDefault();ev.stopPropagation();
  if(b.getAttribute('aria-pressed')==='true'){location.href='/tracker';return}
  try{const r=await fetch('/api/pipeline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track:b.dataset.track})});
    if(!r.ok)throw 0;b.setAttribute('aria-pressed','true');b.title=b.ariaLabel='In your tracker';try{say('Added to your tracker.')}catch(e){}}
  catch(e){try{say('Could not save. Is Lavoro still running?')}catch(_){}}}));
"""


def render(con, cfg) -> str:
    from .browse import BASE_JS, job_row
    ensure(con)
    rows = con.execute("SELECT * FROM pipeline ORDER BY CASE stage WHEN 'closed' THEN 1 ELSE 0 END, "
                       "coalesce(follow_up,'9999'), updated_at DESC").fetchall()
    counts = {k: 0 for k, _ in STAGES}
    for r in rows:
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    due_rows = due(con)
    today = _today()

    stagebar = "".join(f'<span>{label} <b>{counts[k]}</b></span>' for k, label in STAGES if counts[k])
    hero = (f'<h1>Tracker</h1><p class="count">Every role and company you are going for, in one sheet. Change a stage or a '
            f'date and it saves. Applied and emailed roles get a follow-up date a week later.</p>'
            + (f'<div class="stagebar">{stagebar}</div>' if stagebar else ""))

    due_html = ""
    if due_rows:
        cards = "".join(
            f'<div class="duec"><div class="w"><b>{e(r["company"])}{" · " + e(r["title"]) if r["title"] else ""}</b>'
            f'<small>{STAGE_LABEL.get(r["stage"], r["stage"])} {e(ago(r["applied_at"]) if r["applied_at"] else "")}'
            f'{" · " + e(r["email"]) if r["email"] else ""}. A short, friendly nudge is fine.</small></div>'
            f'<a class="btn2 light" href="/tracker/{r["id"]}#followup">Write a follow-up</a>'
            f'<button class="btn2 dark" type="button" data-followed="{r["id"]}">I followed up</button></div>' for r in due_rows)
        due_html = (f'<section class="sec"><h2>Follow up today</h2><p class="lead">{len(due_rows)} '
                    f'role{"s" if len(due_rows) != 1 else ""} waiting a week or more for an answer.</p>'
                    f'<div class="duelist">{cards}</div></section>')

    def opt(cur):
        return "".join(f'<option value="{k}"{" selected" if k == cur else ""}>{label}</option>' for k, label in STAGES)

    trs = []
    for r in rows:
        is_due = r["stage"] in WAITING and r["follow_up"] and r["follow_up"] <= today
        role = (f'<a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["title"] or "Open")}</a>' if r["url"]
                else e(r["title"] or ""))
        co = f'<a href="/companies/{r["company_id"]}" style="color:inherit;text-decoration:none">{e(r["company"])}</a>' if r["company_id"] else e(r["company"])
        trs.append(
            f'<tr data-id="{r["id"]}"{DUE_CLASS if is_due else ""}><td class="co">{co}</td><td class="ro">{role}</td>'
            f'<td><select data-f="stage" aria-label="Stage">{opt(r["stage"])}</select></td>'
            f'<td><input data-f="contact" value="{e(r["contact"] or "")}" placeholder="Name" aria-label="Contact"></td>'
            f'<td><input data-f="email" value="{e(r["email"] or "")}" placeholder="Email" aria-label="Email"></td>'
            f'<td><input type="date" data-f="applied_at" value="{e(r["applied_at"] or "")}" aria-label="Applied on"></td>'
            f'<td><input type="date" data-f="follow_up" value="{e(r["follow_up"] or "")}" aria-label="Follow up on"></td>'
            f'<td><input data-f="notes" value="{e(r["notes"] or "")}" placeholder="Notes" aria-label="Notes"></td>'
            f'<td class="op"><a href="/tracker/{r["id"]}">Kit &amp; follow-up</a></td>'
            f'<td class="x"><button class="del" type="button" aria-label="Remove row">&times;</button></td></tr>')
    if not trs:
        trs.append('<tr class="empty"><td colspan="10">Nothing tracked yet. Press the bookmark on a role below or on All jobs, '
                   'or mark an email as sent on Today.</td></tr>')
    sheet = (f'<section class="sec"><div class="toolbar"><form class="addrow" id="addrow" autocomplete="off">'
             f'<input name="company" placeholder="Company" aria-label="Company" required>'
             f'<input name="title" placeholder="Role (optional)" aria-label="Role">'
             f'<input name="url" placeholder="Link (optional)" aria-label="Link">'
             f'<button class="btn2 dark" type="submit">Add row</button></form>'
             f'<a class="btn2 light" href="/tracker.csv" download="lavoro-tracker.csv">{icon("copy")}Download for Excel or Sheets</a></div>'
             f'<div class="sheetwrap"><table class="sheet"><thead><tr><th>Company</th><th>Role</th><th>Stage</th><th>Contact</th>'
             f'<th>Email</th><th>Applied</th><th>Follow up</th><th>Notes</th><th></th><th></th></tr></thead>'
             f'<tbody>{"".join(trs)}</tbody></table></div></section>')

    recs = con.execute(
        "SELECT j.*, j.company_id AS cid FROM jobs j WHERE j.score >= ? AND j.status NOT IN ('closed','skipped','sent','duplicate') "
        "AND j.key NOT IN (SELECT job_key FROM pipeline WHERE job_key IS NOT NULL) ORDER BY j.score DESC, j.first_seen DESC LIMIT 8",
        (max(min_score(cfg) - 1, 0),)).fetchall()
    rec_html = ""
    if recs:
        items = "".join(job_row(r) for r in recs)  # job_row carries its own Track button
        rec_html = (f'<section class="sec rec"><h2>Recommended next</h2><p class="lead">Your best-fitting roles that are not in '
                    f'the sheet yet.</p><div class="card list">{items}</div></section>')

    from .browse import CSS as BROWSE_CSS
    return f"""{head("Lavoro · Tracker")}<style>{BROWSE_CSS}{CSS}</style></head>
<body class="browse" data-live="1">
{scene()}
{bar("/tracker")}
<header class="hero slim"><div class="wrap">{hero}</div></header>
<main><div class="wrap">{due_html}{sheet}{rec_html}</div></main>
<footer><div class="wrap"><span>Lavoro · your tracker stays on this computer</span><span><a href="/legal">Terms and privacy</a> · <a href="/">Today</a></span></div></footer>
<div class="toast" role="status" aria-live="polite"></div>
<script>{BASE_JS}</script><script>{JS}{TRACK_JS}</script></body></html>"""


# ---------------------------------------------------------------- one row: application kit and follow-up
ROW_CSS = r"""
.detail{max-width:820px}
.back{display:inline-flex;gap:6px;align-items:center;font:600 14px var(--sans);color:var(--ink-2);text-decoration:none;margin-bottom:10px}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.facts span,.facts a{display:inline-flex;align-items:center;height:32px;padding:0 13px;border-radius:999px;background:rgba(255,255,255,.92);
  box-shadow:0 0 0 1px var(--line) inset;font:600 13px var(--sans);color:var(--ink);text-decoration:none}
.wcard{margin-top:22px;padding:24px;border-radius:20px;background:#fff;box-shadow:0 0 0 1px var(--line) inset}
.wcard h2{margin:0;font:400 32px/1.1 var(--serif);letter-spacing:-.01em}
.wcard .lead{margin:6px 0 16px;color:var(--ink-2);font-size:14px}
.wcard h3{margin:22px 0 8px;font:650 14px var(--sans)}
.wcard pre{margin:0;white-space:pre-wrap;font:400 14.5px/1.65 var(--sans);color:#222;background:var(--inset);border-radius:14px;padding:16px 18px}
.wcard ol,.wcard ul{margin:0;padding-left:20px;display:grid;gap:8px;font-size:14.5px}
.wcard li small{display:block;color:var(--mute);font-size:12.5px}
.kw{display:flex;flex-wrap:wrap;gap:7px}
.kw span{height:28px;display:inline-flex;align-items:center;padding:0 11px;border-radius:999px;background:#e0f2fe;color:#075985;font:600 12.5px var(--sans)}
.wrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:14px}
.btn2.rose{background:var(--rose);color:#fff}
.btn2[disabled]{opacity:.6;cursor:progress}
.subj{font:600 14px var(--sans);margin:0 0 8px}
.when{font-size:12.5px;color:var(--mute)}
.werr{display:none;margin-top:12px;padding:10px 14px;border-radius:12px;background:var(--rose-wash);color:var(--rose-ink);font-size:14px}
.werr.on{display:block}
@media (max-width:640px){.wcard{padding:18px}.wcard h2{font-size:28px}}
"""

ROW_JS = r"""
document.querySelectorAll('[data-write]').forEach(b=>b.addEventListener('click',async()=>{
  const card=b.closest('.wcard'),err=card.querySelector('.werr');b.disabled=true;const t=b.textContent;
  b.textContent='Writing… (about a minute)';err.classList.remove('on');
  try{const r=await fetch('/api/write',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:+b.dataset.id,kind:b.dataset.write})});const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.error||'Could not write it.');location.reload()}
  catch(e){err.textContent=e.message;err.classList.add('on');b.disabled=false;b.textContent=t}}));
document.querySelectorAll('[data-copyfrom]').forEach(b=>b.addEventListener('click',async()=>{
  const el=document.getElementById(b.dataset.copyfrom);const pre=b.dataset.prefix||'';
  say(await copy(pre+el.innerText)?'Copied.':'Could not copy. Select the text instead.')}));
"""


def render_row(con, cfg, rid: int) -> str | None:
    from urllib.parse import quote

    from . import apply
    from .browse import BASE_JS
    from .browse import CSS as BROWSE_CSS
    ensure(con)
    p = con.execute("SELECT * FROM pipeline WHERE id=?", (rid,)).fetchone()
    if p is None:
        return None
    w = apply.get(con, rid)
    kit, fu = w.get("kit"), w.get("followup")
    facts = [f'<span>{STAGE_LABEL.get(p["stage"], p["stage"])}</span>']
    if p["applied_at"]:
        facts.append(f'<span>Applied {e(p["applied_at"])}</span>')
    if p["follow_up"]:
        facts.append(f'<span>Follow up {e(p["follow_up"])}</span>')
    if p["url"]:
        facts.append(f'<a href="{e(p["url"])}" target="_blank" rel="noopener">Open the ad</a>')
    if p["company_id"]:
        facts.append(f'<a href="/companies/{p["company_id"]}">{e(p["company"])} on Lavoro</a>')
    hero = (f'<a class="back" href="/tracker">&larr; Tracker</a><h1>{e(p["company"])}</h1>'
            f'<p class="count">{e(p["title"] or "A role")}</p><div class="facts">{"".join(facts)}</div>')

    if kit:
        pts = "".join(f'<li>{e(c["point"])}<small>{e(c["why"])}</small></li>' for c in kit.get("cv_points", []))
        kws = "".join(f"<span>{e(k)}</span>" for k in kit.get("keywords", []))
        gaps = "".join(f"<li>{e(g)}</li>" for g in kit.get("gaps", []))
        kit_html = (f'<h3>Cover letter</h3><pre id="letter">{e(kit["cover_letter"])}</pre>'
                    f'<div class="wrow"><button class="btn2 dark" type="button" data-copyfrom="letter">Copy the letter</button>'
                    f'<span class="when">Written {e(ago(kit["created_at"]))} in {e(kit.get("language", ""))}. '
                    f'Read it through before you use it.</span></div>'
                    + (f'<h3>Put these CV points first</h3><ol>{pts}</ol>' if pts else "")
                    + (f'<h3>Words from the ad to mirror in your CV</h3><div class="kw">{kws}</div>' if kws else "")
                    + (f'<h3>What the ad asks for that your profile does not show</h3><ul>{gaps}</ul>' if gaps else ""))
        kit_btn = f'<button class="btn2 light" type="button" data-write="kit" data-id="{rid}">Write it again</button>'
    else:
        kit_html = ""
        kit_btn = f'<button class="btn2 rose" type="button" data-write="kit" data-id="{rid}">Write the application kit</button>'
    kit_card = (f'<section class="wcard"><h2>Application kit</h2><p class="lead">For applying through the careers site: '
                f'a cover letter, the CV points this ad cares about, and what to prepare for. Only facts from your profile.</p>'
                f'{kit_html}<div class="wrow">{kit_btn}</div><div class="werr" role="alert"></div></section>')

    if fu:
        mailto = (f'mailto:{quote(fu.get("to", ""))}?subject={quote(fu["subject"])}&body={quote(fu["body"])}'
                  if fu.get("to") else "")
        prefix = e("Subject: " + fu["subject"]) + "&#10;&#10;"
        fu_html = (f'<p class="subj">Subject: {e(fu["subject"])}</p><pre id="fubody">{e(fu["body"])}</pre>'
                   f'<div class="wrow"><button class="btn2 dark" type="button" data-copyfrom="fubody" data-prefix="{prefix}">Copy</button>'
                   + (f'<a class="btn2 light" href="{e(mailto)}">Open in your mail app</a>' if mailto else "")
                   + '<span class="when">Nothing is sent. After you send it, press "I followed up" on the tracker.</span></div>')
        fu_btn = f'<button class="btn2 light" type="button" data-write="followup" data-id="{rid}">Write it again</button>'
    else:
        fu_html = ""
        fu_btn = f'<button class="btn2 rose" type="button" data-write="followup" data-id="{rid}">Write a follow-up</button>'
    fu_card = (f'<section class="wcard" id="followup"><h2>Follow-up</h2><p class="lead">A short, friendly nudge when a week '
               f'has passed without an answer. It adds one new thing about you instead of just asking again.</p>'
               f'{fu_html}<div class="wrow">{fu_btn}</div><div class="werr" role="alert"></div></section>')

    return f"""{head("Lavoro · " + (p["company"] or "Tracker"))}<style>{BROWSE_CSS}{CSS}{ROW_CSS}</style></head>
<body class="browse" data-live="1">
{scene()}
{bar("/tracker")}
<header class="hero slim"><div class="wrap detail">{hero}</div></header>
<main><div class="wrap detail">{kit_card}{fu_card}</div></main>
<footer><div class="wrap"><span>Lavoro · your tracker stays on this computer</span><span><a href="/legal">Terms and privacy</a> · <a href="/tracker">Tracker</a></span></div></footer>
<div class="toast" role="status" aria-live="polite"></div>
<script>{BASE_JS}</script><script>{ROW_JS}</script></body></html>"""
