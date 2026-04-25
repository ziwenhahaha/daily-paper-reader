import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llm import LLMClient


class LlmStructuredOutputTest(unittest.TestCase):
    def _mock_success_response(self, message: dict):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "choices": [
                {
                    "message": message,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
        return resp

    def _mock_http_error_response(self, text: str, status_code: int = 400):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"HTTP {status_code}",
            response=resp,
        )
        return resp

    @patch("llm.requests.post")
    def test_chat_structured_falls_back_to_json_object(self, mock_post):
        mock_post.side_effect = [
            self._mock_http_error_response(
                '{"error":{"message":"response_format json_schema is not supported"}}'
            ),
            self._mock_success_response({"content": '{"answer":"ok"}'}),
        ]
        client = LLMClient(
            api_key="test-key",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
        )

        result = client.chat_structured(
            messages=[{"role": "user", "content": "hello"}],
            schema_name="answer_payload",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result["response_format_used"], "json_object")
        self.assertEqual(result["parsed"], {"answer": "ok"})
        self.assertEqual(
            [call.kwargs["json"]["response_format"]["type"] for call in mock_post.call_args_list],
            ["json_schema", "json_object"],
        )

    @patch("llm.requests.post")
    def test_chat_structured_falls_back_for_deepseek_style_enum_error(self, mock_post):
        mock_post.side_effect = [
            self._mock_http_error_response(
                '{"error":{"message":"response_format.type must be one of text or json_object"}}'
            ),
            self._mock_success_response({"content": '{"answer":"ok"}'}),
        ]
        client = LLMClient(
            api_key="test-key",
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
        )

        result = client.chat_structured(
            messages=[{"role": "user", "content": "hello"}],
            schema_name="answer_payload",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result["response_format_used"], "json_object")
        self.assertEqual(result["parsed"], {"answer": "ok"})
        self.assertEqual(
            [call.kwargs["json"]["response_format"]["type"] for call in mock_post.call_args_list],
            ["json_schema", "json_object"],
        )

    @patch("llm.requests.post")
    def test_chat_structured_returns_refusal(self, mock_post):
        mock_post.return_value = self._mock_success_response(
            {"refusal": "I'm sorry, I cannot assist with that request."}
        )
        client = LLMClient(
            api_key="test-key",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
        )

        result = client.chat_structured(
            messages=[{"role": "user", "content": "hello"}],
            schema_name="answer_payload",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(
            result["refusal"],
            "I'm sorry, I cannot assist with that request.",
        )
        self.assertIsNone(result["parsed"])
        self.assertIsNone(result["parse_error"])


if __name__ == "__main__":
    unittest.main()
