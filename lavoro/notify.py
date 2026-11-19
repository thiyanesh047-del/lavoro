"""After the morning run: a desktop notification saying what is new, which opens the Lavoro site when clicked.

Windows shows a toast (through PowerShell, no extra install); macOS and Linux show a plain notification.
So the click has somewhere to go, the site is started in the background first if it is not running.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from xml.sax.saxutils import escape

from .config import ROOT, min_score
from .tracker import due

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"
# Windows only shows toasts from a registered app; PowerShell's own id is always there.
PS_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def summary(con, cfg, since: str) -> str:
    """'2 new emails ready · 1 follow-up due · 3 new roles that fit', or '' when nothing is new."""
    drafts = con.execute("SELECT count(*) FROM drafts d JOIN jobs j ON j.key=d.job_key "
                         "WHERE d.created_at >= ? AND j.status='drafted'", (since,)).fetchone()[0]
    fits = con.execute("SELECT count(*) FROM jobs WHERE first_seen >= ? AND score >= ? "
                       "AND status NOT IN ('closed','skipped','duplicate')", (since, min_score(cfg))).fetchone()[0]
    follow = len(due(con))
    parts = []
    if drafts:
        parts.append(f"{drafts} new email{'s' if drafts != 1 else ''} ready")
    if follow:
        parts.append(f"{follow} follow-up{'s' if follow != 1 else ''} due")
    if fits:
        parts.append(f"{fits} new role{'s' if fits != 1 else ''} that fit")
    return " · ".join(parts)


def site_running(port: int = PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_site() -> None:
    """Start `python -m lavoro serve` in the background, with no window, if nothing answers on the port yet."""
    if site_running():
        return
    py = sys.executable
    kw: dict = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        py = pyw if os.path.exists(pyw) else py
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # detached, own group, no window
    else:
        kw["start_new_session"] = True
    subprocess.Popen([py, "-m", "lavoro", "serve", "--port", str(PORT)], **kw)


def show(title: str, text: str, url: str = URL) -> bool:
    """Show one notification. Returns False if this system has no way to show it."""
    try:
        if os.name == "nt":
            xml = (f'<toast activationType="protocol" launch="{escape(url)}"><visual><binding template="ToastGeneric">'
                   f'<text>{escape(title)}</text><text>{escape(text)}</text></binding></visual>'
                   f'<actions><action content="Open Lavoro" activationType="protocol" arguments="{escape(url)}"/></actions></toast>')
            script = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
                "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
                "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:LAVORO_TOAST);"
                "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:LAVORO_APP).Show($t)")
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                               text=True, timeout=30, env={**os.environ, "LAVORO_TOAST": xml, "LAVORO_APP": PS_APP_ID},
                               creationflags=0x08000000)
            return r.returncode == 0
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}"'], timeout=15)
            return True
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", title, f"{text}\n{url}"], timeout=15)
            return True
    except Exception:
        return False
    return False


def after_run(con, cfg, since: str) -> str:
    """Called at the end of `lavoro run`. Returns what it did, for the log."""
    n = cfg.get("notify", {}) or {}
    if not n.get("enabled", True):
        return "Notifications are off (notify.enabled)."
    if os.environ.get("LAVORO_FROM_SITE"):
        return "Started from the site, so no notification: the timeline shows it."
    text = summary(con, cfg, since)
    if not text:
        return "Nothing new to notify about."
    if n.get("start_site", True):
        start_site()
    ok = show("Lavoro", text)
    return f"Notification: {text}" if ok else f"Could not show a notification on this system ({text})."
