# Apply this update to your existing repository

Extract these files at the repository root and commit them. Keep your current
companies.csv, boards.csv, discovery_state.json, and seeds.txt; this update
intentionally does not contain or overwrite them.

The next manual workflow run will import candidate ATS links from two public
India-focused sources, verify current India jobs using the ATS feeds, and
commit updated CSVs. Check the Actions run summary for candidate and verified
counts. No Brave API key is required for those two public sources. A Brave
Search API key remains optional for wider ongoing web discovery.

The source lists are candidates, not promised verified companies. The live
ATS feed and the India location check decide what reaches companies.csv.
