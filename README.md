# India ATS company discovery

The result is `companies.csv` in this repository. Each row contains a company label, ATS, official career page, count of current India jobs, and the time its public ATS feed was last verified. `boards.csv` retains candidate boards so a company without an India opening today can be checked again later. Neither file contains aggregator links. This project does not update the JobSift website automatically.

## Install

1. Create a GitHub repository and add **all** files here, preserving `.github/workflows/discover-companies.yml`.
2. No API key is required for the first wave: each run imports direct ATS links from [OpenJobs' public India company dataset](https://github.com/outscal/OpenJobs) and an [India ATS board list](https://github.com/AnojSKunte/career-ops-india). To discover additional boards across the web as well, add a `BRAVE_SEARCH_API_KEY` secret in repository **Settings → Secrets and variables → Actions**, using [Brave Search API](https://api-dashboard.search.brave.com/app/documentation/web-search).
3. From **Actions → Discover India ATS companies → Run workflow**, run it once. Check the resulting commit and `companies.csv`. Scheduled runs then happen at 00:17, 05:17, 10:17, 15:17, and 20:17 UTC. Those correspond to 05:47, 10:47, 15:47, 20:47, and 01:47 India time. This is five runs each UTC day; the overnight interval is four hours. GitHub schedules can start late or occasionally be skipped.

The workflow needs `contents: write` to commit the CSV. If branch protection prevents bot pushes, allow the GitHub Actions bot to write the branch or use a separate data branch/PR flow.

## How it works

- Every run checks existing boards plus `seeds.txt`, imports ATS links for companies historically associated with India in the public OpenJobs dataset, and imports another India-focused board list. When a Brave key is present, it also rotates through two of ten India-focused ATS web queries.
- URLs found by search become *candidates*, not companies. Only exact Ashby, Lever, and Greenhouse hostnames are accepted. The three public ATS JSON feeds decide whether the board currently lists an India role.
- Successful boards with at least one India posting appear in `companies.csv`. A successful feed with zero India roles removes that board from the verified CSV. A network/API error leaves its prior verified row, with an older `last_verified_utc`, for retry.
- `boards.csv` keeps all discovered candidates. At most 300 boards are checked per run by default (`MAX_BOARDS_PER_RUN`, range 1–1000); the oldest checked candidates are polled first. At 5,000 boards, one full pass would take at least 17 runs at the default limit. Increase this only after observing runner time and provider limits.
- The CSV contains company boards rather than individual job URLs. It is a discovery registry, not a job-listing feed.

Run locally with `pip install -r requirements.txt` followed by `python scripts/discover.py`. Add ATS URLs to `seeds.txt`, one per line. Workday is deliberately excluded.

The public dataset's `countries` field is historical and only narrows candidate boards; it never counts as verification. Without a search key, new company discovery depends on those public lists being updated or on `seeds.txt`; the known boards are still rechecked every run. There is no guaranteed path to 500 or 1,000 currently verified India employers: live openings and ATS coverage determine the count. Search results are never accepted without an ATS verification. Greenhouse location strings can omit country, so borderline postings are omitted until their location explicitly identifies India or a recognized India city.
