import importlib.util
import pathlib
import requests
import sys
import unittest
from unittest.mock import patch


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.2},
            ],
            "meta": {
                "tokens": {"input_tokens": 123, "output_tokens": 4},
                "billed_units": {"input_tokens": 123, "output_tokens": 4},
            },
        }


class FakeRateLimitedResponse:
    status_code = 403
    text = '"RPM limit exceeded. Please complete identity verification to lift the restriction."'

    def raise_for_status(self):
        raise requests.HTTPError("403 Client Error")

    def json(self):
        return {}


class FakeSession:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def post(self, url, headers, json, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse()


class RerankerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.api_mod = _load_module("reranker_api_test_mod", src_dir / "reranker_api.py")
        cls.exp_mod = _load_module("rerank_size_experiment_test_mod", src_dir / "rerank_model_size_experiment.py")

    def test_siliconflow_reranker_posts_expected_payload_and_records_stats(self):
        session = FakeSession()
        reranker = self.api_mod.SiliconFlowReranker(
            api_key="test-key",
            base_url="https://example.test/v1/rerank",
            timeout=9,
            instruction="academic relevance",
            session=session,
        )

        result = reranker.rerank(
            query="graph neural networks",
            documents=["doc a", "doc b"],
            top_n=2,
            model="Qwen/Qwen3-Reranker-8B",
        )

        self.assertEqual(result["results"][0]["index"], 1)
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://example.test/v1/rerank")
        self.assertEqual(call["timeout"], 9)
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call["json"]["model"], "Qwen/Qwen3-Reranker-8B")
        self.assertEqual(call["json"]["query"], "graph neural networks")
        self.assertEqual(call["json"]["documents"], ["doc a", "doc b"])
        self.assertEqual(call["json"]["top_n"], 2)
        self.assertEqual(call["json"]["instruction"], "academic relevance")
        self.assertEqual(reranker.max_documents_per_request, 64)

        stats = reranker.stats("Qwen/Qwen3-Reranker-8B")
        self.assertEqual(stats["api_calls"], 1)
        self.assertEqual(stats["input_tokens"], 123)
        self.assertEqual(stats["output_tokens"], 4)
        self.assertEqual(stats["price_per_m_token_usd"], 0.04)
        self.assertGreaterEqual(stats["estimated_cost_usd"], 0)

    def test_siliconflow_reranker_handles_classic_model_options(self):
        session = FakeSession()
        reranker = self.api_mod.SiliconFlowReranker(
            api_key="test-key",
            base_url="https://example.test/v1/rerank",
            instruction="academic relevance",
            max_chunks_per_doc=0,
            overlap_tokens=120,
            session=session,
        )

        reranker.rerank(
            query="graph neural networks",
            documents=["doc a", "doc b"],
            top_n=0,
            model="BAAI/bge-reranker-v2-m3",
        )

        call = session.calls[0]
        self.assertEqual(call["json"]["top_n"], 1)
        self.assertNotIn("instruction", call["json"])
        self.assertEqual(call["json"]["max_chunks_per_doc"], 1)
        self.assertEqual(call["json"]["overlap_tokens"], 80)

    def test_siliconflow_reranker_retries_rpm_limit(self):
        session = FakeSession([FakeRateLimitedResponse(), FakeResponse()])
        reranker = self.api_mod.SiliconFlowReranker(
            api_key="test-key",
            base_url="https://example.test/v1/rerank",
            max_retries=1,
            retry_delay_seconds=0,
            session=session,
        )

        result = reranker.rerank(
            query="graph neural networks",
            documents=["doc a", "doc b"],
            top_n=2,
            model="Qwen/Qwen3-Reranker-0.6B",
        )

        self.assertEqual(result["results"][0]["index"], 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(reranker.stats("Qwen/Qwen3-Reranker-0.6B")["api_calls"], 2)

    def test_siliconflow_reranker_requires_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "missing SILICONFLOW_API_KEY"):
                self.api_mod.SiliconFlowReranker()

    def test_model_alias_and_overlap_helpers(self):
        self.assertEqual(
            self.exp_mod.parse_model("large=Qwen/Qwen3-Reranker-8B"),
            ("large", "Qwen/Qwen3-Reranker-8B"),
        )
        matrix = self.exp_mod.top_overlap(
            [
                {"name": "small", "top20_paper_ids": ["p1", "p2", "p3"]},
                {"name": "large", "top20_paper_ids": ["p2", "p4"]},
            ]
        )
        self.assertEqual(matrix["small"]["large"], 1)
        self.assertEqual(matrix["large"]["large"], 2)


if __name__ == "__main__":
    unittest.main()
