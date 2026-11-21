"""Board feed parsers, fed saved-shape answers instead of the network."""
from lavoro import sources


def test_greenhouse(monkeypatch):
    feed = {"jobs": [{"id": 7, "title": "UX Designer", "location": {"name": "Stockholm (Remote)"},
                      "departments": [{"name": "Design"}], "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
                      "content": "&lt;p&gt;Design &lt;b&gt;things&lt;/b&gt;&lt;/p&gt;", "first_published": "2026-11-01T10:00:00Z"}]}
    monkeypatch.setattr(sources, "get_json", lambda url, **kw: feed)
    [j] = sources.greenhouse("acme", "Acme")
    assert j["key"] == "greenhouse:acme:7" and j["company"] == "Acme" and j["title"] == "UX Designer"
    assert j["remote"] is True and j["department"] == "Design"
    assert "Design" in j["description"] and "<" not in j["description"]
    assert j["posted_at"] == "2026-11-01T10:00:00Z"


def test_greenhouse_missing_board(monkeypatch):
    monkeypatch.setattr(sources, "get_json", lambda url, **kw: None)
    assert sources.greenhouse("nope", "Nope") == []


def test_lever_falls_back_to_eu_and_reads_salary(monkeypatch):
    post = {"id": "abc", "text": "Product Designer", "categories": {"location": "Remote", "team": "Design"},
            "workplaceType": "remote", "hostedUrl": "https://jobs.lever.co/acme/abc", "descriptionPlain": "About the role",
            "lists": [{"text": "You have", "content": "<li>Figma</li>"}], "additionalPlain": "",
            "salaryRange": {"min": 40000, "max": 50000, "currency": "EUR", "interval": "per-year-salary"},
            "createdAt": 1767225600000}
    urls = []

    def fake(url, **kw):
        urls.append(url)
        return [] if "api.lever.co" in url else [post]
    monkeypatch.setattr(sources, "get_json", fake)
    [j] = sources.lever("acme", "Acme")
    assert "api.eu.lever.co" in urls[-1]
    assert j["key"] == "lever:acme:abc" and j["remote"] is True and j["department"] == "Design"
    assert "Figma" in j["description"] and j["salary"] and "EUR" in j["salary"]
    assert j["posted_at"].startswith("2026-01-01")
