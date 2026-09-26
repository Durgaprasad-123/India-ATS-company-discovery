import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discover
from discover import board_from_url, candidates_from_dataset, candidates_from_india_yaml, india_jobs, india_location, parse_board


class DiscoveryTests(unittest.TestCase):
    def test_allowlist_and_canonicalization(self):
        self.assertEqual(parse_board("https://boards.greenhouse.io/acme/jobs/123"),
                         ("greenhouse", "acme", "https://job-boards.greenhouse.io/acme"))
        self.assertIsNone(parse_board("https://jobs.lever.co.evil.org/acme"))
        self.assertIsNone(parse_board("http://jobs.lever.co/acme"))
        self.assertEqual(board_from_url("https://jobs.ashbyhq.com/ACME/abc")["slug"], "ACME")

    def test_location_metadata_and_remote(self):
        self.assertTrue(india_location({"postalAddress": {"addressCountry": "IN", "addressLocality": "Bengaluru"}}))
        self.assertFalse(india_location("Remote — Anywhere"))
        self.assertFalse(india_location({"addressCountry": "US", "addressLocality": "India Street"}))

    def test_public_dataset_supplies_only_direct_india_ats_candidates(self):
        rows = [
            {"name": "A", "countries": ["India"], "ats_links": ["https://boards.greenhouse.io/alpha/jobs/3"],
             "list_urls": ["https://www.linkedin.com/jobs/view/3"]},
            {"name": "B", "countries": ["United States"], "ats_links": ["https://jobs.lever.co/bravo"]},
            {"name": "C", "countries": ["India"], "list_urls": ["https://jobs.ashbyhq.com/charlie"]},
        ]
        self.assertEqual(candidates_from_dataset({"companies": rows}), [
            "https://boards.greenhouse.io/alpha/jobs/3", "https://jobs.ashbyhq.com/charlie",
        ])

    def test_india_yaml_accepts_provider_slugs_and_direct_urls(self):
        content = """
greenhouse:
  - name: Alpha
    slug: alpha
lever:
  Beta: beta
tracked_companies:
  - name: Charlie
    provider: ashby
    slug: charlie
  - name: Delta
    careers_url: https://jobs.lever.co/delta
"""
        self.assertEqual(candidates_from_india_yaml(content), [
            "https://job-boards.greenhouse.io/alpha", "https://jobs.lever.co/beta",
            "https://jobs.ashbyhq.com/charlie", "https://jobs.lever.co/delta",
        ])

    def test_provider_feeds(self):
        ashby = {"ats": "ashby"}
        self.assertEqual(india_jobs(ashby, {"jobs": [
            {"id": "1", "jobUrl": "https://jobs.ashbyhq.com/x/1", "location": "India", "isListed": True},
            {"id": "2", "jobUrl": "https://jobs.ashbyhq.com/x/2", "location": "India", "isListed": False},
        ]}), 1)

    def test_end_to_end_keeps_previous_row_on_api_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "seeds.txt").write_text("https://jobs.lever.co/acme\nhttps://jobs.lever.co/acme/jobs/1\n")
            paths = {
                "COMPANIES": root / "companies.csv", "BOARDS": root / "boards.csv",
                "STATE": root / "discovery_state.json", "SEEDS": root / "seeds.txt",
            }
            with patch.multiple(discover, **paths), patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": ""}):
                dataset = [{"name": "Acme", "countries": ["India"], "ats_links": ["https://jobs.lever.co/acme"]}]
                feed = [{"id": "1", "hostedUrl": "https://jobs.lever.co/acme/1",
                         "categories": {"location": "Bengaluru, India"}}]
                with patch.object(discover, "get_text", return_value="lever:\n  - acme\n"):
                    with patch.object(discover, "get_json", side_effect=[dataset, feed]):
                        discover.main()
                self.assertEqual(len(discover.read_csv(paths["COMPANIES"])), 1)
                self.assertEqual(len(discover.read_csv(paths["BOARDS"])), 1)
                with patch.object(discover, "get_text", return_value="lever:\n  - acme\n"):
                    with patch.object(discover, "get_json", side_effect=[dataset, TimeoutError("temporary")]):
                        discover.main()
                self.assertEqual(len(discover.read_csv(paths["COMPANIES"])), 1)
        lever = {"ats": "lever"}
        self.assertEqual(india_jobs(lever, [{"id": "1", "hostedUrl": "https://jobs.lever.co/x/1",
                                            "categories": {"allLocations": ["Hyderabad", "London"]}}]), 1)
        greenhouse = {"ats": "greenhouse"}
        self.assertEqual(india_jobs(greenhouse, {"jobs": [
            {"id": 1, "absolute_url": "https://job-boards.greenhouse.io/x/jobs/1", "location": {"name": "Remote — India"}},
            {"id": 2, "absolute_url": "https://job-boards.greenhouse.io/x/jobs/2", "location": {"name": "Remote — US"}},
        ]}), 1)


if __name__ == "__main__":
    unittest.main()
