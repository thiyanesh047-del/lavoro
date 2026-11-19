"""Region presets for the search: which places count as "in the region", and which remote wording counts.

Set `search.region` in config.yaml to one of the keys below. `custom` uses your own `locations_include` and
`remote_regions` lists instead. A one-off run can override it: `python -m lavoro run --region europe`.
"""
from __future__ import annotations

_SWEDEN = ["sweden", "sverige", "stockholm", "solna", "sundbyberg", "kista", "göteborg", "gothenburg", "malmö", "malmo",
           "uppsala", "lund", "linköping", "linkoping", "västerås", "örebro", "umeå", "helsingborg", "jönköping", "norrköping",
           "luleå", "nacka", "danderyd", "södertälje", "stockholms län", "västra götaland", "skåne"]
_NORDICS = _SWEDEN + ["norway", "norge", "oslo", "bergen", "trondheim", "denmark", "danmark", "copenhagen", "københavn",
                      "aarhus", "finland", "suomi", "helsinki", "espoo", "tampere", "iceland", "reykjavik", "nordic", "nordics",
                      "scandinavia"]
_EUROPE = _NORDICS + [
    "europe", "united kingdom", "uk", "england", "scotland", "london", "manchester", "edinburgh", "cambridge", "oxford",
    "ireland", "dublin", "germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln",
    "netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague", "belgium", "brussels", "antwerp", "ghent",
    "france", "paris", "lyon", "toulouse", "nantes", "spain", "madrid", "barcelona", "valencia", "portugal", "lisbon", "porto",
    "italy", "milan", "milano", "rome", "roma", "turin", "bologna", "switzerland", "zurich", "zürich", "geneva", "lausanne",
    "austria", "vienna", "wien", "poland", "warsaw", "kraków", "krakow", "wrocław", "czech", "prague", "praha", "estonia",
    "tallinn", "latvia", "riga", "lithuania", "vilnius", "hungary", "budapest", "romania", "bucharest", "greece", "athens",
    "croatia", "zagreb", "serbia", "belgrade", "bulgaria", "sofia", "slovenia", "ljubljana", "slovakia", "bratislava",
    "luxembourg", "malta", "cyprus", "ukraine", "kyiv",
    # local spellings that job feeds use
    "nederland", "schweiz", "suisse", "svizzera", "österreich", "españa", "italia", "polska", "belgique", "belgië", "česko",
    "düsseldorf", "stuttgart", "leipzig", "dresden", "hannover", "nürnberg", "nuremberg", "bremen", "essen", "dortmund",
    "mannheim", "karlsruhe", "bonn", "münster", "freiburg", "heidelberg", "potsdam", "basel", "bern", "graz", "salzburg",
    "linz", "innsbruck", "marseille", "lille", "bordeaux", "nice", "strasbourg", "montpellier", "rennes", "seville", "bilbao",
    "malaga", "naples", "florence", "gdansk", "poznan", "brno", "cluj", "iasi", "timisoara", "thessaloniki", "galway", "cork",
    "belfast", "bristol", "leeds", "birmingham", "glasgow", "brighton", "liverpool", "newcastle", "nottingham", "sheffield",
    "reading", "oxfordshire", "cambridgeshire", "aberdeen", "cardiff"]

_ASIA = [
    "asia", "apac", "asia-pacific", "asia pacific",
    # South Asia
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida", "hyderabad",
    "chennai", "pune", "kolkata", "ahmedabad", "kochi", "coimbatore", "jaipur", "chandigarh", "indore", "pakistan",
    "karachi", "lahore", "islamabad", "bangladesh", "dhaka", "sri lanka", "colombo", "nepal", "kathmandu",
    # Southeast Asia
    "singapore", "malaysia", "kuala lumpur", "indonesia", "jakarta", "bali", "thailand", "bangkok", "vietnam", "viet nam",
    "ho chi minh", "hanoi", "philippines", "manila", "cebu", "cambodia", "phnom penh", "myanmar",
    # East Asia
    "japan", "tokyo", "osaka", "kyoto", "south korea", "korea", "seoul", "busan", "china", "beijing", "shanghai", "shenzhen",
    "hangzhou", "guangzhou", "hong kong", "taiwan", "taipei", "mongolia",
    # West Asia / Middle East
    "united arab emirates", "uae", "dubai", "abu dhabi", "saudi arabia", "riyadh", "jeddah", "qatar", "doha", "bahrain",
    "kuwait", "oman", "israel", "tel aviv", "jerusalem", "haifa", "jordan", "amman", "turkey", "türkiye", "istanbul", "ankara"]

REGIONS: dict[str, dict] = {
    "sweden": {"label": "Sweden", "places": _SWEDEN,
               "remote": ["sweden", "nordic", "nordics", "scandinavia", "europe", "emea", "eu", "cet", "worldwide", "anywhere", "global"],
               "jobtech": True, "yc": ["Sweden", "Europe", "Fully Remote", "Remote"]},
    "nordics": {"label": "Nordics", "places": _NORDICS,
                "remote": ["nordic", "nordics", "scandinavia", "europe", "emea", "eu", "cet", "worldwide", "anywhere", "global"],
                "jobtech": True, "yc": ["Europe", "Fully Remote", "Remote"]},
    "europe": {"label": "Europe", "places": _EUROPE,
               "remote": ["europe", "emea", "eu", "cet", "uk", "worldwide", "anywhere", "global"],
               "jobtech": True, "yc": ["Europe", "United Kingdom", "Fully Remote", "Remote"]},
    "asia": {"label": "Asia", "places": _ASIA,
             "remote": ["asia", "apac", "asia-pacific", "india", "ist", "sgt", "jst", "gmt+5", "gmt+8", "utc+5", "utc+8",
                        "worldwide", "anywhere", "global"],
             "jobtech": False, "yc": ["India", "South Asia", "Southeast Asia", "East Asia", "Singapore", "Indonesia", "Vietnam",
                                     "Malaysia", "Hong Kong", "United Arab Emirates", "Israel", "Middle East and North Africa",
                                     "Fully Remote", "Remote"]},
    "worldwide": {"label": "Worldwide", "places": None, "remote": None, "jobtech": True, "yc": []},
}
LABELS = {"custom": "My own list", **{k: v["label"] for k, v in REGIONS.items()}}


def current(cfg: dict) -> str:
    r = (cfg.get("search", {}).get("region") or "custom").lower()
    return r if r in REGIONS or r == "custom" else "custom"


def resolve(cfg: dict) -> dict:
    """The places / remote words / sources to use, after applying the region preset."""
    s = cfg.get("search", {})
    name = current(cfg)
    if name == "custom":
        return {"name": name, "places": s.get("locations_include") or [], "remote": s.get("remote_regions") or [],
                "any_place": False, "jobtech": bool(s.get("jobtech", {}).get("enabled")),
                "yc": s.get("yc", {}).get("regions") or []}
    r = REGIONS[name]
    return {"name": name, "places": r["places"] or [], "remote": r["remote"] or [], "any_place": r["places"] is None,
            "jobtech": r["jobtech"] and bool(s.get("jobtech", {}).get("enabled", True)), "yc": r["yc"]}
