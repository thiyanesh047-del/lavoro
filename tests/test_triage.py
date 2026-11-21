"""The quick check and the full score, with Claude replaced by a stub."""
import pytest

from lavoro import db, llm, match

from .conftest import job

CFG = {"llm": {"triage": True, "triage_batch": 40, "max_jobs_to_triage_per_run": 600, "max_jobs_to_score_per_run": 40}}


@pytest.fixture
def stub(monkeypatch):
    calls = []
    monkeypatch.setattr(match, "has_claude", lambda: True)
    monkeypatch.setattr(match, "read_profile", lambda cfg: "Product designer in Stockholm.")
    llm._stop.clear()
    return calls


def _new(con, n, **kw):
    for i in range(1, n + 1):
        db.upsert_job(con, job(f"greenhouse:acme:{i}", title=f"Role {i}", **kw))
    con.execute("UPDATE jobs SET passed_filter=1")


def test_triage_drops_keeps_and_keeps_unanswered(con, stub, monkeypatch):
    _new(con, 3)

    def fake(**kw):
        stub.append(kw)
        return match.TriageBatch(jobs=[match.TriageItem(id=1, keep=True, reason="fits"),
                                       match.TriageItem(id=2, keep=False, reason="sales role")])  # id 3: no answer
    monkeypatch.setattr(llm, "parse", fake)
    rows = dict(con.execute("SELECT title, key FROM jobs").fetchall())
    # newest first decides the ids; read the verdict per job key instead of assuming an order
    assert match.triage_jobs(con, CFG) == (2, 1)
    assert len(stub) == 1 and "JOBS:" in stub[0]["user"]
    dropped = con.execute("SELECT score, status, score_reason FROM jobs WHERE triage='drop'").fetchall()
    assert len(dropped) == 1 and dropped[0]["score"] == 0 and dropped[0]["status"] == "scored"
    assert dropped[0]["score_reason"] == "Quick check: sales role."
    assert len(rows) == 3


def test_triage_failure_leaves_jobs_for_next_run(con, stub, monkeypatch):
    _new(con, 2)

    def boom(**kw):
        raise RuntimeError("network")
    monkeypatch.setattr(llm, "parse", boom)
    assert match.triage_jobs(con, CFG) == (0, 0)
    assert con.execute("SELECT count(*) FROM jobs WHERE triage IS NULL").fetchone()[0] == 2


def test_triage_off_without_claude(con, monkeypatch):
    monkeypatch.setattr(match, "has_claude", lambda: False)
    _new(con, 2)
    assert match.triage_jobs(con, CFG) == (0, 0)
    assert not match.triage_enabled({"llm": {"triage": False}})


def _score(**kw):
    return match.JobScore(score=7, reason="good", fits=["Figma"], missing=[], red_flags=[], hiring_team="Design",
                          language="en")


def test_full_score_only_for_kept_jobs(con, stub, monkeypatch):
    _new(con, 2)
    con.execute("UPDATE jobs SET triage='keep' WHERE key='greenhouse:acme:1'")
    monkeypatch.setattr(llm, "parse", lambda **kw: stub.append(kw) or _score())
    assert match.score_jobs(con, CFG) == 1
    assert con.execute("SELECT score FROM jobs WHERE key='greenhouse:acme:1'").fetchone()[0] == 7
    assert con.execute("SELECT score FROM jobs WHERE key='greenhouse:acme:2'").fetchone()[0] is None


def test_full_score_waits_for_dropped_ad_text(con, stub, monkeypatch):
    _new(con, 1)
    con.execute("UPDATE jobs SET triage='keep', description=NULL")
    monkeypatch.setattr(llm, "parse", lambda **kw: stub.append(kw) or _score())
    assert match.score_jobs(con, CFG) == 0 and not stub
    assert con.execute("SELECT status FROM jobs").fetchone()[0] == "new"
