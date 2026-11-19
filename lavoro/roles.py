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
    return con.execute(f"""SELECT j.*, c.id AS cid FROM jobs j LEFT JOIN companies c ON c.id = j.company_id
                           WHERE j.status NOT IN ('closed','duplicate') AND {cond}
                           ORDER BY substr(coalesce(j.posted_at, j.first_seen), 1, 10) DESC, j.first_seen DESC""",
                       [f"%{w}%" for w in words]).fetchall()


# ---------------------------------------------------------------- page CSS
CSS = r"""
.sec{margin-top:40px}
.sec h2{margin:0 0 4px}
.payline{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.payline .big{font:400 clamp(40px,6vw,58px)/1 var(--serif);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.payline .per{color:var(--mute);font-size:15px}
.pad{padding:22px 24px}
.note2{margin:10px 0 0;color:var(--ink-2);font-size:14px;max-width:66ch}
.bars{display:grid;gap:2px}
.brow{position:relative;display:grid;grid-template-columns:160px 1fr 52px;align-items:center;gap:14px;padding:7px 6px;border-radius:8px}
.brow:hover{background:#faf9f6}
.brow .lbl{font-size:14px;color:var(--ink)}
.brow .track{display:block;height:10px;border-radius:999px;background:#f1efea;overflow:hidden}
.brow .fill{display:block;height:100%;border-radius:0 4px 4px 0;background:#e11d48}
.brow .pct{text-align:right;font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.brow[data-tip]:hover::after{content:attr(data-tip);position:absolute;right:66px;top:-30px;z-index:3;white-space:nowrap;
  background:var(--ink);color:#fff;font:500 12.5px/1 var(--sans);padding:7px 10px;border-radius:8px;
  box-shadow:0 8px 20px -8px rgba(0,0,0,.4);pointer-events:none}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.tile{padding:18px 20px}
.tile .v{font:400 40px/1 var(--serif);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile .k{margin-top:8px;font-size:14px;color:var(--ink-2)}
.tile .s{margin-top:4px;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums}
.cos{display:flex;flex-wrap:wrap;gap:8px}
.cochip{display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:999px;background:#fff;
  box-shadow:0 0 0 1px var(--line) inset;text-decoration:none;font:500 14px var(--sans)}
.cochip span{color:var(--mute);font-size:12.5px;font-variant-numeric:tabular-nums}
a.cochip:hover{box-shadow:0 0 0 1px rgba(225,29,72,.4) inset}
.more-link{display:inline-block;margin-top:12px;font-weight:600;font-size:14.5px}
.rcards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.rcard{display:block;padding:16px 18px;text-decoration:none;transition:transform .2s var(--ease),box-shadow .2s}
.rcard:hover{transform:translateY(-2px);box-shadow:0 10px 30px -14px rgba(30,40,30,.3)}
.rcard .t{font:400 24px/1.1 var(--serif);letter-spacing:-.01em}
.rcard .c{margin-top:6px;font-size:13px;color:var(--mute);font-variant-numeric:tabular-nums}
.rcard.mine{box-shadow:0 0 0 1px rgba(225,29,72,.35) inset}
@media (max-width:980px){.rcards{grid-template-columns:repeat(2,minmax(0,1fr))}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){
  .brow{grid-template-columns:110px 1fr 44px;gap:10px}
  .rcards{grid-template-columns:1fr}
  .brow[data-tip]:hover::after{right:auto;left:0}
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
    hero = (f'<h1>{e(name)}</h1><p class="count"><b>{n:,}</b> open role{"s" if n != 1 else ""} at <b>{len(companies):,}</b> '
            f'compan{"ies" if len(companies) != 1 else "y"}, from the job boards Lavoro reads. Updated every run.</p>')

    # pay
    by_cur: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        p = parse_pay(r["salary"])
        if p:
            by_cur.setdefault(p[0], []).append((p[1], p[2]))
    if by_cur:
        cur, ranges = max(by_cur.items(), key=lambda kv: len(kv[1]))
        k = len(ranges)
        lo, hi = statistics.median(x for x, _ in ranges), statistics.median(y for _, y in ranges)
        other = sum(len(v) for c, v in by_cur.items() if c != cur)
        pay = (f'<div class="card pad"><div class="payline"><span class="big">{money(cur, lo)}–{money(cur, hi)}</span>'
               f'<span class="per">a year</span></div>'
               f'<p class="note2">The median range across the {k} role{"s" if k != 1 else ""} that list pay in {cur}'
               f'{f", out of {n:,} open" if n > k else ""}.'
               f'{f" {other} more list pay in other currencies." if other else ""} '
               f'{"Few roles list pay, so treat this as a rough guide." if k < 5 else ""}</p></div>')
    else:
        pay = '<div class="card pad"><p class="note2" style="margin:0">None of these roles list pay yet.</p></div>'

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
        bars = "".join(
            f'<div class="brow" data-tip="{c} of {nd} roles"><span class="lbl">{e(s)}</span>'
            f'<span class="track"><span class="fill" style="width:{max(2, round(100 * c / nd))}%"></span></span>'
            f'<span class="pct">{round(100 * c / nd)}%</span></div>' for s, c in top)
        skills = (f'<div class="card pad"><div class="bars" role="list" aria-label="Skills mentioned in the ads">{bars}</div></div>')
    else:
        skills = '<div class="card pad"><p class="note2" style="margin:0">Not enough ad text to count skills.</p></div>'

    # offers
    tiles = []
    for label, test in OFFERS:
        hits = sum(1 for r in rows if test(r, r["description"] or ""))
        tiles.append(f'<div class="card tile"><div class="v">{round(100 * hits / n)}%</div><div class="k">{e(label)}</div>'
                     f'<div class="s">{hits:,} of {n:,}</div></div>')

    cos = "".join(
        (f'<a class="cochip" href="/companies/{cid}">{e(cname)}<span>{cnt}</span></a>' if cid else
         f'<span class="cochip">{e(cname)}<span>{cnt}</span></span>')
        for (cid, cname), cnt in companies.most_common(24))
    latest = "".join(job_row(r) for r in rows[:15])

    body = (f'<section class="sec" style="margin-top:0"><h2>What it pays</h2><p class="sub">Yearly, from the pay ranges companies list.</p>{pay}</section>'
            f'<section class="sec"><h2>What these roles ask for</h2><p class="sub">Share of the {nd:,} ads with full text that mention each skill.</p>{skills}</section>'
            f'<section class="sec"><h2>What they offer</h2><p class="sub">Across all {n:,} open roles.</p><div class="tiles">{"".join(tiles)}</div></section>'
            f'<section class="sec"><h2>Who’s hiring</h2><p class="sub">Companies with the most open {e(role)} roles.</p><div class="cos">{cos}</div></section>'
            f'<section class="sec"><h2>Newest roles</h2><p class="sub">The 15 most recent.</p><div class="card list">{latest}</div>'
            f'<a class="more-link" href="/jobs?q={e(role)}">See all {n:,} in All jobs →</a></section>')
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
