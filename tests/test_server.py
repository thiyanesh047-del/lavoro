"""The local site refuses requests that do not come from this computer's own pages."""
import http.client
import json
import threading

import pytest

from lavoro import server


@pytest.fixture
def site():
    httpd = server._Server(("127.0.0.1", 0), server.make_handler(0))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = server.make_handler(port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    httpd.shutdown()
    httpd.server_close()


def _req(port, method, path, host=None, origin=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = c.getresponse()
    return r.status, r.read()


def test_status_from_this_computer(site):
    status, body = _req(site, "GET", "/api/status")
    assert status == 200 and "running" in json.loads(body)


def test_other_host_is_refused(site):
    # DNS rebinding: another name that points at 127.0.0.1
    assert _req(site, "GET", "/api/status", host="evil.example:80")[0] == 403


def test_post_from_another_site_is_refused(site):
    status, _ = _req(site, "POST", "/api/mark", origin="https://evil.example", body={"key": "x", "status": "sent"})
    assert status == 403


def test_bad_status_is_rejected(site):
    status, _ = _req(site, "POST", "/api/mark", origin=f"http://127.0.0.1:{site}", body={"key": "x", "status": "delete"})
    assert status == 400
