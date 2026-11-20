"""Command line: python -m lavoro <command>"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import contacts, db, digest, discover, draft, llm, match, regions, websearch
from .config import load_config
from .net import domain_of
from .sources import ATS_FETCHERS, arbeitnow, hn_hiring, jobtech


def cmd_seed_yc(con, cfg, a):
    n = discover.seed_yc(con, regions.resolve(cfg)["yc"])
    print(f"Added {n} YC companies. Next: python -m lavoro detect")


def cmd_seed_startups(con, cfg, a):
    n = discover.seed_startups(con)
    print(f"Added {n} companies from the bundled startup list.")


def cmd_detect(con, cfg, a):
    checked, found = discover.detect_all(con, a.limit)
    print(f"Checked {checked} companies, found a job board for {found}.")


def cmd_add(con, cfg, a):
    """Add a company from its name, website or careers-page URL, and fetch its open roles."""
    try:
        r = discover.add_company(con, a.url, a.name)
    except discover.AddError as e:
        print(e)
        return
    verb = "Already watching" if r["existed"] else "Added"
    print(f"{verb} {r['name']} ({r['ats']}): {r['roles']} open roles, {r['new']} new (id {r['id']})")


def cmd_probe(con, cfg, a):
    for name in a.names:
        p = discover.probe(name, a.domain or "")
        if p:
            cid = db.upsert_company(con, name=name, domain=a.domain or None, ats=p[0], slug=p[1], source="probe")
            print(f"{name}: {p[0]}/{p[1]} — {p[2]} open jobs (saved, id {cid})")
        else:
            print(f"{name}: no board found on {', '.join(ATS_FETCHERS)}")
    con.commit()


def cmd_fetch(con, cfg, a):
    s = cfg.get("search", {})
    comps = con.execute("SELECT * FROM companies WHERE ats IS NOT NULL AND ats<>'none'").fetchall()

    def work(c):
        try:
            return c, ATS_FETCHERS[c["ats"]](c["slug"], c["name"])
        except Exception as e:
            print(f"  ! {c['name']} ({c['ats']}): {e}")
            return c, None

    new = total = 0
    with ThreadPoolExecutor(10) as ex:
        for c, jobs in ex.map(work, comps):
            if jobs is None:
                continue
            keys = []
            for j in jobs:
                j["company_id"], j["domain"] = c["id"], c["domain"]
                new += db.upsert_job(con, j)
                keys.append(j["key"])
            total += len(jobs)
            # Jobs from this board that disappeared are closed.
            if jobs:
                q = ",".join("?" * len(keys))
                con.execute(f"UPDATE jobs SET status='closed' WHERE company_id=? AND key NOT IN ({q}) AND status NOT IN ('sent','closed')",
                            (c["id"], *keys))
            con.execute("UPDATE companies SET checked_at=? WHERE id=?", (db.now(), c["id"]))
    print(f"Job boards: {len(comps)} companies, {total} open jobs, {new} new.")

    jt, region = s.get("jobtech", {}), regions.resolve(cfg)
    if region["jobtech"]:
        jn = jt_total = 0
        # A region preset searches all of Sweden; "custom" keeps your own county list (e.g. ["01"] = Stockholm).
        counties = jt.get("regions") if region["name"] == "custom" else []
        for q in jt.get("queries", []):
            jobs = jobtech(q, counties, jt.get("limit_per_query", 100), s.get("max_age_days", 30))
            jt_total += len(jobs)
            for j in jobs:
                jn += db.upsert_job(con, j)
        print(f"Platsbanken (JobTech): {jt_total} hits, {jn} new.")

    if s.get("hn", {}).get("enabled", True):
        jobs = hn_hiring(s.get("hn", {}).get("months", 1))
        hn_new = sum(db.upsert_job(con, j) for j in jobs)
        if jobs:  # posts from older threads, or deleted ones, are closed
            q = ",".join("?" * len(jobs))
            con.execute(f"UPDATE jobs SET status='closed' WHERE source='hn' AND key NOT IN ({q}) AND status NOT IN ('sent','closed')",
                        [j["key"] for j in jobs])
        print(f"Hacker News 'Who is hiring': {len(jobs)} posts, {hn_new} new.")

    an = s.get("arbeitnow", {})
    if an.get("enabled", True) and region["name"] != "asia":
        jobs = arbeitnow(an.get("pages", 3))
        an_new = sum(db.upsert_job(con, j) for j in jobs)
        print(f"Arbeitnow (Europe): {len(jobs)} jobs, {an_new} new.")
    con.commit()


def cmd_web(con, cfg, a):
    """Claude searches the open web for postings the boards above miss (search results only; LinkedIn never opened)."""
    found, new = websearch.search_jobs(con, cfg)
    print(f"Web search (Claude): {found} postings, {new} new.")


def cmd_funding(con, cfg, a):
    """Companies in your region that just raised money; Lavoro adds their job boards. Weekly."""
    found, boards = websearch.find_raises(con, cfg, force=getattr(a, "force", False))
    print(f"Recently funded: {found} companies, {boards} with a job board." if found else
          "Recently funded: checked this week already (or nothing found).")


def cmd_describe(con, cfg, a):
    """One line about each hiring company that has none, from its job board, website or Wikipedia."""
    from . import describe
    print(f"Described {describe.describe_companies(con, getattr(a, 'limit', 400) or 400)} companies.")


def cmd_legal(con, cfg, a):
    """Write the terms and privacy page to docs/legal.html, for GitHub Pages."""
    from . import legal
    from .config import ROOT
    print(f"Wrote {legal.write_docs(ROOT)}")


def cmd_match(con, cfg, a):
    n = match.apply_filter(con, cfg)
    print(f"{n} new jobs passed the title/location filter.")
    print(f"  AI: {llm.describe()}")
    print(f"Scored {match.score_jobs(con, cfg)} jobs.")
    explained = match.explain_jobs(con, cfg)
    if explained:
        print(f"Split the fit note into what fits and what is missing for {explained} jobs scored earlier.")


def cmd_ai_check(con, cfg, a):
    """One tiny call to confirm Claude works with the current settings."""
    print(f"AI: {llm.describe()}")
    if not llm.backend():
        return
    try:
        r = llm.parse(effort="low", system="Answer the question.", user="Reply with ok=true and the word 'ready'.",
                      schema=match.AiCheck)
    except RuntimeError as e:
        print(f"Claude call failed: {e}")
        return
    print("Claude answered:", r.model_dump() if r else "nothing (see message above)")


def cmd_contacts(con, cfg, a):
    print(f"Found contacts for {contacts.find_contacts(con, cfg)} jobs.")


def cmd_draft(con, cfg, a):
    svc = None
    if cfg.get("email", {}).get("gmail_drafts"):
        try:
            from .gmail import service
            svc = service()
        except Exception as e:
            print(f"  ! Gmail not available ({e}); drafts stay in the digest only.")
    print(f"Wrote {draft.write_drafts(con, cfg, svc)} email drafts.")


def cmd_digest(con, cfg, a):
    path = digest.build(con, cfg)
    print(f"Digest: {path}")
    if a.open:
        import webbrowser
        webbrowser.open(f"file:///{path}")


def cmd_run(con, cfg, a):
    try:
        lock = db.RunLock().__enter__()
    except RuntimeError as e:
        print(e)
        sys.exit(2)
    try:
        if getattr(a, "region", None):
            cfg.setdefault("search", {})["region"] = a.region
        print(f"Region: {regions.LABELS[regions.current(cfg)]}", flush=True)
        since = db.now()
        stamp = db.DB_PATH.parent / "last_discover.txt"
        days = cfg.get("search", {}).get("yc", {}).get("refresh_days", 7)
        stale = not stamp.exists() or (time.time() - stamp.stat().st_mtime) > days * 86400
        if a.discover or (days and stale and not getattr(a, "no_refresh", False)):
            print("\n== companies ==", flush=True)
            cmd_seed_yc(con, cfg, a)
            if cfg.get("search", {}).get("startups", {}).get("enabled", True):
                cmd_seed_startups(con, cfg, a)
            cmd_detect(con, cfg, a)
            cmd_describe(con, cfg, a)
            stamp.write_text(db.now(), encoding="utf-8")
        for step in (cmd_fetch, cmd_web, cmd_funding, cmd_match, cmd_contacts, cmd_draft, cmd_digest):
            print(f"\n== {step.__name__.removeprefix('cmd_')} ==", flush=True)
            step(con, cfg, a)
        try:  # logos for companies seen for the first time; a failure here never stops the run
            from . import logos
            found, _, _ = logos.fetch_all(con)
            if found:
                print(f"\nLogos: {found} new.", flush=True)
        except Exception as ex:  # noqa: BLE001
            print(f"\nLogos skipped: {ex}", flush=True)
        from . import notify
        print(notify.after_run(con, cfg, since), flush=True)
    finally:
        lock.__exit__(None, None, None)


def cmd_notify(con, cfg, a):
    """Show the desktop notification now (with --test, a sample one), to check it works on this computer."""
    from . import notify
    if a.test:
        notify.start_site()
        print("Shown." if notify.show("Lavoro", "This is how the morning note looks. Click to open Lavoro.")
              else "This system could not show a notification.")
        return
    text = notify.summary(con, cfg, "1970-01-01") or "Nothing new right now."
    print(text, "(shown)" if notify.show("Lavoro", text) else "(could not show it)")


def cmd_list(con, cfg, a):
    rows = con.execute("SELECT key, score, title, company, location, status FROM jobs WHERE score >= ? ORDER BY score DESC, first_seen DESC LIMIT ?",
                       (a.min_score, a.limit)).fetchall()
    for r in rows:
        print(f"{r['score']:>4}  {r['status']:<10} {r['title']} — {r['company']} ({r['location']})\n      {r['key']}")


def cmd_export(con, cfg, a):
    """Save the full description of matching roles to a Word file."""
    from . import export
    path, n = export.save(con, a.words, a.out, a.closed)
    print(f"Saved {n} roles to {path.resolve()}" if path else "No saved roles match those words.")


def cmd_logos(con, cfg, a):
    """Fetch company logos from each company's own website into data/logos/."""
    from . import logos
    found, missed, had = logos.fetch_all(con, everyone=a.all, force=a.force)
    print(f"Logos: {found} found, {missed} with none to use, {had} already done.")


def cmd_mark(con, cfg, a):
    cur = con.execute("UPDATE jobs SET status=? WHERE key=?", (a.status, a.key))
    con.commit()
    print("Updated." if cur.rowcount else "No job with that key.")


def cmd_serve(con, cfg, a):
    from .server import serve
    con.close()
    serve(cfg, a.port, a.open)


def cmd_region(con, cfg, a):
    """Show or set the search region in config.yaml."""
    if not a.name:
        print(f"Region: {regions.LABELS[regions.current(cfg)]}. Choices: {', '.join(regions.LABELS)}")
        return
    from .onboard import set_region
    reopened = set_region(con, a.name)
    print(f"Region set to {regions.LABELS[a.name]}. {reopened} earlier jobs will be checked again on the next run.")


def cmd_stats(con, cfg, a):
    for label, q in [
        ("companies", "SELECT count(*) FROM companies"),
        ("companies with a job board", "SELECT count(*) FROM companies WHERE ats IS NOT NULL AND ats<>'none'"),
        ("companies not checked yet", "SELECT count(*) FROM companies WHERE ats IS NULL"),
        ("jobs open", "SELECT count(*) FROM jobs WHERE status<>'closed'"),
        ("jobs passed filter", "SELECT count(*) FROM jobs WHERE passed_filter=1"),
        ("jobs scored", "SELECT count(*) FROM jobs WHERE score IS NOT NULL"),
        ("contacts", "SELECT count(*) FROM contacts"),
        ("drafts", "SELECT count(*) FROM drafts"),
    ]:
        print(f"{label:<30}{con.execute(q).fetchone()[0]}")
    for r in con.execute("SELECT ats, count(*) n FROM companies GROUP BY ats ORDER BY n DESC"):
        print(f"   board {r['ats'] or 'unchecked':<16}{r['n']}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="lavoro", description="Find startup jobs and the person to email.")
    ap.add_argument("--config", help="path to config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed-yc", help="add YC companies that are hiring in your regions")
    sub.add_parser("seed-startups", help="add the bundled list of about 6,800 startups that are hiring, with their job boards")
    p = sub.add_parser("detect", help="find the job board (ATS) for companies without one"); p.add_argument("--limit", type=int, default=200)
    p = sub.add_parser("add", help="add a company by name, website or careers URL"); p.add_argument("url", metavar="name_or_url"); p.add_argument("--name")
    p = sub.add_parser("probe", help="guess a company's job board from its name"); p.add_argument("names", nargs="+"); p.add_argument("--domain")
    sub.add_parser("fetch", help="pull jobs from all boards + Platsbanken")
    sub.add_parser("web", help="Claude web search for postings the job boards miss")
    p = sub.add_parser("funding", help="find companies that just raised money, and their job boards"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("describe", help="add a one-line description to hiring companies that have none")
    p.add_argument("--limit", type=int, default=400)
    sub.add_parser("match", help="filter and score new jobs")
    sub.add_parser("contacts", help="find the hiring person for top jobs")
    sub.add_parser("draft", help="write emails for top jobs")
    p = sub.add_parser("digest", help="build the HTML digest"); p.add_argument("--open", action="store_true")
    p = sub.add_parser("run", help="fetch → match → contacts → draft → digest")
    p.add_argument("--discover", action="store_true", help="also re-seed YC and the bundled startup list and detect boards first")
    p.add_argument("--region", choices=list(regions.LABELS), help="search this region for this run only")
    p.add_argument("--no-refresh", action="store_true", help="skip the weekly company-list refresh")
    p.add_argument("--limit", type=int, default=200); p.add_argument("--open", action="store_true")
    p = sub.add_parser("list", help="list scored jobs"); p.add_argument("--min-score", type=float, default=0); p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("export", help="save the full description of matching roles to a Word file")
    p.add_argument("words", nargs="+", help="every word must appear in the company or title, e.g. volvo graduate program")
    p.add_argument("--out", help="file path (default: output/<words>-<date>.docx)")
    p.add_argument("--closed", action="store_true", help="also include roles whose ad has closed")
    p = sub.add_parser("logos", help="fetch company logos from each company's own website")
    p.add_argument("--all", action="store_true", help="every company, not only the ones hiring")
    p.add_argument("--force", action="store_true", help="look again, even for logos already saved")
    p = sub.add_parser("mark", help="set a job's status"); p.add_argument("key"); p.add_argument("status", choices=["sent", "skipped", "drafted", "scored"])
    sub.add_parser("stats", help="counts")
    p = sub.add_parser("notify", help="show the desktop notification now"); p.add_argument("--test", action="store_true")
    p = sub.add_parser("region", help="show or set the search region"); p.add_argument("name", nargs="?", choices=list(regions.LABELS))
    sub.add_parser("legal", help="write the terms and privacy page to docs/legal.html")
    sub.add_parser("ai-check", help="one tiny Claude call to confirm the AI backend works")
    p = sub.add_parser("serve", help="open the Lavoro site on http://127.0.0.1:8765 (this computer only)")
    p.add_argument("--port", type=int, default=8765); p.add_argument("--open", action="store_true")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    llm.configure(cfg)
    con = db.connect()
    globals()["cmd_" + a.cmd.replace("-", "_")](con, cfg, a)
