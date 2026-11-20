"""Role insight pages: /roles (index) and /roles/<slug> (e.g. /roles/product-designer).

For one role, from the open jobs in the local database: how many are open and who is hiring, what the role pays
(parsed from listed pay ranges), which skills the ads ask for, what the companies offer, and the newest roles.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

from .browse import _page, job_row
from .config import load_config
from .digest import e

# ---------------------------------------------------------------- pay
_CUR = [("CA$", "CAD"), ("A$", "AUD"), ("US$", "USD"), ("$", "USD"), ("£", "GBP"), ("€", "EUR"), ("₹", "INR"),
        ("SEK", "SEK"), ("NOK", "NOK"), ("DKK", "DKK"), ("CAD", "CAD"), ("USD", "USD"), ("EUR", "EUR"),
        ("GBP", "GBP"), ("CHF", "CHF"), ("kr", "SEK")]
_SYMBOL = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹", "CAD": "CA$", "AUD": "A$"}
_NUM = re.compile(r"(\d[\d,\.]*)\s*([kKmMlL])?\b")


def parse_pay(text: str | None) -> tuple[str, float, float] | None:
    """'$130K – $200K • Offers Equity' → ('USD', 130000, 200000), yearly. None if it can't be read safely."""
    if not text:
        return None
    s = text.replace("\xa0", " ").split("•")[0]
    cur = next((code for sym, code in _CUR if sym in s), None)
    if not cur:
        return None
    vals = []
    for num, suf in _NUM.findall(s):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        mult = {"k": 1e3, "m": 1e6, "l": 1e5}.get((suf or "").lower(), 1)
        vals.append(v * mult)
    vals = [v for v in vals if v > 0][:2]
    if not vals:
        return None
    low, high = min(vals), max(vals)
    low_s = s.lower()
    if "hour" in low_s or "/hr" in low_s:
        low, high = low * 2080, high * 2080
    elif "month" in low_s or "/mo" in low_s or "månad" in low_s:
        low, high = low * 12, high * 12
    if high < 5000 or high > 5e7:  # not a yearly salary we can trust
        return None
    return cur, low, high


def money(cur: str, v: float) -> str:
    sym = _SYMBOL.get(cur)
    if v >= 1e6:
        txt = f"{v / 1e6:.1f}M".replace(".0M", "M")
    else:
        txt = f"{round(v / 1e3):,}K"
    return f"{sym}{txt}" if sym else f"{cur} {txt}"


def _nice_step(span: float) -> float:
    raw = span / 5
    mag = 10 ** (len(str(int(raw))) - 1)
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


def _pay_svg(cur: str, ranges: list[tuple[float, float]], lo: float, hi: float) -> str:
    """One thin line per role's pay range, sorted by midpoint, over a shaded band for the typical range."""
    rows = sorted(ranges, key=lambda p: (p[0] + p[1]) / 2)
    if len(rows) > 80:  # keep the chart readable: an even sample
        rows = [rows[round(i * (len(rows) - 1) / 79)] for i in range(80)]
    step = _nice_step(max(y for _, y in rows) - min(x for x, _ in rows) or 1)
    axis_lo = step * int(min(x for x, _ in rows) // step)
    axis_hi = step * -int(-max(y for _, y in rows) // step)
    w, top, gap = 640, 10, max(3.5, min(8.0, 240 / len(rows)))
    plot_h = top + len(rows) * gap
    x = lambda v: 32 + (v - axis_lo) / (axis_hi - axis_lo) * (w - 64)  # room for the first and last axis label
    out = [f'<svg viewBox="0 0 {w} {plot_h + 30:.0f}" role="img" aria-label="Pay ranges of {len(ranges)} roles in {cur}; '
           f'typical range {money(cur, lo)} to {money(cur, hi)}">',
           f'<rect x="{x(lo):.1f}" y="2" width="{max(2, x(hi) - x(lo)):.1f}" height="{plot_h:.0f}" rx="8" fill="#fff1f3"/>']
    for v in (lo, hi):
        out.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="2" y2="{plot_h + 2:.0f}" stroke="#e11d48" stroke-width="1.5" stroke-dasharray="3 3"/>')
    r = 2.6 if gap >= 6 else 1.8
    for i, (a, b) in enumerate(rows):
        y = top + i * gap
        out.append(f'<line x1="{x(a):.1f}" x2="{x(b):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#bdb7ad" stroke-width="{min(2.5, gap * .45):.1f}" stroke-linecap="round"/>'
                   f'<circle cx="{x(a):.1f}" cy="{y:.1f}" r="{r}" fill="#8f897f"/><circle cx="{x(b):.1f}" cy="{y:.1f}" r="{r}" fill="#8f897f"/>')
    v = axis_lo
    while v <= axis_hi + 1:
        out.append(f'<text x="{x(v):.1f}" y="{plot_h + 24:.0f}" text-anchor="middle">{money(cur, v)}</text>')
        v += step
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- skills and offers
SKILLS = [
    ("Figma", r"\bfigma\b"), ("Prototyping", r"\bprototyp"), ("User research", r"user research|usability test|user interview"),
    ("Design systems", r"design system"), ("Accessibility", r"\baccessib|\bwcag\b"), ("Sketch", r"\bsketch\b"),
    ("Adobe", r"\badobe\b|photoshop|illustrator"), ("Interaction design", r"interaction design"),
    ("Python", r"\bpython\b"), ("SQL", r"\bsql\b"), ("JavaScript", r"\bjavascript\b|\bjs\b"), ("TypeScript", r"\btypescript\b"),
    ("React", r"\breact\b"), ("Node.js", r"\bnode(\.js)?\b"), ("Java", r"\bjava\b"), ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("AWS", r"\baws\b|amazon web services"), ("Google Cloud", r"\bgcp\b|google cloud"), ("Azure", r"\bazure\b"),
    ("Docker", r"\bdocker\b"), ("Machine learning", r"machine learning|\bml\b"), ("LLMs", r"\bllms?\b|large language model|generative ai|genai"),
    ("Excel", r"\bexcel\b"), ("Tableau", r"\btableau\b"), ("Power BI", r"power ?bi"), ("Salesforce", r"\bsalesforce\b"),
    ("HubSpot", r"\bhubspot\b"), ("B2B", r"\bb2b\b"), ("SaaS", r"\bsaas\b"), ("Agile", r"\bagile\b|\bscrum\b"),
    ("Stakeholders", r"stakeholder"), ("Swedish", r"\bswedish\b|\bsvenska\b"), ("German", r"\bgerman\b|\bdeutsch\b"),
    ("Startup experience", r"\bstartup\b|early[- ]stage"),
]
SKILLS_RE = [(name, re.compile(rx, re.I)) for name, rx in SKILLS]
OFFERS = [
    ("disclose pay", lambda r, d: bool(r["salary"])),
    ("mention equity or stock options", lambda r, d: bool(re.search(r"equity|stock option|esop|\bshares\b|optioner", (r["salary"] or "") + " " + d, re.I))),
    ("are remote or hybrid", lambda r, d: bool(r["remote"]) or bool(re.search(r"remote|hybrid|distans", r["location"] or "", re.I))),
    ("mention visas or relocation", lambda r, d: bool(re.search(r"\bvisa\b|relocat|sponsorship", d, re.I))),
]

_SENIORITY = re.compile(r"\b(senior|sr\.?|junior|jr\.?|lead|staff|principal|head of|intern(ship)?|i{1,3}|iv|mid|level \d|associate)\b", re.I)


def normalize_title(t: str) -> str:
    t = (t or "").lower()
    t = re.split(r"\s+[-–—|/@]\s+|\(|,|:| - ", t)[0]
    t = _SENIORITY.sub(" ", t)
    t = re.sub(r"[^a-zåäöéü&/ +.#]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_UPPER = {"ux", "ui", "ux/ui", "ui/ux", "ai", "ml", "qa", "hr", "pr", "sre", "gtm", "b2b", "saas", "it", "ios", "seo", "vp", "cto", "ceo"}


def display_title(t: str) -> str:
    """'ux designer' -> 'UX designer'; first letter capitalised, known acronyms upper-case."""
    words = [w.upper() if w in _UPPER else w for w in t.split()]
    out = " ".join(words)
    return out[:1].upper() + out[1:]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9åäö]+", "-", s.lower()).strip("-")


def unslug(slug: str) -> str:
    return re.sub(r"-+", " ", slug).strip()


def _words(role: str) -> list[str]:
    return [w for w in re.split(r"\s+", role.lower()) if w]


def _match(con, role: str):
    words = _words(role)
    if not words:
        return []
    cond = " AND ".join(["lower(j.title) LIKE ?"] * len(words))
    return con.execute(f"""SELECT j.*, c.id AS cid, (SELECT 1 FROM pipeline p WHERE p.job_key = j.key) AS tracked FROM jobs j LEFT JOIN companies c ON c.id = j.company_id
                           WHERE j.status NOT IN ('closed','duplicate') AND {cond}
                           ORDER BY substr(coalesce(j.posted_at, j.first_seen), 1, 10) DESC, j.first_seen DESC""",
                       [f"%{w}%" for w in words]).fetchall()


# ---------------------------------------------------------------- page CSS
CSS = r"""
.sec{margin-top:40px}
.sec h2{margin:0 0 4px}
.back{display:inline-flex;align-items:center;gap:6px;font:500 13.5px var(--sans);color:var(--ink-2);text-decoration:none;margin:0 0 10px}
.back:hover{color:var(--ink)}
.facts4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-radius:18px;background:#fff;box-shadow:0 0 0 1px var(--line) inset}
.facts4>div{padding:20px 22px;min-width:0}.facts4>div+div{border-left:1px solid var(--line)}
.facts4 b{display:block;font:400 34px/1 var(--serif);letter-spacing:-.02em;font-variant-numeric:tabular-nums;white-space:nowrap}
.facts4 span{display:block;margin-top:8px;font-size:13.5px;color:var(--mute)}
.rgrid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:20px;margin-top:20px;align-items:start}
.panel{background:#fff;border-radius:18px;box-shadow:0 0 0 1px var(--line) inset;padding:22px 24px}
.panel+.panel{margin-top:20px}
.panel h2{font:600 15px/1.3 var(--sans);letter-spacing:0;margin:0}
.panel .ps{margin:3px 0 16px;font-size:13px;color:var(--mute)}
.panel .none{margin:0;font-size:14px;color:var(--ink-2)}
.paychart svg{display:block;width:100%;height:auto}
.paychart text{font:500 11.5px var(--sans);fill:#6b6b6b;font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:8px;font-size:12.5px;color:var(--ink-2)}
.legend .band{display:inline-block;width:14px;height:10px;border-radius:3px;background:var(--rose-wash);box-shadow:0 0 0 1.5px var(--rose) inset;margin-right:7px;vertical-align:-1px}
.legend .one{display:inline-block;width:18px;height:2.5px;border-radius:2px;background:#bdb7ad;margin-right:7px;vertical-align:3px}
.sks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 28px}
.sk .top{display:flex;justify-content:space-between;gap:10px;font-size:14px}
.sk .top b{font-weight:600;font-variant-numeric:tabular-nums}
.meter{display:flex;gap:5px;margin-top:7px}
.meter i{flex:1;height:8px;border-radius:3px;background:#efece7}.meter i.on{background:var(--ink)}
.terms,.colist{list-style:none;margin:0;padding:0}
.terms li{display:flex;align-items:baseline;gap:12px;padding:10px 0;border-top:1px solid var(--line);font-size:14px;color:var(--ink-2)}
.terms li:first-child,.colist li:first-child{border-top:0;padding-top:0}
.terms b{flex:none;min-width:48px;font:400 24px/1 var(--serif);color:var(--ink);font-variant-numeric:tabular-nums}
.colist li{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--line);font-size:14px}
.colist a{text-decoration:none}.colist a:hover{text-decoration:underline}
.colist span{color:var(--mute);font-variant-numeric:tabular-nums}
.more-link{display:inline-block;margin-top:12px;font-weight:600;font-size:14.5px}
.rcards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.rcard{display:block;padding:16px 18px;text-decoration:none;transition:transform .2s var(--ease),box-shadow .2s}
.rcard:hover{transform:translateY(-2px);box-shadow:0 10px 30px -14px rgba(30,40,30,.3)}
.rcard .t{font:400 24px/1.1 var(--serif);letter-spacing:-.01em}
.rcard .c{margin-top:6px;font-size:13px;color:var(--mute);font-variant-numeric:tabular-nums}
.rcard.mine{box-shadow:0 0 0 1px rgba(225,29,72,.35) inset}
@media (max-width:980px){.rcards{grid-template-columns:repeat(2,minmax(0,1fr))}.rgrid{grid-template-columns:1fr}
  .facts4{grid-template-columns:repeat(2,minmax(0,1fr))}.facts4>div:nth-child(3){border-left:0}
  .facts4>div:nth-child(n+3){border-top:1px solid var(--line)}}
@media (max-width:640px){
  .rcards{grid-template-columns:1fr}
  .sks{grid-template-columns:1fr}
  .facts4 b{font-size:28px}
}
"""


def _roles_page(title, hero, body):
    return _page(title, "/roles", hero, f"<style>{CSS}</style>{body}")


# ---------------------------------------------------------------- /roles/<slug>
def render_role(con, slug: str) -> str:
    role = unslug(slug)
    rows = _match(con, role)
    n = len(rows)
    name = display_title(role)
    if not n:
        hero = f'<h1>{e(name)}</h1><p class="count">No open roles match “{e(role)}” right now.</p>'
        body = ('<div class="card empty-note">Try a shorter title, such as “designer” or “engineer”. '
                '<a href="/roles">See all roles</a>.</div>')
        return _roles_page(f"Lavoro · {name}", hero, body)

    companies = Counter((r["cid"], r["company"]) for r in rows)
    hero = (f'<a class="back" href="/roles">← All roles</a><h1>{e(name)}</h1>'
            '<p class="count">From the open roles in your Lavoro database, refreshed every run.</p>')

    # pay: every listed yearly range in the commonest currency
    by_cur: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        p = parse_pay(r["salary"])
        if p:
            by_cur.setdefault(p[0], []).append((p[1], p[2]))
    typical = "Not listed"
    if by_cur:
        cur, ranges = max(by_cur.items(), key=lambda kv: len(kv[1]))
        k = len(ranges)
        lo, hi = statistics.median(x for x, _ in ranges), statistics.median(y for _, y in ranges)
        typical = f"{money(cur, lo)}–{money(cur, hi)}"
        other = sum(len(v) for c, v in by_cur.items() if c != cur)
        note = (f'Each line is one role that lists a yearly range in {cur} ({k} of {n:,}).'
                + (f' {other} more list pay in other currencies.' if other else '')
                + (' Few roles list pay, so read this as a rough guide.' if k < 5 else ''))
        pay = (f'<section class="panel"><h2>Pay ranges</h2><p class="ps">{e(note)}</p>'
               f'<div class="paychart">{_pay_svg(cur, ranges, lo, hi)}</div>'
               f'<div class="legend"><span><i class="band"></i>Typical range, {e(typical)}: the median low to the median high</span>'
               f'<span><i class="one"></i>One role</span></div></section>')
    else:
        cur = ""
        pay = '<section class="panel"><h2>Pay ranges</h2><p class="ps">None of these roles list pay yet.</p></section>'

    # skills (only roles that have a description count)
    described = [(r, r["description"] or "") for r in rows if (r["description"] or "").strip()]
    nd = len(described)
    skill_counts = Counter()
    for _, d in described:
        for skill, rx in SKILLS_RE:
            if rx.search(d):
                skill_counts[skill] += 1
    top = [(s, c) for s, c in skill_counts.most_common(10) if nd and c / nd >= 0.03]
    if top:
        meters = "".join(
            f'<div class="sk" title="{c} of {nd} ads"><div class="top"><span>{e(s)}</span><b>{round(100 * c / nd)}%</b></div>'
            f'<div class="meter" aria-hidden="true">{"".join("<i class=on></i>" if i < round(10 * c / nd) else "<i></i>" for i in range(10))}</div></div>'
            for s, c in top)
        skills = (f'<section class="panel"><h2>Skills in demand</h2><p class="ps">How often each skill appears in the {nd:,} ads '
                  f'with full text. Each block is 10%.</p><div class="sks">{meters}</div></section>')
    else:
        skills = '<section class="panel"><h2>Skills in demand</h2><p class="ps">Not enough ad text to count skills yet.</p></section>'

    # the ads: equity, remote, pay shown, visas
    terms, remote_pct = [], 0
    for label, test in OFFERS:
        pct = round(100 * sum(1 for r in rows if test(r, r["description"] or "")) / n)
        if label.startswith("are remote"):
            remote_pct = pct
        terms.append((pct, label))
    terms_html = "".join(f'<li><b>{pct}%</b>{e(label)}</li>' for pct, label in sorted(terms, reverse=True))

    def co_name(cid, cname):
        return f'<a href="/companies/{cid}">{e(cname)}</a>' if cid else e(cname)
    cos = "".join(f'<li>{co_name(cid, cname)}<span>{cnt}</span></li>' for (cid, cname), cnt in companies.most_common(10))

    facts = (f'<div class="facts4"><div><b>{n:,}</b><span>open role{"s" if n != 1 else ""}</span></div>'
             f'<div><b>{len(companies):,}</b><span>compan{"ies" if len(companies) != 1 else "y"} hiring</span></div>'
             f'<div><b>{e(typical)}</b><span>typical yearly pay{f", {cur}" if cur else ""}</span></div>'
             f'<div><b>{remote_pct}%</b><span>remote or hybrid</span></div></div>')
    latest = "".join(job_row(r) for r in rows[:15])
    body = (facts
            + f'<div class="rgrid"><div>{pay}{skills}</div><aside>'
            + f'<section class="panel"><h2>In the ads</h2><p class="ps">Across all {n:,} roles.</p><ul class="terms">{terms_html}</ul></section>'
            + f'<section class="panel"><h2>Hiring most</h2><p class="ps">Open {e(role)} roles per company.</p><ul class="colist">{cos}</ul></section>'
            + '</aside></div>'
            + f'<section class="sec"><h2>Newest roles</h2><p class="sub">The 15 most recent.</p><div class="card list">{latest}</div>'
            + f'<a class="more-link" href="/jobs?q={e(role)}">See all {n:,} in All jobs</a></section>')
    return _roles_page(f"Lavoro · {name}", hero, body)


# ---------------------------------------------------------------- /roles
def render_index(con) -> str:
    titles = Counter(normalize_title(t) for (t,) in con.execute("SELECT title FROM jobs WHERE status NOT IN ('closed','duplicate')"))
    popular = [(t, c) for t, c in titles.most_common(80) if len(t) >= 4 and 1 <= len(t.split()) <= 4 and c >= 4][:30]
    mine = []
    for t in (load_config().get("search", {}).get("titles_include") or [])[:12]:
        c = len(_match(con, t))
        if c:
            mine.append((t, c))
    card = lambda t, c, cls="": (f'<a class="card rcard{cls}" href="/roles/{e(slugify(t))}"><div class="t">{e(display_title(t))}</div>'
                                 f'<div class="c">{c:,} open role{"s" if c != 1 else ""}</div></a>')
    hero = ('<h1>Roles</h1><p class="count">What each kind of role pays, what the ads ask for, and who is hiring. '
            'Built from the open roles in your Lavoro database.</p>')
    search = ('<form class="filters" method="get" action="/roles/go" role="search"><div class="frow">'
              '<label class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>'
              '<input type="search" name="role" placeholder="Any role, e.g. product designer" aria-label="Role"></label>'
              '<button class="apply" type="submit">Show insights</button></div></form>')
    body = search
    if mine:
        body += (f'<section class="sec" style="margin-top:8px"><h2>Your roles</h2><p class="sub">From the roles you search for.</p>'
                 f'<div class="rcards">{"".join(card(t, c, " mine") for t, c in mine)}</div></section>')
    body += (f'<section class="sec"><h2>Most open roles</h2><p class="sub">The commonest job titles right now, seniority left out.</p>'
             f'<div class="rcards">{"".join(card(t, c) for t, c in popular)}</div></section>')
    return _roles_page("Lavoro · Roles", hero, body)
