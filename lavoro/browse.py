"""Browse pages: every open job (/jobs), every tracked company (/companies) and one company (/companies/<id>).

Server-rendered from the local database with plain GET forms, so links can be bookmarked and the back button works.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urlencode

from . import logos
from .digest import CSS as BASE_CSS
from .digest import JS as BASE_JS
from .digest import ago, bar, e, fit_score, head, icon, scene
from .discover import SUPPORTED
from .tracker import TRACK_JS

PAGE_JOBS = 50
PAGE_COMPANIES = 60

CATEGORIES = [("", "All"), ("design", "Design"), ("product", "Product"), ("tech", "Tech"), ("marketing", "Marketing"),
              ("sales", "Sales"), ("operations", "Operations"), ("healthcare", "Healthcare"), ("other", "Other")]

# A role's category, guessed from its title. First match wins, so the order matters.
# The title is matched with a space on each side, so " ux " finds UX as a word but not the "ux" in Linux or Benelux.
_DESIGN_WORDS = ["design", " ux ", " ux/", "/ux ", "/ux/", " ux-", " ux,", "(ux)", "(ux ", "(ux/", " ux)", "/ux)",
                 " ui ", " ui/", "/ui ", " ui-", " ui,", "(ui)", "(ui ", "(ui/", " ui)", "/ui)",
                 "user experience", "user research"]
# Design words in an engineering or CAD title (Design Engineer, Mechanical Designer, UI Engineer): that role is Tech.
_ENGINEERING_DESIGN = ["engineer", "ingenjör", "developer", "utvecklare", "verification", "design-for-test",
                       "design for test", "mechanical design", "electrical design", "hardware design", "pcb", "ecad",
                       " cad", "hvac", "rtl", "asic", "structural design", "civil", "antenna", "electronics"]
_CAT_RULES = [
    ("tech", _ENGINEERING_DESIGN, _DESIGN_WORDS),
    ("design", _DESIGN_WORDS),
    # Engineers on a content or growth team, and finance roles with "content" in the team name, are not Marketing.
    ("tech", ["engineer", "developer", "scientist", "architect"], ["content", "growth", "brand", "seo", "communications"]),
    ("operations", ["accounting", "accountant", "payroll", "legal counsel", "general counsel", "paralegal"]),
    ("product", ["product manager", "product owner", "product lead", "head of product", "product operations",
                 "product management", "product director", "vp product", "product specialist"]),
    ("marketing", ["marketing", "growth", "content", "seo", "brand", "communications", "social media", "copywriter", "pr "]),
    ("sales", ["sales", "account executive", "business development", "account manager", "sdr", "bdr", "partnership",
               "customer success", "solutions consultant", "revenue", "gtm", "customer ", " account ", "enterprise"]),
    ("healthcare", ["nurse", "psychiatr", "physician", "practitioner", "therap", "rbt", "clinical", "clinician", "medical",
                    "dentist", "pmhnp", "behavior", "pharmac", "counselor", "telehealth", "health"]),
    ("tech", ["engineer", "developer", "data", "scientist", "machine learning", "devops", "security", "software",
              "infrastructure", "platform", "qa", "research", "architect", "programmer", "ml ", "ai ", "technical", "deployment"]),
    ("operations", ["operations", "finance", "legal", "counsel", "people", "recruit", "talent", "hr ", "accountant",
                    "controller", "office", "analyst", "support", "payroll", "procurement", "chief of staff", "program manager",
                    "project manager", "delivery", "implementation", "technician", "strateg", "consultant", "warehouse",
                    "logistics", "coordinator", "administrator", "assistant", "manager", "analytiker", "director"]),
]
def _any_sql(words: list[str]) -> str:
    return "(" + " OR ".join(f"(' ' || lower(j.title) || ' ') LIKE '%{w}%'" for w in words) + ")"


# A rule is (category, words) or (category, words, also_needs): the title must contain one of the words, and, when
# given, one of also_needs as well.
CAT_SQL = "CASE " + " ".join(
    f"WHEN {_any_sql(rule[1])}{' AND ' + _any_sql(rule[2]) if len(rule) > 2 else ''} THEN '{rule[0]}'"
    for rule in _CAT_RULES) + " ELSE 'other' END"

BOARD_URL = {
    "greenhouse": "https://boards.greenhouse.io/{s}", "lever": "https://jobs.lever.co/{s}",
    "ashby": "https://jobs.ashbyhq.com/{s}", "workable": "https://apply.workable.com/{s}",
    "recruitee": "https://{s}.recruitee.com", "smartrecruiters": "https://jobs.smartrecruiters.com/{s}",
}


def board_url(ats: str | None, slug: str | None) -> str | None:
    if not ats or not slug or ats == "none":
        return None
    if ats == "teamtailor":
        return f"https://{slug}" if "." in slug else f"https://{slug}.teamtailor.com/jobs"
    if ats in ("workday", "successfactors"):
        return f"https://{slug}"
    return BOARD_URL.get(ats, "").format(s=slug) or None


CSS = r"""
body.browse .wrap{max-width:1040px}
header.hero.slim{min-height:auto;padding:9vh 0 60px}
header.hero.slim h1{font-size:clamp(44px,6.4vw,68px);max-width:none}
.count{margin:16px 0 0;font:500 16px/1.6 var(--sans);color:#1f1f1f;max-width:60ch;text-shadow:0 1px 18px rgba(255,252,248,.95)}
.count b{font-weight:700}
.addco{display:flex;gap:10px;margin-top:22px;max-width:560px}
.addco .search{box-shadow:0 0 0 1px var(--line) inset,0 10px 30px -14px rgba(20,20,20,.35)}
.addco .apply:disabled{opacity:.6;cursor:progress}
.addco-note{margin:8px 0 0;font:500 13px/1.5 var(--sans);color:var(--ink-2);max-width:560px;text-shadow:0 1px 14px rgba(255,252,248,.95)}
.addco-note.bad{color:var(--rose-ink)}
.filters{position:sticky;top:64px;z-index:4;margin:0 -12px 18px;padding:12px;border-radius:18px;
  background:rgba(251,250,248,.9);backdrop-filter:blur(12px) saturate(1.3)}
.frow{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.search{flex:1 1 260px;display:flex;align-items:center;gap:8px;height:46px;padding:0 14px;border-radius:12px;background:#fff;
  box-shadow:0 0 0 1px var(--line) inset}
.search:focus-within{box-shadow:0 0 0 2px rgba(225,29,72,.35) inset}
.search svg{width:16px;height:16px;color:var(--mute);flex:none}
.search input{flex:1;min-width:0;border:0;outline:0;background:transparent;font:500 15px var(--sans);color:var(--ink)}
.search.where{flex:0 1 200px}
.toggle{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 14px;border-radius:999px;background:#fff;cursor:pointer;
  box-shadow:0 0 0 1px var(--line) inset;font:500 14px var(--sans);white-space:nowrap;user-select:none}
.toggle input{accent-color:var(--rose);width:16px;height:16px;margin:0}
.toggle:has(input:checked){box-shadow:0 0 0 1px rgba(225,29,72,.45) inset;background:var(--rose-wash);color:var(--rose-ink)}
.apply{white-space:nowrap;height:46px;padding:0 18px;border:0;border-radius:12px;background:var(--ink);color:#fff;font:600 14.5px var(--sans);cursor:pointer}
.tabs{display:flex;gap:6px;margin-top:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:none;display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;border-radius:999px;text-decoration:none;
  font:500 14px var(--sans);color:var(--ink-2);background:transparent;box-shadow:0 0 0 1px var(--line) inset;white-space:nowrap}
.tab:hover{background:#fff}
.tab span{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}
.tab[aria-current=page]{background:var(--ink);color:#fff;box-shadow:none}.tab[aria-current=page] span{color:rgba(255,255,255,.7)}
.results{color:var(--mute);font-size:13.5px;margin:0 0 10px}
.pager{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:18px 0 0}
.pager a,.pager span.off{display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 16px;border-radius:999px;
  text-decoration:none;font:600 14px var(--sans);background:#fff;box-shadow:0 0 0 1px var(--line) inset}
.pager span.off{opacity:.4}
.pager .where{color:var(--mute);font-size:13.5px;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media (max-width:980px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.co{display:block;padding:18px 20px;text-decoration:none;transition:transform .2s var(--ease),box-shadow .2s}
.co:hover{transform:translateY(-2px);box-shadow:0 10px 30px -14px rgba(30,40,30,.3)}
.co-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
.co-id{display:flex;align-items:center;gap:12px;min-width:0}
.colog{width:42px;height:42px;border-radius:12px;font-size:22px}
.co-name{font:400 26px/1.1 var(--serif);letter-spacing:-.01em}
.co-roles{font-size:12.5px;color:var(--mint-ink);font-weight:600;white-space:nowrap}
.co-roles.none{color:var(--mute);font-weight:500}
.co-line{margin:6px 0 0;color:var(--ink-2);font-size:14px;line-height:1.5}
.co-meta{margin-top:8px;color:var(--mute);font-size:12.5px}
.co-line.hint{color:var(--mute);font-size:13.5px}
/* company page: open roles by team */
.mix{margin:4px 0 26px}
.mixbar{display:flex;height:12px;border-radius:999px;overflow:hidden;gap:2px;background:#fff;box-shadow:0 0 0 1px var(--line)}
.mixbar span{display:block;min-width:4px}
.mixkey{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.mixkey a{display:inline-flex;align-items:center;gap:8px;height:34px;padding:0 13px;border-radius:999px;background:#fff;
  box-shadow:0 0 0 1px var(--line) inset;text-decoration:none;font:500 14px var(--sans);color:var(--ink)}
.mixkey a:hover{box-shadow:0 0 0 1px rgba(23,23,23,.35) inset}
.mixkey i{width:10px;height:10px;border-radius:3px}
.mixkey b{font-weight:500;color:var(--mute);font-variant-numeric:tabular-nums}
.team{scroll-margin-top:84px;margin-top:30px}
.team-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.team-head h3{display:flex;align-items:center;gap:10px;margin:0;font:400 30px/1.1 var(--serif);letter-spacing:-.015em}
.team-head h3 i{width:12px;height:12px;border-radius:4px}
.team-head h3 small{font:500 15px var(--sans);color:var(--mute);font-variant-numeric:tabular-nums}
.team-head a{font:500 13.5px var(--sans);color:var(--ink-2)}
.team-sub{margin:6px 0 12px;color:var(--ink-2);font-size:14px}
.lead-row{display:flex;align-items:center;gap:12px;padding:12px 16px;margin-bottom:10px;border-radius:14px;background:var(--mint-wash);
  box-shadow:0 0 0 1px var(--mint-ring) inset;font-size:14px;color:var(--mint-ink)}
.lead-row .av{flex:none;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#fff;font:600 12.5px var(--sans)}
.lead-row b{color:var(--ink);font-weight:600}
.more-roles summary{list-style:none;cursor:pointer;padding:13px 20px;font:600 14px var(--sans);color:var(--ink-2);border-top:1px solid var(--line)}
.more-roles summary::-webkit-details-marker{display:none}
.more-roles summary:hover{color:var(--ink);background:#fcfbf9}
.more-roles[open] summary{display:none}
.star{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;border-radius:999px;border:0;cursor:pointer;
  background:rgba(255,255,255,.85);box-shadow:0 0 0 1px var(--line) inset;font:600 13.5px var(--sans);color:var(--ink-2);
  backdrop-filter:blur(8px);transition:background .2s,color .2s,box-shadow .2s}
.star svg{width:15px;height:15px;transition:fill .2s,transform .3s var(--ease)}
.star:hover{color:var(--ink);background:#fff}
.star[aria-pressed=true]{background:#fff4d6;color:#8a5a00;box-shadow:0 0 0 1px rgba(234,179,8,.55) inset}
.star[aria-pressed=true] svg{fill:#eab308;color:#b7791f;transform:scale(1.08)}
.star.mini{position:absolute;right:12px;bottom:12px;width:34px;height:34px;padding:0;justify-content:center}
.co-wrap{position:relative;display:flex}
.co-wrap .co{flex:1;padding-bottom:54px}  /* room for the follow star, so it never covers the text */
.facts{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.fact{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 14px;border-radius:999px;background:rgba(255,255,255,.85);
  box-shadow:0 0 0 1px var(--line) inset;font:500 13.5px var(--sans);color:var(--ink-2);text-decoration:none;backdrop-filter:blur(8px)}
a.fact:hover{background:#fff;color:var(--ink)}
.fact svg{width:14px;height:14px}
.empty-note{padding:28px 24px;color:var(--ink-2)}
@media (max-width:640px){
  header.hero.slim{padding:5vh 0 40px}
  .filters{top:0;position:relative;margin:0 0 14px;padding:10px}
  .search.where{flex:1 1 100%}
  .apply{flex:1}
  .grid{grid-template-columns:1fr}
  .jrow{padding:14px}
}
"""

JS = r"""
document.querySelectorAll('form.filters input[type=checkbox]').forEach(c=>c.addEventListener('change',()=>c.form.submit()));
document.querySelectorAll('[data-star]').forEach(b=>b.addEventListener('click',async ev=>{
  ev.preventDefault();ev.stopPropagation();const on=b.getAttribute('aria-pressed')!=='true';
  try{const r=await fetch('/api/star',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:+b.dataset.star,on})});if(!r.ok)throw 0;
    b.setAttribute('aria-pressed',on);const t=b.querySelector('span');if(t)t.textContent=on?'Following':'Follow';
    say(on?'Following. New roles from them show up on Today.':'Stopped following.')}
  catch(e){say('Could not save. Is Lavoro still running?')}}));
const addco=document.querySelector('form.addco');
if(addco){const note=document.querySelector('.addco-note'),btn=addco.querySelector('button'),inp=addco.querySelector('input');
  addco.addEventListener('submit',async ev=>{ev.preventDefault();const text=inp.value.trim();
    if(!text){note.textContent='Type a company name or paste a link.';note.classList.add('bad');inp.focus();return}
    btn.disabled=true;btn.textContent='Looking…';note.classList.remove('bad');
    note.textContent='Looking for '+text+'’s job board. This takes up to half a minute.';
    try{const r=await fetch('/api/company',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Could not add that company.');
      note.textContent=(d.existed?'Already watching ':'Added ')+d.name+': '+d.roles+' open role'+(d.roles===1?'':'s')+'. Opening it…';
      location.href='/companies/'+d.id}
    catch(e){note.textContent=e.message==='Failed to fetch'?'Could not reach Lavoro. Is it still running?':e.message;
      note.classList.add('bad');btn.disabled=false;btn.textContent='Add'}})}
"""

EXT = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
       'aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3"/></svg>')
PLUS = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true"><path d="M12 5v14"/><path d="M5 12h14"/></svg>')
SEARCH = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
          'aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>')
PIN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
       'aria-hidden="true"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/>'
       '<circle cx="12" cy="10" r="3"/></svg>')


STAR = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 '
        '.294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 '
        '21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 '
        '1.597-1.16z"/></svg>')


def star_btn(cid: int, name: str, on: bool, label: bool = True) -> str:
    text = f'<span>{"Following" if on else "Follow"}</span>' if label else ""
    return (f'<button class="star{"" if label else " mini"}" type="button" data-star="{cid}" aria-pressed="{"true" if on else "false"}" '
            f'aria-label="Follow {e(name)}">{STAR}{text}</button>')


def _page(title: str, active: str, hero: str, body: str) -> str:
    return f"""{head(title)}<style>{CSS}</style></head>
<body class="browse" data-live="1">
{scene()}
{bar(active)}
<header class="hero slim"><div class="wrap">{hero}</div></header>
<main><div class="wrap">{body}</div></main>
<footer><div class="wrap"><span>Lavoro · read from public job boards, on your computer</span>
<span><a href="/legal">Terms and privacy</a> · <a href="/welcome">Set up again</a></span></div></footer>
<div class="toast" role="status" aria-live="polite"></div>
<script>{BASE_JS}</script><script>{JS}{TRACK_JS}</script></body></html>"""


def _qs(params: dict, **change) -> str:
    p = {k: v for k, v in {**params, **change}.items() if v not in ("", None, "0", 0, False)}
    return ("?" + urlencode(p)) if p else ""


def _int(v, default=1) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return default


def _pager(path: str, params: dict, page: int, total: int, size: int) -> str:
    last = max(1, -(-total // size))
    prev = f'<a href="{path}{e(_qs(params, page=page - 1 if page > 2 else ""))}">← Newer</a>' if page > 1 else '<span class="off">← Newer</span>'
    nxt = f'<a href="{path}{e(_qs(params, page=page + 1))}">Older →</a>' if page < last else '<span class="off">Older →</span>'
    return f'<nav class="pager" aria-label="Pages">{prev}<span class="where">Page {page} of {last:,}</span>{nxt}</nav>'


def job_row(r, extra_meta: str = "", with_company: bool = True) -> str:
    """One job line: title (to the ad), company (to its Lavoro page), place, and on the right fit/pay/age."""
    company = ""
    if with_company:
        cid = r["cid"] if "cid" in r.keys() else r["company_id"]
        company = (f'<a href="/companies/{cid}">{logos.tile(cid, r["company"], "mini")}{e(r["company"])}</a>' if cid
                   else e(r["company"]))
    meta = " · ".join(x for x in [company, e(r["location"]), e(r["department"]) if r["department"] else "", extra_meta] if x)
    side = []
    if r["status"] == "drafted":
        side.append('<a class="tag ready" href="/">Email ready</a>')
    elif r["score"] is not None:
        side.append(fit_score(r["score"]))
    if r["salary"]:
        side.append(f'<span class="tag pay">{e(r["salary"].split("•")[0].strip()[:30])}</span>')
    side.append(f'<span class="age">{e(ago(r["posted_at"] or r["first_seen"]))}</span>')
    mark = ""
    if "key" in r.keys():
        from .tracker import track_btn
        mark = track_btn(r["key"], bool(r["tracked"]) if "tracked" in r.keys() else False)
    return (f'<div class="jrow"><div><a class="jt" href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["title"])}</a>'
            f'<div class="jm">{meta}</div></div><div class="side"><div class="sv">{"".join(side)}</div>{mark}</div></div>')


# ---------------------------------------------------------------- /jobs
def render_jobs(con, params: dict) -> str:
    q, where = params.get("q", "").strip(), params.get("where", "").strip()
    cat = params.get("cat", "") if params.get("cat", "") in dict(CATEGORIES) else ""
    remote, pay, page = params.get("remote") == "1", params.get("pay") == "1", _int(params.get("page"))
    visa = params.get("visa") == "1"

    cond, args = ["j.status NOT IN ('closed','duplicate')"], []
    if q:
        cond.append("(j.title LIKE ? OR j.company LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if where:
        cond.append("j.location LIKE ?")
        args.append(f"%{where}%")
    if remote:
        cond.append("(j.remote = 1 OR lower(j.location) LIKE '%remote%')")
    if pay:
        cond.append("j.salary IS NOT NULL AND j.salary <> ''")
    if visa:  # the ad mentions a visa, sponsorship or relocation
        cond.append("(lower(j.description) LIKE '%visa%' OR lower(j.description) LIKE '%relocat%' "
                    "OR lower(j.description) LIKE '%sponsorship%')")
    base = f"SELECT j.*, {CAT_SQL} AS cat, (SELECT 1 FROM pipeline p WHERE p.job_key = j.key) AS tracked FROM jobs j WHERE {' AND '.join(cond)}"

    counts = dict(con.execute(f"SELECT cat, count(*) FROM ({base}) GROUP BY cat", args).fetchall())
    total_all = sum(counts.values())
    total = counts.get(cat, 0) if cat else total_all
    sql = (f"SELECT x.*, c.id AS cid FROM ({base}) x LEFT JOIN companies c ON c.id = x.company_id "
           + ("WHERE x.cat = ? " if cat else "")
           + "ORDER BY substr(coalesce(x.posted_at, x.first_seen), 1, 10) DESC, x.first_seen DESC LIMIT ? OFFSET ?")
    rows = con.execute(sql, args + ([cat] if cat else []) + [PAGE_JOBS, (page - 1) * PAGE_JOBS]).fetchall()

    open_all = con.execute("SELECT count(*) FROM jobs WHERE status NOT IN ('closed','duplicate')").fetchone()[0]
    hiring = con.execute("SELECT count(DISTINCT coalesce(company_id, company)) FROM jobs WHERE status NOT IN ('closed','duplicate')").fetchone()[0]
    hero = (f'<h1>All jobs</h1><p class="count"><b>{open_all:,}</b> open roles at <b>{hiring:,}</b> companies, read straight from '
            f'their own job boards{" and Platsbanken" if con.execute("SELECT 1 FROM jobs WHERE source=? LIMIT 1", ("jobtech",)).fetchone() else ""}. '
            f'Roles that close are removed on the next run.</p>')

    keep = {"q": q, "where": where, "remote": "1" if remote else "", "pay": "1" if pay else "", "visa": "1" if visa else ""}
    tabs = "".join(
        f'<a class="tab" href="/jobs{e(_qs(keep, cat=k))}"{" aria-current=page" if k == cat else ""}>{label}'
        f'<span>{(counts.get(k, 0) if k else total_all):,}</span></a>' for k, label in CATEGORIES)
    form = f"""<form class="filters" method="get" action="/jobs" role="search">
<div class="frow"><label class="search">{SEARCH}<input type="search" name="q" value="{e(q)}" placeholder="Role or company" aria-label="Role or company"></label>
<label class="search where">{PIN}<input type="search" name="where" value="{e(where)}" placeholder="City or country" aria-label="City or country"></label>
{f'<input type="hidden" name="cat" value="{e(cat)}">' if cat else ''}
<label class="toggle"><input type="checkbox" name="remote" value="1"{" checked" if remote else ""}>Remote</label>
<label class="toggle"><input type="checkbox" name="pay" value="1"{" checked" if pay else ""}>Pay listed</label>
<label class="toggle"><input type="checkbox" name="visa" value="1"{" checked" if visa else ""}>Visa or relocation</label>
<button class="apply" type="submit">Search</button></div>
<div class="tabs">{tabs}</div></form>"""

    items = [job_row(r) for r in rows]
    listing = (f'<div class="card list">{"".join(items)}</div>' if items else
               '<div class="card empty-note">No open roles match. Try fewer words, or clear a filter.</div>')
    insight = ""
    if q:
        slug = re.sub(r"[^a-z0-9åäö]+", "-", q.lower()).strip("-")
        insight = f' · <a href="/roles/{e(slug)}">Pay and skills for “{e(q)}” →</a>'
    showing = f'<p class="results">{total:,} role{"s" if total != 1 else ""}{" match" if (q or where or remote or pay or visa or cat) else ""}, newest first.{insight}</p>'
    body = form + showing + listing + (_pager("/jobs", {**keep, "cat": cat}, page, total, PAGE_JOBS) if total > PAGE_JOBS else "")
    return _page("Lavoro · All jobs", "/jobs", hero, body)


# ---------------------------------------------------------------- /companies
def _info(row) -> dict:
    try:
        return json.loads(row["info"] or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _places(rows) -> "Counter":
    """How many roles sit in each place, by the first part of each location ("Stockholm, Sweden" counts as Stockholm)."""
    from collections import Counter
    places = Counter()
    for r in rows:
        first = re.split(r"[,/|(;]", r["location"] or "")[0].strip()
        if first and "from the ad" not in (r["location"] or "") and len(first) < 40 and not first[0].isdigit():
            places[first] += 1
    return places


def _place_text(places, top_n: int = 2) -> str:
    """'Stockholm and London', 'Stockholm, London and 3 more places'."""
    top = [p for p, _ in places.most_common(top_n)]
    more = len(places) - len(top)
    if not top:
        return ""
    if not more:
        return " and ".join(top)
    return f"{', '.join(top)} and {more} more place{'s' if more != 1 else ''}"


def hiring_summary(con, cid: int) -> str:
    """'Hiring in Stockholm, Göteborg and 12 more places · mostly Engineering', from the company's open roles."""
    from collections import Counter
    rows = con.execute("SELECT location, department FROM jobs WHERE company_id=? AND status NOT IN ('closed','duplicate')",
                       (cid,)).fetchall()
    places = _places(rows)
    depts = Counter((r["department"] or "").split(",")[0].strip() for r in rows if r["department"])
    parts = []
    if places:
        top = [p for p, _ in places.most_common(2)]
        more = len(places) - len(top)
        parts.append("Hiring in " + " and ".join(top) if not more else
                     f"Hiring in {', '.join(top)} and {more} more place{'s' if more != 1 else ''}" if more <= 30 else
                     f"Hiring in {', '.join(top)} and {more} other places")
    company = (con.execute("SELECT name FROM companies WHERE id=?", (cid,)).fetchone() or [""])[0].lower()
    dept = depts.most_common(1)[0][0] if depts else ""
    if dept and len(rows) > 3 and dept.lower() not in company and company.split()[0] not in dept.lower():
        parts.append(f"mostly {dept}")
    return " · ".join(parts)


def render_companies(con, params: dict) -> str:
    q = params.get("q", "").strip()
    hiring, has_board = params.get("hiring") == "1", params.get("board") == "1"
    following = params.get("following") == "1"
    fresh = params.get("new") == "1"
    sort = "az" if params.get("sort") == "az" else "roles"
    page = _int(params.get("page"))
    cond, args = ["1=1"], []
    if q:
        cond.append("(c.name LIKE ? OR c.domain LIKE ? OR c.info LIKE ?)")
        args += [f"%{q}%"] * 3
    if has_board:
        cond.append("c.ats IS NOT NULL AND c.ats <> 'none'")
    if following:
        cond.append("c.starred = 1")
    if fresh:  # posted or first seen in the last seven days
        cond.append("EXISTS (SELECT 1 FROM jobs j WHERE j.company_id = c.id AND j.status NOT IN ('closed','duplicate') "
                    "AND substr(coalesce(j.posted_at, j.first_seen), 1, 10) >= date('now', '-7 day'))")
    base = (f"SELECT c.*, (SELECT count(*) FROM jobs j WHERE j.company_id = c.id AND j.status NOT IN ('closed','duplicate')) AS roles "
            f"FROM companies c WHERE {' AND '.join(cond)}")
    outer = f"SELECT * FROM ({base})" + (" WHERE roles > 0" if hiring else "")
    total = con.execute(f"SELECT count(*) FROM ({outer})", args).fetchone()[0]
    order = "lower(name)" if sort == "az" else "roles DESC, lower(name)"
    rows = con.execute(f"{outer} ORDER BY {order} LIMIT ? OFFSET ?", args + [PAGE_COMPANIES, (page - 1) * PAGE_COMPANIES]).fetchall()

    all_n = con.execute("SELECT count(*) FROM companies").fetchone()[0]
    hiring_n = con.execute("SELECT count(DISTINCT company_id) FROM jobs WHERE status NOT IN ('closed','duplicate') AND company_id IS NOT NULL").fetchone()[0]
    hero = (f'<h1>Companies</h1><p class="count"><b>{all_n:,}</b> companies watched, <b>{hiring_n:,}</b> hiring right now. '
            f'Open one for its roles, its job board and what it does.</p>'
            f'<form class="addco" novalidate><label class="search">{PLUS}<input type="text" name="text" autocomplete="off" '
            f'placeholder="Add a company: name or careers link" aria-label="Company name or careers link to add" required></label>'
            f'<button class="apply" type="submit">Add</button></form>'
            f'<p class="addco-note" role="status" aria-live="polite">Works for companies hiring on {SUPPORTED}.</p>')
    keep ={"q": q, "hiring": "1" if hiring else "", "board": "1" if has_board else "", "following": "1" if following else "",
            "new": "1" if fresh else "", "sort": sort if sort == "az" else ""}
    form = f"""<form class="filters" method="get" action="/companies" role="search">
<div class="frow"><label class="search">{SEARCH}<input type="search" name="q" value="{e(q)}" placeholder="Company, product or field" aria-label="Search companies"></label>
<label class="toggle"><input type="checkbox" name="hiring" value="1"{" checked" if hiring else ""}>Hiring now</label>
<label class="toggle"><input type="checkbox" name="board" value="1"{" checked" if has_board else ""}>Has a job board</label>
<label class="toggle"><input type="checkbox" name="following" value="1"{" checked" if following else ""}>Following</label>
<label class="toggle"><input type="checkbox" name="new" value="1"{" checked" if fresh else ""}>New roles this week</label>
{f'<input type="hidden" name="sort" value="az">' if sort == "az" else ''}
<button class="apply" type="submit">Search</button></div>
<div class="tabs"><a class="tab" href="/companies{e(_qs(keep, sort=''))}"{" aria-current=page" if sort == "roles" else ""}>Most roles</a>
<a class="tab" href="/companies{e(_qs(keep, sort='az'))}"{" aria-current=page" if sort == "az" else ""}>A to Z</a></div></form>"""

    cards = []
    for r in rows:
        info = _info(r)
        meta = " · ".join(x for x in [
            f"{info['team_size']} people" if info.get("team_size") not in (None, "", "None", "0") else "",
            f"YC {info['batch']}" if info.get("batch") else "",
            e((info.get("locations") or "").split(";")[0][:40]),
        ] if x)
        roles = r["roles"]
        roles_txt = (f"{roles} open role{'s' if roles != 1 else ''}") if roles else "No open roles"
        if info.get("one_liner"):
            line = f'<p class="co-line">{e(info["one_liner"])}</p>'
        else:  # no description found anywhere: say where they hire instead of leaving the card empty
            hint = hiring_summary(con, r["id"]) if roles else ""
            line = f'<p class="co-line hint">{e(hint)}</p>' if hint else ""
        meta_html = f'<div class="co-meta">{meta}</div>' if meta else ""
        cards.append(f'<div class="co-wrap"><a class="card co" href="/companies/{r["id"]}"><div class="co-top"><span class="co-id">{logos.tile(r["id"], r["name"], "colog")}<span class="co-name">{e(r["name"])}</span></span>'
                     f'<span class="co-roles{"" if roles else " none"}">{roles_txt}</span></div>{line}{meta_html}</a>'
                     f'{star_btn(r["id"], r["name"], bool(r["starred"]), label=False)}</div>')
    listing = (f'<div class="grid">{"".join(cards)}</div>' if cards else
               '<div class="card empty-note">No companies match. Try another word, or clear a filter.</div>')
    showing = f'<p class="results">{total:,} compan{"ies" if total != 1 else "y"}.</p>'
    body = form + showing + listing + (_pager("/companies", keep, page, total, PAGE_COMPANIES) if total > PAGE_COMPANIES else "")
    return _page("Lavoro · Companies", "/companies", hero, body)


# ---------------------------------------------------------------- /companies/<id>
def render_company(con, cid: int) -> str | None:
    from .company import render_company as page  # the company page lives in company.py
    return page(con, cid)
