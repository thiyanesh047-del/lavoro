"""Job fetchers. Each ATS has a public, keyless JSON/RSS endpoint per company.

Every fetcher returns a list of normalized job dicts:
  key, source, company, title, location, remote, department, url, salary, description, posted_at, ad_contacts
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .net import domain_of, get, get_json, html_to_text

# Domains that belong to job platforms, never to the employer.
PLATFORM_DOMAINS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "teamtailor.com",
    "smartrecruiters.com", "arbetsformedlingen.se", "jobtechdev.se", "linkedin.com", "indeed.com",
    "varbi.com", "reachmee.com", "jobylon.com", "emply.com", "career.", "jobs.", "gmail.com", "hotmail.com",
    "outlook.com", "thehub.io", "webcruiter", "successfactors", "workday", "pinpointhq.com", "homerun.co",
)


def is_platform(domain: str) -> bool:
    return not domain or any(p in domain for p in PLATFORM_DOMAINS)


def _iso_ms(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


# Some boards give only a two-letter country code ("Göteborg, SE"); the region filter matches country names.
COUNTRY = {
    "se": "Sweden", "no": "Norway", "dk": "Denmark", "fi": "Finland", "is": "Iceland", "gb": "United Kingdom",
    "uk": "United Kingdom", "ie": "Ireland", "de": "Germany", "nl": "Netherlands", "be": "Belgium", "fr": "France",
    "es": "Spain", "pt": "Portugal", "it": "Italy", "ch": "Switzerland", "at": "Austria", "pl": "Poland", "cz": "Czech Republic",
    "ee": "Estonia", "lv": "Latvia", "lt": "Lithuania", "hu": "Hungary", "ro": "Romania", "gr": "Greece", "hr": "Croatia",
    "rs": "Serbia", "bg": "Bulgaria", "si": "Slovenia", "sk": "Slovakia", "lu": "Luxembourg", "mt": "Malta", "cy": "Cyprus",
    "ua": "Ukraine", "us": "United States", "ca": "Canada", "mx": "Mexico", "br": "Brazil", "in": "India", "cn": "China",
    "jp": "Japan", "kr": "South Korea", "sg": "Singapore", "my": "Malaysia", "id": "Indonesia", "th": "Thailand",
    "vn": "Vietnam", "ph": "Philippines", "au": "Australia", "ae": "United Arab Emirates", "sa": "Saudi Arabia",
    "il": "Israel", "tr": "Turkey", "za": "South Africa", "hk": "Hong Kong", "tw": "Taiwan",
}


def with_country(loc: str) -> str:
    """'Göteborg, SE, 405 08' -> 'Göteborg, SE, 405 08 (Sweden)'. Leaves text without a known code alone."""
    # The country comes last ("Fresno, CA, US, 93725"), so read from the end; "CA" there is a US state.
    for part in (p.strip().lower() for p in reversed((loc or "").split(","))):
        if len(part) == 2 and part in COUNTRY:
            return f"{loc} ({COUNTRY[part]})"
    return loc


def _salary(mn, mx, cur, per) -> str | None:
    if not (mn or mx):
        return None
    rng = f"{mn or '?'}–{mx or '?'}" if mn != mx else f"{mn}"
    return " ".join(x for x in [rng, cur or "", f"/{per}" if per else ""] if x).strip()


# ---------------------------------------------------------------- Greenhouse
def greenhouse(slug: str, company: str | None = None) -> list[dict]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if not data or "jobs" not in data:
        return []
    if not company:
        meta = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}") or {}
        company = meta.get("name") or slug
    out = []
    for j in data["jobs"]:
        loc = (j.get("location") or {}).get("name") or ""
        out.append(dict(
            key=f"greenhouse:{slug}:{j['id']}", source="greenhouse", company=company, title=j.get("title"),
            location=loc, remote="remote" in loc.lower(),
            department=", ".join(d.get("name", "") for d in j.get("departments") or []),
            url=j.get("absolute_url"), salary=None, description=html_to_text(j.get("content")),
            posted_at=j.get("first_published") or j.get("updated_at"),
        ))
    return out


# ---------------------------------------------------------------- Lever
def lever(slug: str, company: str | None = None) -> list[dict]:
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(data, list) or not data:
        data = get_json(f"https://api.eu.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(data, list):
        return []
    out = []
    for j in data:
        cat = j.get("categories") or {}
        sr = j.get("salaryRange") or {}
        desc = "\n\n".join(filter(None, [j.get("descriptionPlain"), *[
            f"{l.get('text')}\n{html_to_text(l.get('content'))}" for l in j.get("lists") or []
        ], j.get("additionalPlain")]))
        loc = cat.get("location") or ", ".join(cat.get("allLocations") or [])
        out.append(dict(
            key=f"lever:{slug}:{j['id']}", source="lever", company=company or slug, title=j.get("text"),
            location=loc, remote=(j.get("workplaceType") == "remote") or "remote" in (loc or "").lower(),
            department=cat.get("team") or cat.get("department"), url=j.get("hostedUrl"),
            salary=_salary(sr.get("min"), sr.get("max"), sr.get("currency"), sr.get("interval")),
            description=desc, posted_at=_iso_ms(j.get("createdAt")),
        ))
    return out


# ---------------------------------------------------------------- Ashby
def ashby(slug: str, company: str | None = None) -> list[dict]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    if not data or "jobs" not in data:
        return []
    out = []
    for j in data["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        comp = (j.get("compensation") or {}).get("compensationTierSummary")
        out.append(dict(
            key=f"ashby:{slug}:{j['id']}", source="ashby", company=company or slug, title=(j.get("title") or "").strip(),
            location=" / ".join(l for l in locs if l), remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            department=j.get("department") or j.get("team"), url=j.get("jobUrl"), salary=comp,
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            posted_at=j.get("publishedAt"),
        ))
    return out


# ---------------------------------------------------------------- Workable
def workable(slug: str, company: str | None = None) -> list[dict]:
    data = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if not data or "jobs" not in data:
        return []
    company = company or data.get("name") or slug
    out = []
    for j in data["jobs"]:
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        out.append(dict(
            key=f"workable:{slug}:{j.get('shortcode')}", source="workable", company=company, title=j.get("title"),
            location=loc, remote=bool(j.get("telecommuting")), department=j.get("department"), url=j.get("url"),
            salary=None, description=html_to_text(j.get("description")), posted_at=j.get("published_on"),
        ))
    return out


# ---------------------------------------------------------------- Recruitee
def recruitee(slug: str, company: str | None = None) -> list[dict]:
    data = get_json(f"https://{slug}.recruitee.com/api/offers/")
    if not data or "offers" not in data:
        return []
    out = []
    for j in data["offers"]:
        s = j.get("salary") or {}
        out.append(dict(
            key=f"recruitee:{slug}:{j['id']}", source="recruitee", company=company or j.get("company_name") or slug,
            title=j.get("title"), location=j.get("location"), remote=bool(j.get("remote")),
            department=j.get("department"), url=j.get("careers_url"),
            salary=_salary(s.get("min"), s.get("max"), s.get("currency"), s.get("period")),
            description=html_to_text((j.get("description") or "") + (j.get("requirements") or "")),
            posted_at=j.get("published_at"),
        ))
    return out


# ---------------------------------------------------------------- Teamtailor (very common in Sweden)
_TT = "{https://teamtailor.com/locations}"


_tt_demo: dict[str, bool] = {}


def _teamtailor_demo(host: str) -> bool:
    """Teamtailor runs demo career sites whose jobs are not real ("This is just a demo career site")."""
    if host not in _tt_demo:
        r = get(f"https://{host}/jobs", timeout=15)
        _tt_demo[host] = r is not None and "demo career site" in r.text.lower()
    return _tt_demo[host]


def teamtailor(slug: str, company: str | None = None) -> list[dict]:
    # slug is either "acme" (acme.teamtailor.com) or a custom careers host like "careers.acme.com"
    host = slug if "." in slug else f"{slug}.teamtailor.com"
    r = get(f"https://{host}/jobs.rss")
    if r is None or r.status_code != 200 or b"<rss" not in r.content[:300]:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    ch = root.find("channel")
    company = company or (ch.findtext("title") if ch is not None else None) or slug
    if root.find("channel/item") is not None and _teamtailor_demo(host):
        return []  # a Teamtailor demo site: its jobs are not real
    out = []
    for it in root.iter("item"):
        locs = []
        for l in it.iter(f"{_TT}location"):
            locs.append(", ".join(x for x in [l.findtext(f"{_TT}city"), l.findtext(f"{_TT}country")] if x))
        remote_status = (it.findtext("remoteStatus") or "").lower()
        posted = it.findtext("pubDate")
        try:
            posted = datetime.strptime(posted, "%a, %d %b %Y %H:%M:%S %z").isoformat()
        except (TypeError, ValueError):
            pass
        out.append(dict(
            key=f"teamtailor:{slug}:{it.findtext('guid')}", source="teamtailor", company=company,
            title=it.findtext("title"), location=" / ".join(l for l in locs if l) + (f" ({remote_status})" if remote_status else ""),
            remote=remote_status in ("fully", "remote"), department=it.findtext(f"{_TT}department"),
            url=it.findtext("link"), salary=None, description=html_to_text(it.findtext("description")), posted_at=posted,
        ))
    return out


# ---------------------------------------------------------------- SmartRecruiters
SR_MAX = 2000  # big employers (H&M lists ~2,000) are paged 100 at a time


def smartrecruiters(slug: str, company: str | None = None) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
    data = get_json(url)
    if not data or not data.get("content"):
        return []
    total = min(int(data.get("totalFound") or 0), SR_MAX)
    with ThreadPoolExecutor(4) as ex:
        pages = [data, *ex.map(lambda off: get_json(f"{url}&offset={off}") or {}, range(100, total, 100))]
    out, seen = [], set()
    for j in (j for p in pages for j in p.get("content") or []):
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        loc = j.get("location") or {}
        out.append(dict(
            key=f"smartrecruiters:{slug}:{j['id']}", source="smartrecruiters",
            company=company or (j.get("company") or {}).get("name") or slug, title=j.get("name"),
            location=with_country(", ".join(x for x in [loc.get("city"), loc.get("country")] if x)), remote=bool(loc.get("remote")),
            department=(j.get("department") or {}).get("label"),
            url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", salary=None,
            description="", posted_at=j.get("releasedDate"),
        ))
    return out


# ---------------------------------------------------------------- Workday
# Big employers (AstraZeneca, NVIDIA, many banks and car makers) run their career site on Workday, at
# https://<tenant>.wd<N>.myworkdayjobs.com/<site>. The site itself reads a public JSON endpoint, which we read too.
# The slug is "<host>/<site>", e.g. "astrazeneca.wd3.myworkdayjobs.com/Careers".
WORKDAY_MAX = 2000   # Workday stops listing at 2,000 jobs anyway
_WD_AGO = re.compile(r"(\d+)\+?\s+days?\s+ago", re.I)


def _workday_api(host: str, site: str) -> str:
    return f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}"


def _workday_posted(text: str | None) -> str | None:
    """Workday says "Posted Today", "Posted Yesterday", "Posted 3 Days Ago" or "Posted 30+ Days Ago"."""
    t = (text or "").lower()
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    else:
        m = _WD_AGO.search(t)
        if not m:
            return None
        days = int(m.group(1)) + (1 if "+" in t else 0)
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def workday(slug: str, company: str | None = None) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    from .net import post_json
    host, _, site = slug.partition("/")
    if not host.endswith(".myworkdayjobs.com") or not site:
        return []
    api = _workday_api(host, site) + "/jobs"
    page = lambda off: post_json(api, {"appliedFacets": {}, "limit": 20, "offset": off, "searchText": ""}) or {}
    first = page(0)
    if not first.get("jobPostings"):
        return []
    total = min(int(first.get("total") or 0), WORKDAY_MAX)
    with ThreadPoolExecutor(4) as ex:
        rest = list(ex.map(page, range(20, total, 20)))
    company = company or host.split(".")[0].title()
    out, seen = [], set()
    for data in [first, *rest]:
        for j in data.get("jobPostings") or []:
            path = j.get("externalPath") or ""
            if not path or path in seen:
                continue
            seen.add(path)
            loc = j.get("locationsText") or ""
            out.append(dict(
                key=f"workday:{host}:{path.rsplit('/', 1)[-1]}", source="workday", company=company, title=j.get("title"),
                location=loc, remote="remote" in f"{loc} {j.get('title', '')}".lower(), department=None,
                url=f"https://{host}/{site}{path}", salary=None, description="", posted_at=_workday_posted(j.get("postedOn")),
            ))
    return out


# ---------------------------------------------------------------- SAP SuccessFactors career sites
# Volvo Group (jobs.volvogroup.com), Volvo Cars (jobs.volvocars.com) and many European corporates run a SuccessFactors
# career site. Its public search page lists 25 jobs at a time; its sitemap gives each job's date. The slug is the host.
SF_MAX = 2000
_SF_ROW = re.compile(r'<tr class="data-row">(.*?)</tr>', re.S)
_SF_LINK = re.compile(r'<a href="(/job/[^"]+)" class="jobTitle-link">(.*?)</a>', re.S)
_SF_LOC = re.compile(r'<span class="jobLocation">\s*(.*?)\s*</span>', re.S)
_SF_DEPT = re.compile(r'<td class="colFacility[^"]*"[^>]*>\s*<span class="jobFacility">(.*?)</span>', re.S)
_SF_TOTAL = re.compile(r'of <b>([\d,.\s]+)</b>')
_SF_SITEMAP = re.compile(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>")


def successfactors(slug: str, company: str | None = None) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import unquote
    host = slug.strip("/").split("/")[0]
    search = f"https://{host}/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow="
    first = get(search + "0", timeout=30)
    if first is None or first.status_code != 200:
        return []
    if 'class="data-row"' not in first.text:
        # The newer "career site builder" (e.g. Atlas Copco) loads its jobs from a JSON endpoint instead.
        return _sf_builder(host, company) if "j2w" in first.text or "successfactors" in first.text else []
    m = _SF_TOTAL.search(first.text)
    step = len(_SF_ROW.findall(first.text)) or 25   # sites page 20 or 25 at a time
    total = min(int(re.sub(r"\D", "", m.group(1))) if m else step, SF_MAX)
    with ThreadPoolExecutor(4) as ex:
        rest = list(ex.map(lambda s: (get(search + str(s), timeout=30) or None), range(step, total, step)))
    sm = get(f"https://{host}/sitemap.xml", timeout=30)
    dates = {unquote(u).rstrip("/").rsplit("/", 1)[-1]: d for u, d in _SF_SITEMAP.findall(sm.text if sm is not None else "")}
    company = company or host.split(".")[1].title()
    out, seen = [], set()
    for page in [first, *rest]:
        if page is None or page.status_code != 200:
            continue
        for row in _SF_ROW.findall(page.text):
            link = _SF_LINK.search(row)
            if not link:
                continue
            path, title = link.group(1), html.unescape(link.group(2)).strip()
            job_id = path.rstrip("/").rsplit("/", 1)[-1]
            if job_id in seen:
                continue
            seen.add(job_id)
            loc = _SF_LOC.search(row)
            dept = _SF_DEPT.search(row)
            # "Oostakker, BE, 9041 <small>+2 more…</small>" -> "Oostakker, BE, 9041 +2 more…"
            loc_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", loc.group(1))).strip() if loc else ""
            location = with_country(html.unescape(loc_text))
            out.append(dict(
                key=f"successfactors:{host}:{job_id}", source="successfactors", company=company, title=title,
                location=location, remote="remote" in f"{location} {title}".lower(),
                department=html.unescape(dept.group(1)).strip() if dept else None,
                url=f"https://{host}{path}", salary=None, description="", posted_at=dates.get(job_id),
            ))
    return out


def _fix_mojibake(t: str) -> str:
    """'TÃ©cnico' -> 'Técnico': some sites send UTF-8 text that was decoded twice."""
    if "Ã" in t or "Â" in t:
        try:
            return t.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return t


def _sf_builder(host: str, company: str | None) -> list[dict]:
    """SuccessFactors career site builder: POST /services/recruiting/v1/jobs, 10 jobs a page, newest first."""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import unquote
    from .net import post_json
    api = f"https://{host}/services/recruiting/v1/jobs"

    def page(n: int) -> dict:
        return post_json(api, {"locale": "en_US", "pageNumber": n, "sortBy": "date", "keywords": "", "location": "",
                               "facetFilters": {}, "brand": "", "skills": [], "categoryId": 0, "alertId": "",
                               "rcmCandidateId": ""}, timeout=30) or {}
    first = page(0)
    rows = first.get("jobSearchResult") or []
    if not rows:
        return []
    size = len(rows)
    total = min(int(first.get("totalJobs") or size), SF_MAX)
    with ThreadPoolExecutor(6) as ex:
        pages = [first, *ex.map(page, range(1, (total + size - 1) // size))]
    company = company or host.split(".")[-2].title()
    out, seen = [], set()
    for pg in pages:
        for row in pg.get("jobSearchResult") or []:
            j = row.get("response") or {}
            jid = str(j.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            title = _fix_mojibake(html.unescape(j.get("unifiedStandardTitle") or unquote(j.get("urlTitle") or "")))
            loc = " / ".join(re.sub(r"<[^>]+>", "", x).strip() for x in (j.get("jobLocationShort") or []) if x)
            country = ", ".join(j.get("jobLocationCountry") or [])
            location = _fix_mojibake(f"{loc} ({country})" if loc and country and country not in loc else (loc or country))
            posted = None
            try:
                posted = datetime.strptime(j.get("unifiedStandardStart") or "", "%m/%d/%y").date().isoformat()
            except ValueError:
                pass
            out.append(dict(
                key=f"successfactors:{host}:{jid}", source="successfactors", company=company, title=title,
                location=with_country(location), remote="remote" in f"{location} {title}".lower(),
                department=", ".join(j.get("filter2") or []) or None,
                url=f"https://{host}/job/{j.get('urlTitle') or 'job'}/{jid}-en_US/", salary=None, description="",
                posted_at=posted))
    return out


def _span_inner(text: str, marker: str) -> str:
    """The inside of the <span> that starts at `marker`, counting nested spans."""
    i = text.find(marker)
    if i < 0:
        return ""
    start = text.find(">", i) + 1
    depth, pos = 1, start
    for m in re.finditer(r"<(/?)span\b[^>]*>", text[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return text[start:start + m.start()]
    return text[start:start + 20000]


ATS_FETCHERS = {
    "greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workable": workable,
    "recruitee": recruitee, "teamtailor": teamtailor, "smartrecruiters": smartrecruiters, "workday": workday,
    "successfactors": successfactors,
}


def fill_description(job) -> str:
    """Fetch the ad text for boards whose job list leaves it out (Workday, SmartRecruiters). Returns "" if none."""
    url, src = job["url"] or "", job["source"]
    try:
        if src == "workday":
            from urllib.parse import urlparse
            u = urlparse(url)
            site, _, path = u.path.lstrip("/").partition("/")
            data = get_json(f"{_workday_api(u.hostname, site)}/{path}") or {}
            info = data.get("jobPostingInfo") or {}
            extra = " · ".join(x for x in [info.get("timeType"), ", ".join(info.get("additionalLocations") or [])] if x)
            return (html_to_text(info.get("jobDescription")) + (f"\n\n{extra}" if extra else "")).strip()
        if src == "successfactors":
            r = get(url, timeout=30)
            if r is None or r.status_code != 200:
                return ""
            return html_to_text(_span_inner(r.text, 'class="jobdescription"') or _span_inner(r.text, 'itemprop="description"'))
        if src == "smartrecruiters":
            m = re.match(r"https://jobs\.smartrecruiters\.com/([^/]+)/([^/?#]+)", url)
            if not m:
                return ""
            data = get_json(f"https://api.smartrecruiters.com/v1/companies/{m[1]}/postings/{m[2]}") or {}
            sections = (data.get("jobAd") or {}).get("sections") or {}
            return "\n\n".join(html_to_text(s.get("text")) for s in sections.values() if isinstance(s, dict) and s.get("text"))
    except Exception:
        return ""
    return ""


# ---------------------------------------------------------------- JobTech / Platsbanken (Sweden, public API)
def jobtech(query: str, regions: list[str] | None = None, limit: int = 100, max_age_days: int = 30) -> list[dict]:
    since = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%S")
    params = [("q", query), ("limit", str(min(limit, 100))), ("published-after", since)]
    for r in regions or []:
        params.append(("region", r))
    data = get_json("https://jobsearch.api.jobtechdev.se/search", params=params)
    if not data:
        return []
    out = []
    for h in data.get("hits", []):
        emp = h.get("employer") or {}
        app = h.get("application_details") or {}
        addr = h.get("workplace_address") or {}
        contacts = [
            {"name": c.get("name"), "title": c.get("contact_type") or c.get("description"), "email": c.get("email")}
            for c in h.get("application_contacts") or [] if c.get("name") or c.get("email")
        ]
        domain = ""
        for cand in [emp.get("url"), app.get("url"), *[f"x@{c['email'].split('@')[-1]}" for c in contacts if c.get("email")]]:
            d = domain_of(cand.split("@")[-1] if cand and "@" in cand else cand)
            if d and not is_platform(d):
                domain = d
                break
        model = ((h.get("workplace_model") or {}) if isinstance(h.get("workplace_model"), dict) else {}).get("label") or ""
        out.append(dict(
            key=f"jobtech:{h['id']}", source="jobtech",
            company=re.sub(r"\s*\(publ\)|\s+AB$", "", emp.get("name") or "").strip() or emp.get("workplace"),
            domain=domain, title=h.get("headline"),
            location=", ".join(x for x in [addr.get("municipality"), addr.get("region"), addr.get("country")] if x),
            remote="distans" in model.lower() or "remote" in model.lower(),
            department=(h.get("occupation") or {}).get("label"),
            url=app.get("url") or h.get("webpage_url"), salary=h.get("salary_description"),
            description=(h.get("description") or {}).get("text") or "", posted_at=h.get("publication_date"),
            ad_contacts=contacts + ([{"name": None, "title": "application email", "email": app["email"]}] if app.get("email") else []),
        ))
    return out



# ---------------------------------------------------------------- Hacker News "Ask HN: Who is hiring?" (monthly, public)
_ROLE = re.compile(r"engineer|developer|designer|design|manager|scientist|analyst|lead|head of|founding|marketing|sales|"
                   r"product|\bux\b|\bui\b|data|\bml\b|\bai\b|devops|\bsre\b|recruit|operations|researcher|architect|"
                   r"consultant|intern|cto|vp|director|writer|support|success|phd|specialist", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SEP_AT = r"(?:\s+at\s+|\s*[\[\(\{<]\s*at\s*[\]\)\}>]\s*)"
_SEP_DOT = r"(?:\s+dot\s+|\s*[\[\(\{<]\s*dot\s*[\]\)\}>]\s*|\.)"
# "jane at acme dot com", "jane [at] acme [dot] com" — the 'at'/'dot' must stand alone, never inside a word.
_OBF = re.compile(rf"\b([A-Za-z0-9._%+-]+){_SEP_AT}([A-Za-z0-9-]+(?:{_SEP_DOT}[A-Za-z0-9-]+)*{_SEP_DOT}[A-Za-z]{{2,12}})\b", re.I)
_CLOSED = re.compile(r"no longer (taking|accepting|hiring)|position (has been )?filled|\bfilled\b.*\broles?\b|hiring is paused", re.I)


def _hn_emails(text: str) -> list[str]:
    found = set(m.lower() for m in _EMAIL.findall(text))
    for user, dom in _OBF.findall(text):
        dom = re.sub(_SEP_DOT, ".", dom, flags=re.I)
        if "." in dom and len(user) > 1:
            found.add(f"{user}@{dom}".lower())
    return sorted(e for e in found if not e.endswith((".png", ".jpg")))


def parse_hn_post(c: dict) -> dict | None:
    raw = c.get("text") or ""
    if not raw or _CLOSED.search(raw[:400]):
        return None
    paras = re.split(r"(?i)<p>", raw)
    header = next((p for p in paras[:3] if p.count("|") >= 2), None)
    if header is None:
        return None
    hrefs = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', raw)]  # HN writes "/" as &#x2F;
    segs = [html_to_text(x).strip() for x in header.split("|")]
    segs = [x for x in segs if x]
    if not segs:
        return None
    company = re.sub(r"\s*\((?:yc|series|seed)[^)]*\)\s*$", "", segs[0], flags=re.I).strip() or segs[0]
    role = next((x for x in segs[1:] if _ROLE.search(x) and not x.lower().startswith("http") and len(x) < 140), "")
    salary = next((x for x in segs[1:] if re.search(r"[$€£₹]|\d+\s?[kK]\b|\bsek\b|\beur\b", x)), None)
    rest = [x for x in segs[1:] if x not in (role, salary) and not x.lower().startswith("http")
            and not re.match(r"(?i)(full|part)[- ]?time|contract(or)?|intern(ship)?|permanent", x)]
    location = " · ".join(rest)[:160]
    remote = bool(re.search(r"\bremote\b", " ".join(segs), re.I))
    emails = _hn_emails(html_to_text(raw))
    link = next((h for h in hrefs if "news.ycombinator.com" not in h), None)
    domain = ""
    not_employer = ("github.com", "arxiv.org", "docs.google", "notion.", "forms.gle", "calendly", "youtube", "x.com",
                    "twitter.com", "medium.com", "substack.com", "typeform", "tally.so", "airtable")
    for cand in [*[f"x@{x.split('@')[1]}" for x in emails if not x.split("@")[1].endswith((".edu", ".ac.uk"))], link]:
        d = domain_of(cand.split("@")[-1] if cand and "@" in cand else cand)
        if d and not is_platform(d) and not any(n in d for n in not_employer):
            domain = d
            break
    return dict(
        key=f"hn:{c['id']}", source="hn", company=company[:80], domain=domain, title=role or "Several roles",
        location=location or ("Remote" if remote else ""), remote=remote, department="Hacker News",
        url=f"https://news.ycombinator.com/item?id={c['id']}", salary=salary,
        description=html_to_text(raw), posted_at=c.get("created_at"),
        ad_contacts=[{"name": None, "title": "email in the HN post", "email": x} for x in emails[:3]],
    )


def hn_hiring(months: int = 1) -> list[dict]:
    """Top-level posts from the latest `months` 'Ask HN: Who is hiring?' threads (Algolia's public HN API)."""
    data = get_json("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=12")
    threads = [h for h in (data or {}).get("hits", []) if (h.get("title") or "").startswith("Ask HN: Who is hiring")][:max(1, months)]
    out = []
    for t in threads:
        item = get_json(f"https://hn.algolia.com/api/v1/items/{t['objectID']}", timeout=60) or {}
        for c in item.get("children") or []:
            j = parse_hn_post(c)
            if j:
                out.append(j)
    return out



# ---------------------------------------------------------------- Arbeitnow (free public EU job API; credit: arbeitnow.com)
def arbeitnow(pages: int = 3) -> list[dict]:
    """Newest Europe-focused jobs from https://www.arbeitnow.com/api/job-board-api (no key; please keep pages low)."""
    out = []
    for page in range(1, max(1, pages) + 1):
        data = get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}", timeout=40)
        if not data or not data.get("data"):
            break
        for j in data["data"]:
            try:
                posted = datetime.fromtimestamp(int(j.get("created_at") or 0), tz=timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                posted = None
            out.append(dict(
                key=f"arbeitnow:{j['slug']}", source="arbeitnow", company=j.get("company_name"), domain="",
                title=j.get("title"), location=j.get("location") or "", remote=bool(j.get("remote")),
                department=", ".join(j.get("tags") or [])[:80] or None, url=j.get("url"), salary=None,
                description=html_to_text(j.get("description")), posted_at=posted,
            ))
    return out
