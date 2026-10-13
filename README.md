# thaijo-retrieve

A [Claude Code](https://claude.com/claude-code) skill, also usable as plain Python scripts, for
finding research articles in **ThaiJo** ([Thai Journals Online](https://www.tci-thaijo.org/)) by
keyword and publication year.

ThaiJo publishes metadata through [OAI-PMH](https://www.tci-thaijo.org/public/oai.html), which has
**no keyword search**. This project harvests the metadata into a local cache that only fetches
changes after the first run, then searches that cache offline. It stays within ThaiJo's limit of
10 requests per minute.

## Install

As a Claude Code skill:

```bash
git clone https://github.com/thitipedia/thaijo-retrieve.git ~/.claude/skills/thaijo-retrieve
```

Then ask Claude something like *"find ThaiJo articles on phytochemicals published in 2026"* or
*"ค้นบทความใน ThaiJo เรื่องสมุนไพรต้านเบาหวาน"*. Claude checks the cache, harvests only what is
missing (it tells you how long that will take first), and returns a CSV.

Requirements: Python 3.9+ and nothing else (standard library only).

## Use the scripts directly

```bash
cd ~/.claude/skills/thaijo-retrieve/scripts

# What is cached?
python thaijo_harvest.py status

# Sync Life, Physical and Health Sciences + sc01 from 2026-01-01 (~17k records, ~25 min)
python thaijo_harvest.py update science --from 2026-01-01

# Later: fetch only what changed since the last sync (minutes)
python thaijo_harvest.py update science

# Search offline, English and Thai terms, publication year 2026
python thaijo_search.py --any phytochem "พฤกษเคมี" --years 2026 -o phytochemical_2026.csv
```

### Harvester (`thaijo_harvest.py`)

| Command | What it does |
|---|---|
| `status` | Coverage and record count per endpoint in the cache |
| `update <eps> [--from DATE \| --full]` | Incremental sync; an earlier `--from` backfills only the missing window |
| `identify <ep>` / `sets <ep>` | Repository info / list of journal and section sets |
| `record <ep> <oai-id>` | One record as JSON |
| `records <eps> -o file.jsonl` | One-off harvest outside the cache |

`<eps>` can be a code (`li03`), a group (`sc`, `li`, `ph`, `he`, `so`), `science`
(sc+li+ph+he), `all`, or a comma-separated list. Long runs save progress after every page, so if
one is interrupted, rerun the same command to resume.

### Search (`thaijo_search.py`)

- `--any`, `--all` and `--not` take case-insensitive regular expressions. Thai terms work as
  plain substrings.
- `--fields` sets which fields are searched: `title,subject,description` by default, or
  `title,subject` for stricter matching.
- `--years 2026` or `--years 2022-2026` limits the publication year. `--year-source` chooses
  where the year comes from:
  - `auto` (default): the volume year, with Buddhist years such as 2569 converted to 2026, or
    `dc_date` if there is no volume year.
  - `volume`: only the volume year.
  - `date`: only `dc_date`.
- `--endpoints li,he05` narrows which endpoints are searched.
- `--include-retracted` keeps retracted articles, which are dropped by default.
- `-o hits.csv` writes an Excel-friendly UTF-8 CSV. `-o hits.jsonl` writes full records,
  including abstracts.

The CSV has these columns: year, dc_date, title_en, title_th, authors, journal_issue, keywords,
doi, url, endpoint, identifier, retracted, and matched terms.

## Cache

The cache is stored in `~/.thaijo/`, or in the `THAIJO_CACHE` directory if that is set. It is
shared by every project on the machine:

- `records/<endpoint>.jsonl`: harvested records. Updated versions are appended, and search uses
  the newest one.
- `state.json`: the date range each endpoint covers, and the position of any unfinished run.

## Endpoints

36 endpoints at `https://<code>.tci-thaijo.org/index.php/index/oai`. Approximate total record
counts as of October 2026:

| Group | Codes | Size |
|---|---|---|
| Science | sc01 | ~0.9k |
| Life Sciences | li01–li05 | li01 ~26k, others 1–2k |
| Physical Sciences | ph01–ph05 | ph01 ~18k, ph02 ~17k, others under 4k |
| Health Sciences | he01–he05 | he01 ~47k, he02 ~45k, others under 7k |
| Social Sciences | so01–so20 | not measured |

Metadata is Dublin Core (`oai_dc`) only: titles, authors, keywords, abstract, journal and issue,
date, DOI and link. There is no full text.

## Be polite to the server

ThaiJo allows **10 requests per minute per IP**. Going over the limit slows access to 3 per
minute, and continuing to go over it gets you temporarily blocked. The harvester waits 7 seconds
between requests and backs off when the server returns 429 or 503. Don't set `--interval` below
6 seconds or run two harvests at the same time. Each request returns up to 100 records, so plan
on about 1 minute per 850 records. A complete harvest of the science endpoints (about 180k
records) takes around 3.5 hours.

## Known data quirks (handled by the scripts)

- `dc_date` is sometimes a recent date for an old issue. This is why the year comes from the
  volume by default.
- Retracted articles (`[RETRACTED ARTICLE] …`) are dropped by default and counted in the output.
- Bilingual titles separated by ` | ` are split into English and Thai columns.
- Duplicate articles are removed by DOI, then by normalized title.
- Some abstracts contain characters that aren't valid XML. These are removed before parsing.
