from lavoro import db
from lavoro.cli import boards_to_fetch

from .conftest import job


def _board(con, name, **kw):
    cid = db.upsert_company(con, name=name, ats="greenhouse", slug=name.lower(), source=kw.pop("source", "startups"))
    if kw.get("starred"):
        con.execute("UPDATE companies SET starred=1 WHERE id=?", (cid,))
    return cid


def _job(con, cid, n, passed=0):
    db.upsert_job(con, job(f"greenhouse:c{cid}:{n}", company_id=cid))
    con.execute("UPDATE jobs SET passed_filter=? WHERE key=?", (passed, f"greenhouse:c{cid}:{n}"))


def test_busy_boards_every_run_quiet_ones_in_turns(con):
    fits = _board(con, "Fits");          _job(con, fits, 1, passed=1)
    followed = _board(con, "Followed", starred=True); _job(con, followed, 1)
    mine = _board(con, "Mine", source="manual");      _job(con, mine, 1)
    empty = _board(con, "Empty")                       # never read, or no roles yet: read every run
    quiet = [_board(con, f"Quiet{i}") for i in range(9)]
    for q in quiet:
        _job(con, q, 1)

    seen = {q: 0 for q in quiet}
    for day in range(3):
        ids = {c["id"] for c in boards_to_fetch(con, every=3, day=day)[0]}
        assert {fits, followed, mine, empty} <= ids
        for q in quiet:
            seen[q] += q in ids
    assert all(n == 1 for n in seen.values())  # each quiet board exactly once in 3 days


def test_every_one_reads_all(con):
    for i in range(5):
        _job(con, _board(con, f"Q{i}"), 1)
    comps, total = boards_to_fetch(con, every=1)
    assert len(comps) == total == 5
