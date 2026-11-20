"""Company pages: /companies/<id> (roles by team, who to write to, pay, email format, similar companies),
/companies/<id>/pay (every role that states pay), and /pay (pay across all companies and roles).

Everything shown comes from the local database. A person is shown only when Lavoro found them; an email format
only when a real address confirms it. Nothing is guessed on these pages and nothing is ever sent.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from urllib.parse import quote

from .browse import (CAT_SQL, CATEGORIES, EXT, PIN, _info, _page, _place_text, _places, board_url, job_row, star_btn)
from .digest import ago, e, icon

TEAM_LABEL = dict(CATEGORIES) | {"tech": "Tech", "other": "Other roles"}
TEAM_COLOR = {"tech": "#171717", "design": "#e11d48", "product": "#9f1239", "marketing": "#fb7185", "sales": "#78716c",
              "operations": "#a8a29e", "healthcare": "#0f766e", "other": "#d6d3d1"}
SHOW_PER_TEAM = 5
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
/* who to write to */
.sheet{background:#fff;border-radius:18px;box-shadow:0 0 0 1px var(--line) inset;overflow:hidden}
.srow{display:grid;grid-template-columns:200px minmax(0,1fr) auto;gap:16px;align-items:center;padding:16px 20px}
.srow+.srow,.reach-out+.srow{border-top:1px solid var(--line)}
.steam{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
.steam i{flex:none;width:11px;height:11px;border-radius:4px}
.steam small{font-weight:500;color:var(--mute);font-variant-numeric:tabular-nums}
.sperson{min-width:0;font-size:14px;color:var(--ink-2)}
.sperson b{color:var(--ink);font-weight:600}
.sperson .for{display:block;margin-top:2px;font-size:12.5px;color:var(--mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sperson .none{color:var(--mute)}
.trust{display:inline-flex;align-items:center;height:20px;padding:0 8px;margin-left:6px;border-radius:999px;font:600 11px/1 var(--sans);
  background:var(--inset);color:var(--ink-2);vertical-align:1px}
.trust.listed_in_ad,.trust.published,.trust.verified{background:var(--mint-wash);color:var(--mint-ink)}
.trust.guessed{background:var(--amber-wash);color:var(--amber-ink)}
.reachbtn{display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 16px;border-radius:12px;border:0;cursor:pointer;
  background:var(--ink);color:#fff;font:600 14px var(--sans);white-space:nowrap}
.reachbtn:hover{background:#000}
.reachbtn.soft{background:#fff;color:var(--ink);box-shadow:0 0 0 1px var(--line) inset}
.reachbtn.soft:hover{box-shadow:0 0 0 1px rgba(23,23,23,.4) inset}
.reachbtn[disabled]{opacity:.7;cursor:progress}
.reachbtn svg{width:16px;height:16px}
.reach-out{padding:0 20px 20px 236px}
.reach-out[hidden]{display:none}
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
.sheet-note{margin:12px 2px 0;font-size:13px;color:var(--mute)}
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
@media (max-width:640px){
  .srow{grid-template-columns:1fr;gap:8px}.reach-out{padding:0 16px 16px}
  .sim{grid-template-columns:1fr}
}
"""

REACH_JS = r"""
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
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
document.querySelectorAll('[data-reach]').forEach(b=>b.addEventListener('click',async()=>{
  const out=document.getElementById(b.getAttribute('aria-controls'));
  if(out.dataset.ready){out.hidden=!out.hidden;b.setAttribute('aria-expanded',String(!out.hidden));return}
  const label=b.textContent;b.disabled=true;b.textContent='Looking… up to a minute';
  try{const r=await post('/api/reach',{key:b.dataset.reach});const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.error||'Could not look that up.');
    out.replaceChildren(letter(d));out.dataset.ready='1';out.hidden=false;b.setAttribute('aria-expanded','true');
    b.textContent=d.found&&d.subject?'Hide email':'Hide';
    const p=b.closest('.srow').querySelector('.sperson');
    if(d.found){p.innerHTML='<b></b><span class="trust"></span><span class="for"></span>';p.querySelector('b').textContent=d.name+(d.title?', '+d.title:'');
      const t=p.querySelector('.trust');t.textContent=d.trust;t.classList.add(d.status);p.querySelector('.for').textContent='For '+d.job}}
  catch(e){say(e.message==='Failed to fetch'?'Could not reach Lavoro. Is it still running?':e.message);b.textContent=label}
  finally{b.disabled=false}}));
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


# ---------------------------------------------------------------- who to write to
def _sheet(con, company, order, teams) -> str:
    from . import reach
    rows = []
    for k in order:
        team = teams[k]
        best = reach.best_for(con, [r["key"] for r in team])
        target = max(team, key=lambda r: ((r["score"] or 0), r["posted_at"] or r["first_seen"] or ""))
        out_id = f"reach-{k}"
        if best is not None:
            d = reach.as_dict(best)
            person = (f'<b>{e(d["name"])}{", " + e(d["title"]) if d["title"] else ""}</b>'
                      f'<span class="trust {e(d["status"])}">{e(d["trust"])}</span><span class="for">For {e(d["job"])}</span>')
            label = "Show email" if d["subject"] else "Write email"
            key = d["key"]
        else:
            person = '<span class="none">Not looked up yet</span>'
            label, key = "Find who hires", target["key"]
        rows.append(f'<div class="srow"><div class="steam"><i style="background:{TEAM_COLOR[k]}"></i>{e(TEAM_LABEL[k])}'
                    f'<small>{len(team)}</small></div><div class="sperson">{person}</div>'
                    f'<button class="reachbtn{" soft" if best is not None else ""}" type="button" data-reach="{e(key)}" '
                    f'aria-controls="{out_id}" aria-expanded="false">{icon("mail")}{label}</button></div>'
                    f'<div class="reach-out" id="{out_id}" hidden></div>')
    return (f'<section class="block"><h2>Who to write to</h2><p class="sub">One person per team. Lavoro looks them up only when '
            f'you ask, then drafts a short email from your profile. You read it and send it yourself.</p>'
            f'<div class="sheet">{"".join(rows)}</div>'
            f'<p class="sheet-note">The lookup uses the ad, then a web search with Claude. It reads public pages only and '
            f'takes up to a minute.</p></section>')


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

    facts = [star_btn(c["id"], c["name"], bool(c["starred"]))]
    if c["website"] or c["domain"]:
        site = c["website"] or f"https://{c['domain']}"
        facts.append(f'<a class="fact" href="{e(site)}" target="_blank" rel="noopener">{EXT}{e(c["domain"] or site)}</a>')
    board = board_url(c["ats"], c["slug"])
    if board:
        facts.append(f'<a class="fact" href="{e(board)}" target="_blank" rel="noopener">{EXT}Job board ({e(c["ats"].title())})</a>')
    if info.get("yc_url"):
        facts.append(f'<a class="fact" href="{e(info["yc_url"])}" target="_blank" rel="noopener">{EXT}YC {e(info.get("batch") or "profile")}</a>')
    if info.get("team_size") not in (None, "", "None", "0"):
        facts.append(f'<span class="fact">{e(info["team_size"])} people</span>')
    if info.get("locations"):
        facts.append(f'<span class="fact">{PIN}{e(info["locations"][:60])}</span>')
    checked = f'<p class="checked">Roles read from the job board {e(ago(c["checked_at"]))}.</p>' if c["checked_at"] else ""
    hero = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/companies">All companies</a><span>/</span><span>{e(c["name"])}</span></nav>'
            f'<h1>{e(c["name"])}</h1>'
            + (f'<p class="count">{e(info["one_liner"])}</p>' if info.get("one_liner") else "")
            + f'<div class="facts">{"".join(facts)}</div>{checked}')

    if not jobs:
        body = ('<section class="block"><h2>No open roles</h2><div class="card empty-note">No open roles right now. '
                'Lavoro checks again on every run.</div></section>')
        return _page(f"Lavoro · {c['name']}", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>" + body + _similar(con, c, None))

    teams = defaultdict(list)
    for r in jobs:
        teams[r["cat"]].append(r)
    order = sorted(teams, key=lambda k: (k == "other", -len(teams[k])))

    parts = [_sheet(con, c, order, teams), _teams(c, order, teams)]

    # pay and email format, side by side when both exist
    side = []
    pays = _pay_rows(jobs)
    cur = _main_currency(pays)
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
        duo = (f'<section class="block"><h2>Pay and email</h2><p class="sub">From the roles {e(c["name"])} lists and the '
               f'addresses Lavoro has confirmed.</p><div class="duo{" one" if not (side and fmt) else ""}">'
               f'{"".join(side)}{fmt}</div></section>')
    parts.append(duo)
    parts.append(_similar(con, c, order[0]))
    return _page(f"Lavoro · {c['name']}", "/companies", hero, f"<style>{ROLE_CSS}{CSS}</style>" + "".join(parts)
                 ).replace("</body>", f"<script>{REACH_JS}</script></body>", 1)


def _teams(company, order, teams) -> str:
    n = sum(len(v) for v in teams.values())
    bar = "".join(f'<span style="flex:{len(teams[k])};background:{TEAM_COLOR[k]}" title="{e(TEAM_LABEL[k])}: {len(teams[k])}"></span>'
                  for k in order)
    key = "".join(f'<a href="#team-{k}"><i style="background:{TEAM_COLOR[k]}"></i>{e(TEAM_LABEL[k])}<b>{len(teams[k])}</b></a>'
                  for k in order)
    out = [f'<section class="block"><h2>{n} open role{"s" if n != 1 else ""}, by team</h2>'
           f'<p class="sub">From {e(company["name"])}\'s own job board, grouped by the kind of work, newest first.</p>'
           f'<div class="mix"><div class="mixbar" role="img" aria-label="Open roles by team">{bar}</div>'
           f'<nav class="mixkey" aria-label="Jump to a team">{key}</nav></div>']
    for k in order:
        rows = teams[k]
        cnt = len(rows)
        where = _place_text(_places(rows))
        newest = ago(rows[0]["posted_at"] or rows[0]["first_seen"])
        sub_line = f'{cnt} open role{"s" if cnt != 1 else ""}' + (f' in {where}' if where else '') + f', newest {newest}.'
        shown = "".join(job_row(r, with_company=False) for r in rows[:SHOW_PER_TEAM])
        rest = rows[SHOW_PER_TEAM:]
        noun = TEAM_LABEL[k].lower() if k != "other" else "other"
        more = (f'<details class="more-roles"><summary>Show {len(rest)} more {e(noun)} role{"s" if len(rest) != 1 else ""}</summary>'
                f'{"".join(job_row(r, with_company=False) for r in rest)}</details>' if rest else "")
        link = f'/jobs?q={quote(company["name"])}' + (f'&cat={k}' if k != "other" else "")
        out.append(f'<section class="team" id="team-{k}"><div class="team-head"><h3><i style="background:{TEAM_COLOR[k]}"></i>'
                   f'{e(TEAM_LABEL[k])}<small>{cnt}</small></h3>'
                   + (f'<a href="{e(link)}">Open in All jobs</a>' if cnt > SHOW_PER_TEAM else '')
                   + f'</div><p class="team-sub">{e(sub_line)}</p><div class="card list">{shown}{more}</div></section>')
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
    cards = "".join(f'<a href="/companies/{r["company_id"]}"><b>{e(names.get(r["company_id"], "?"))}</b>'
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
