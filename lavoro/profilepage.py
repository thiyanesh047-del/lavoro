"""/profile: the profile Lavoro scores roles against and writes emails from, and what it searches for.

Shows profile.md as a readable page, lets you change the search settings in config.yaml without starting a run,
and links to the setup page to build the profile again from a new CV or portfolio link (the old profile is
backed up first). Everything here stays on this computer.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from . import regions
from .browse import _page
from .config import ROOT
from .digest import ago, e

CSS = r"""
.eyebrow{margin:0 0 10px;font:600 12px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}
.pf-lede{margin:14px 0 0;color:var(--ink-2);font-size:17px;line-height:1.55;max-width:62ch}
.pf-meta{margin:14px 0 0;font-size:13.5px;color:var(--mute)}
.pf-acts{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.pf-btn{display:inline-flex;align-items:center;gap:8px;height:44px;padding:0 18px;border-radius:999px;text-decoration:none;
  font:600 14.5px var(--sans);color:var(--ink);background:rgba(255,255,255,.6);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  box-shadow:0 0 0 1px rgba(23,23,23,.12) inset;border:0;cursor:pointer}
.pf-btn:hover{background:#fff;box-shadow:0 0 0 1px rgba(23,23,23,.3) inset}
.pf-btn.main{background:var(--ink);color:#fff;box-shadow:none}.pf-btn.main:hover{background:#000}
.pf-btn svg{width:16px;height:16px}
.pf-note{margin:12px 0 0;font-size:13px;color:var(--mute);max-width:62ch}
.pf-grid{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:24px;align-items:start;margin-top:8px}
.pf-side{position:sticky;top:84px;display:flex;flex-direction:column;gap:20px}
.pf-card{background:#fff;border-radius:20px;box-shadow:0 0 0 1px var(--line) inset;padding:26px 28px}
.pf-card>h2{margin:0 0 4px}.pf-card>.sub{margin:0 0 18px}
.todo-n{display:inline-flex;align-items:center;height:28px;padding:0 12px;border-radius:999px;font:600 13px var(--sans);
  background:var(--amber-wash);color:var(--amber-ink);margin-left:8px;vertical-align:4px}
.doc{font-size:15px;line-height:1.65;color:var(--ink-2)}
.doc h1{display:none}
.doc h2{margin:26px 0 8px;font:400 26px/1.15 var(--serif);color:var(--ink);letter-spacing:-.01em}
.doc h2:first-child{margin-top:0}
.doc h3{margin:18px 0 6px;font:600 15.5px/1.35 var(--sans);color:var(--ink)}
.doc p{margin:0 0 10px}
.doc ul{margin:0 0 10px;padding-left:20px}.doc li{margin:4px 0}
.doc strong{color:var(--ink);font-weight:600}
.doc a{color:var(--ink);text-underline-offset:3px;word-break:break-word}
.doc .todo{background:var(--amber-wash);color:var(--amber-ink);border-radius:6px;padding:1px 5px}
.form{display:flex;flex-direction:column;gap:14px}
.form label{display:flex;flex-direction:column;gap:6px;font:600 13px var(--sans);color:var(--ink-2)}
.form label small{font-weight:400;color:var(--mute)}
.form input[type=text],.form input[type=url],.form textarea,.form select{font:400 14.5px var(--sans);color:var(--ink);background:var(--inset);
  border:0;border-radius:12px;padding:11px 13px;box-shadow:0 0 0 1px var(--line) inset;width:100%;box-sizing:border-box}
.form textarea{resize:vertical;min-height:72px;line-height:1.45}
.form input:focus,.form textarea:focus,.form select:focus{outline:2px solid var(--ink);outline-offset:1px;background:#fff}
.form .check{flex-direction:row;align-items:center;gap:10px;font-weight:500;color:var(--ink)}
.form .check input{width:18px;height:18px;accent-color:var(--ink)}
.form .save{align-self:flex-start;height:42px;padding:0 20px;border:0;border-radius:12px;background:var(--ink);color:#fff;
  font:600 14px var(--sans);cursor:pointer}
.form .save:hover{background:#000}.form .save[disabled]{opacity:.6;cursor:progress}
.form .err{display:none;margin:0;font-size:13.5px;color:var(--rose-ink)}.form .err.on{display:block}
.olds{margin:0;padding:0;list-style:none;font-size:13.5px;color:var(--ink-2)}
.olds li{padding:8px 0;border-top:1px solid var(--line)}.olds li:first-child{border-top:0;padding-top:0}
.olds code{font-size:12px;color:var(--mute);background:none;padding:0}
@media (max-width:980px){.pf-grid{grid-template-columns:minmax(0,1fr)}.pf-side{position:static}}
@media (max-width:640px){.pf-card{padding:20px 16px}}
"""

JS = r"""
(()=>{
const form=document.getElementById('prefs');if(!form)return;
const list=s=>s.split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean);
const err=form.querySelector('.err'), save=form.querySelector('.save');
let region=form.region.value;
form.addEventListener('submit',async ev=>{ev.preventDefault();err.classList.remove('on');save.disabled=true;
  try{
    await api('/api/preferences',{name:form.name.value,portfolio:form.portfolio.value,linkedin:form.linkedin.value,
      titles:list(form.titles.value),locations:list(form.locations.value),remote_ok:form.remote.checked,in_sweden:form.sweden.checked,keep_queries:true});
    let extra='';
    if(form.region.value!==region){const r=await api('/api/region',{region:form.region.value});region=form.region.value;
      extra=r.reopened?` ${r.reopened.toLocaleString()} earlier roles will be checked again.`:''}
    say('Saved. The next run searches with these.'+extra)}
  catch(e){err.textContent=e.message||'Could not save.';err.classList.add('on')}
  finally{save.disabled=false}});
})();
"""


# ---------------------------------------------------------------- profile.md → html
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"(?<![\"'>=])(https?://[^\s<)]+)")


def _inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = _LINK.sub(lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    s = _URL.sub(lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\bTODO\b[^<]*", lambda m: f'<span class="todo">{m.group(0)}</span>', s)
    return s


def to_html(md: str) -> str:
    """The small part of Markdown profile.md uses: headings, bullets, bold, links, paragraphs."""
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif re.match(r"^\s*[-*]\s+", line):
            if para:
                flush()
            items.append(re.sub(r"^\s*[-*]\s+", "", line))
        elif line.startswith((" ", "\t")) and items and line.strip():
            items[-1] += " " + line.strip()  # a bullet that wraps onto the next line
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "".join(out)


def _split_header(text: str) -> tuple[str, str]:
    """(the note Lavoro wrote at the top, the profile itself)."""
    m = re.match(r"\s*<!--(.*?)-->", text, re.S)
    return (m.group(1).strip(), text[m.end():]) if m else ("", text)


def _date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day} {d:%B %Y}"


def _backups() -> list[tuple[datetime, Path]]:
    out = []
    for p in (ROOT / "data").glob("profile.backup-*.md"):
        m = re.search(r"(\d{8})-(\d{6})", p.name)
        if m:
            out.append((datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"), p))
    return sorted(out, reverse=True)


# ---------------------------------------------------------------- the page
def render(cfg) -> str:
    me, search = cfg.get("me", {}) or {}, cfg.get("search", {}) or {}
    path = ROOT / me.get("profile_file", "profile.md")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    note, md = _split_header(text)
    todos = len(re.findall(r"\bTODO\b", md))
    headline = ""
    m = re.search(r"^##\s+Headline\s*\n+(.+?)(?:\n\s*\n|\n##)", md, re.S | re.M)
    if m:
        headline = " ".join(m.group(1).split())
        headline = re.split(r"(?<=[.!?])\s", headline)[0]

    src = ""
    flat = " ".join(note.split())
    sm = re.search(r"Built (?:by Lavoro )?(?:from (?P<a>.+?) )?on (?P<d>\d{4}-\d{2}-\d{2})(?: from (?P<b>.+?)\.(?:\s|$))?", flat)
    if sm:
        frm = (sm.group("a") or sm.group("b") or "").strip()
        frm = frm if len(frm) <= 140 else frm[:137].rsplit(" ", 1)[0] + "…"
        src = f"Built from {frm} on {_date(sm.group('d'))}." if frm else f"Built on {_date(sm.group('d'))}."
    changed = ""
    if path.exists():
        changed = f"Last changed {ago(datetime.fromtimestamp(path.stat().st_mtime).isoformat())}."
    meta = " ".join(x for x in (src, changed) if x)

    name = (me.get("name") or "").strip()
    hero = (f'<p class="eyebrow">Your profile</p><h1>{e(name) if name else "Your profile"}</h1>'
            + (f'<p class="pf-lede">{e(headline)}</p>' if headline else "")
            + (f'<p class="pf-meta">{e(meta)}</p>' if meta else "")
            + f'<div class="pf-acts"><a class="pf-btn main" href="/welcome">Upload a new CV</a><a class="pf-btn" href="/welcome">Use a portfolio link</a></div>'
            + '<p class="pf-note">Lavoro reads it and builds your profile again. Your current profile is kept as a backup '
              'first, and your jobs, tracker and drafts stay as they are.</p>')

    doc = to_html(md) if md.strip() else '<p>No profile yet. Upload a CV to make one.</p>'
    profile_card = (f'<section class="pf-card"><h2>What Lavoro knows about you'
                    + (f'<span class="todo-n">{todos} to fill in</span>' if todos else "") + '</h2>'
                    f'<p class="sub">Every role is scored against this, and every email is written from it. Lavoro never '
                    f'adds facts of its own. To change a line, edit <code>{e(path.name)}</code> in the Lavoro folder.</p>'
                    f'<div class="doc">{doc}</div></section>')

    titles = search.get("titles_include") or []
    places = search.get("locations_include") or []
    cur = regions.current(cfg)
    opts = "".join(f'<option value="{k}"{" selected" if k == cur else ""}>{e(v)}</option>' for k, v in regions.LABELS.items())
    jobtech = (search.get("jobtech") or {}).get("enabled", False)
    form = (f'<section class="pf-card"><h2>What Lavoro looks for</h2>'
            f'<p class="sub">Saved to <code>config.yaml</code>. The next run uses them; saving does not start one.</p>'
            f'<form id="prefs" class="form" novalidate>'
            f'<label>Your name<input type="text" name="name" value="{e(name)}" autocomplete="name"></label>'
            f'<label>Roles to search for <small>One per line, or separated by commas.</small>'
            f'<textarea name="titles" rows="7">{e(chr(10).join(titles))}</textarea></label>'
            f'<label>Places <small>Cities or countries, one per line.</small>'
            f'<textarea name="locations" rows="5">{e(chr(10).join(p for p in places if p != "remote"))}</textarea></label>'
            f'<label>Region<select name="region">{opts}</select></label>'
            f'<label class="check"><input type="checkbox" name="remote"{" checked" if search.get("remote_ok", True) else ""}>'
            f'Remote roles are fine</label>'
            f'<label class="check"><input type="checkbox" name="sweden"{" checked" if jobtech else ""}>'
            f'Also search Platsbanken (Sweden)</label>'
            f'<label>Portfolio<input type="url" name="portfolio" value="{e(me.get("portfolio") or "")}"></label>'
            f'<label>LinkedIn<input type="url" name="linkedin" value="{e(me.get("linkedin") or "")}"></label>'
            f'<p class="err" role="alert"></p><button class="save" type="submit">Save</button></form></section>')

    olds = _backups()
    old_card = ""
    if olds:
        items = "".join(f'<li>{d.day} {d:%B %Y}, {d:%H:%M}<br><code>data/{e(p.name)}</code></li>' for d, p in olds[:6])
        more = f'<p class="pf-note">And {len(olds) - 6} older.</p>' if len(olds) > 6 else ""
        old_card = (f'<section class="pf-card"><h2>Earlier versions</h2><p class="sub">Kept each time the profile was built '
                    f'again. Copy one back over <code>{e(path.name)}</code> to return to it.</p><ul class="olds">{items}</ul>{more}</section>')

    body = (f'<style>{CSS}</style><div class="pf-grid">{profile_card}<div class="pf-side">{form}{old_card}</div></div>')
    return _page("Lavoro · Your profile", "/profile", hero, body).replace("</body>", f"<script>{JS}</script></body>", 1)

