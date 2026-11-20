"""Company pages: /companies/<id> (roles by team, who to write to, pay, email format, similar companies),
/companies/<id>/pay (every role that states pay), and /pay (pay across all companies and roles).

Everything shown comes from the local database. A person is shown only when Lavoro found them; an email format
only when a real address confirms it. Nothing is guessed on these pages and nothing is ever sent.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from urllib.parse import quote

from .browse import (CAT_SQL, CATEGORIES, EXT, PIN, _info, _page, _place_text, _places, board_url, job_row, star_btn)
from . import logos
from .digest import ago, e, icon
from .sources import COUNTRY

TEAM_LABEL = dict(CATEGORIES) | {"tech": "Tech", "other": "Other roles"}
# Each team gets a soft tint on its card and section: (wash, ring, accent).
TEAM_TINT = {"tech": ("#f5f3ff", "#ddd6fe", "#7c3aed"), "design": ("#fff1f3", "#fecdd3", "#e11d48"),
             "product": ("#fdf4ff", "#f5d0fe", "#a21caf"), "marketing": ("#fff7ed", "#fed7aa", "#ea580c"),
             "sales": ("#eff6ff", "#bfdbfe", "#2563eb"), "operations": ("#ecfdf5", "#a7f3d0", "#059669"),
             "healthcare": ("#f0fdfa", "#99f6e4", "#0d9488"), "other": ("#f7f6f3", "#e7e5e4", "#78716c")}
TEAM_COLOR = {k: v[2] for k, v in TEAM_TINT.items()}
# Who usually decides for each kind of team. Shown as a role, never as a person, until Lavoro finds someone.
USUAL_HIRER = {"tech": "Head of Engineering", "design": "Head of Design", "product": "Head of Product",
               "marketing": "Head of Marketing", "sales": "Head of Sales", "operations": "Head of Operations",
               "healthcare": "Medical Director", "other": "Hiring manager"}
OK_TRUST = ("listed_in_ad", "published", "verified")
SHOW_PER_TEAM = 4
PATTERN_TEXT = {"{first}.{last}": ("firstname.lastname", "first name, a dot, then last name"),
                "{first}": ("firstname", "first name only"),
                "{f}{last}": ("flastname", "first initial, then last name"),
                "{first}{last}": ("firstnamelastname", "first and last name run together"),
                "{first}_{last}": ("firstname_lastname", "first name, an underscore, then last name"),
                "{f}.{last}": ("f.lastname", "first initial, a dot, then last name"),
                "{first}{l}": ("firstnamel", "first name, then last initial"),
                "{last}": ("lastname", "last name only")}

CSS = r"""
.crumbs{display:flex;gap:8px;align-items:center;font:500 13.5px var(--sans);color:var(--mute);margin:0 0 12px}
.crumbs a{color:var(--ink-2);text-decoration:none}.crumbs a:hover{text-decoration:underline}
.checked{margin:10px 0 0;font-size:13px;color:var(--mute)}
.block{margin-top:44px}
.block>h2{margin:0 0 4px}
.block>.sub{margin:0 0 16px}
/* masthead: the company floats on the page background, no card */
header.hero.slim>.wrap{width:100%}  /* line up with the sections below */
.ctop{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:28px}
.ctop .crumbs{margin:0}.ctop .checked{margin:0}
.careers{margin:0 0 10px;font:600 12px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}
.careers .live{color:var(--mint-ink);margin-left:10px}
.careers .live::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--mint);margin-right:6px;
  vertical-align:1px;box-shadow:0 0 0 4px rgba(16,185,129,.18)}
.cid{display:flex;gap:22px;align-items:center}
.cid h1{margin:0}
.mono{width:76px;height:76px;border-radius:20px;font-size:38px}
.mono.has{background:transparent;box-shadow:none}
.mono.has img{inset:0;width:100%;height:100%;background:transparent}
.mono.has.lo img{inset:18%;width:64%;height:64%}  /* a small icon stays near its real size instead of going soft */
.oneliner{margin:16px 0 0;color:var(--ink-2);font-size:17px;line-height:1.55;max-width:60ch}
.figs{display:flex;flex-wrap:wrap;align-items:flex-end;row-gap:18px;margin:28px 0 0;padding:0;list-style:none}
.figs li{padding:2px 28px 2px 0;margin-right:28px;border-right:1px solid rgba(23,23,23,.14);min-width:0}
.figs li:last-child{border-right:0;margin-right:0;padding-right:0}
.figs b{display:block;font:400 34px/1.05 var(--serif);letter-spacing:-.02em;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.figs b.word{font-size:26px;line-height:1.25}
.figs span{display:block;margin-top:6px;font-size:13px;color:var(--mute)}
.figs li.open b{color:var(--mint-ink)}
.where{margin:16px 0 0;font-size:14px;color:var(--ink-2)}
.lbtns{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:22px}
.lbtn{display:inline-flex;align-items:center;height:38px;padding:0 15px;border-radius:999px;color:var(--ink);text-decoration:none;
  font:600 14px var(--sans);background:rgba(255,255,255,.6);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  box-shadow:0 0 0 1px rgba(23,23,23,.12) inset}
.lbtn:hover{background:#fff;box-shadow:0 0 0 1px rgba(23,23,23,.3) inset}
.people{margin-top:44px}
.ph{margin:0 0 14px;font:400 26px/1.15 var(--serif);letter-spacing:-.01em}
.pcards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.pcards.n1{grid-template-columns:minmax(0,1fr)}.pcards.n2{grid-template-columns:repeat(2,minmax(0,1fr))}
.pcard{display:flex;flex-direction:column;justify-content:space-between;gap:16px;padding:18px;border-radius:18px;
  background:color-mix(in srgb,var(--wash) 78%,transparent);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
  box-shadow:0 0 0 1px var(--ring) inset,0 18px 40px -28px rgba(23,23,23,.35)}
.ptop,.hirer{display:flex;gap:12px;align-items:center;min-width:0}
.av{flex:none;width:48px;height:48px;border-radius:50%;display:grid;place-items:center;font:600 14px var(--sans);color:var(--ink);
  background:radial-gradient(circle at 32% 28%,#fff 0,var(--wash) 38%,var(--ring) 70%,var(--accent) 140%)}
.pwho{display:flex;flex-direction:column;min-width:0;gap:1px}
.pwho .eyebrow{white-space:nowrap;font:600 11px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin-bottom:2px}
.pwho .wname{font-weight:700;font-size:15.5px;line-height:1.25;color:var(--ink)}
.pwho .wtitle{font-size:13.5px;color:var(--ink-2)}
.pwho .wteam{font-size:13px;color:var(--mute);margin-top:2px}
.wtrust{display:inline-flex;align-items:center;gap:5px;margin-top:3px;font:600 12.5px var(--sans);color:var(--mute)}
.wtrust.ok{color:var(--mint-ink)}.wtrust.warn{color:var(--amber-ink)}
.wtrust.ok::before{content:"";flex:none;width:14px;height:14px;border-radius:50%;background:var(--mint) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E") center/9px no-repeat}
.seebtn{height:42px;border:0;border-radius:12px;background:#fff;color:var(--ink);font:600 14.5px var(--sans);cursor:pointer;
  box-shadow:0 0 0 1px var(--line) inset,0 2px 6px -2px rgba(23,23,23,.15)}
.seebtn:hover{box-shadow:0 0 0 1px rgba(23,23,23,.3) inset,0 4px 10px -4px rgba(23,23,23,.25)}
.cfoot{margin:14px 2px 0;font-size:13.5px;color:var(--ink-2)}.cfoot a{color:var(--ink);text-underline-offset:3px}
/* teams */
.bhead{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.bhead h2{margin:0 0 4px}.bmeta{font-size:13px;color:var(--mute)}.bmeta a{color:var(--ink-2)}
.team.tinted{margin-top:22px;padding:24px;border-radius:24px;background:var(--wash);box-shadow:0 0 0 1px var(--ring) inset}
.thead{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.tleft{min-width:0;flex:1}
.thead h3{display:flex;align-items:baseline;gap:8px;margin:0;font:400 32px/1.1 var(--serif);letter-spacing:-.015em}
.thead h3 small{font:400 20px var(--serif);color:var(--accent)}
.thead .team-sub{margin:8px 0 0;max-width:56ch}
.hirer{flex:none;width:min(460px,100%);padding:14px 16px;border-radius:16px;background:#fff;box-shadow:0 6px 18px -10px rgba(23,23,23,.25)}
.hirer .pwho{flex:1}
.mailbtn{flex:none;display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;border:0;border-radius:999px;cursor:pointer;
  background:var(--rose);color:#fff;font:600 13.5px var(--sans)}
.mailbtn:hover{background:var(--rose-ink)}.mailbtn svg{width:15px;height:15px}
.mailbtn[disabled]{opacity:.75;cursor:progress}
.reach-out{margin-top:14px}
.reach-out[hidden]{display:none}
.reach-out>div{background:#fff;border-radius:16px;padding:16px}
.rlist{margin-top:16px;background:#fff;border-radius:18px;overflow:hidden}
.rrow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:14px 18px}
.rrow+.rrow,.rrow+.more-roles,.more-roles .rrow:first-of-type{border-top:1px solid var(--line)}
.rrow:hover{background:#fcfbf9}
.rrow .jt{font-weight:600;font-size:15.5px;color:var(--ink);text-decoration:none}.rrow .jt:hover{text-decoration:underline}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:7px}
.chip{display:inline-flex;align-items:center;height:26px;padding:0 10px;border-radius:999px;background:var(--inset);
  font:500 13px var(--sans);color:var(--ink-2);white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.chip.pay{color:var(--ink);font-weight:600}.chip.fit{background:var(--rose-wash);color:var(--rose-ink)}
.chip.ready{background:var(--mint-wash);color:var(--mint-ink)}
.seen{font-size:13px;color:var(--mute);margin-left:2px}
.ract{display:flex;gap:8px;align-items:center}
.apply{display:inline-flex;align-items:center;height:38px;padding:0 18px;border-radius:12px;background:#fff;color:var(--ink);
  text-decoration:none;font:600 14px var(--sans);box-shadow:0 0 0 1px var(--line) inset}
.apply:hover{box-shadow:0 0 0 1px rgba(23,23,23,.4) inset}
.team .more-roles summary{color:var(--ink);font-weight:600;border-top:1px solid var(--line)}
.tall{display:inline-block;margin:12px 4px 0;font:500 13.5px var(--sans);color:var(--ink-2)}
.letter2{border-radius:14px;background:var(--inset);padding:16px 18px}
.letter2 .lto{font-size:13px;color:var(--mute);margin-bottom:8px}
.letter2 .lto b{color:var(--ink);font-weight:600}
.letter2 .subj{font-weight:600;font-size:15px;margin-bottom:8px}
.letter2 pre{margin:0;white-space:pre-wrap;font:400 14.5px/1.6 var(--sans);color:var(--ink-2)}
.acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.acts a,.acts button{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;border-radius:11px;border:0;cursor:pointer;
  font:600 13.5px var(--sans);text-decoration:none;background:#fff;color:var(--ink);box-shadow:0 0 0 1px var(--line) inset}
.acts a.main{background:var(--rose);color:#fff;box-shadow:none}.acts a.main:hover{background:var(--rose-ink)}
.acts svg{width:15px;height:15px}
.reach-msg{margin:0;font-size:14px;color:var(--ink-2)}
@media (max-width:900px){.pcards,.pcards.n2{grid-template-columns:minmax(0,1fr)}
  .thead{flex-direction:column}.hirer{width:100%}}
@media (max-width:640px){.cid{gap:14px}.figs li{padding-right:18px;margin-right:18px}.figs b{font-size:28px}.figs b.word{font-size:21px}.team.tinted{padding:16px;border-radius:20px}
  .rrow{grid-template-columns:1fr;gap:10px;padding:14px}.mono{width:56px;height:56px;border-radius:16px;font-size:28px}
  .hirer{flex-wrap:wrap}.hirer .mailbtn{width:100%;justify-content:center}}
/* pay + email format */
.duo{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;align-items:start}
.duo.one{grid-template-columns:minmax(0,1fr)}
.payline2{font-size:15px;color:var(--ink-2);margin:0 0 14px}
.payline2 b{font:400 30px/1 var(--serif);color:var(--ink);margin-right:6px;font-variant-numeric:tabular-nums}
.fmt code{display:block;margin:6px 0 10px;padding:12px 14px;border:0;border-radius:12px;font:500 15px/1.4 ui-monospace,Consolas,monospace;
  white-space:normal;word-break:break-all}
.fmt p{margin:0;font-size:13.5px;color:var(--ink-2)}
.panel .more{display:inline-block;margin-top:12px;font:600 14px var(--sans)}
/* similar companies */
.sim{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.sim a{display:block;padding:14px 16px;border-radius:14px;background:#fff;box-shadow:0 0 0 1px var(--line) inset;text-decoration:none}
.sim a:hover{box-shadow:0 0 0 1px rgba(23,23,23,.35) inset}
.sim b{display:block;font:400 21px/1.15 var(--serif)}
.simlogo{width:34px;height:34px;border-radius:10px;font-size:18px;margin-bottom:10px}
.sim span{display:block;margin-top:4px;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums}
/* pay pages */
.paylist .prow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center;padding:13px 20px}
.paylist .prow+.prow{border-top:1px solid var(--line)}
.paylist .prow a{font-weight:600;text-decoration:none}.paylist .prow a:hover{text-decoration:underline}
.paylist .prow small{display:block;color:var(--mute);font-size:13px}
.paylist .amt{font:400 22px/1 var(--serif);font-variant-numeric:tabular-nums;white-space:nowrap}
.paylist .amt em{font:500 12px var(--sans);font-style:normal;color:var(--mute);margin-left:4px}
table.byteam{width:100%;border-collapse:collapse;font-size:14px}
table.byteam th{text-align:left;font:600 12.5px var(--sans);color:var(--mute);padding:0 0 8px}
table.byteam td{padding:9px 0;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
table.byteam td:not(:first-child),table.byteam th:not(:first-child){text-align:right}
@media (max-width:980px){.duo{grid-template-columns:1fr}.sim{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.sim{grid-template-columns:1fr}}
"""

REACH_JS = r"""
(()=>{
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const OK_TRUST=['listed_in_ad','published','verified'];
const initials=s=>(s||'').split(/[\s,]+/).filter(w=>w&&!/^(of|the|and|&|for)$/i.test(w)).slice(0,2).map(w=>w[0].toUpperCase()).join('')||'?';
function letter(d){
  const wrap=document.createElement('div');
  if(!d.found){wrap.innerHTML='<p class="reach-msg"></p>';wrap.querySelector('p').textContent=d.message;return wrap}
  if(!d.subject){wrap.innerHTML='<p class="reach-msg"></p>';
    wrap.querySelector('p').textContent=`Lavoro found ${d.name}${d.title?', '+d.title:''}, but no email address it could trust. Look them up on the company site.`;return wrap}
  wrap.innerHTML=`<div class="letter2"><div class="lto">To <b></b> <span class="em"></span></div><div class="subj"></div><pre></pre></div>
<div class="acts"><a class="main" target="_blank" rel="noopener">Open in Gmail</a><a class="mail">Mail app</a>
<button type="button" class="copy">Copy</button><button type="button" class="sent">Mark as sent</button></div>`;
  wrap.querySelector(".lto b").textContent=d.name+(d.title?', '+d.title:'');
  wrap.querySelector(".lto .em").textContent=d.email?'<'+d.email+'> · '+d.trust:'';
  wrap.querySelector('.subj').textContent=d.subject;wrap.querySelector('pre').textContent=d.body;
  wrap.querySelector('a.main').href=d.gmail;wrap.querySelector('a.mail').href=d.mailto;
  wrap.querySelector('.copy').onclick=async()=>{try{await navigator.clipboard.writeText('Subject: '+d.subject+'\n\n'+d.body);say('Copied.')}catch(e){say('Could not copy. Select the text instead.')}};
  wrap.querySelector('.sent').onclick=async ev=>{try{const r=await post('/api/mark',{key:d.key,status:'sent'});if(!r.ok)throw 0;
    ev.target.textContent='Sent, on your tracker';ev.target.disabled=true;say('Marked as sent. It is on your tracker with a follow-up date.')}catch(e){say('Could not save. Is Lavoro still running?')}};
  return wrap}
// Repaint the team's person, in its section and in the top card.
function paintWho(k,d){
  document.querySelectorAll(`[data-who="${k}"]`).forEach(w=>{
    const tr=w.querySelector('.wtrust');
    if(!d.found){tr.className='wtrust';tr.textContent='No one found for '+d.job+'. Reload to try the next role.';return}
    w.querySelector('.eyebrow').textContent='Hires for this team';
    w.querySelector('.wname').textContent=d.name;
    const ti=w.querySelector('.wtitle');ti.textContent=d.title||'';ti.hidden=!d.title;
    tr.className='wtrust'+(OK_TRUST.includes(d.status)?' ok':d.status==='guessed'?' warn':'');tr.textContent=d.trust||'';
    const av=w.parentElement.querySelector('.av');if(av)av.textContent=initials(d.name)});
  const go=document.querySelector(`[data-go="${k}"]`);if(go&&d.found)go.textContent=d.subject?'Show email':'See who'}
document.querySelectorAll('[data-reach]').forEach(b=>b.addEventListener('click',async()=>{
  const out=document.getElementById(b.getAttribute('aria-controls')),txt=b.querySelector('span');
  if(out.dataset.ready){out.hidden=!out.hidden;b.setAttribute('aria-expanded',String(!out.hidden));
    txt.textContent=out.hidden?(out.dataset.label||'Email'):'Hide';return}
  const label=txt.textContent;b.disabled=true;txt.textContent='Looking… up to a minute';
  try{const r=await post('/api/reach',{key:b.dataset.reach});const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.error||'Could not look that up.');
    out.replaceChildren(letter(d));out.dataset.ready='1';out.dataset.label=d.found&&d.subject?'Email':label;out.hidden=false;
    b.setAttribute('aria-expanded','true');txt.textContent='Hide';paintWho(b.dataset.team,d)}
  catch(e){say(e.message==='Failed to fetch'?'Could not reach Lavoro. Is it still running?':e.message);txt.textContent=label}
  finally{b.disabled=false}}));
// The buttons on the top cards jump to the team and open (or start) its lookup.
document.querySelectorAll('[data-go]').forEach(g=>g.addEventListener('click',()=>{
  const t=document.getElementById('team-'+g.dataset.go);if(!t)return;
  t.scrollIntoView({behavior:'smooth',block:'start'});
  const b=t.querySelector('[data-reach]'),out=document.getElementById(b.getAttribute('aria-controls'));
  if(!b.disabled&&(!out.dataset.ready||out.hidden))b.click()}));
})();
"""


# ---------------------------------------------------------------- pay helpers
def _pay_rows(rows):
    """[(row, currency, low, high)] for every role whose listed pay reads as a yearly range."""
    from .roles import parse_pay
    out = []
    for r in rows:
        p = parse_pay(r["salary"])
        if p:
            out.append((r, p[0], p[1], p[2]))
    return out


def _main_currency(pays):
    by = Counter(c for _, c, _, _ in pays)
    return by.most_common(1)[0][0] if by else None


def _quartiles(vals: list[float]) -> tuple[float, float]:
    if len(vals) < 4:
        return min(vals), max(vals)
    q = statistics.quantiles(vals, n=4)
    return q[0], q[2]


def _money(cur, v):
    from .roles import money
    return money(cur, v)


# ---------------------------------------------------------------- who hires, team by team
def _tint(k: str) -> str:
    wash, ring, accent = TEAM_TINT[k]
    return f"--wash:{wash};--ring:{ring};--accent:{accent}"


def _initials(s: str) -> str:
    words = [w for w in re.split(r"[\s,]+", s or "") if w and w.lower() not in ("of", "the", "and", "&", "for")]
    return "".join(w[0].upper() for w in words[:2]) or "?"


def _who(con, team) -> dict:
    """The person Lavoro holds for this team, or which role to look up next."""
    from . import reach
    best = reach.best_for(con, [r["key"] for r in team])
    if best is not None:
        d = reach.as_dict(best)
        return {"found": True, **d}
    # Look up the best-fitting role nobody has tried yet; a role already looked up with no one found is a dead end.
    tried = [r for r in team if r["status"] in ("looked_up", "no_contact")]
    fresh = [r for r in team if r["status"] not in ("looked_up", "no_contact")]
    target = max(fresh or team, key=lambda r: ((r["score"] or 0), r["posted_at"] or r["first_seen"] or ""))
    return {"found": False, "tried": len(tried), "fresh": bool(fresh), "key": target["key"], "next": target["title"]}


def _who_lines(w: dict, k: str, n: int, with_team: bool) -> str:
    """Name (or the usual hiring role), title, team and how much to trust the address. The page script repaints these."""
    team = (f'<span class="wteam">{e(TEAM_LABEL[k])} · {n} open role{"s" if n != 1 else ""}</span>' if with_team else "")
    if w["found"]:
        cls = "ok" if w["status"] in OK_TRUST else "warn" if w["status"] == "guessed" else ""
        return (f'<small class="eyebrow">Hires for this team</small><b class="wname">{e(w["name"])}</b>'
                f'<span class="wtitle"{"" if w["title"] else " hidden"}>{e(w["title"])}</span>{team}'
                f'<span class="wtrust {cls}">{e(w["trust"])}</span>')
    state = (f'No one found yet · {w["tried"]} role{"s" if w["tried"] != 1 else ""} tried' if w["tried"] else "Not looked up yet")
    return (f'<small class="eyebrow">Usually hires for this</small><b class="wname">{e(USUAL_HIRER[k])}</b>'
            f'<span class="wtitle" hidden></span>{team}<span class="wtrust">{e(state)}</span>')


def _avatar(w: dict, k: str) -> str:
    return f'<span class="av" aria-hidden="true">{e(_initials(w["name"] if w["found"] else USUAL_HIRER[k]))}</span>'


def _people(order, teams, who) -> str:
    """The top of the page: the people who decide who gets hired for the three biggest teams."""
    top = [k for k in order if k != "other"][:3] or order[:3]
    cards = []
    for k in top:
        w = who[k]
        label = (("Show email" if w["subject"] else "See who") if w["found"] else
                 ("Try another role" if w["tried"] and w["fresh"] else "Search again" if w["tried"] else "Find who hires"))
        cards.append(f'<div class="pcard" style="{_tint(k)}"><div class="ptop">{_avatar(w, k)}'
                     f'<div class="pwho" data-who="{k}">{_who_lines(w, k, len(teams[k]), True)}</div></div>'
                     f'<button class="seebtn" type="button" data-go="{k}">{e(label)}</button></div>')
    return f'<h2 class="ph">Who decides who gets hired</h2><div class="pcards n{len(cards)}">{"".join(cards)}</div>'


# ---------------------------------------------------------------- one role, as a row of chips

def _multi(text: str) -> list[str]:
    """'new york new york city san francisco' → known multi-word names first, then single words."""
    multi = ["new york city", "new york", "san francisco", "los angeles", "palo alto", "mountain view", "menlo park",
             "san jose", "san diego", "washington dc", "abu dhabi", "tel aviv", "são paulo", "sao paulo", "rio de janeiro",
             "mexico city"]
    out = [m for m in multi if m in text]
    for m in out:
        text = text.replace(m, " ")
    return out + text.split()

_LEVELS = [(r"\bintern(ship)?\b|\bpraktik", "Intern"), (r"\bgraduate\b|\btrainee\b|\bnew grad", "Graduate"),
           (r"\bjunior\b|\bjr\.?\b|\bentry", "Junior"), (r"\b(head|director|vp|vice president|chief)\b", "Leadership"),
           (r"\b(principal|staff|lead)\b", "Lead"), (r"\bsenior\b|\bsr\.?\b", "Senior")]
_COUNTRY_NAMES = {v.lower(): v for v in COUNTRY.values()} | {
    "sverige": "Sweden", "norge": "Norway", "danmark": "Denmark", "suomi": "Finland", "deutschland": "Germany",
    "österreich": "Austria", "schweiz": "Switzerland", "españa": "Spain", "italia": "Italy", "usa": "United States",
    "united states of america": "United States", "england": "United Kingdom", "nederland": "Netherlands"}


# Cities that job ads often name without their country.
_CITY_COUNTRY = {c: k for k, cities in {
    "Sweden": "stockholm göteborg gothenburg goteborg malmö malmo uppsala lund linköping linkoping västerås vasteras örebro "
              "umeå umea skövde skovde eskilstuna köping koping södertälje sodertalje sundbyberg solna kista jönköping "
              "norrköping helsingborg luleå karlstad flen",
    "Norway": "oslo bergen trondheim stavanger", "Denmark": "copenhagen københavn aarhus odense",
    "Finland": "helsinki espoo tampere oulu", "United Kingdom": "london manchester edinburgh cambridge oxford bristol glasgow",
    "Ireland": "dublin cork", "Germany": "berlin munich münchen hamburg frankfurt cologne köln stuttgart düsseldorf",
    "France": "paris lyon toulouse marseille", "Spain": "madrid barcelona valencia", "Portugal": "lisbon lisboa porto",
    "Italy": "milan milano rome roma turin torino", "Netherlands": "amsterdam rotterdam utrecht eindhoven",
    "Belgium": "brussels antwerp ghent", "Switzerland": "zurich zürich geneva basel lausanne",
    "Austria": "vienna wien graz", "Poland": "warsaw warszawa krakow kraków wroclaw wrocław gdansk",
    "Czech Republic": "prague brno", "Estonia": "tallinn tartu", "Latvia": "riga", "Lithuania": "vilnius",
    "United States": "new york new york city nyc san francisco sf los angeles seattle boston austin chicago denver miami "
                     "atlanta washington dc palo alto mountain view menlo park sunnyvale san jose san diego greensboro",
    "Canada": "toronto vancouver montreal ottawa calgary", "India": "bangalore bengaluru mumbai delhi pune hyderabad chennai gurugram",
    "Singapore": "singapore", "Japan": "tokyo osaka", "Australia": "sydney melbourne brisbane",
    "United Arab Emirates": "dubai abu dhabi", "Israel": "tel aviv", "Brazil": "são paulo sao paulo rio de janeiro",
    "Mexico": "mexico city",
}.items() for c in _multi(cities)}
_US_STATES = set("al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh nj nm ny nc nd oh ok "
                 "or pa ri sc sd tn tx ut vt va wa wv wi wy dc".split())


def _level(title: str) -> str:
    """Seniority only when the title says it outright."""
    t = (title or "").lower()
    return next((name for pat, name in _LEVELS if re.search(pat, t)), "")


def _place(loc: str | None) -> str:
    """'Göteborg, SE, 417 15 (Sweden)' → 'Göteborg, Sweden'; 'Sundbyberg, Stockholms län, Sverige' → 'Sundbyberg, Sweden'."""
    s = (loc or "").strip()
    if not s:
        return ""
    s = re.sub(r"\((hybrid|remote|onsite|on-site)\)", "", s, flags=re.I).strip()
    country = ""
    m = re.search(r"\(([^()]+)\)\s*$", s)
    inner = m.group(1).strip().lower() if m else ""
    if inner in _COUNTRY_NAMES or (len(inner) == 2 and inner in COUNTRY):  # "(Sweden)", "Remote (US)"
        country, s = _COUNTRY_NAMES.get(inner) or COUNTRY[inner], s[:m.start()].strip()
    parts = [p.strip() for p in re.split(r",|\s[-–·•]\s", s) if p.strip()]
    if not parts:
        return country
    if not country:
        for p in reversed(parts[1:]):
            low = p.lower()
            if low in _COUNTRY_NAMES:
                country = _COUNTRY_NAMES[low]
                break
            if len(low) == 2 and low in COUNTRY and low not in ("ca", "in", "de") or (low in ("de", "in") and p.isupper()):
                country = COUNTRY[low]
                break
    extra = 0
    if "/" in parts[0]:  # "Stockholm HQ / Madrid / Munich" → the first place, and how many more
        many = [x.strip() for x in parts[0].split("/") if x.strip()]
        parts[0], extra = many[0], len(many) - 1
    parts[0] = re.sub(r"\s+(hq|office|headquarters)$", "", parts[0], flags=re.I)
    city = parts[0]
    if not country and len(parts) > 1 and parts[1].strip().lower() in _US_STATES and len(parts[1].strip()) == 2:
        country = "United States"
    if not country:
        country = _CITY_COUNTRY.get(city.lower(), "")
    more = f" +{extra}" if extra else ""
    if len(parts) > 1 and len(city) == 2 and city.isupper() and city.lower() in COUNTRY:  # "US · Tarzana · CA"
        country, city = country or COUNTRY[city.lower()], parts[1]
    if city.lower().startswith("remote"):
        return country
    if city.lower() in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[city.lower()]
    if country:
        return f"{city}, {country}{more}"
    second = parts[1] if len(parts) > 1 and len(parts[1]) <= 20 and not re.search(r"\d", parts[1]) else ""
    return (f"{city}, {second}" if second else city[:48]) + more


def _pay_chip(salary: str | None) -> str:
    from .roles import money, parse_pay
    if not salary:
        return ""
    p = parse_pay(salary)
    low = salary.lower()
    if p and any(w in low for w in ("month", "/mo", "månad", "hour", "/hr")):  # keep the unit the ad used
        txt = re.sub(r"\s*/\s*month|\s*per month|\s*a month", "/mo", salary.split("•")[0].split("(")[0]).strip()
        return f'<span class="chip pay" title="{e(salary)}">{e(txt[:24])}</span>'
    if p:
        cur, lo, hi = p
        txt = money(cur, lo) if abs(hi - lo) < 1 else f"{money(cur, lo)}–{money(cur, hi)}"
        return f'<span class="chip pay" title="{e(salary)}">{e(txt)}</span>'
    return f'<span class="chip pay">{e(salary.split("•")[0].strip()[:28])}</span>'


def _role_row(r) -> str:
    from .tracker import track_btn
    loc = r["location"] or ""
    chips = []
    place = _place(loc)
    if place:
        chips.append(f'<span class="chip" title="{e(loc)}">{e(place)}</span>')
    if r["remote"] or "remote" in loc.lower():
        chips.append('<span class="chip">Remote</span>')
    level = _level(r["title"])
    if level:
        chips.append(f'<span class="chip">{level}</span>')
    chips.append(_pay_chip(r["salary"]))
    if r["status"] == "drafted":
        chips.append('<span class="chip ready">Email ready</span>')
    elif (r["score"] or 0) >= 5:  # only a fit worth pointing out
        chips.append(f'<span class="chip fit" title="Fit with your profile">Fit {int(r["score"])}</span>')
    seen = (f'Posted {ago(r["posted_at"])}' if r["posted_at"] else f'First seen {ago(r["first_seen"])}')
    chips.append(f'<span class="seen">{e(seen)}</span>')
    tracked = bool(r["tracked"]) if "tracked" in r.keys() else False
    return (f'<div class="rrow"><div class="rmain"><a class="jt" href="{e(r["url"])}" target="_blank" rel="noopener">'
            f'{e(r["title"])}</a><div class="chips">{"".join(chips)}</div></div>'
            f'<div class="ract">{track_btn(r["key"], tracked)}<a class="apply" href="{e(r["url"])}" target="_blank" '
            f'rel="noopener">Apply</a></div></div>')


# ---------------------------------------------------------------- /companies/<id>
def render_company(con, cid: int) -> str | None:
    from .roles import CSS as ROLE_CSS, _pay_svg
    c = con.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
    if c is None:
        return None
    info = _info(c)
    jobs = con.execute(
        f"SELECT j.*, {CAT_SQL} AS cat, (SELECT 1 FROM pipeline p WHERE p.job_key = j.key) AS tracked FROM jobs j "
        "WHERE j.company_id = ? AND j.status NOT IN ('closed','duplicate') "
        "ORDER BY substr(coalesce(j.posted_at, j.first_seen), 1, 10) DESC", (cid,)).fetchall()
    n = len(jobs)
    teams = defaultdict(list)
    for r in jobs:
        teams[r["cat"]].append(r)
    order = sorted(teams, key=lambda k: (k == "other", -len(teams[k])))
    who = {k: _who(con, teams[k]) for k in order}

    # chips under the name, then the facts strip
    figs = [(f"{n:,}", f"open role{'s' if n != 1 else ''}", "open" if n else "")]
    if jobs:
        figs.append((str(len(order)), f"team{'s' if len(order) != 1 else ''} hiring", ""))
    remote = sum(1 for r in jobs if r["remote"] or "remote" in (r["location"] or "").lower())
    if remote:
        figs.append((f"{remote:,}", "remote", ""))
    if info.get("team_size") not in (None, "", "None", "0"):
        figs.append((e(str(info["team_size"])), "people", ""))
    fund = con.execute("SELECT round, amount FROM funding WHERE company_id = ? ORDER BY announced DESC LIMIT 1", (cid,)).fetchone()
    if fund and fund["amount"]:
        figs.append((e(fund["amount"]), e(f"{fund['round']} round" if fund["round"] else "latest round"), "word"))
    if c["ats"] and c["ats"] != "none":
        figs.append((e(c["ats"].title()), "job board", "word"))
    if jobs:
        figs.append((e(ago(jobs[0]["posted_at"] or jobs[0]["first_seen"]).capitalize()), "newest role", "word"))
    fig_html = '<ul class="figs">' + "".join(
        f'<li class="{cls if cls == "open" else ""}"><b class="{cls if cls == "word" else ""}">{v}</b><span>{lab}</span></li>'
        for v, lab, cls in figs) + "</ul>"
    where = _place_text(_places(jobs)) if jobs else ""
    where_html = f'<p class="where">Hiring in {e(where)}.</p>' if where else ""

    links = [star_btn(c["id"], c["name"], bool(c["starred"]))]
    if c["website"] or c["domain"]:
        site = c["website"] or f"https://{c['domain']}"
        links.append(f'<a class="lbtn" href="{e(site)}" target="_blank" rel="noopener">Visit site ↗</a>')
    board = board_url(c["ats"], c["slug"])
    if board:
        links.append(f'<a class="lbtn" href="{e(board)}" target="_blank" rel="noopener">Their job board ↗</a>')
    if info.get("yc_url"):
        links.append(f'<a class="lbtn" href="{e(info["yc_url"])}" target="_blank" rel="noopener">YC {e(info.get("batch") or "profile")} ↗</a>')
    shown_people = min(3, len([k for k in order if k != "other"]) or len(order))
    more_teams = len(order) - shown_people
    foot_note = (f'<a href="#teams">{more_teams} more team{"s" if more_teams != 1 else ""} below</a>, each with who hires for it.'
                 if more_teams > 0 else ('<a href="#teams">Every role is below</a>, by team.' if jobs else ""))

    checked = f'Last checked {e(ago(c["checked_at"]))} · on every run' if c["checked_at"] else ""
    hero = (f'<div class="ctop"><nav class="crumbs" aria-label="Breadcrumb"><a href="/companies">All companies</a><span>/</span>'
            f'<span>{e(c["name"])}</span></nav><span class="checked">{checked}</span></div>'
            f'<p class="careers">Careers at {e(c["name"])}{" <span class=\"live\">Hiring now</span>" if n else ""}</p>'
            f'<div class="cid">{logos.tile(c["id"], c["name"], "mono")}<h1>{e(c["name"])}</h1></div>'
            + (f'<p class="oneliner">{e(info["one_liner"])}</p>' if info.get("one_liner") else "")
            + fig_html + where_html + f'<div class="lbtns">{"".join(links)}</div>'
            + (f'<section class="people">{_people(order, teams, who)}<p class="cfoot">{foot_note}</p></section>' if jobs else ""))

    if not jobs:
        body = ('<section class="block"><h2>No open roles</h2><div class="card empty-note">No open roles right now. '
                'Lavoro checks again on every run.</div></section>')
        return _page(f"Lavoro · {c['name']}", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>" + body + _similar(con, c, None))

    pays = _pay_rows(jobs)
    cur = _main_currency(pays)
    parts = [_teams(c, order, teams, who, bool(cur))]

    # pay and email format, side by side when both exist
    side = []
    if cur:
        ranges = [(lo, hi) for _, cu, lo, hi in pays if cu == cur]
        mids = [(lo + hi) / 2 for lo, hi in ranges]
        q1, q3 = _quartiles(mids)
        spread = (f"middle half {_money(cur, q1)}–{_money(cur, q3)}" if len(mids) >= 4 else
                  "too few roles state pay to show a spread")
        med_lo, med_hi = statistics.median(lo for lo, _ in ranges), statistics.median(hi for _, hi in ranges)
        side.append(f'<section class="panel"><h2>Pay</h2><p class="ps">{len(ranges)} of {n} roles state a yearly range in {e(cur)}. '
                    f'Each role counts at the middle of its range.</p>'
                    f'<p class="payline2"><b>{e(_money(cur, statistics.median(mids)))}</b>median, {e(spread)}</p>'
                    f'<div class="paychart">{_pay_svg(cur, ranges, med_lo, med_hi)}</div>'
                    f'<a class="more" href="/companies/{cid}/pay">Every role with pay</a></section>')
    fmt = _email_format(con, c)
    duo = ""
    if side or fmt:
        duo = (f'<section class="block" id="pay"><h2>Pay and email</h2><p class="sub">From the roles {e(c["name"])} lists and the '
               f'addresses Lavoro has confirmed.</p><div class="duo{" one" if not (side and fmt) else ""}">'
               f'{"".join(side)}{fmt}</div></section>')
    parts.append(duo)
    parts.append(_similar(con, c, order[0]))
    return _page(f"Lavoro · {c['name']}", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>" + "".join(parts)
                 ).replace("</body>", f"<script>{REACH_JS}</script></body>", 1)


def _teams(company, order, teams, who, has_pay) -> str:
    n = sum(len(v) for v in teams.values())
    bar = "".join(f'<span style="flex:{len(teams[k])};background:{TEAM_COLOR[k]}" title="{e(TEAM_LABEL[k])}: {len(teams[k])}"></span>'
                  for k in order)
    key = "".join(f'<a href="#team-{k}"><i style="background:{TEAM_COLOR[k]}"></i>{e(TEAM_LABEL[k])}<b>{len(teams[k])}</b></a>'
                  for k in order)
    meta = (f'{n} role{"s" if n != 1 else ""} · {len(order)} team{"s" if len(order) != 1 else ""} · re-checked every run'
            + (f' · <a href="#pay">What {e(company["name"])} pays</a>' if has_pay else ""))
    out = [f'<section class="block" id="teams"><div class="bhead"><h2>Open roles at {e(company["name"])}, by team</h2>'
           f'<span class="bmeta">{meta}</span></div>'
           f'<p class="sub">Each team shows who decides who gets hired. Lavoro looks them up only when you ask, then drafts '
           f'a short email from your profile. You read it and send it yourself.</p>'
           f'<div class="mix"><div class="mixbar" role="img" aria-label="Open roles by team">{bar}</div>'
           f'<nav class="mixkey" aria-label="Jump to a team">{key}</nav></div>']
    for k in order:
        rows = teams[k]
        cnt = len(rows)
        w = who[k]
        where = _place_text(_places(rows))
        newest = ago(rows[0]["posted_at"] or rows[0]["first_seen"])
        sub_line = f'{cnt} open role{"s" if cnt != 1 else ""}' + (f' in {where}' if where else '') + f', newest {newest}.'
        if w["found"]:
            who_line = f' Lavoro found {w["name"]}{", " + w["title"] if w["title"] else ""}, for {w["job"]}.'
            label = "Email" if w["subject"] else "Write email"
        else:
            who_line = f' Roles like these usually go to the {USUAL_HIRER[k]}.' if k != "other" else ""
            label = "Find who hires" if not w["tried"] else ("Try another role" if w["fresh"] else "Search again")
        shown = "".join(_role_row(r) for r in rows[:SHOW_PER_TEAM])
        rest = rows[SHOW_PER_TEAM:]
        noun = TEAM_LABEL[k] if k != "other" else ""
        more = (f'<details class="more-roles"><summary>+ {len(rest)} more {e(noun)} role{"s" if len(rest) != 1 else ""}</summary>'
                f'{"".join(_role_row(r) for r in rest)}</details>' if rest else "")
        link = f'/jobs?q={quote(company["name"])}' + (f'&cat={k}' if k != "other" else "")
        out.append(f'<section class="team tinted" id="team-{k}" style="{_tint(k)}"><div class="thead"><div class="tleft">'
                   f'<h3>{e(TEAM_LABEL[k])}<small>{cnt}</small></h3><p class="team-sub">{e(sub_line + who_line)}</p></div>'
                   f'<div class="hirer">{_avatar(w, k)}<div class="pwho" data-who="{k}">{_who_lines(w, k, cnt, False)}</div>'
                   f'<button class="mailbtn" type="button" data-reach="{e(w["key"])}" data-team="{k}" aria-controls="reach-{k}" '
                   f'aria-expanded="false">{icon("mail")}<span>{e(label)}</span></button></div></div>'
                   f'<div class="reach-out" id="reach-{k}" hidden></div>'
                   f'<div class="rlist">{shown}{more}</div>'
                   + (f'<a class="tall" href="{e(link)}">Open all {cnt} in All jobs</a>' if cnt > SHOW_PER_TEAM else '')
                   + '</section>')
    return "".join(out) + "</section>"


def _email_format(con, c) -> str:
    from .contacts import known_pattern
    domain = (c["domain"] or "").lower().removeprefix("www.")
    if not domain:
        return ""
    p = known_pattern(con, domain, confirmed_only=True)
    if not p or p not in PATTERN_TEXT:
        return ""
    sample, words = PATTERN_TEXT[p]
    basis = con.execute("SELECT count(*) FROM contacts WHERE email LIKE ? AND name IS NOT NULL AND "
                        "email_status IN ('listed_in_ad','published','verified')", (f"%@{domain}",)).fetchone()[0]
    return (f'<section class="panel fmt"><h2>Email format</h2><p class="ps">How {e(c["name"])} writes addresses.</p>'
            f'<code>{e(sample)}@{e(domain)}</code><p>{e(words.capitalize())}, at {e(domain)}. Learned from {basis} '
            f'address{"es" if basis != 1 else ""} published in an ad or online. Check the name before you send.</p></section>')


def _similar(con, c, top_cat) -> str:
    """Other companies whose biggest team is the same kind of work, most open roles first."""
    if not top_cat:
        return ""
    rows = con.execute(
        f"""SELECT company_id, cat, n FROM (
              SELECT j.company_id, {CAT_SQL} AS cat, count(*) AS n,
                     row_number() OVER (PARTITION BY j.company_id ORDER BY count(*) DESC) AS rk
              FROM jobs j WHERE j.status NOT IN ('closed','duplicate') AND j.company_id IS NOT NULL AND j.company_id <> ?
              GROUP BY j.company_id, cat) WHERE rk = 1 AND cat = ? ORDER BY n DESC LIMIT 8""", (c["id"], top_cat)).fetchall()
    if not rows:
        return ""
    names = dict(con.execute(f"SELECT id, name FROM companies WHERE id IN ({','.join('?' * len(rows))})",
                             [r["company_id"] for r in rows]).fetchall())
    label = TEAM_LABEL[top_cat].lower() if top_cat != "other" else "a mix of"
    cards = "".join(f'<a href="/companies/{r["company_id"]}">{logos.tile(r["company_id"], names.get(r["company_id"], "?"), "simlogo")}<b>{e(names.get(r["company_id"], "?"))}</b>'
                    f'<span>{r["n"]} open {e(label)} role{"s" if r["n"] != 1 else ""}</span></a>' for r in rows)
    return (f'<section class="block"><h2>Others hiring for {e(label)} roles</h2><p class="sub">Companies in your Lavoro '
            f'database whose biggest team is the same kind of work.</p><div class="sim">{cards}</div></section>')


# ---------------------------------------------------------------- /companies/<id>/pay
def render_company_pay(con, cid: int) -> str | None:
    from .roles import CSS as ROLE_CSS, _pay_svg
    c = con.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
    if c is None:
        return None
    jobs = con.execute(f"SELECT j.*, {CAT_SQL} AS cat FROM jobs j WHERE j.company_id = ? AND j.status NOT IN ('closed','duplicate')",
                       (cid,)).fetchall()
    pays = _pay_rows(jobs)
    cur = _main_currency(pays)
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/companies">All companies</a><span>/</span>'
              f'<a href="/companies/{cid}">{e(c["name"])}</a><span>/</span><span>Pay</span></nav>')
    if not cur:
        hero = crumbs + f'<h1>Pay at {e(c["name"])}</h1><p class="count">None of the {len(jobs)} open roles state pay yet.</p>'
        return _page(f"Lavoro · {c['name']} pay", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>")
    main = [(r, lo, hi) for r, cu, lo, hi in pays if cu == cur]
    mids = sorted((lo + hi) / 2 for _, lo, hi in main)
    q1, q3 = _quartiles(mids)
    lo_all, hi_all = min(lo for _, lo, _ in main), max(hi for _, _, hi in main)
    other = len(pays) - len(main)
    hero = (crumbs + f'<h1>Pay at {e(c["name"])}</h1><p class="count">As each open role states it, read from the job board '
            f'on every run. {len(pays)} of {len(jobs)} roles state pay.</p>')
    cells = [f'<div><b>{e(_money(cur, statistics.median(mids)))}</b><span>median, {e(cur)} a year</span></div>']
    if len(mids) >= 4:
        cells.append(f'<div><b>{e(_money(cur, q1))}–{e(_money(cur, q3))}</b><span>middle half of roles</span></div>')
    cells += [f'<div><b>{e(_money(cur, lo_all))}–{e(_money(cur, hi_all))}</b><span>lowest to highest stated</span></div>',
              f'<div><b>{len(main)}</b><span>role{"s" if len(main) != 1 else ""} stating {e(cur)}'
              f'{f", {other} in other currencies" if other else ""}</span></div>']
    facts = (f'<div class="facts4" style="grid-template-columns:repeat({len(cells)},minmax(0,1fr))">{"".join(cells)}</div>')
    med_lo = statistics.median(lo for _, lo, _ in main)
    med_hi = statistics.median(hi for _, _, hi in main)
    chart = (f'<section class="panel"><h2>Every range</h2><p class="ps">One line per role, sorted by the middle of its range. '
             f'The shaded band runs from the median low to the median high.</p>'
             f'<div class="paychart">{_pay_svg(cur, [(lo, hi) for _, lo, hi in main], med_lo, med_hi)}</div></section>')
    byteam = defaultdict(list)
    for r, lo, hi in main:
        byteam[r["cat"]].append((lo + hi) / 2)
    trs = "".join(f'<tr><td>{e(TEAM_LABEL[k])}</td><td>{len(v)}</td><td>{e(_money(cur, statistics.median(v)))}</td></tr>'
                  for k, v in sorted(byteam.items(), key=lambda kv: -statistics.median(kv[1])))
    teams = (f'<section class="panel"><h2>By team</h2><p class="ps">Median of the middle of each range.</p>'
             f'<table class="byteam"><thead><tr><th>Team</th><th>Roles</th><th>Median</th></tr></thead><tbody>{trs}</tbody></table></section>')
    items = "".join(
        f'<div class="prow"><div><a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["title"])}</a>'
        f'<small>{e(r["location"] or "")}</small></div><div class="amt">{e(_money(cur, lo))}'
        f'{"–" + e(_money(cur, hi)) if hi != lo else ""}<em>a year</em></div></div>'
        for r, lo, hi in sorted(main, key=lambda x: -(x[1] + x[2])))
    body = (facts + f'<div class="rgrid"><div>{chart}</div><aside>{teams}</aside></div>'
            f'<section class="block"><h2>Every role with pay</h2><p class="sub">Best paid first, as each ad states it.</p>'
            f'<div class="card paylist">{items}</div></section>')
    return _page(f"Lavoro · {c['name']} pay", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>" + body)


# ---------------------------------------------------------------- /pay
def render_pay_index(con) -> str:
    from .roles import CSS as ROLE_CSS, display_title, normalize_title, slugify
    rows = con.execute("SELECT j.title, j.salary, j.company_id, c.name AS cname FROM jobs j LEFT JOIN companies c ON c.id = j.company_id "
                       "WHERE j.status NOT IN ('closed','duplicate') AND j.salary IS NOT NULL AND j.salary <> ''").fetchall()
    pays = _pay_rows(rows)
    cur = _main_currency(pays)
    hero = ('<h1>Pay</h1><p class="count">What roles and companies state in their ads, from the open roles in your Lavoro '
            'database. Each role counts at the middle of its range.</p>')
    if not cur:
        return _page("Lavoro · Pay", "/pay", hero, f"<style>{ROLE_CSS}{CSS}</style>"
                     '<div class="card empty-note">No open roles state pay yet. Run Lavoro to read more job boards.</div>')
    main = [(r, (lo + hi) / 2) for r, cu, lo, hi in pays if cu == cur]
    by_role, by_co = defaultdict(list), defaultdict(list)
    for r, mid in main:
        t = normalize_title(r["title"]).strip(" /-|,.&")
        if 4 <= len(t) and 2 <= len(t.split()) <= 4 or t in ("psychiatrist", "designer", "engineer", "recruiter"):
            by_role[t].append(mid)
        if r["company_id"]:
            by_co[(r["company_id"], r["cname"])].append(mid)
    roles = sorted(((t, v) for t, v in by_role.items() if len(v) >= 4), key=lambda tv: -statistics.median(tv[1]))[:40]
    cos = sorted(((k, v) for k, v in by_co.items() if len(v) >= 3), key=lambda kv: -len(kv[1]))[:40]
    role_rows = "".join(
        f'<div class="prow"><div><a href="/roles/{e(slugify(t))}">{e(display_title(t))}</a><small>{len(v)} roles state pay</small></div>'
        f'<div class="amt">{e(_money(cur, statistics.median(v)))}<em>median</em></div></div>' for t, v in roles)
    co_rows = "".join(
        f'<div class="prow"><div><a href="/companies/{cid}/pay">{e(name)}</a><small>{len(v)} roles state pay</small></div>'
        f'<div class="amt">{e(_money(cur, statistics.median(v)))}<em>median</em></div></div>' for (cid, name), v in cos)
    other = len(pays) - len(main)
    facts = (f'<div class="facts4"><div><b>{len(main):,}</b><span>roles stating {e(cur)}</span></div>'
             f'<div><b>{e(_money(cur, statistics.median(m for _, m in main)))}</b><span>median, {e(cur)} a year</span></div>'
             f'<div><b>{len(by_co):,}</b><span>companies stating pay</span></div>'
             f'<div><b>{other:,}</b><span>roles in other currencies</span></div></div>')
    body = (facts + '<div class="duo" style="margin-top:20px;grid-template-columns:1fr 1fr">'
            f'<section><h2>By role</h2><p class="sub">Titles with at least four roles stating pay, best paid first.</p>'
            f'<div class="card paylist">{role_rows or "<div class=prow>Not enough data yet.</div>"}</div></section>'
            f'<section><h2>By company</h2><p class="sub">Companies with the most roles stating pay.</p>'
            f'<div class="card paylist">{co_rows or "<div class=prow>Not enough data yet.</div>"}</div></section></div>')
    return _page("Lavoro · Pay", "/pay", hero, f"<style>{ROLE_CSS}{CSS}</style>" + body)
