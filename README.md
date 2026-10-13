# thaijo-retrieve

**English** | [ภาษาไทย](#ภาษาไทย)

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

---

## ภาษาไทย

[English](#thaijo-retrieve) | **ภาษาไทย**

skill สำหรับ [Claude Code](https://claude.com/claude-code) (ใช้เป็นสคริปต์ Python ธรรมดาก็ได้)
สำหรับค้นหาบทความวิจัยใน **ThaiJo** ([Thai Journals Online](https://www.tci-thaijo.org/))
ตามคำค้นและปีที่ตีพิมพ์

ThaiJo เปิดให้ดึงข้อมูลบทความผ่าน [OAI-PMH](https://www.tci-thaijo.org/public/oai.html)
ซึ่ง**ค้นหาด้วยคำค้นไม่ได้** โปรเจกต์นี้จึงดึงข้อมูลบทความมาเก็บไว้ในเครื่อง
(ครั้งต่อไปดึงเฉพาะส่วนที่เปลี่ยนแปลง) แล้วค้นหาจากข้อมูลในเครื่องโดยไม่ต้องต่ออินเทอร์เน็ต
และไม่เกินขีดจำกัด 10 คำขอต่อนาทีของ ThaiJo

### การติดตั้ง

ติดตั้งเป็น skill ของ Claude Code:

```bash
git clone https://github.com/thitipedia/thaijo-retrieve.git ~/.claude/skills/thaijo-retrieve
```

จากนั้นสั่ง Claude ได้เลย เช่น *"ค้นบทความใน ThaiJo เรื่องสารพฤกษเคมีที่ตีพิมพ์ปี 2026"*
Claude จะตรวจข้อมูลในเครื่อง ดึงเฉพาะส่วนที่ยังขาด (โดยแจ้งก่อนว่าจะใช้เวลานานเท่าไร)
แล้วส่งผลลัพธ์เป็นไฟล์ CSV

ต้องใช้ Python 3.9 ขึ้นไป ไม่ต้องติดตั้งแพ็กเกจเพิ่ม

### ใช้สคริปต์โดยตรง

```bash
cd ~/.claude/skills/thaijo-retrieve/scripts

# ดูว่ามีข้อมูลอะไรในเครื่องแล้วบ้าง
python thaijo_harvest.py status

# ดึงข้อมูลกลุ่มวิทยาศาสตร์ชีวภาพ กายภาพ สุขภาพ และ sc01 ตั้งแต่ 2026-01-01 (~17,000 รายการ ใช้เวลา ~25 นาที)
python thaijo_harvest.py update science --from 2026-01-01

# ครั้งต่อไป ดึงเฉพาะที่เปลี่ยนแปลงตั้งแต่ครั้งล่าสุด (ไม่กี่นาที)
python thaijo_harvest.py update science

# ค้นหาในเครื่อง ด้วยคำค้นภาษาอังกฤษและไทย เฉพาะที่ตีพิมพ์ปี 2026
python thaijo_search.py --any phytochem "พฤกษเคมี" --years 2026 -o phytochemical_2026.csv
```

#### สคริปต์ดึงข้อมูล (`thaijo_harvest.py`)

| คำสั่ง | หน้าที่ |
|---|---|
| `status` | ช่วงวันที่และจำนวนรายการที่เก็บไว้ของแต่ละ endpoint |
| `update <eps> [--from DATE \| --full]` | ดึงเฉพาะส่วนที่ขาด ถ้าระบุ `--from` ย้อนหลังกว่าเดิม จะดึงเพิ่มเฉพาะช่วงที่ขาด |
| `identify <ep>` / `sets <ep>` | ข้อมูลของ repository / รายชื่อวารสารและหมวด (sets) |
| `record <ep> <oai-id>` | ข้อมูลบทความเดียวในรูปแบบ JSON |
| `records <eps> -o file.jsonl` | ดึงข้อมูลครั้งเดียวลงไฟล์ โดยไม่เก็บเข้าข้อมูลในเครื่อง |

`<eps>` ใส่ได้ทั้งรหัส (`li03`) กลุ่ม (`sc`, `li`, `ph`, `he`, `so`) `science`
(sc+li+ph+he) `all` หรือหลายค่าคั่นด้วยจุลภาค การดึงข้อมูลนาน ๆ จะบันทึกความคืบหน้าทุกหน้า
ถ้าหยุดกลางคัน ให้รันคำสั่งเดิมซ้ำเพื่อทำต่อ

#### สคริปต์ค้นหา (`thaijo_search.py`)

- `--any` (ตรงอย่างน้อยหนึ่งคำ), `--all` (ต้องตรงทุกคำ) และ `--not` (ต้องไม่มีคำนี้)
  รับ regular expression แบบไม่สนตัวพิมพ์เล็กใหญ่ คำภาษาไทยใช้เป็นข้อความธรรมดาได้เลย
- `--fields` เลือกส่วนที่จะค้น ค่าเริ่มต้นคือ `title,subject,description` (ชื่อเรื่อง
  คำสำคัญ บทคัดย่อ) หรือใช้ `title,subject` ถ้าต้องการผลที่ตรงกว่า
- `--years 2026` หรือ `--years 2022-2026` จำกัดปีที่ตีพิมพ์ ส่วน `--year-source`
  เลือกว่าจะเอาปีจากไหน:
  - `auto` (ค่าเริ่มต้น): ปีของเล่มวารสาร (แปลงปี พ.ศ. เช่น 2569 เป็น 2026 ให้)
    ถ้าไม่มีปีของเล่มจึงใช้ `dc_date`
  - `volume`: ใช้เฉพาะปีของเล่มวารสาร
  - `date`: ใช้เฉพาะ `dc_date`
- `--endpoints li,he05` จำกัด endpoint ที่จะค้น
- `--include-retracted` เก็บบทความที่ถูกเพิกถอนไว้ด้วย (ค่าเริ่มต้นจะตัดออก)
- `-o hits.csv` บันทึกเป็น CSV แบบ UTF-8 ที่เปิดใน Excel แล้วภาษาไทยไม่เพี้ยน
  `-o hits.jsonl` บันทึกข้อมูลเต็มรวมบทคัดย่อ

คอลัมน์ใน CSV: year, dc_date, title_en, title_th, authors, journal_issue, keywords,
doi, url, endpoint, identifier, retracted และคำค้นที่ตรง (matched)

### ข้อมูลที่เก็บในเครื่อง

เก็บไว้ที่ `~/.thaijo/` (หรือโฟลเดอร์ที่ตั้งใน `THAIJO_CACHE`) ใช้ร่วมกันทุกโปรเจกต์ในเครื่อง:

- `records/<endpoint>.jsonl`: ข้อมูลบทความที่ดึงมา ฉบับที่มีการแก้ไขจะถูกต่อท้าย
  และการค้นหาจะใช้ฉบับล่าสุด
- `state.json`: ช่วงวันที่ที่แต่ละ endpoint มีข้อมูล และตำแหน่งของการดึงที่ยังไม่เสร็จ

### Endpoints

มีทั้งหมด 36 endpoint ที่ `https://<code>.tci-thaijo.org/index.php/index/oai`
จำนวนบทความโดยประมาณ ณ ตุลาคม 2026:

| กลุ่ม | รหัส | ขนาด |
|---|---|---|
| วิทยาศาสตร์ (Science) | sc01 | ~900 |
| วิทยาศาสตร์ชีวภาพ (Life Sciences) | li01–li05 | li01 ~26,000 ที่เหลือ 1,000–2,000 |
| วิทยาศาสตร์กายภาพ (Physical Sciences) | ph01–ph05 | ph01 ~18,000, ph02 ~17,000 ที่เหลือไม่ถึง 4,000 |
| วิทยาศาสตร์สุขภาพ (Health Sciences) | he01–he05 | he01 ~47,000, he02 ~45,000 ที่เหลือไม่ถึง 7,000 |
| สังคมศาสตร์ (Social Sciences) | so01–so20 | ยังไม่ได้วัด |

ข้อมูลเป็นแบบ Dublin Core (`oai_dc`) เท่านั้น ได้แก่ ชื่อเรื่อง ผู้แต่ง คำสำคัญ บทคัดย่อ
วารสารและฉบับ วันที่ DOI และลิงก์ **ไม่มีเนื้อหาฉบับเต็ม**

### ใช้งานอย่างสุภาพต่อเซิร์ฟเวอร์

ThaiJo อนุญาต **10 คำขอต่อนาทีต่อ IP** ถ้าเกินจะถูกลดเหลือ 3 คำขอต่อนาที
และถ้ายังเกินต่อไปจะถูกบล็อกชั่วคราว สคริปต์จึงเว้นระยะ 7 วินาทีระหว่างคำขอ
และรอเพิ่มเมื่อเซิร์ฟเวอร์ตอบ 429 หรือ 503 อย่าตั้ง `--interval` ต่ำกว่า 6 วินาที
และอย่ารันการดึงข้อมูลสองชุดพร้อมกัน แต่ละคำขอได้ไม่เกิน 100 รายการ
จึงใช้เวลาประมาณ 1 นาทีต่อ 850 รายการ การดึงกลุ่มวิทยาศาสตร์ทั้งหมด (~180,000 รายการ)
ใช้เวลาราว 3.5 ชั่วโมง

### ข้อควรรู้เกี่ยวกับข้อมูล (สคริปต์จัดการให้แล้ว)

- `dc_date` ของฉบับเก่าบางครั้งเป็นวันที่ล่าสุด ค่าเริ่มต้นจึงใช้ปีของเล่มวารสารแทน
- บทความที่ถูกเพิกถอน (`[RETRACTED ARTICLE] …`) จะถูกตัดออกโดยค่าเริ่มต้นและนับแยกไว้
- ชื่อเรื่องสองภาษาที่คั่นด้วย ` | ` จะถูกแยกเป็นคอลัมน์ภาษาอังกฤษและภาษาไทย
- บทความซ้ำจะถูกตัดออกโดยดูจาก DOI ก่อน แล้วจึงดูจากชื่อเรื่อง
- บทคัดย่อบางเรื่องมีอักขระที่ XML ไม่รองรับ สคริปต์จะลบออกก่อนอ่านข้อมูล
