from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import topic_preview as preview


class PreviewTests(unittest.TestCase):
    def test_keyword_is_bm25_and_query_is_only_compatibility_fallback(self):
        self.assertEqual(
            preview.english_groups(
                {
                    "keywords": [
                        {"keyword": "RL", "query": "offline reinforcement learning"}
                    ]
                }
            ),
            [["RL"]],
        )
        self.assertEqual(
            preview.english_groups(
                {"keywords": [{"query": "offline reinforcement learning"}]}
            ),
            [["offline reinforcement learning"]],
        )

    def setUp(self):
        preview._CACHE.clear()

    def run_preview(self, values, mode="90", profile=None):
        responses = [
            Mock(status_code=200, headers={"Content-Range": value}) for value in values
        ]
        call = Mock(side_effect=responses)
        with patch.object(
            preview,
            "backend_for",
            return_value=(
                "https://example.invalid/rest/v1/arxiv_papers",
                "sb_publishable_test",
                "public",
            ),
        ):
            result = preview.preview(
                profile=profile or {"keywords": ["ATSP", "asymmetric TSP"]},
                mode=mode,
                as_of="2026-09-12",
                request=call,
            )
        return result, call

    def test_exact_counts_from_headers_not_returned_rows(self):
        result, call = self.run_preview(["0-0/600", "0-0/500", "0-0/100"])
        self.assertEqual((result["status"], result["count"]), ("exact", 1200))
        self.assertEqual(call.call_count, 3)
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Prefer"], "count=exact")
        self.assertEqual(kwargs["params"]["limit"], "1")
        self.assertNotIn("Authorization", kwargs["headers"])

    def test_lower_bound_stops_recent_window(self):
        result, call = self.run_preview(["0-0/1501"])
        self.assertEqual((result["status"], result["count"]), ("lower_bound", 1501))
        self.assertEqual(call.call_count, 1)
        self.assertIn("published.lt.2026-09-12", call.call_args.kwargs["params"]["and"])

    def test_missing_header_is_unknown_not_zero(self):
        result, _ = self.run_preview(["0-999/*"])
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["count"])

    def test_starter_arxiv_complete_is_still_partial(self):
        result, _ = self.run_preview(["*/0"] * 13, mode="starter")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"]["arxiv"]["status"], "exact")
        self.assertEqual(result["coverage"]["conference"]["status"], "unavailable")

    def test_chinese_not_sent_to_english_fts(self):
        result, call = self.run_preview([], profile={"keywords": ["强化学习"]})
        self.assertEqual(result["status"], "unknown")
        call.assert_not_called()

    def test_boolean_groups_and_escaping(self):
        groups = preview.english_groups(
            {
                "constraint_groups": [
                    ["ATSP", "asymmetric TSP"],
                    ["approximation", "ratio"],
                ]
            }
        )
        text = preview.count_filter(groups, "2026-01-01", "2026-02-01")
        self.assertEqual(text.count("or("), 2)
        self.assertIn('search_tsv.plfts(english)."asymmetric TSP"', text)
        self.assertIn('\\"', preview.count_filter([['a"),evil']], "a", "b"))

    def test_service_secret_keys_rejected(self):
        import base64
        import json

        jwt = (
            "a."
            + base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode())
            .decode()
            .rstrip("=")
            + ".z"
        )
        self.assertFalse(preview.public_key(jwt))
        self.assertFalse(preview.public_key("sb_secret_test"))
        self.assertTrue(preview.public_key("sb_publishable_test"))

    def test_nonoverlapping_calendar_and_leap_boundary(self):
        result, call = self.run_preview(["*/0"] * 3)
        filters = [c.kwargs["params"]["and"] for c in call.call_args_list]
        self.assertIn("published.gte.2026-08-13", filters[0])
        self.assertIn("published.lt.2026-08-13", filters[1])
        self.assertEqual(
            preview.scope_for("starter", "2024-02-29")["conference"]["start"],
            "2022-02-28",
        )

    def test_short_cache_avoids_repeated_requests(self):
        first, call = self.run_preview(["0-0/1501"])
        second, no_call = self.run_preview([])
        self.assertEqual(first, second)
        no_call.assert_not_called()
        self.assertNotIn("sb_publishable", str(second))

    def test_custom_threshold_and_cache_identity(self):
        response = Mock(status_code=200, headers={"Content-Range": "0-0/400"})
        call = Mock(return_value=response)
        with patch.object(
            preview,
            "backend_for",
            return_value=(
                "https://example.invalid/rest/v1/arxiv_papers",
                "sb_publishable_test",
                "public",
            ),
        ):
            args = dict(
                profile={"keywords": ["ATSP"]},
                mode="90",
                as_of="2026-09-12",
                request=call,
            )
            first = preview.preview(
                **args, config={"topic_research": {"preview_threshold": 300}}
            )
            self.assertEqual(
                (first["threshold"], first["status"]), (300, "lower_bound")
            )
            self.assertEqual(call.call_count, 1)
            second = preview.preview(
                **args,
                threshold=1500,
                config={"topic_research": {"preview_threshold": 300}}
            )
            self.assertEqual((second["threshold"], second["status"]), (1500, "exact"))
            self.assertEqual(call.call_count, 4)
            for invalid in (0, 10001, True, "1abc", float("nan"), 1.5):
                result = preview.preview(**args, threshold=invalid)
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["threshold"])
            self.assertEqual(call.call_count, 4)

    def test_explicit_group_limits_match_backend(self):
        for groups in ([["ATSP"]] * 4, [["a"] * 9], [["a"] * 4, ["b"] * 3, ["c"] * 3]):
            with self.assertRaises(ValueError):
                preview.english_groups({"constraint_groups": groups})
        self.assertEqual(
            len(
                preview.english_groups(
                    {"keywords": ["word" + str(i) for i in range(24)]}
                )[0]
            ),
            24,
        )
        with self.assertRaises(ValueError):
            preview.english_groups({"keywords": ["word" + str(i) for i in range(25)]})


if __name__ == "__main__":
    unittest.main()
