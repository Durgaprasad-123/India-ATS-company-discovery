# India ATS company discovery

The result is `companies.csv` in this repository. Each row contains a company label, ATS, official career page, count of current India jobs, and the time its public ATS feed was last verified. `boards.csv` retains candidate boards so a company without an India opening today can be checked again later. Neither file contains aggregator links. This project does not update the JobSift website automatically.

## Install

1. Create a GitHub repository and add **all** files here, preserving `.github/workflows/discover-companies.yml`.
2. In repository **Settings → Secrets and variables → Actions**, add a secret called `BRAVE_SEARCH_API_KEY` from [Brave Search API](https://api-dashboard.search.brave.com/app/documentation/web-search). It is optional, but **required for ongoing web discovery** beyond `seeds.txt` and the boards already saved in `boards.csv`.
3. From **Actions → Discover India ATS companies → Run workflow**, run it once. Check the resulting commit and `companies.csv`. Scheduled runs then happen at 00:17, 05:17, 10:17, 15:17, and 20:17 UTC. Those correspond to 05:47, 10:47, 15:47, 20:47, and 01:47 India time. This is five runs each UTC day; the overnight interval is four hours. GitHub schedules can start late or occasionally be skipped.

The workflow needs `contents: write` to commit the CSV. If branch protection prevents bot pushes, allow the GitHub Actions bot to write the branch or use a separate data branch/PR flow.

## How it works

- Every run checks existing boards plus `seeds.txt`, and rotates through two of ten India-focused ATS web queries when the search key is present.
- URLs found by search become *candidates*, not companies. Only exact Ashby, Lever, and Greenhouse hostnames are accepted. The three public ATS JSON feeds decide whether the board currently lists an India role.
- Successful boards with at least one India posting appear in `companies.csv`. A successful feed with zero India roles removes that board from the verified CSV. A network/API error leaves its prior verified row, with an older `last_verified_utc`, for retry.
- `boards.csv` keeps all discovered candidates. At most 300 boards are checked per run by default (`MAX_BOARDS_PER_RUN`, range 1–1000); the oldest checked candidates are polled first. At 5,000 boards, one full pass would take at least 17 runs at the default limit. Increase this only after observing runner time and provider limits.
- The CSV contains company boards rather than individual job URLs. It is a discovery registry, not a job-listing feed.

Run locally with `python scripts/discover.py`. Add ATS URLs to `seeds.txt`, one per line. Workday is deliberately excluded.

There is no guaranteed path to 500 or 1,000 verified India employers: search coverage, the number of real India openings, API availability, and your search API quota determine growth. Search results are never accepted without an ATS verification. Greenhouse location strings can omit country, so borderline postings are omitted until their location explicitly identifies India or a recognized India city.
