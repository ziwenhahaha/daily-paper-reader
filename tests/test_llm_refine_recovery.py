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
                    {"id": "p-1", "matched_requirement_index": 1, "score": 8},
                ]
            return [
                {"id": "p-1", "matched_requirement_index": 1, "score": 8},
                {"id": "p-2", "matched_requirement_index": 2, "score": 7},
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
                    {
                        "id": batch_docs[0]["id"],
                        "matched_requirement_index": 0,
                        "score": 6,
                    }
                ]
            return [
                {"id": "p-1", "matched_requirement_index": 0, "score": 6},
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=1, debug_tag="split_test")
        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertIn((("p-1",), 1), calls)
        self.assertIn((("p-2",), 1), calls)

    def test_call_filter_repeats_user_prompt_with_separator(self):
        captured = {}

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
                        '"evidence_en":"ok","evidence_cn":"相关","tldr_en":"ok","tldr_cn":"相关","score":8}]}'
                    ),
                    "parsed": {
                        "results": [
                            {
                                "id": "p-1",
                                "matched_requirement_index": 1,
                                "evidence_en": "ok",
                                "evidence_cn": "相关",
                                "tldr_en": "ok",
                                "tldr_cn": "相关",
                                "score": 8,
                            }
                        ]
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
        user_content = captured["messages"][1]["content"]
        self.assertEqual(captured["schema_name"], "rerank_batch")
        self.assertTrue(captured["strict"])
        self.assertTrue(captured["allow_json_object_fallback"])
        self.assertIn("Let me repeat that:", user_content)
        self.assertEqual(user_content.count("User requirements list:"), 2)
        self.assertEqual(user_content.count("Papers:"), 2)
        self.assertTrue(user_content.rstrip().endswith("Output must be strict JSON only, no markdown, no fences, no extra text."))


if __name__ == "__main__":
    unittest.main()
