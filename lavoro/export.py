"""Save job descriptions to a Word file (.docx), so you keep a copy after the ad comes down.

    python -m lavoro export volvo graduate program

Every word must appear in the company name or the job title. The same role posted on two
boards is kept once (the longer text wins). Uses only the standard library: a .docx is a
zip of a few XML files.
"""
from __future__ import annotations

import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def find(con, words: list[str], include_closed: bool = False) -> list[dict]:
    """Jobs whose company + title contain every word, one per role and town, newest first."""
    words = [w.lower() for w in words if w.strip()]
    if not words:
        return []
    where = " AND ".join("lower(coalesce(company,'') || ' ' || coalesce(title,'')) LIKE ?" for _ in words)
    sql = f"SELECT * FROM jobs WHERE {where}" + ("" if include_closed else " AND status <> 'closed'")
    rows = [dict(r) for r in con.execute(sql, [f"%{w}%" for w in words])]
    groups: dict[tuple, list[dict]] = {}
    for r in rows:  # 1) same title, same town
        groups.setdefault((" ".join(_words(r["title"])), _town(r)), []).append(r)
    for k in sorted(groups, key=lambda k: len(k[0])):  # 2) one board shortened the title ("Business Dev.", "EATS Engineer")
        g = groups[k]
        srcs = {r["source"] for r in g}
        if len(srcs) > 1:
            continue
        for k2, g2 in groups.items():
            if k2 != k and k2[1] == k[1] and g2 and not srcs & {r["source"] for r in g2} and _shortens(k[0], k2[0]):
                g2.extend(g)
                groups[k] = []
                break
    best = [max(g, key=lambda r: len(r["description"] or "")) for g in groups.values() if g]
    return sorted(best, key=lambda r: (r["title"] or "", r["location"] or ""))


def _words(s: str | None) -> list[str]:
    s = (s or "").lower().replace("&amp;", "&")
    return [w for w in re.findall(r"[a-z0-9åäöé]+", s) if w not in ("program", "programme")]


def _town(r: dict) -> str:
    return "".join(_words((r["location"] or "").split(",")[0]))


def _shortens(short: str, long: str) -> bool:
    """Every word of the short title starts a word of the long one, in order."""
    lw = long.split()
    i = 0
    for w in short.split():
        while i < len(lw) and not lw[i].startswith(w):
            i += 1
        if i == len(lw):
            return False
        i += 1
    return True


# ---- the Word file ----

def _t(s: str) -> str:
    return escape(_BAD_XML.sub("", s.replace("&amp;", "&")))


def _run(text: str, bold=False, color=None, size=None) -> str:
    props = ("<w:b/>" if bold else "") + (f'<w:color w:val="{color}"/>' if color else "") + \
            (f'<w:sz w:val="{size}"/>' if size else "")
    return f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{_t(text)}</w:t></w:r>'


def _p(inner: str, style=None, page_break=False, indent=False) -> str:
    props = (f'<w:pStyle w:val="{style}"/>' if style else "") + \
            ("<w:pageBreakBefore/>" if page_break else "") + ('<w:ind w:left="360"/>' if indent else "")
    return f'<w:p>{f"<w:pPr>{props}</w:pPr>" if props else ""}{inner}</w:p>'


def _link(rid: str, text: str) -> str:
    return (f'<w:hyperlink r:id="{rid}"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
            f'<w:t xml:space="preserve">{_t(text)}</w:t></w:r></w:hyperlink>')


def _body(description: str) -> list[str]:
    """Plain ad text → paragraphs. Short lines with no closing punctuation read as section headings."""
    out = []
    for line in (description or "").replace("\r", "").split("\n"):
        line = line.replace("\xa0", " ").strip()
        if not line:
            continue
        bullet = re.match(r"^([-•*·▪●]|\d+[.)])\s+", line)
        if bullet:
            out.append(_p(_run("• " + line[bullet.end():]), indent=True))
        elif len(line) < 70 and len(line.split()) <= 9 and not line.endswith((".", ",", ";", "!", "?")):
            out.append(_p(_run(line, bold=True), style="Heading3"))
        else:
            out.append(_p(_run(line)))
    return out


def to_docx(jobs: list[dict], heading: str) -> bytes:
    rels, paras = [], []
    paras.append(_p(_run(heading), style="Title"))
    paras.append(_p(_run(f"Saved {date.today().isoformat()} by Lavoro · {len(jobs)} roles. "
                         "A copy of each ad as it read on that day.", color="666666")))
    for i, j in enumerate(jobs, 1):
        paras.append(_p(_run(f"{i}. {j['title']} — {(j['location'] or '').split(',')[0]}")))
    for i, j in enumerate(jobs, 1):
        rid = f"rIdLink{i}"
        rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    f'relationships/hyperlink" Target="{escape(j["url"] or "", {chr(34): "&quot;"})}" TargetMode="External"/>')
        paras.append(_p(_run(j["title"] or "Untitled role"), style="Heading1", page_break=True))
        meta = " · ".join(x for x in [j["company"], j["location"], j["salary"],
                                     f"posted {j['posted_at'][:10]}" if j["posted_at"] else ""] if x)
        paras.append(_p(_run(meta, color="666666")))
        if j["url"]:
            paras.append(_p(_run("Ad: ", color="666666") + _link(rid, j["url"])))
        paras.extend(_body(j["description"]) or [_p(_run("No description was saved for this role. Open the ad link above.",
                                                          color="666666"))])

    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>{"".join(paras)}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1300" w:right="1300" w:bottom="1300" '
                'w:left="1300" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            + "".join(rels) + '</Relationships>'),
        "word/styles.xml": _STYLES,
        "word/document.xml": document,
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, xml in files.items():
            z.writestr(name, xml)
    return buf.getvalue()


def _style(sid, name, size, bold=False, color=None, before=0, after=120, kind="paragraph") -> str:
    rpr = ('<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>' + ("<w:b/>" if bold else "") +
           (f'<w:color w:val="{color}"/>' if color else "") + f'<w:sz w:val="{size}"/>')
    return (f'<w:style w:type="{kind}" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
            f'<w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{before}" w:after="{after}"/></w:pPr>'
            f'<w:rPr>{rpr}</w:rPr></w:style>')


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
    '<w:sz w:val="22"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _style("Title", "Title", 40, bold=True, after=200)
    + _style("Heading1", "heading 1", 30, bold=True, color="1F3864", after=80)
    + _style("Heading3", "heading 3", 23, bold=True, color="1F3864", before=200, after=60)
    + '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
      '<w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
    '</w:styles>')


def save(con, words: list[str], out: str | None = None, include_closed: bool = False) -> tuple[Path | None, int]:
    jobs = find(con, words, include_closed)
    if not jobs:
        return None, 0
    heading = " ".join(words).strip().title() + " — job descriptions"
    path = Path(out) if out else Path("output") / f"{re.sub(r'[^a-z0-9]+', '-', ' '.join(words).lower()).strip('-')}-{date.today().isoformat()}.docx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(to_docx(jobs, heading))
    return path, len(jobs)
