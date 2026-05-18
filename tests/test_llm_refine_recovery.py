import importlib.util
import json
import pathlib
import sys
import tempfile
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

    def test_process_file_skips_seen_before_api_key_lookup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            archive_root = root / "archive"
            recommend_dir = archive_root / "20260517" / "recommend"
            recommend_dir.mkdir(parents=True, exist_ok=True)
            (recommend_dir / "arxiv_papers_20260517.standard.json").write_text(
                json.dumps(
                    {
                        "deep_dive": [
                            {
                                "id": "paper-gene",
                                "matched_query_tag": "query:GENE",
                            }
                        ],
                        "quick_skim": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            input_path = root / "ranked.json"
            output_path = root / "out.json"
            input_path.write_text(
                json.dumps(
                    {
                        "papers": [
                            {
                                "id": "paper-gene",
                                "title": "Seen Paper",
                                "abstract": "Already recommended.",
                            }
                        ],
                        "queries": [
                            {
                                "type": "intent_query",
                                "ranked": [
                                    {
                                        "paper_id": "paper-gene",
                                        "star_rating": 5,
                                    }
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            old_archive_root = self.mod.ARCHIVE_ROOT
            old_today_str = self.mod.TODAY_STR
            old_load_config = self.mod.load_config
            old_first_env = self.mod.first_env
            self.mod.ARCHIVE_ROOT = str(archive_root)
            self.mod.TODAY_STR = "20260518"
            self.mod.load_config = lambda: {
                "subscriptions": {
                    "intent_profiles": [
                        {
                            "tag": "GENE",
                            "keywords": [{"keyword": "gene therapy"}],
                        }
                    ]
                }
            }

            def fail_first_env(*args):
                raise AssertionError("API key lookup should be skipped when all candidates are seen")

            self.mod.first_env = fail_first_env
            try:
                self.mod.process_file(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    min_star=4,
                    batch_size=10,
                    max_chars=850,
                    filter_model="test-model",
                    max_output_tokens=128,
                    filter_concurrency=1,
                )
            finally:
                self.mod.ARCHIVE_ROOT = old_archive_root
                self.mod.TODAY_STR = old_today_str
                self.mod.load_config = old_load_config
                self.mod.first_env = old_first_env

            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertNotIn("llm_ranked", payload)


if __name__ == "__main__":
    unittest.main()
