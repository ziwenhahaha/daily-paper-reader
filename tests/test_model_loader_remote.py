import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

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
        self.assertEqual(model.api_key, "dpr-embed-public")


if __name__ == "__main__":
    unittest.main()
