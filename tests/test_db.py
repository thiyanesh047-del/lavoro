import pytest

from lavoro import db

from .conftest import job


def test_upsert_job_new_then_seen_again(con):
    assert db.upsert_job(con, job("greenhouse:acme:1")) is True
    assert db.upsert_job(con, job("greenhouse:acme:1")) is False
    assert con.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_closed_job_that_reappears_is_new_again(con):
    db.upsert_job(con, job("greenhouse:acme:1"))
    con.execute("UPDATE jobs SET status='closed'")
    db.upsert_job(con, job("greenhouse:acme:1"))
    assert con.execute("SELECT status FROM jobs").fetchone()[0] == "new"


def test_dropped_description_comes_back_only_once_the_job_is_in_play(con):
    db.upsert_job(con, job("greenhouse:acme:1", description="full ad text"))
    con.execute("UPDATE jobs SET status='skipped', description=NULL")
    db.upsert_job(con, job("greenhouse:acme:1", description="full ad text"))
    assert con.execute("SELECT description FROM jobs").fetchone()[0] is None   # still skipped: stays small
    con.execute("UPDATE jobs SET status='new'")                                 # reopened, e.g. by refilter
    db.upsert_job(con, job("greenhouse:acme:1", description="full ad text"))
    assert con.execute("SELECT description FROM jobs").fetchone()[0] == "full ad text"


def test_existing_description_is_kept(con):
    db.upsert_job(con, job("greenhouse:acme:1", description="first"))
    db.upsert_job(con, job("greenhouse:acme:1", description="second"))
    assert con.execute("SELECT description FROM jobs").fetchone()[0] == "first"


def test_upsert_company_merges_by_board_domain_and_name(con):
    a = db.upsert_company(con, name="Acme", ats="greenhouse", slug="acme")
    assert db.upsert_company(con, name="Acme AB", ats="greenhouse", slug="acme") == a
    b = db.upsert_company(con, name="Beta", domain="beta.com")
    assert db.upsert_company(con, name="Beta Inc", domain="beta.com", ats="lever", slug="beta") == b
    assert con.execute("SELECT ats FROM companies WHERE id=?", (b,)).fetchone()[0] == "lever"
    assert db.upsert_company(con, name="acme") == a


def test_run_lock_allows_one_run(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "lavoro.db")
    with db.RunLock():
        with pytest.raises(RuntimeError):
            db.RunLock().__enter__()
    with db.RunLock():  # released when the first run ended
        pass
