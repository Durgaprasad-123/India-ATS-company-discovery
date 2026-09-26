import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discover
from discover import board_from_url, india_jobs, india_location, parse_board


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
                with patch.object(discover, "get_json", return_value=[
                    {"id": "1", "hostedUrl": "https://jobs.lever.co/acme/1",
                     "categories": {"location": "Bengaluru, India"}},
                ]):
                    discover.main()
                self.assertEqual(len(discover.read_csv(paths["COMPANIES"])), 1)
                self.assertEqual(len(discover.read_csv(paths["BOARDS"])), 1)
                with patch.object(discover, "get_json", side_effect=TimeoutError("temporary")):
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
