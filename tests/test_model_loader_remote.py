import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import requests

from src.model_loader import RemoteSentenceTransformer, load_sentence_transformer


class RemoteSentenceTransformerTest(unittest.TestCase):
    @patch("src.model_loader.requests.post")
    def test_remote_encode_batches_and_normalizes(self, mock_post):
        resp1 = MagicMock()
        resp1.raise_for_status.return_value = None
        resp1.json.return_value = {
            "embeddings": [
                [3.0, 4.0],
                [0.0, 5.0],
            ]
        }
        resp2 = MagicMock()
        resp2.raise_for_status.return_value = None
        resp2.json.return_value = {
            "embeddings": [
                [8.0, 6.0],
            ]
        }
        mock_post.side_effect = [resp1, resp2]

        model = RemoteSentenceTransformer(
            model_name="BAAI/bge-small-en-v1.5",
            endpoint="https://embed.zwwen.online",
            api_key="test-key",
            timeout=30,
            default_batch_size=2,
        )
        arr = model.encode(
            ["a", "b", "c"],
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=2,
        )

        self.assertEqual(arr.shape, (3, 2))
        np.testing.assert_allclose(arr[0], np.asarray([0.6, 0.8], dtype=np.float32), atol=1e-6)
        np.testing.assert_allclose(arr[1], np.asarray([0.0, 1.0], dtype=np.float32), atol=1e-6)
        np.testing.assert_allclose(arr[2], np.asarray([0.8, 0.6], dtype=np.float32), atol=1e-6)
        self.assertEqual(mock_post.call_count, 2)
        first_call = mock_post.call_args_list[0]
        self.assertEqual(first_call.kwargs["json"], {"texts": ["a", "b"]})
        self.assertEqual(first_call.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(first_call.kwargs["timeout"], 30)

    @patch("src.model_loader._load_local_sentence_transformer")
    @patch("src.model_loader.requests.post")
    def test_remote_encode_falls_back_to_local_model_when_remote_fails(self, mock_post, mock_load_local):
        mock_post.side_effect = requests.exceptions.Timeout("remote timeout")
        local_model = MagicMock()
        local_model.encode.return_value = np.asarray([[0.1, 0.2]], dtype=np.float32)
        mock_load_local.return_value = local_model

        model = RemoteSentenceTransformer(
            model_name="BAAI/bge-small-en-v1.5",
            endpoint="https://embed.zwwen.online",
            api_key="test-key",
            timeout=30,
            default_batch_size=2,
        )
        arr = model.encode(
            ["a"],
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=2,
        )

        self.assertEqual(mock_post.call_count, 1)
        mock_load_local.assert_called_once()
        local_model.encode.assert_called_once()
        self.assertEqual(arr.shape, (1, 2))

    @patch("src.model_loader._load_local_sentence_transformer")
    @patch("src.model_loader.requests.post")
    def test_remote_failure_disables_remote_for_later_calls(self, mock_post, mock_load_local):
        mock_post.side_effect = requests.exceptions.Timeout("remote timeout")
        local_model = MagicMock()
        local_model.encode.side_effect = [
            np.asarray([[0.1, 0.2]], dtype=np.float32),
            np.asarray([[0.3, 0.4]], dtype=np.float32),
        ]
        mock_load_local.return_value = local_model

        model = RemoteSentenceTransformer(
            model_name="BAAI/bge-small-en-v1.5",
            endpoint="https://embed.zwwen.online",
            api_key="test-key",
            timeout=30,
            default_batch_size=2,
        )

        arr1 = model.encode(["a"], convert_to_numpy=True, normalize_embeddings=True, batch_size=2)
        arr2 = model.encode(["b"], convert_to_numpy=True, normalize_embeddings=True, batch_size=2)

        self.assertEqual(mock_post.call_count, 1)
        mock_load_local.assert_called_once()
        self.assertEqual(local_model.encode.call_count, 2)
        self.assertFalse(model._remote_available)
        self.assertEqual(arr1.shape, (1, 2))
        self.assertEqual(arr2.shape, (1, 2))

    @patch.dict(
        os.environ,
        {
            "DPR_EMBED_API_TIMEOUT": "45",
        },
        clear=False,
    )
    def test_load_sentence_transformer_returns_remote_wrapper_with_fixed_key(self):
        model = load_sentence_transformer("BAAI/bge-small-en-v1.5", device="cpu")
        self.assertTrue(getattr(model, "is_remote", False))
        self.assertEqual(model.model_name, "BAAI/bge-small-en-v1.5")
        self.assertEqual(model.endpoint, "https://embed.zwwen.online/embed")
        self.assertEqual(model.timeout, 45)
        self.assertEqual(
            model.api_key,
            "26932a86d772001af60cbd9d2c162bfda3a90e094f797f3d6806f6077478b27a",
        )

    @patch("src.model_loader._load_local_sentence_transformer")
    def test_load_sentence_transformer_can_force_local(self, mock_load_local):
        local_model = MagicMock()
        mock_load_local.return_value = local_model

        model = load_sentence_transformer(
            "BAAI/bge-small-en-v1.5",
            device="cpu",
            allow_remote=False,
        )

        mock_load_local.assert_called_once()
        self.assertIs(model, local_model)


if __name__ == "__main__":
    unittest.main()
