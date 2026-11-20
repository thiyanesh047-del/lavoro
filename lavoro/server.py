"""`python -m lavoro serve` — the Lavoro site on http://127.0.0.1:8765, on your own computer only.

GET  /                       today's list, or the welcome screen if no profile has been set up yet
GET  /welcome                the welcome screen (set up again)
GET  /jobs                   every open job: ?q= &where= &cat= &remote=1 &pay=1 &page=
GET  /companies              every tracked company: ?q= &hiring=1 &board=1 &sort=az &page=
GET  /companies/<id>         one company: facts, links and its open roles
GET  /roles, /roles/<slug>   role insights: pay, skills asked for, offers, who is hiring
GET  /assets/<f>             images and fonts
GET  /api/status             whether a run is going, and its current step
POST /api/profile/upload     {"name": "cv.pdf", "data": "<base64>"}  → builds profile.md from a CV
POST /api/profile/link       {"url": "https://..."}                   → builds profile.md from a portfolio site
POST /api/preferences        {"titles": [...], "locations": [...], ...} → saves search settings to config.yaml
GET  /tracker, /tracker.csv   the pipeline tracker, and its CSV download
GET  /profile                your profile, what Lavoro searches for, and a way to build the profile again
POST /api/pipeline           {"track": key} | {"add": true, company, title, url} | {"id", "field", "value"} | {"id", "remove": true}
POST /api/write              {"id", "kind": "kit" | "followup"} Claude writes an application kit or a follow-up
POST /api/mark               {"key": ..., "status": "sent" | "skipped" | "drafted"}
POST /api/company            {"text"} add a company by name or link, fetch its roles
POST /api/run               {"discover": bool} start the pipeline in the background
"""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from . import browse, db, digest, llm, onboard, roles, welcome
from .config import ROOT, load_config, output_dir

ALLOWED_STATUS = {"sent", "skipped", "drafted"}
MAX_BODY = 22 * 1024 * 1024  # a 15 MB CV is ~20 MB as base64
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/webp", ".webp")
STEP_LABEL = {"companies": "Finding companies", "fetch": "Fetching jobs", "web": "Searching the web",
              "funding": "Checking who just raised", "match": "Scoring roles",
              "contacts": "Finding people", "draft": "Writing emails", "digest": "Finishing"}
_run = {"running": False, "step": "", "ok": True, "last": "", "started": None, "finished": None}
_lock = threading.Lock()
_profile_busy = threading.Lock()


def _run_pipeline(cfg, discover: bool):
    log = output_dir(cfg) / "run.log"
    try:
        # live progress lines; LAVORO_FROM_SITE: the timeline shows the result, so no desktop notification
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "LAVORO_FROM_SITE": "1"}
        cmd = [sys.executable, "-m", "lavoro", "run"] + (["--discover", "--limit", "1000"] if discover else [])
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, env=env,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        with open(log, "a", encoding="utf-8") as f:
            for line in p.stdout:
                f.write(line)
                s = line.strip()
                if s.startswith("== ") and s.endswith(" =="):
                    name = s.strip("= ")
                    _run["step"] = STEP_LABEL.get(name, name)
                elif s:
                    _run["last"] = s[:200]
        _run["ok"] = p.wait() == 0
    except Exception as e:  # keep the server alive whatever happens
        _run["ok"], _run["last"] = False, str(e)
    finally:
        _run["running"], _run["finished"] = False, db.now()


def _companies_with_boards() -> int:
    con = db.connect()
    try:
        return con.execute("SELECT count(*) FROM companies WHERE ats IS NOT NULL AND ats<>'none'").fetchone()[0]
    finally:
        con.close()


def _draft_payload(d: onboard.ProfileDraft) -> dict:
    return {"ok": True, **d.model_dump()}


def make_handler(port: int):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Lavoro"

        def log_message(self, fmt, *args):  # quiet console
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", cache=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _local_only(self) -> bool:
            # Refuse requests whose Host/Origin is not this machine (protects against DNS rebinding and other sites).
            if self.headers.get("Host") not in hosts:
                self._json(403, {"error": "local access only"})
                return False
            origin = self.headers.get("Origin")
            if self.command == "POST" and origin and origin.split("://", 1)[-1] not in hosts:
                self._json(403, {"error": "bad origin"})
                return False
            return True

        def _cfg(self):
            cfg = load_config()
            llm.configure(cfg)
            return cfg

        # ------------------------------------------------------------ GET
        def do_GET(self):
            if not self._local_only():
                return
            path = urlparse(self.path).path
            if path in ("/", "/index.html", "/welcome"):
                cfg = self._cfg()
                if path == "/welcome" or onboard.needs_setup(cfg):
                    page = welcome.render(cfg)
                else:
                    con = db.connect()
                    try:
                        page = digest.render(con, cfg, live=True)
                    finally:
                        con.close()
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/roles/go":  # the role search box: /roles/go?role=Product Designer → /roles/product-designer
                role = (parse_qs(urlparse(self.path).query).get("role") or [""])[0]
                self.send_response(302)
                self.send_header("Location", f"/roles/{roles.slugify(role)}" if role.strip() else "/roles")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/roles" or re.fullmatch(r"/roles/[^/]+", path):
                con = db.connect()
                try:
                    page = roles.render_index(con) if path == "/roles" else roles.render_role(con, unquote(path.split("/", 2)[2]))
                finally:
                    con.close()
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/pay" or re.fullmatch(r"/companies/\d+/pay", path):
                from . import company
                con = db.connect()
                try:
                    page = (company.render_pay_index(con) if path == "/pay"
                            else company.render_company_pay(con, int(path.split("/")[2])))
                finally:
                    con.close()
                if page is None:
                    return self._send(404, b"<h1>No such company</h1><p><a href='/companies'>All companies</a></p>",
                                      "text/html; charset=utf-8")
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path in ("/jobs", "/companies") or re.fullmatch(r"/companies/\d+", path):
                params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                con = db.connect()
                try:
                    if path == "/jobs":
                        page = browse.render_jobs(con, params)
                    elif path == "/companies":
                        page = browse.render_companies(con, params)
                    else:
                        page = browse.render_company(con, int(path.rsplit("/", 1)[1]))
                finally:
                    con.close()
                if page is None:
                    return self._send(404, b"<h1>No such company</h1><p><a href='/companies'>All companies</a></p>",
                                      "text/html; charset=utf-8")
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if re.fullmatch(r"/tracker/\d+", path):
                from . import tracker
                con = db.connect()
                try:
                    page = tracker.render_row(con, self._cfg(), int(path.rsplit("/", 1)[1]))
                finally:
                    con.close()
                if page is None:
                    return self._send(404, b"<h1>Not in your tracker</h1><p><a href='/tracker'>Tracker</a></p>",
                                      "text/html; charset=utf-8")
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path in ("/tracker", "/tracker.csv"):
                from . import tracker
                con = db.connect()
                try:
                    if path == "/tracker.csv":
                        body = tracker.to_csv(con)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/csv; charset=utf-8")
                        self.send_header("Content-Disposition", 'attachment; filename="lavoro-tracker.csv"')
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    page = tracker.render(con, self._cfg())
                finally:
                    con.close()
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/profile":  # your profile and what Lavoro searches for
                from . import profilepage
                return self._send(200, profilepage.render(self._cfg()).encode("utf-8"), "text/html; charset=utf-8")
            if path in ("/terms", "/privacy"):  # short links to the matching part of /legal
                self.send_response(302)
                self.send_header("Location", "/legal" + ("#privacy" if path == "/privacy" else ""))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/legal":
                from . import legal
                return self._send(200, legal.render().encode("utf-8"), "text/html; charset=utf-8")
            if re.fullmatch(r"/logo/\d+", path):  # a company's logo, fetched once and kept in data/logos/
                from . import logos
                cid = int(path.rsplit("/", 1)[1])
                f = logos.path(cid)
                if f is None and logos.state(cid) == "unknown":
                    con = db.connect()
                    try:
                        f = logos.fetch(con, cid)
                    finally:
                        con.close()
                if f is None:
                    return self._send(404, b"", "text/plain")
                self.send_response(200)
                self.send_header("Content-Type", logos.TYPES[f.suffix[1:]])
                self.send_header("Content-Length", str(f.stat().st_size))
                self.send_header("Cache-Control", "max-age=604800")
                # An SVG opened on its own must not run scripts on this site.
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(f.read_bytes())
                return
            if path.startswith("/assets/"):
                f = (digest.STATIC / path.removeprefix("/assets/")).resolve()
                if f.parent == digest.STATIC and f.is_file():
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream", cache=True)
                return self._json(404, {"error": "not found"})
            if path == "/api/status":
                return self._json(200, _run)
            if path == "/api/timeline":
                from . import timeline
                return self._json(200, {**_run, **timeline.data(self._cfg(), _run["started"])})
            if path == "/favicon.ico":
                return self._send(204, b"")
            self._json(404, {"error": "not found"})

        # ------------------------------------------------------------ POST
        def do_POST(self):
            if not self._local_only():
                return
            path = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._json(413, {"error": "That file is too large (max 15 MB)."})
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "bad JSON"})

            if path in ("/api/profile/upload", "/api/profile/link"):
                if not _profile_busy.acquire(blocking=False):
                    return self._json(409, {"error": "Already reading a profile. Give it a moment."})
                try:
                    self._cfg()
                    if path.endswith("upload"):
                        try:
                            data = base64.b64decode(str(body.get("data", "")), validate=True)
                        except (binascii.Error, ValueError):
                            return self._json(400, {"error": "The file didn't arrive intact. Try again."})
                        saved = onboard.save_upload(str(body.get("name", "cv")), data)
                        draft = onboard.build_profile(path=saved)
                        onboard.save_profile(draft.markdown, f"your CV ({saved.name})")
                    else:
                        url = str(body.get("url", "")).strip()
                        draft = onboard.build_profile(url=url)
                        onboard.save_profile(draft.markdown, f"your site {url}")
                    return self._json(200, _draft_payload(draft))
                except onboard.SetupError as e:
                    return self._json(422, {"error": str(e)})
                except Exception as e:  # unexpected: say so plainly, keep the server up
                    return self._json(500, {"error": f"Something went wrong reading that: {e}"})
                finally:
                    _profile_busy.release()

            if path == "/api/preferences":
                try:
                    onboard.save_preferences(onboard.Preferences(**body))
                except ValidationError:
                    return self._json(400, {"error": "Some fields were not filled in correctly."})
                except onboard.SetupError as e:
                    return self._json(422, {"error": str(e)})
                return self._json(200, {"ok": True, "companies": _companies_with_boards()})

            if path == "/api/star":
                try:
                    cid, on = int(body.get("id")), bool(body.get("on"))
                except (TypeError, ValueError):
                    return self._json(400, {"error": "id must be a number"})
                con = db.connect()
                try:
                    cur = con.execute("UPDATE companies SET starred=? WHERE id=?", (int(on), cid))
                    con.commit()
                finally:
                    con.close()
                return self._json(200 if cur.rowcount else 404, {"ok": bool(cur.rowcount), "on": on})

            if path == "/api/region":
                from . import regions
                name = str(body.get("region", ""))
                con = db.connect()
                try:
                    reopened = onboard.set_region(con, name)
                except onboard.SetupError as e:
                    return self._json(422, {"error": str(e)})
                finally:
                    con.close()
                return self._json(200, {"ok": True, "label": regions.LABELS[name], "reopened": reopened})

            if path == "/api/mark":
                key, status = str(body.get("key", "")), body.get("status")
                if status not in ALLOWED_STATUS:
                    return self._json(400, {"error": "status must be sent, skipped or drafted"})
                con = db.connect()
                try:
                    cur = con.execute("UPDATE jobs SET status=? WHERE key=?", (status, key))
                    con.commit()
                    if status == "sent" and cur.rowcount:
                        from . import tracker
                        tracker.on_sent(con, key)  # an email you sent goes on the tracker, follow up in a week
                finally:
                    con.close()
                return self._json(200 if cur.rowcount else 404, {"ok": bool(cur.rowcount)})

            if path == "/api/write":
                from . import apply
                kind = body.get("kind")
                if kind not in ("kit", "followup"):
                    return self._json(400, {"error": "kind must be kit or followup"})
                cfg = self._cfg()
                con = db.connect()
                try:
                    rid = int(body.get("id"))
                    data = (apply.make_kit if kind == "kit" else apply.make_followup)(con, cfg, rid)
                    return self._json(200, {"ok": True, kind: data})
                except KeyError:
                    return self._json(404, {"error": "Not in your tracker."})
                except (TypeError, ValueError):
                    return self._json(400, {"error": "id must be a number"})
                except RuntimeError as err:
                    return self._json(503, {"error": str(err)})
                finally:
                    con.close()

            if path == "/api/reach":  # find who hires for one role and draft an email; never sends
                from . import reach
                cfg = self._cfg()
                con = db.connect()
                try:
                    out = reach.reach(con, cfg, str(body.get("key", "")))
                    if not out.get("found") and body.get("team"):  # tell the page which role to try next
                        from .company import next_for_team
                        out |= next_for_team(con, str(body["key"]), str(body["team"])) or {}
                    return self._json(200, out)
                except KeyError:
                    return self._json(404, {"error": "That role is no longer in Lavoro."})
                except reach.ReachError as err:
                    return self._json(409, {"error": str(err)})
                except Exception as err:  # network or Claude trouble: say so plainly, keep the server up
                    return self._json(500, {"error": f"The lookup did not finish: {err}"})
                finally:
                    con.close()

            if path == "/api/pipeline":
                from . import tracker
                con = db.connect()
                try:
                    if body.get("track"):
                        return self._json(200, {"ok": True, "id": tracker.track(con, str(body["track"]))})
                    if body.get("add"):
                        return self._json(200, {"ok": True, "id": tracker.add_manual(
                            con, str(body.get("company", "")), str(body.get("title", "")), str(body.get("url", "")))})
                    rid = int(body.get("id"))
                    if body.get("remove"):
                        tracker.remove(con, rid)
                        return self._json(200, {"ok": True})
                    row = tracker.set_field(con, rid, str(body.get("field", "")), str(body.get("value", "")))
                    return self._json(200, {"ok": True, "row": row})
                except KeyError:
                    return self._json(404, {"error": "Not found."})
                except (TypeError, ValueError) as e:
                    return self._json(400, {"error": str(e) or "That value does not fit."})
                finally:
                    con.close()

            if path == "/api/company":
                from . import discover
                con = db.connect()
                try:
                    r = discover.add_company(con, str(body.get("text", "")))
                except discover.AddError as e:
                    return self._json(422, {"error": str(e)})
                except Exception as e:  # network trouble etc.: say so plainly, keep the server up
                    return self._json(500, {"error": f"Something went wrong looking that up: {e}"})
                finally:
                    con.close()
                return self._json(200, {"ok": True, **r})

            if path == "/api/run":
                cfg = self._cfg()
                discover = bool(body.get("discover")) or _companies_with_boards() == 0
                with _lock:
                    if _run["running"]:
                        return self._json(409, {"error": "A search is already running."})
                    _run.update(running=True, step="Starting", ok=True, last="", started=db.now(), finished=None)
                threading.Thread(target=_run_pipeline, args=(cfg, discover), daemon=True).start()
                return self._json(202, {"ok": True, "discover": discover})

            self._json(404, {"error": "not found"})

    return Handler


class _Server(ThreadingHTTPServer):
    # On Windows, address reuse lets a second copy bind the same port without an error, and the two then share the
    # requests. Refuse instead, so "already running" is said out loud.
    allow_reuse_address = os.name != "nt"


def serve(cfg, port: int = 8765, open_browser: bool = False):
    url = f"http://127.0.0.1:{port}/"
    try:
        httpd = _Server(("127.0.0.1", port), make_handler(port))
    except OSError:
        print(f"Port {port} is already in use. Lavoro's site is probably running already: open {url}\n"
              f"To run a second copy, pick another port: python -m lavoro serve --port {port + 1}")
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        return
    print(f"Lavoro is running at {url}  (only on this computer; Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
