---
name: thaijo-retrieve
description: Retrieve research articles from ThaiJo (Thai Journals Online, tci-thaijo.org, TCI-indexed Thai journals) by keyword, year, field or journal, via its OAI-PMH service and a shared local cache. Use whenever the user wants to find, list, count, export or harvest papers or metadata from ThaiJo / TCI / Thai journals, e.g. "find ThaiJo articles on phytochemical published in 2026", "ค้นบทความใน ThaiJo เรื่อง...", or asks about ThaiJo's OAI endpoints. Output is a CSV/JSONL of matching records (titles, authors, abstracts, DOIs, links); writing or synthesis is left to other skills.
---

# ThaiJo retrieve

ThaiJo's OAI-PMH service **has no keyword search**. The only way to search is to
harvest metadata into a local cache, then filter locally. Both scripts are Python
standard library only.

- `scripts/thaijo_harvest.py`: the only thing that touches the network. It keeps the
  cache at `~/.thaijo/` (override with `THAIJO_CACHE`) in sync, incrementally.
- `scripts/thaijo_search.py`: offline search over the cache, writing CSV or JSONL.

Paths below are relative to this skill's directory.

## Hard rules (the server will block you otherwise)

- Limit is **10 requests/min per IP**. Exceeding it throttles to 3/min, then a
  temporary block. The harvester spaces requests 7 s apart; never pass
  `--interval` below 6, never run two harvests at once, and never fetch ThaiJo
  pages in parallel with a running harvest.
- Each request returns up to 100 records, so cost is about **1 minute per 850
  records**. Estimate before harvesting and tell the user the expected time.
- Long harvests: run in the background. They save progress after every page and
  resume when the same `update` command is rerun.

## Workflow

1. **Check the cache first**: `python scripts/thaijo_harvest.py status`.
   It shows, per endpoint, the earliest date covered and the last sync date.
2. **Decide what is missing** for the request: which endpoints (see the table
   below) and from which date. Articles published in year Y were modified on or
   after Y-01-01, so `--from Y-01-01` is enough for "published in Y or later".
3. **Sync only the gap**, after telling the user the estimate:
   `python scripts/thaijo_harvest.py update science --from 2026-01-01`.
   Rerunning `update` on cached endpoints fetches only changes since the last sync.
   An earlier `--from` (or `--full`) backfills just the older window. Use
   `--full` only when the user explicitly wants the whole history (hours).
4. **Search** with English **and Thai** synonyms, since many records are bilingual:
   `python scripts/thaijo_search.py --any phytochem "พฤกษเคมี" --years 2026 -o hits.csv`
   Use `--all` for required co-terms, `--not` to exclude, `--endpoints li,he` to
   narrow, and `.jsonl` output when the full abstracts are needed downstream.
5. **Report**: the hit count, the funnel line the script prints, the main
   journals, a handful of example titles, the CSV path, and the caveats that apply
   (below). Don't paste every hit into chat.

To size an endpoint without harvesting it, one `ListIdentifiers` request returns
`completeListSize` in its resumptionToken. `identify <ep>` and `sets <ep>` (one
request each) show repository info and the journal/section sets.

## Endpoints

`https://<code>.tci-thaijo.org/index.php/index/oai`, grouped by field:

| Group | Codes | Approx. total records (Oct 2026) |
|---|---|---|
| Science | sc01 | 0.9k |
| Life Sciences | li01–li05 | li01 26k, others 1–2k |
| Physical Sciences | ph01–ph05 | ph01 18k, ph02 17k, others under 4k |
| Health Sciences | he01–he05 | he01 47k, he02 45k, others under 7k |
| Social Sciences | so01–so20 | not measured |

The CLI accepts a code, a group prefix (`li`), `science` (sc+li+ph+he), `all`, or
a comma list. A science-wide `--full` harvest is about 180k records, roughly 3.5 h.
Only `oai_dc` (Dublin Core) metadata is available: title, creators, subjects
(keywords), abstract, journal/issue, date, DOI, link. There is **no full text**.

## Data quirks (already handled by the scripts, but mention them when relevant)

- **The year in `dc_date` can be wrong**: old issues get re-stamped with recent
  dates. Search's default `--year-source auto` uses the volume year in
  `dc_source` ("Vol. 60 No. 5 (2026)", converting Buddhist years such as 2569 to
  2026) and falls back to `dc_date`.
- **Retracted articles** have titles starting `[RETRACTED ARTICLE]`. They're
  dropped by default and counted; use `--include-retracted` to keep them.
- **Bilingual titles** joined with ` | ` are split into `title_en` / `title_th`.
- **Duplicates** across journals or endpoints are dropped by DOI, then by
  normalized title.
- **Invalid XML characters** in some abstracts are stripped before parsing.
- **Updated records** are appended to the cache; search keeps the newest version
  per identifier and drops deleted ones.
- **Loose matches**: matching on abstracts catches passing mentions. For tighter
  results use `--fields title,subject` or `--all` co-terms, and say which you used.
