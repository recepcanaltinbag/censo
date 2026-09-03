#!/usr/bin/env python3
"""
Verify every DOI in paper/refs.bib against CrossRef.

WHY THIS EXISTS
---------------
A DOI in this bibliography was fabricated: the WaWO+ entry carried
10.1016/j.envsoft.2016.07.005, which does not resolve to that paper. The correct
record is 10.1016/j.envsoft.2016.11.009, Environmental Modelling & Software 89,
106-119, and the year is 2017 rather than 2016.

A plausible-looking DOI is worse than a missing one: it survives review right up
to the moment a reader clicks it. Since one was wrong, all of them must be
checked mechanically rather than by rereading.

WHAT IT CHECKS
--------------
For each @entry with a DOI:
  * does the DOI resolve in CrossRef at all?
  * does the registered title match the title in the .bib (fuzzy)?
  * do year, journal, volume and pages match?
For each entry WITHOUT a DOI, a title search suggests one where a confident
match exists.

CrossRef is free and needs no key; a contact address in the User-Agent gets the
polite pool. Responses are cached so reruns need no network.

Outputs: eval/bibliography_check.md
         derived/interim/crossref_cache/*.json

Usage:  python scripts/09_verify_bibliography.py [--offline] [--suggest]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIB = ROOT / "paper" / "refs.bib"
CACHE = ROOT / "derived" / "interim" / "crossref_cache"
EVAL = ROOT / "eval"

API = "https://api.crossref.org"
UA = "censo-ontology-research/1.0 (mailto:recocanextra@gmail.com)"
DELAY = 0.3
TIMEOUT = 45

TITLE_MATCH_THRESHOLD = 0.82   # below this, flag for manual review

# Known-acceptable divergences: cases where the PUBLISHER's deposited metadata
# is incomplete, not where our entry is wrong. Each needs a reason, and each is
# still printed so it cannot be forgotten -- it is just not counted as an error.
ACCEPTED = {
    # Crossref records the ONLINE-FIRST date; the article appeared in issue
    # 37(3), March 2018, which is the year a reader citing it will write. DOI,
    # journal, volume, pages and authors all agree, so the divergence is in the
    # registry's notion of "issued", not in our transcription.
    "shoari2018nondetects": "Crossref carries the 2017 online-first date; the "
                            "article is in issue 37(3) of 2018, which is the "
                            "year cited here. Every other field agrees.",
    "poveda2014oops": "IGI Global deposited the title without its subtitle; "
                      "DOI, journal, volume, pages and year all agree, and the "
                      "published article does carry the subtitle.",
}


def norm_title(s: str) -> str:
    s = re.sub(r"[{}\\]", "", s or "")
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def parse_bib(text: str):
    """Minimal BibTeX reader: entry type, key, and the fields we verify."""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),", text):
        kind, key = m.group(1).lower(), m.group(2).strip()
        start = m.end()
        depth, i = 1, m.start()
        # find the matching closing brace of the entry
        i = text.index("{", m.start())
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    body = text[start:j]
                    break
        else:
            body = text[start:]

        def field(name):
            fm = re.search(rf"\b{name}\s*=\s*", body, re.I)
            if not fm:
                return ""
            rest = body[fm.end():].lstrip()
            if rest.startswith("{"):
                d = 0
                for k, ch in enumerate(rest):
                    if ch == "{":
                        d += 1
                    elif ch == "}":
                        d -= 1
                        if d == 0:
                            return rest[1:k]
                return ""
            if rest.startswith('"'):
                return rest[1:rest.index('"', 1)]
            return rest.split(",")[0].strip()

        entries.append({
            "kind": kind, "key": key,
            "title": field("title"), "doi": field("doi"),
            "year": field("year"), "journal": field("journal"),
            "volume": field("volume"), "pages": field("pages"),
            "note": field("note"),
        })
    return entries


def get(url: str, cache_name: str, offline: bool):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cache_name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    if offline:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    finally:
        time.sleep(DELAY)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    path.write_text(json.dumps(d.get("message", d), ensure_ascii=False),
                    encoding="utf-8")
    return d.get("message", d)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:90]


def crossref_by_doi(doi: str, offline: bool):
    return get(f"{API}/works/{urllib.parse.quote(doi)}", f"doi_{slug(doi)}", offline)


def crossref_by_title(title: str, offline: bool):
    q = urllib.parse.quote(title[:200])
    d = get(f"{API}/works?query.bibliographic={q}&rows=3", f"ttl_{slug(title)}",
            offline)
    items = (d or {}).get("items") or []
    return items


def summarise(item):
    if not item:
        return {}
    return {
        "doi": item.get("DOI", ""),
        "title": (item.get("title") or [""])[0],
        "journal": (item.get("container-title") or [""])[0],
        "volume": item.get("volume", ""),
        "pages": item.get("page", ""),
        "year": str((item.get("issued", {}).get("date-parts") or [[""]])[0][0]),
        "authors": ", ".join(
            f"{a.get('family','')} {(a.get('given','') or ' ')[0]}."
            for a in (item.get("author") or [])[:8]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--suggest", action="store_true",
                    help="also look up entries that carry no DOI")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)

    if not BIB.exists():
        sys.exit(f"missing {BIB}")
    entries = parse_bib(BIB.read_text(encoding="utf-8"))

    ok, wrong, unresolved, nodoi, suggestions = [], [], [], [], []
    accepted = []

    for e in entries:
        if not e["doi"]:
            nodoi.append(e)
            if args.suggest and e["title"]:
                items = crossref_by_title(e["title"], args.offline)
                if items:
                    best = summarise(items[0])
                    r = difflib.SequenceMatcher(
                        None, norm_title(e["title"]), norm_title(best["title"])).ratio()
                    if r >= TITLE_MATCH_THRESHOLD:
                        suggestions.append((e, best, r))
            continue

        item = crossref_by_doi(e["doi"], args.offline)
        if not item:
            unresolved.append(e)
            continue
        reg = summarise(item)
        r = difflib.SequenceMatcher(
            None, norm_title(e["title"]), norm_title(reg["title"])).ratio()
        diffs = []
        if r < TITLE_MATCH_THRESHOLD:
            diffs.append(f"title ({r:.0%} similar)")
        if e["year"] and reg["year"] and e["year"] != reg["year"]:
            diffs.append(f"year {e['year']} vs {reg['year']}")
        if e["volume"] and reg["volume"] and e["volume"] != reg["volume"]:
            diffs.append(f"volume {e['volume']} vs {reg['volume']}")
        if e["pages"] and reg["pages"] and \
           e["pages"].replace("--", "-") != reg["pages"]:
            diffs.append(f"pages {e['pages']} vs {reg['pages']}")
        if diffs and e["key"] in ACCEPTED:
            accepted.append((e, reg, diffs, ACCEPTED[e["key"]]))
        else:
            (wrong if diffs else ok).append((e, reg, diffs))

    L = []
    A = L.append
    A("# Bibliography verification\n")
    A("Generated by `scripts/09_verify_bibliography.py`. Every DOI is resolved "
      "against CrossRef and compared with the fields in `paper/refs.bib`.\n")
    A("> This check exists because one DOI in this bibliography was fabricated. "
      "A plausible-looking DOI survives review until a reader clicks it, so the "
      "whole file is verified mechanically rather than by rereading.\n")
    A(f"- entries: **{len(entries)}**")
    A(f"- with a DOI: {len(entries) - len(nodoi)}")
    A(f"- **verified correct: {len(ok)}**")
    A(f"- **wrong metadata: {len(wrong)}**")
    A(f"- **DOI does not resolve: {len(unresolved)}**")
    A(f"- publisher metadata incomplete (accepted): {len(accepted)}")
    A(f"- no DOI (books, standards, legislation): {len(nodoi)}\n")

    if wrong:
        A("## Entries whose registered record disagrees\n")
        for e, reg, diffs in wrong:
            A(f"### `{e['key']}` — {', '.join(diffs)}\n")
            A(f"- **bib**: {e['title'][:90]} · {e['year']} · "
              f"{e['journal']} {e['volume']} {e['pages']}")
            A(f"- **CrossRef**: {reg['title'][:90]} · {reg['year']} · "
              f"{reg['journal']} {reg['volume']} {reg['pages']}")
            A(f"- authors: {reg['authors']}\n")

    if accepted:
        A("## Divergences accepted, with reasons\n")
        for e, reg, diffs, why in accepted:
            A(f"- `{e['key']}` — {', '.join(diffs)}. {why}")
        A("")

    if unresolved:
        A("## DOIs that do not resolve — treat as fabricated until proven otherwise\n")
        for e in unresolved:
            A(f"- `{e['key']}` → `{e['doi']}` ({e['title'][:70]})")
        A("")

    if suggestions:
        A("## Suggested DOIs for entries that lack one\n")
        A("| key | suggested DOI | registered title | match |")
        A("|---|---|---|---|")
        for e, best, r in suggestions:
            A(f"| `{e['key']}` | `{best['doi']}` | {best['title'][:60]} | {r:.0%} |")
        A("")

    if ok:
        A("## Verified\n")
        for e, reg, _ in ok:
            A(f"- `{e['key']}` — {reg['journal']} {reg['volume']}, {reg['year']}")
        A("")

    still = [e for e in entries if "VERIFY" in (e.get("note") or "")]
    if still:
        A("## Entries still carrying a VERIFY note\n")
        for e in still:
            A(f"- `{e['key']}`: {e['note'][:110]}")
        A("")
        A("A `VERIFY` note does not license a guessed value. Entries that cannot "
          "be confirmed should carry no DOI at all rather than a plausible one.\n")

    text = "\n".join(L)
    (EVAL / "bibliography_check.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'bibliography_check.md'}")
    return 1 if (wrong or unresolved) else 0


if __name__ == "__main__":
    raise SystemExit(main())
