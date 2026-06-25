import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class LlmRefineRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("llm_refine_mod_recovery", src_dir / "4.llm_refine_papers.py")

    def relevant_result(self, paper_id="p-1", score=8):
        return {
            "id": paper_id,
            "matched_requirement_index": 1,
            "evidence_en": "relevant method",
            "tldr_en": "This paper is relevant because it studies a method that matches the requested research direction and provides useful technical evidence. It explains the core problem and technical approach, and offers experimental or theoretical grounds for judging relevance.",
            "motivation_en": "The motivation directly addresses the user's search requirement and the key shortcomings of current methods on the target task.",
            "method_en": "The method centers on the technical core of the requirement, with a clear modeling idea, algorithm flow, or implementation strategy.",
            "result_en": "The results show the method achieves effective improvements on related tasks or experimental settings, with further reference value.",
            "conclusion_en": "The conclusion indicates the direction is worth further exploration and provides reusable ideas for the user's problem.",
            "score": score,
        }

    def test_recover_filter_results_retries_for_missing_ids(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            calls.append((tuple(item["id"] for item in batch_docs), attempt, retry_note))
            if attempt == 1:
                return [
                    self.relevant_result("p-1"),
                ]
            return [
                self.relevant_result("p-1"),
                self.relevant_result("p-2", score=7),
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=2, debug_tag="batch_test")
        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertEqual(len(calls), 2)
        self.assertIn("p-1, p-2", calls[1][2])
        self.assertIn("missing ids=p-2", calls[1][2])

    def test_recover_filter_results_split_batch_after_retry_exhausted(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            doc_ids = tuple(item["id"] for item in batch_docs)
            calls.append((doc_ids, attempt))
            if len(batch_docs) == 1:
                return [
                    self.relevant_result(batch_docs[0]["id"], score=6)
                ]
            return [
                self.relevant_result("p-1", score=6),
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=1, debug_tag="split_test")
        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertIn((("p-1",), 1), calls)
        self.assertIn((("p-2",), 1), calls)

    def test_recover_filter_results_splits_immediately_on_truncated_output(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            doc_ids = tuple(item["id"] for item in batch_docs)
            calls.append((doc_ids, attempt))
            if len(batch_docs) > 1:
                raise self.mod.FilterOutputTruncatedError("unexpected finish_reason: length")
            return [
                self.relevant_result(batch_docs[0]["id"], score=6)
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=3, debug_tag="length_test")

        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertEqual(calls.count((("p-1", "p-2"), 1)), 1)
        self.assertNotIn((("p-1", "p-2"), 2), calls)
        self.assertIn((("p-1",), 1), calls)
        self.assertIn((("p-2",), 1), calls)

    def test_recover_filter_results_accepts_short_best_effort_fields(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            calls.append((tuple(item["id"] for item in batch_docs), attempt, retry_note))
            return [
                {
                    **self.relevant_result("p-1", score=8),
                    "tldr_en": "Relevant, but the abstract has limited information.",
                    "motivation_en": "Limited information.",
                    "method_en": "Limited information.",
                    "result_en": "Limited information.",
                    "conclusion_en": "Limited information.",
                }
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=3, debug_tag="short_test")

        self.assertEqual(out[0]["id"], "p-1")
        self.assertEqual(out[0]["tldr_en"], "Relevant, but the abstract has limited information.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 1)
        self.assertEqual(calls[0][2], "")

    def test_call_filter_repeats_user_prompt_with_separator(self):
        captured = {}
        test_case = self

        class FakeClient:
            model = "gemini-3-flash-preview-nothinking"

            def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
                captured["messages"] = messages
                captured["schema_name"] = schema_name
                captured["schema"] = schema
                captured["strict"] = strict
                captured["allow_json_object_fallback"] = allow_json_object_fallback
                return {
                    "content": (
                        '{"results":[{"id":"p-1","matched_requirement_index":1,'
                        '"evidence_en":"ok","tldr_en":"ok","score":8}]}'
                    ),
                    "parsed": {
                        "results": [test_case.relevant_result("p-1")]
                    },
                    "parse_error": None,
                    "refusal": "",
                    "finish_reason": "stop",
                }

        out = self.mod.call_filter(
            client=FakeClient(),
            all_requirements=[
                {
                    "id": "req-1",
                    "query": "symbolic regression methods",
                    "tag": "query:sr",
                    "kind": "direct",
                    "description_en": "Find papers relevant to symbolic regression methods",
                }
            ],
            docs=[{"id": "p-1", "content": "Title: A\nAbstract: B"}],
            debug_dir="",
            debug_tag="prompt_test",
        )

        self.assertEqual(out[0]["id"], "p-1")
        self.assertIn("The method centers on", out[0]["method_en"])
        user_content = captured["messages"][1]["content"]
        self.assertEqual(captured["schema_name"], "rerank_batch")
        self.assertTrue(captured["strict"])
        self.assertTrue(captured["allow_json_object_fallback"])
        self.assertIn("Let me repeat that:", user_content)
        self.assertEqual(user_content.count("User requirements list:"), 2)
        self.assertEqual(user_content.count("Papers:"), 2)
        self.assertIn("method_en", user_content)
        self.assertNotIn("title_zh", user_content)
        self.assertIn("60-90 words", user_content)
        self.assertIn("15-35 words", user_content)
        self.assertIn("length targets are guidance", user_content)
        self.assertIn("same style as a paper-page TLDR abstract", user_content)
        self.assertNotIn("Chinese characters", user_content)
        self.assertTrue(user_content.rstrip().endswith("Output must be strict JSON only, no markdown, no fences, no extra text."))


if __name__ == "__main__":
    unittest.main()
