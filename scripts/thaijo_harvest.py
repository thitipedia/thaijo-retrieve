#!/usr/bin/env python3
"""Rate-limited OAI-PMH harvester for ThaiJo (tci-thaijo.org) with a shared local cache.

ThaiJo limits: 10 requests/min per user/IP; exceeding it throttles to 3/min and
continued abuse leads to a temporary block. Requests are spaced evenly (default
7s, ~8.5/min) and back off on 429/503.

Cache layout (default ~/.thaijo, override with --cache or THAIJO_CACHE):
    records/<endpoint>.jsonl   one record per line (appended; newest datestamp wins)
    state.json                 per-endpoint coverage_from / synced_until / in_progress

Commands:
    status                         show what is cached per endpoint
    update <eps> [--from DATE]     incremental sync into the cache (resumable)
    identify <ep>                  repository info
    sets <ep>                      list setSpec / setName
    record <ep> <oai-identifier>   one record as JSON
    records <ep> [-o out.jsonl]    one-off harvest outside the cache

<eps> is a code (sc01, li03), a group (sc, li, ph, he, so), 'science' (sc+li+ph+he)
or 'all'; comma-separate to combine, e.g. li,he05.

Only the Python standard library is used.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ENDPOINT_CODES = (
    ["sc01"]
    + [f"li{i:02d}" for i in range(1, 6)]
    + [f"ph{i:02d}" for i in range(1, 6)]
    + [f"he{i:02d}" for i in range(1, 6)]
    + [f"so{i:02d}" for i in range(1, 21)]
)
GROUPS = {"science": ("sc", "li", "ph", "he"), "all": ("sc", "li", "ph", "he", "so")}

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
DC_FIELDS = ("title", "creator", "subject", "description", "publisher", "contributor",
             "date", "type", "format", "identifier", "source", "language",
             "relation", "coverage", "rights")
USER_AGENT = "thaijo-harvester/1.1 (+OAI-PMH; polite, rate-limited)"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def endpoint_url(code):
    return f"https://{code}.tci-thaijo.org/index.php/index/oai"


def resolve_endpoints(spec):
    out = []
    for part in spec.lower().split(","):
        part = part.strip()
        if part in GROUPS:
            out += [c for c in ENDPOINT_CODES if c[:2] in GROUPS[part]]
        elif part in ENDPOINT_CODES:
            out.append(part)
        elif part in ("sc", "li", "ph", "he", "so"):
            out += [c for c in ENDPOINT_CODES if c.startswith(part)]
        else:
            raise SystemExit(f"unknown endpoint or group: {part!r}")
    return list(dict.fromkeys(out))


def cache_dir(arg):
    return os.path.expanduser(arg or os.environ.get("THAIJO_CACHE") or "~/.thaijo")


# ---------------------------------------------------------------- HTTP / XML

class OAIError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


class RateLimitedClient:
    """HTTP client that enforces a minimum interval between requests."""

    def __init__(self, interval=7.0, max_retries=5, timeout=60):
        self.interval = interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last = 0.0

    def _wait_turn(self):
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()

    def get(self, url, params):
        full = f"{url}?{urllib.parse.urlencode(params)}"
        backoff = 60.0
        for attempt in range(1, self.max_retries + 1):
            self._wait_turn()
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    ra = e.headers.get("Retry-After")
                    wait = float(ra) if ra and ra.isdigit() else backoff
                    log(f"  HTTP {e.code}; backing off {wait:.0f}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(wait)
                    backoff = min(backoff * 2, 900)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                log(f"  network error: {e}; retrying in {backoff:.0f}s (attempt {attempt}/{self.max_retries})")
                time.sleep(backoff)
                backoff = min(backoff * 2, 900)
        raise RuntimeError(f"giving up after {self.max_retries} attempts: {full}")


_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def parse(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        # Some ThaiJo records contain control chars or bad UTF-8 in abstracts.
        cleaned = _ILLEGAL_XML.sub("", xml_bytes.decode("utf-8", errors="replace"))
        root = ET.fromstring(cleaned.encode("utf-8"))
    err = root.find("oai:error", NS)
    if err is not None:
        raise OAIError(err.get("code", "unknown"), (err.text or "").strip())
    return root


def text_list(parent, tag):
    return [el.text.strip() for el in parent.findall(tag, NS) if el.text and el.text.strip()]


def record_to_dict(rec, endpoint):
    header = rec.find("oai:header", NS)
    out = {
        "endpoint": endpoint,
        "identifier": header.findtext("oai:identifier", default="", namespaces=NS),
        "datestamp": header.findtext("oai:datestamp", default="", namespaces=NS),
        "sets": text_list(header, "oai:setSpec"),
        "deleted": header.get("status") == "deleted",
    }
    dc = rec.find("oai:metadata/oai_dc:dc", NS)
    if dc is not None:
        for field in DC_FIELDS:
            values = text_list(dc, f"dc:{field}")
            if values:
                out[f"dc_{field}"] = values
    return out


def list_paged(client, endpoint, verb, params, item_path, token=None, on_page=None):
    """Yield items across resumptionToken pages; on_page(next_token) runs after each page."""
    url = endpoint_url(endpoint)
    while True:
        query = {"verb": verb, "resumptionToken": token} if token else {"verb": verb, **params}
        try:
            root = parse(client.get(url, query))
        except OAIError as e:
            if e.code == "noRecordsMatch":
                if on_page:
                    on_page(None)
                return
            raise
        container = root.find(f"oai:{verb}", NS)
        for item in container.findall(item_path, NS):
            yield item
        tok_el = container.find("oai:resumptionToken", NS)
        token = tok_el.text.strip() if tok_el is not None and tok_el.text else None
        if tok_el is not None and tok_el.get("completeListSize"):
            log(f"  [{endpoint}] cursor={tok_el.get('cursor')} total={tok_el.get('completeListSize')}")
        if on_page:
            on_page(token)
        if not token:
            return


# ---------------------------------------------------------------- cache

def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def today_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def run_into_cache(client, ep, run, state, state_path, rec_path):
    """Execute one ListRecords window {kind, from, until, started, token}; resumable."""
    st = state.setdefault(ep, {})
    st["in_progress"] = run
    save_state(state_path, state)
    params = {"metadataPrefix": "oai_dc"}
    if run.get("from"):
        params["from"] = run["from"]
    if run.get("until"):
        params["until"] = run["until"]
    count = 0
    with open(rec_path, "a", encoding="utf-8") as out:
        def checkpoint(next_token):
            out.flush()
            run["token"] = next_token
            save_state(state_path, state)

        for rec in list_paged(client, ep, "ListRecords", params, "oai:record",
                              token=run.get("token"), on_page=checkpoint):
            out.write(json.dumps(record_to_dict(rec, ep), ensure_ascii=False) + "\n")
            count += 1

    # window complete: fold into coverage
    if run["kind"] == "backfill":
        st["coverage_from"] = run.get("from")
    else:
        if "coverage_from" not in st:
            st["coverage_from"] = run.get("from")
        st["synced_until"] = run["started"]
    st.pop("in_progress", None)
    save_state(state_path, state)
    return count


def plan_runs(st, want_from, full):
    """Return the windows needed so the cache covers [want_from or beginning, today]."""
    runs = []
    start = today_utc()
    if "synced_until" not in st:
        return [{"kind": "forward", "from": None if full else want_from, "until": None, "started": start}]
    have_from = st.get("coverage_from")
    if have_from is not None and (full or (want_from and want_from < have_from)):
        runs.append({"kind": "backfill", "from": None if full else want_from, "until": have_from, "started": start})
    runs.append({"kind": "forward", "from": st["synced_until"], "until": None, "started": start})
    return runs


def cmd_update(client, args):
    root = cache_dir(args.cache)
    os.makedirs(os.path.join(root, "records"), exist_ok=True)
    state_path = os.path.join(root, "state.json")
    state = load_state(state_path)
    eps = resolve_endpoints(args.endpoints)
    fresh = [e for e in eps if "synced_until" not in state.get(e, {}) and not state.get(e, {}).get("in_progress")]
    if not args.full and not args.from_date and fresh:
        raise SystemExit("some endpoints have never been harvested: pass --from YYYY-MM-DD or --full")
    total = 0
    try:
        for ep in eps:
            st = state.setdefault(ep, {})
            rec_path = os.path.join(root, "records", f"{ep}.jsonl")
            runs = [st["in_progress"]] if st.get("in_progress") else []
            if runs:
                log(f"[{ep}] resuming interrupted {runs[0]['kind']} window")
            for run in runs:
                total += run_into_cache(client, ep, run, state, state_path, rec_path)
            for run in plan_runs(st, args.from_date, args.full):
                log(f"[{ep}] {run['kind']} from={run['from'] or 'beginning'} until={run['until'] or 'now'}")
                n = run_into_cache(client, ep, run, state, state_path, rec_path)
                log(f"[{ep}] +{n} records")
                total += n
    except KeyboardInterrupt:
        log("interrupted; progress saved, rerun the same command to resume")
    except Exception as e:
        log(f"stopped on error: {e!r}; progress saved, rerun the same command to resume")
        raise
    log(f"done: {total} records fetched")


def cmd_status(client, args):
    root = cache_dir(args.cache)
    state = load_state(os.path.join(root, "state.json"))
    print(f"cache: {root}")
    print(f"{'endpoint':9} {'covers from':12} {'synced to':11} {'lines':>8}  note")
    for ep in ENDPOINT_CODES:
        st = state.get(ep)
        if not st:
            continue
        path = os.path.join(root, "records", f"{ep}.jsonl")
        lines = sum(1 for _ in open(path, encoding="utf-8")) if os.path.exists(path) else 0
        note = "INTERRUPTED - rerun update" if st.get("in_progress") else ""
        cov = st.get("coverage_from") or ("beginning" if "synced_until" in st else "-")
        print(f"{ep:9} {cov:12} {st.get('synced_until', '-'):11} {lines:>8}  {note}")
    missing = [e for e in ENDPOINT_CODES if e not in state]
    if missing:
        print(f"never harvested: {', '.join(missing)}")


# ---------------------------------------------------------------- one-off commands

def cmd_identify(client, args):
    root = parse(client.get(endpoint_url(args.endpoint), {"verb": "Identify"}))
    for child in root.find("oai:Identify", NS):
        if child.text and child.text.strip():
            print(f"{child.tag.split('}')[-1]}: {child.text.strip()}")


def cmd_sets(client, args):
    for s in list_paged(client, args.endpoint, "ListSets", {}, "oai:set"):
        print(f"{s.findtext('oai:setSpec', default='', namespaces=NS)}\t"
              f"{s.findtext('oai:setName', default='', namespaces=NS)}")


def cmd_record(client, args):
    root = parse(client.get(endpoint_url(args.endpoint), {
        "verb": "GetRecord", "identifier": args.identifier, "metadataPrefix": "oai_dc"}))
    rec = root.find("oai:GetRecord/oai:record", NS)
    print(json.dumps(record_to_dict(rec, args.endpoint), ensure_ascii=False, indent=2))


def cmd_records(client, args):
    params = {"metadataPrefix": "oai_dc"}
    for k, v in (("set", args.set), ("from", args.from_date), ("until", args.until)):
        if v:
            params[k] = v
    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    n = 0
    try:
        for ep in resolve_endpoints(args.endpoints):
            for rec in list_paged(client, ep, "ListRecords", params, "oai:record"):
                out.write(json.dumps(record_to_dict(rec, ep), ensure_ascii=False) + "\n")
                n += 1
                if args.limit and n >= args.limit:
                    return
            out.flush()
    finally:
        if out is not sys.stdout:
            out.close()
        log(f"{n} records written")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=float, default=7.0,
                   help="seconds between requests (default 7 = ~8.5 req/min; limit is 10/min)")
    p.add_argument("--cache", help="cache directory (default $THAIJO_CACHE or ~/.thaijo)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show cache coverage")
    sp = sub.add_parser("update", help="incremental sync into the cache")
    sp.add_argument("endpoints", help="codes/groups, e.g. science, li,he05, all")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--from", dest="from_date", help="ensure coverage from YYYY-MM-DD (backfills if needed)")
    g.add_argument("--full", action="store_true", help="ensure coverage of the entire history")

    for name in ("identify", "sets", "record"):
        sp = sub.add_parser(name)
        sp.add_argument("endpoint", choices=ENDPOINT_CODES, metavar="endpoint")
        if name == "record":
            sp.add_argument("identifier")
    sp = sub.add_parser("records", help="one-off harvest to a file (not cached)")
    sp.add_argument("endpoints")
    sp.add_argument("-o", "--output")
    sp.add_argument("--set")
    sp.add_argument("--from", dest="from_date")
    sp.add_argument("--until")
    sp.add_argument("--limit", type=int)

    args = p.parse_args()
    if args.interval < 6.0:
        log(f"warning: --interval {args.interval}s exceeds 10 req/min; you risk throttling or a block")
    client = RateLimitedClient(interval=args.interval)
    {"status": cmd_status, "update": cmd_update, "identify": cmd_identify, "sets": cmd_sets,
     "record": cmd_record, "records": cmd_records}[args.cmd](client, args)


if __name__ == "__main__":
    main()
