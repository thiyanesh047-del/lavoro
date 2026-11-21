from datetime import datetime, timedelta, timezone

from lavoro.match import _has_any, passes_filter

S = {"titles_include": ["product designer", "ux designer"], "titles_exclude": ["senior", "lead"],
     "companies_exclude": ["randstad"], "remote_ok": True, "max_age_days": 30, "board_max_age_days": 0}
REGION = {"places": ["stockholm", "sweden"], "remote": ["europe", "emea"], "any_place": False}


def j(**kw):
    base = {"title": "Product Designer", "company": "Acme", "location": "Stockholm", "remote": 0,
            "source": "greenhouse", "posted_at": None}
    return {**base, **kw}


def test_has_any_matches_whole_words_and_hyphens():
    assert _has_any("UX-designer till Volvo", ["ux designer"])
    assert _has_any("Senior Product Designer", ["senior"])
    assert not _has_any("Seniority-free designer", ["senior"])
    assert not _has_any("Leadership trainee", ["lead"])


def test_title_include_and_exclude():
    assert passes_filter(j(), S, REGION)
    assert not passes_filter(j(title="Backend Engineer"), S, REGION)
    assert not passes_filter(j(title="Senior Product Designer"), S, REGION)
    assert not passes_filter(j(title="Lead UX Designer"), S, REGION)


def test_company_exclude():
    assert not passes_filter(j(company="Randstad Sverige"), S, REGION)


def test_location_and_remote():
    assert not passes_filter(j(location="Berlin, Germany"), S, REGION)
    assert passes_filter(j(location="Remote"), S, REGION)                 # remote, no region named
    assert passes_filter(j(location="Remote - EMEA"), S, REGION)          # remote in an accepted region
    assert not passes_filter(j(location="Remote - US"), S, REGION)        # remote somewhere else
    assert passes_filter(j(location="Berlin", remote=1), S, {**REGION, "any_place": True})


def test_age_limit_only_for_aggregators():
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    assert not passes_filter(j(source="jobtech", posted_at=old), S, REGION)
    assert passes_filter(j(source="greenhouse", posted_at=old), S, REGION)  # still on the company's own board
    assert not passes_filter(j(source="greenhouse", posted_at=old), {**S, "board_max_age_days": 30}, REGION)
