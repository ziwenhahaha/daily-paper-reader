import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_module():
    module_path = ROOT / "scripts" / "sync_conference_year_stats.py"
    spec = importlib.util.spec_from_file_location("sync_conference_year_stats_mod", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ConferenceYearStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_status_counts_keep_rejected_rows_visible(self):
        rows_by_table = {
            "iclr_openreview_papers": [
                {"id": "a", "source": "ICLR-2025-Accepted", "published": "2025-01-01T00:00:00Z"},
                {"id": "b", "source": "ICLR-2025-Rejected-Public", "published": "2025-01-01T00:00:00Z"},
                {"id": "c", "source": "ICLR-2025-Withdrawn-Public", "published": "2025-01-01T00:00:00Z"},
                {"id": "d", "source": "ICLR-2025-Public", "published": "2024-10-01T00:00:00Z"},
            ],
        }

        stats = self.mod.build_conference_year_stats(
            rows_by_table,
            official_counts={("iclr", 2025): 379},
            generated_at="2026-06-30T00:00:00+00:00",
        )

        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["id"], "iclr-2025")
        self.assertEqual(stats[0]["stored_total_count"], 4)
        self.assertEqual(stats[0]["stored_accepted_count"], 1)
        self.assertEqual(stats[0]["stored_rejected_count"], 1)
        self.assertEqual(stats[0]["stored_other_count"], 2)
        self.assertEqual(stats[0]["official_accepted_count"], 379)

    def test_official_count_falls_back_to_stored_accepted_count(self):
        rows_by_table = {
            "cvpr_papers": [
                {"id": "a", "source": "CVPR-2024-Accepted", "published": "2024-06-01T00:00:00Z"},
                {"id": "b", "source": "CVPR-2024-Accepted", "published": "2024-06-01T00:00:00Z"},
            ],
        }

        stats = self.mod.build_conference_year_stats(
            rows_by_table,
            official_counts={},
            generated_at="2026-06-30T00:00:00+00:00",
        )

        self.assertEqual(stats[0]["official_accepted_count"], 2)
        self.assertEqual(stats[0]["stored_total_count"], 2)

    def test_icml_public_proceedings_count_as_accepted(self):
        rows_by_table = {
            "icml_openreview_papers": [
                {"id": "a", "source": "ICML-2024-Public", "published": "2024-07-01T00:00:00Z"},
                {"id": "b", "source": "ICML-2024-Public", "published": "2024-07-01T00:00:00Z"},
            ],
        }

        stats = self.mod.build_conference_year_stats(
            rows_by_table,
            official_counts={},
            generated_at="2026-06-30T00:00:00+00:00",
        )

        self.assertEqual(stats[0]["stored_accepted_count"], 2)
        self.assertEqual(stats[0]["official_accepted_count"], 2)


if __name__ == "__main__":
    unittest.main()
