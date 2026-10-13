#!/usr/bin/env python3
"""Search the local ThaiJo cache (built by thaijo_harvest.py update). No network access.

Terms are case-insensitive regular expressions matched against title, subject
(keywords) and abstract by default. Thai terms work as plain substrings.

Examples:
    thaijo_search.py --any phytochem "สารพฤกษเคมี" --years 2026 -o hits.csv
    thaijo_search.py --all "curcum" "antioxidant" --not "review" --endpoints li,he
    thaijo_search.py --any "\\bdiabet" --years 2022-2026 --year-source volume -o d.jsonl

Year sources:
    auto    (default) volume year parsed from dc_source "(2026)" / Buddhist "(2569)",
            falling back to dc_date. Best estimate of the real publication year.
    volume  only the volume year (records without one are excluded when --years is set)
    date    only dc_date; beware: OJS sometimes stamps old issues with recent dates.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

ENDPOINT_GROUPS = ("sc", "li", "ph", "he", "so")
THAI = re.compile("[฀-๿]")
VOL_YEAR = re.compile(r"\((\d{4})\)")
RETRACTED = re.compile(r"retract|เพิกถอน", re.I)


def cache_dir(arg):
    return os.path.expanduser(arg or os.environ.get("THAIJO_CACHE") or "~/.thaijo")


def load_records(root, endpoints):
    """Latest version of every record across the selected endpoint files; deleted dropped."""
    latest = {}
    rec_dir = os.path.join(root, "records")
    if not os.path.isdir(rec_dir):
        raise SystemExit(f"no cache at {rec_dir}; run thaijo_harvest.py update first")
    for name in sorted(os.listdir(rec_dir)):
        ep = name.removesuffix(".jsonl")
        if not name.endswith(".jsonl") or (endpoints and not any(ep.startswith(e) for e in endpoints)):
            continue
        with open(os.path.join(rec_dir, name), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                prev = latest.get(r["identifier"])
                if prev is None or r["datestamp"] >= prev["datestamp"]:
                    latest[r["identifier"]] = r
    return [r for r in latest.values() if not r.get("deleted")]


def pub_year(r, source):
    vol = None
    for s in r.get("dc_source", []):
        m = VOL_YEAR.search(s)
        if m:
            y = int(m.group(1))
            vol = y - 543 if y > 2400 else y  # Buddhist Era -> CE
            break
    dates = r.get("dc_date", [])
    date = int(dates[0][:4]) if dates and dates[0][:4].isdigit() else None
    if source == "volume":
        return vol
    if source == "date":
        return date
    return vol or date


def split_titles(titles):
    en, th = [], []
    for t in titles:
        for part in (p.strip() for p in t.split(" | ")):
            if part:
                (th if THAI.search(part) else en).append(part)
    return " / ".join(dict.fromkeys(en)), " / ".join(dict.fromkeys(th))


def norm_title(s):
    return re.sub(r"\W+", "", s.lower())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--any", nargs="+", default=[], metavar="TERM", help="match at least one")
    p.add_argument("--all", nargs="+", default=[], metavar="TERM", help="match every one")
    p.add_argument("--not", dest="exclude", nargs="+", default=[], metavar="TERM", help="match none")
    p.add_argument("--fields", default="title,subject,description",
                   help="dc fields to search (default title,subject,description)")
    p.add_argument("--years", help="YYYY or YYYY-YYYY")
    p.add_argument("--year-source", choices=("auto", "volume", "date"), default="auto")
    p.add_argument("--endpoints", help="comma-separated codes or group prefixes, e.g. li,he05")
    p.add_argument("--include-retracted", action="store_true")
    p.add_argument("-o", "--out", help="write .csv (Excel-friendly UTF-8) or .jsonl (full records)")
    p.add_argument("--show", type=int, default=25, help="print first N hits (default 25)")
    p.add_argument("--cache")
    args = p.parse_args()
    if not (args.any or args.all):
        p.error("give --any and/or --all terms")

    any_rx = [re.compile(t, re.I) for t in args.any]
    all_rx = [re.compile(t, re.I) for t in args.all]
    not_rx = [re.compile(t, re.I) for t in args.exclude]
    fields = [f"dc_{f.strip()}" for f in args.fields.split(",")]
    lo = hi = None
    if args.years:
        a, _, b = args.years.partition("-")
        lo, hi = int(a), int(b or a)
    eps = [e.strip() for e in args.endpoints.split(",")] if args.endpoints else None

    root = cache_dir(args.cache)
    records = load_records(root, eps)
    counts = collections.Counter(searched=len(records))
    hits, seen_doi, seen_title = [], set(), set()

    for r in records:
        text = " ".join(v for f in fields for v in r.get(f, []))
        if any_rx and not any(rx.search(text) for rx in any_rx):
            continue
        if not all(rx.search(text) for rx in all_rx):
            continue
        if any(rx.search(text) for rx in not_rx):
            continue
        counts["keyword"] += 1
        year = pub_year(r, args.year_source)
        if lo is not None and (year is None or not lo <= year <= hi):
            continue
        counts["year"] += 1
        retracted = any(RETRACTED.search(t) for t in r.get("dc_title", []))
        if retracted:
            counts["retracted"] += 1
            if not args.include_retracted:
                continue
        ids = r.get("dc_identifier", [])
        doi = next((i for i in ids if "doi" in i.lower() or i.startswith("10.")), "")
        en, th = split_titles(r.get("dc_title", []))
        key_t = norm_title(en or th)
        if (doi and doi.lower() in seen_doi) or (key_t and key_t in seen_title):
            counts["duplicate"] += 1
            continue
        if doi:
            seen_doi.add(doi.lower())
        if key_t:
            seen_title.add(key_t)
        matched = sorted({m.group(0).lower() for rx in any_rx + all_rx for m in rx.finditer(text)})
        dates = r.get("dc_date", [])
        hits.append({
            "year": year or "",
            "dc_date": dates[0][:10] if dates else "",
            "title_en": en,
            "title_th": th,
            "authors": "; ".join(r.get("dc_creator", [])),
            "journal_issue": (r.get("dc_source") or [""])[0],
            "keywords": "; ".join(r.get("dc_subject", [])),
            "doi": doi,
            "url": next((i for i in ids if i.startswith("http") and "doi" not in i.lower()), ""),
            "endpoint": r["endpoint"],
            "identifier": r["identifier"],
            "retracted": "yes" if retracted else "",
            "matched": "; ".join(matched),
            "_record": r,
        })

    hits.sort(key=lambda h: (str(h["year"]), h["dc_date"]), reverse=True)

    if args.out:
        if args.out.lower().endswith(".jsonl"):
            with open(args.out, "w", encoding="utf-8") as f:
                for h in hits:
                    f.write(json.dumps({**h["_record"], "pub_year": h["year"], "retracted": bool(h["retracted"])},
                                       ensure_ascii=False) + "\n")
        else:
            cols = [k for k in (hits[0] if hits else {"year": 0}) if k != "_record"]
            with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(hits)

    # report
    state_path = os.path.join(root, "state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    covered = sorted(e for e in state if not eps or any(e.startswith(x) for x in eps))
    cov = collections.Counter((state[e].get("coverage_from") or "beginning") for e in covered)
    print(f"cache {root}: {len(covered)} endpoints, coverage from {dict(cov)}")
    missing = [g for g in ENDPOINT_GROUPS if (not eps or g in "".join(eps)) and not any(e.startswith(g) for e in covered)]
    if missing:
        print(f"NOT cached (not searched): {', '.join(missing)} endpoints")
    print(f"searched {counts['searched']} records -> keyword {counts['keyword']} -> year {counts['year']}"
          f" -> retracted {counts['retracted']}{' (kept)' if args.include_retracted else ' (dropped)'}"
          f" -> duplicates {counts['duplicate']} -> {len(hits)} hits")
    by_group = collections.Counter(h["endpoint"][:2] for h in hits)
    by_journal = collections.Counter(h["journal_issue"].split(";")[0].strip() for h in hits)
    print("by group:", dict(by_group))
    print("top journals:", "; ".join(f"{j} ({n})" for j, n in by_journal.most_common(5)))
    for h in hits[: args.show]:
        print(f"- {h['year']} | {(h['title_en'] or h['title_th'])[:110]} | "
              f"{h['journal_issue'].split(';')[0][:50]} | {h['doi'] or h['url']}"
              f"{' | RETRACTED' if h['retracted'] else ''}")
    if len(hits) > args.show:
        print(f"... {len(hits) - args.show} more{' in ' + args.out if args.out else ''}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
