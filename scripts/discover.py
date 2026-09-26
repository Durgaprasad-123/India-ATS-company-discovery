"""Discover public ATS boards and retain companies with a live India job.

An India-filtered public company dataset supplies candidates without an API key.
BRAVE_SEARCH_API_KEY adds ongoing web discovery. Candidate ATS URLs are parsed,
never fetched; only provider-owned JSON endpoints verify live jobs. Errors
leave prior verified rows intact for the next run.
"""

import csv
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ROOT / "companies.csv"
BOARDS = ROOT / "boards.csv"
STATE = ROOT / "discovery_state.json"
SEEDS = ROOT / "seeds.txt"
PUBLIC_DATASET = "https://raw.githubusercontent.com/outscal/OpenJobs/main/data/companies_v2.json"
PUBLIC_INDIA_LIST = "https://raw.githubusercontent.com/AnojSKunte/career-ops-india/main/portals/india.yml"
COMPANY_FIELDS = ["company", "ats", "career_page", "india_jobs", "last_verified_utc"]
BOARD_FIELDS = ["ats", "slug", "career_page", "first_seen_utc", "last_checked_utc"]
QUERIES = [
    'site:jobs.ashbyhq.com "India"',
    'site:jobs.ashbyhq.com "Bengaluru"',
    'site:jobs.ashbyhq.com "Hyderabad"',
    'site:jobs.lever.co "India"',
    'site:jobs.lever.co "Pune"',
    'site:jobs.lever.co "Bangalore"',
    'site:boards.greenhouse.io "India"',
    'site:job-boards.greenhouse.io "India"',
    'site:job-boards.greenhouse.io "Mumbai"',
    'site:boards.greenhouse.io "Chennai"',
]
INDIA = re.compile(r"\b(india|bharat|bengaluru|bangalore|hyderabad|pune|mumbai|chennai|gurugram|gurgaon|noida|new delhi|delhi|kolkata|kochi|cochin|ahmedabad|jaipur)\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_json(url, headers=None, max_bytes=32_000_000):
    request = Request(url, headers={"User-Agent": "JobSiftPersonalDiscovery/1.0", "Accept": "application/json", **(headers or {})})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=18) as response:
                if int(response.headers.get("Content-Length", "0")) > max_bytes:
                    raise ValueError("Response too large")
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ValueError("Response too large")
                return json.load(io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(1 + attempt * 2)


def get_text(url, max_bytes=2_000_000):
    request = Request(url, headers={"User-Agent": "JobSiftPersonalDiscovery/1.0"})
    with urlopen(request, timeout=18) as response:
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("Public list too large")
    return payload.decode("utf-8-sig")


def parse_board(url):
    """Return (ATS, slug, canonical board URL) for allowlisted ATS hosts."""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        parts = [p for p in parsed.path.split("/") if p]
        if parsed.scheme != "https" or not parts:
            return None
        provider = {
            "jobs.ashbyhq.com": "ashby",
            "jobs.lever.co": "lever",
            "boards.greenhouse.io": "greenhouse",
            "job-boards.greenhouse.io": "greenhouse",
        }.get(host)
        slug = parts[0]
        if not provider or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", slug):
            return None
        canonical_host = "job-boards.greenhouse.io" if provider == "greenhouse" else host
        return provider, slug, f"https://{canonical_host}/{slug}"
    except ValueError:
        return None


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def key(board):
    return (board["ats"], board["slug"].lower())


def board_from_url(url):
    parsed = parse_board(url)
    if parsed:
        ats, slug, page = parsed
        return {"ats": ats, "slug": slug, "career_page": page}
    return None


def discover_search(api_key, start, count=2):
    candidates = []
    for i in range(count):
        query = QUERIES[(start + i) % len(QUERIES)]
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 20, "country": "IN"})
        try:
            data = get_json(url, {"X-Subscription-Token": api_key})
            candidates.extend(item.get("url", "") for item in data.get("web", {}).get("results", []))
        except Exception as exc:
            print(f"Search failed for {query}: {exc}", file=sys.stderr)
        time.sleep(1)
    return candidates


def candidates_from_dataset(records):
    """Import only direct ATS links for companies historically seen hiring in India.

    The source is a candidate list. Each board still needs a current India job
    from its own ATS feed before it enters companies.csv.
    """
    if isinstance(records, dict):
        records = records.get("companies") or records.get("data")
    if not isinstance(records, list):
        raise ValueError("Unexpected public dataset format")
    candidates = []
    for company in records:
        if not isinstance(company, dict):
            continue
        countries = company.get("countries") or []
        if not isinstance(countries, list) or not any(isinstance(c, str) and c.casefold() == "india" for c in countries):
            continue
        for field in ("ats_links", "list_urls"):
            links = company.get(field) or []
            if isinstance(links, str):
                links = [links]
            if isinstance(links, list):
                candidates.extend(link for link in links if isinstance(link, str) and parse_board(link))
    return candidates


def candidates_from_india_yaml(content):
    """Accept ATS board URLs or provider/slug entries from a public YAML list."""
    document = yaml.safe_load(content)
    candidates = []
    hosts = {
        "ashby": "jobs.ashbyhq.com",
        "lever": "jobs.lever.co",
        "greenhouse": "job-boards.greenhouse.io",
    }

    def walk(node, provider=None, slug_value=False):
        if isinstance(node, str):
            if parse_board(node):
                candidates.append(node)
            elif slug_value and provider in hosts and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", node):
                candidates.append(f"https://{hosts[provider]}/{node}")
        elif isinstance(node, list):
            for value in node:
                walk(value, provider, slug_value)
        elif isinstance(node, dict):
            declared = str(node.get("ats") or node.get("provider") or node.get("source") or "").lower()
            provider = declared if declared in hosts else provider
            is_record = any(k in node for k in ("slug", "board", "board_token", "site", "ats", "provider", "source", "name"))
            for field in ("slug", "board", "board_token", "site"):
                if isinstance(node.get(field), str):
                    walk(node[field], provider, True)
            for field in ("url", "careers_url", "board_url"):
                if isinstance(node.get(field), str):
                    walk(node[field])
            for field, value in node.items():
                if field in ("slug", "board", "board_token", "site", "url", "careers_url", "board_url",
                             "ats", "provider", "source", "name", "description", "id"):
                    continue
                child_provider = str(field).lower() if str(field).lower() in hosts else provider
                walk(value, child_provider, str(field).lower() in hosts or (slug_value and not is_record))

    walk(document)
    return list(dict.fromkeys(candidates))


def india_location(value):
    if not value:
        return False
    if isinstance(value, dict):
        country = value.get("addressCountry") or value.get("country")
        if isinstance(country, str) and country.strip():
            return country.strip().lower() in ("in", "ind", "india")
        return any(india_location(v) for v in value.values())
    if isinstance(value, list):
        return any(india_location(v) for v in value)
    return isinstance(value, str) and bool(INDIA.search(value))


def india_jobs(board, data):
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        raise ValueError("Unexpected ATS response")
    matches = set()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        provider = board["ats"]
        if provider == "ashby":
            if job.get("isListed") is False:
                continue
            places = [job.get("address"), job.get("location"), job.get("secondaryLocations")]
            valid_url = job.get("jobUrl")
        elif provider == "lever":
            categories = job.get("categories") or {}
            places = [categories.get("location"), categories.get("allLocations"), job.get("workplaceType")]
            valid_url = job.get("hostedUrl")
        else:
            places = [job.get("location"), job.get("offices")]
            valid_url = job.get("absolute_url")
        if valid_url and any(india_location(place) for place in places):
            matches.add(str(job.get("id") or valid_url))
    return len(matches)


def api_url(board):
    slug = quote(board["slug"], safe="")
    return {
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    }[board["ats"]]


def verify(board):
    return india_jobs(board, get_json(api_url(board)))


def company_name(slug):
    # The ATS slugs aren't always brand names. This is a display label only.
    label = slug.replace("_", " ").replace("-", " ").strip().title()
    return label if label[:1] not in ("=", "+", "-", "@") else "'" + label


def main():
    timestamp = now()
    existing_boards = {(r["ats"], r["slug"].lower()): r for r in read_csv(BOARDS)}
    companies = {r["career_page"]: r for r in read_csv(COMPANIES)}
    state = json.loads(STATE.read_text()) if STATE.exists() else {"next_query": 0}
    candidates = [r.get("career_page", "") for r in existing_boards.values()]
    candidates += [line.strip() for line in SEEDS.read_text().splitlines() if line.strip() and not line.startswith("#")]
    source_ok = False
    try:
        public_candidates = candidates_from_dataset(get_json(PUBLIC_DATASET))
        if not public_candidates:
            raise ValueError("Dataset contained no supported India ATS links; check upstream schema")
        candidates += public_candidates
        source_ok = True
        print(f"Public India dataset supplied {len(public_candidates)} ATS links before deduplication")
    except Exception as exc:
        print(f"Public dataset unavailable; retaining saved boards and seeds: {exc}", file=sys.stderr)
    try:
        india_candidates = candidates_from_india_yaml(get_text(PUBLIC_INDIA_LIST))
        if not india_candidates:
            raise ValueError("India YAML list contained no supported ATS boards")
        candidates += india_candidates
        source_ok = True
        print(f"India ATS list supplied {len(india_candidates)} boards before deduplication")
    except Exception as exc:
        print(f"India ATS list unavailable; retaining other candidates: {exc}", file=sys.stderr)
    search_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if search_key:
        candidates += discover_search(search_key, state["next_query"])
        state["next_query"] = (state["next_query"] + 2) % len(QUERIES)
    else:
        print("No BRAVE_SEARCH_API_KEY: checking public dataset, saved boards and seeds only")

    for url in candidates:
        board = board_from_url(url)
        if board and key(board) not in existing_boards:
            existing_boards[key(board)] = {**board, "first_seen_utc": timestamp, "last_checked_utc": ""}

    boards = list(existing_boards.values())
    # Oldest checked first prevents fresh candidates starving when the registry grows.
    boards.sort(key=lambda b: (b.get("last_checked_utc", ""), b["ats"], b["slug"].lower()))
    max_boards = min(max(int(os.environ.get("MAX_BOARDS_PER_RUN", "300")), 1), 1000)
    checked = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(verify, board): board for board in boards[:max_boards]}
        for future in as_completed(futures):
            board = futures[future]
            try:
                count = future.result()
            except Exception as exc:
                print(f"Verification failed: {board['career_page']}: {exc}", file=sys.stderr)
                continue
            checked += 1
            board["last_checked_utc"] = timestamp
            page = board["career_page"]
            if count:
                old = companies.get(page, {})
                companies[page] = {
                    "company": old.get("company") or company_name(board["slug"]),
                    "ats": board["ats"],
                    "career_page": page,
                    "india_jobs": count,
                    "last_verified_utc": timestamp,
                }
            else:
                companies.pop(page, None)

    write_csv(BOARDS, BOARD_FIELDS, sorted(boards, key=lambda b: (b["ats"], b["slug"].lower())))
    write_csv(COMPANIES, COMPANY_FIELDS, sorted(companies.values(), key=lambda c: (c["company"].lower(), c["ats"])))
    STATE.write_text(json.dumps(state, sort_keys=True) + "\n")
    summary = f"Checked {checked}/{min(len(boards), max_boards)} boards; {len(companies)} verified India companies; {len(boards)} candidate boards; public list discovery {'OK' if source_ok else 'FAILED'}"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as report:
            report.write("## India ATS discovery\n\n" + summary + "\n")
    if not source_ok and not search_key:
        raise RuntimeError("No keyless discovery source available; see public list errors above")


if __name__ == "__main__":
    main()
