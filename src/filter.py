#!/usr/bin/env python
# General-purpose vector retrieval utility: wraps sentence-transformers for embedding computation and coarse filtering

from __future__ import annotations

import os
import numpy as np
from typing import Any, Dict, List, TYPE_CHECKING
import time
from datetime import datetime, timezone

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

from model_loader import is_remote_embedding_enabled, load_sentence_transformer

if TYPE_CHECKING:
  from sentence_transformers import SentenceTransformer

# E5-family models recommend query/passage prefixes to distinguish the query side from the document side
E5_QUERY_PREFIX = "query: "


def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)

def debug_hf_runtime(prefix: str) -> None:
  """
  Print Hugging Face runtime information to diagnose cache path / symlink issues in CI.
  Output is suppressed by default unless running on GitHub Actions or DPR_DEBUG_HF=1.
  """
  enable = (os.getenv("DPR_DEBUG_HF") == "1") or (os.getenv("GITHUB_ACTIONS") == "true")
  if not enable:
    return
  if is_remote_embedding_enabled():
    return

  log(f"[DEBUG][HF] {prefix}")
  keys = [
    "GITHUB_ACTIONS",
    "GITHUB_WORKSPACE",
    "HOME",
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "HF_HUB_DISABLE_SYMLINKS",
    "TRANSFORMERS_CACHE",
    "XDG_CACHE_HOME",
  ]
  for k in keys:
    log(f"[DEBUG][HF] env {k}={os.getenv(k, '<unset>')}")

  try:
    import huggingface_hub  # type: ignore
    log(f"[DEBUG][HF] huggingface_hub={getattr(huggingface_hub, '__version__', '<unknown>')}")
    try:
      from huggingface_hub import constants as c  # type: ignore
      log(f"[DEBUG][HF] constants.HF_HOME={getattr(c, 'HF_HOME', None)}")
      log(f"[DEBUG][HF] constants.HUGGINGFACE_HUB_CACHE={getattr(c, 'HUGGINGFACE_HUB_CACHE', None)}")
      log(f"[DEBUG][HF] constants.HF_HUB_DISABLE_SYMLINKS={getattr(c, 'HF_HUB_DISABLE_SYMLINKS', None)}")
    except Exception as e:
      log(f"[DEBUG][HF] import huggingface_hub.constants failed: {e}")
  except Exception as e:
    log(f"[DEBUG][HF] import huggingface_hub failed: {e}")

  # Quick directory probe (non-recursive to avoid flooding the log)
  def ls_dir(path: str) -> None:
    try:
      items = os.listdir(path)
      items = items[:30]
      log(f"[DEBUG][HF] ls {path} ({len(items)} items shown): {items}")
    except Exception as e:
      log(f"[DEBUG][HF] ls {path} failed: {e}")

  ls_dir(os.path.expanduser("~/.cache/huggingface"))
  hf_home = os.getenv("HF_HOME")
  if hf_home:
    ls_dir(hf_home)


def _set_max_seq_length(model: Any, max_length: int | None) -> None:
  """Best-effort: set the SentenceTransformer's max_seq_length to control truncation."""
  if max_length is None or max_length <= 0:
    return
  if hasattr(model, "max_seq_length"):
    try:
      model.max_seq_length = max_length
      return
    except Exception:
      pass
  if hasattr(model, "_first_module"):
    try:
      first = model._first_module()
      if hasattr(first, "max_seq_length"):
        first.max_seq_length = max_length
    except Exception:
      pass


def encode_queries(
  model: Any,
  texts: List[str],
  batch_size: int = 8,
  max_length: int | None = None,
) -> np.ndarray:
  """
  Encode query texts into embeddings.

  Explicitly prepends the E5 query prefix:
  query: <user query>
  """
  decorated: List[str] = []
  for t in texts:
    t = (t or "").strip()
    if not t:
      decorated.append("")
    else:
      decorated.append(f"{E5_QUERY_PREFIX}{t}")

  _set_max_seq_length(model, max_length)

  encode_kwargs: Dict[str, Any] = {
    "convert_to_numpy": True,
    "normalize_embeddings": True,
    "show_progress_bar": False,
    "batch_size": batch_size,
  }

  return model.encode(
    decorated,
    **encode_kwargs,
  )


def compute_embeddings(
  model: Any,
  items: List[Any],
  batch_size: int = 8,
  max_length: int | None = None,
  log_every: int = 20,
) -> np.ndarray:
  """
  Compute embeddings for a list of items.
  Convention: each item must expose a `text_for_embedding` attribute returning the text to embed.
  Returns a normalized (N, D) numpy array — dot product approximates cosine similarity.
  """
  texts = []
  for it in items:
    text = getattr(it, "text_for_embedding", None)
    if callable(text):
      text = text()
    if isinstance(text, str):
      texts.append(text)
    else:
      texts.append(str(it))

  _set_max_seq_length(model, max_length)

  if not texts:
    return np.zeros((0, 0), dtype=np.float32)

  total = len(texts)
  log(f"[INFO] Computing embeddings for {total} records...")
  encode_kwargs: Dict[str, Any] = {
    "convert_to_numpy": True,
    "normalize_embeddings": True,
    "batch_size": batch_size,
  }

  embeddings_list: List[np.ndarray] = []
  start_time = time.time()
  processed = 0
  next_log_at = log_every if log_every > 0 else 0
  for start in range(0, total, batch_size):
    batch = texts[start : start + batch_size]
    batch_emb = model.encode(batch, **encode_kwargs)
    embeddings_list.append(batch_emb)
    processed += len(batch)
    if log_every > 0:
      while processed >= next_log_at and next_log_at <= total:
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0.0
        log(f"[INFO] Embedding progress: {processed}/{total} (~{rate:.2f} paper/s)")
        next_log_at += log_every
    elif processed == total:
      elapsed = time.time() - start_time
      rate = processed / elapsed if elapsed > 0 else 0.0
      log(f"[INFO] Embedding progress: {processed}/{total} (~{rate:.2f} paper/s)")

  return np.vstack(embeddings_list)


class EmbeddingCoarseFilter:
  """
  Coarse-filter class backed by sentence-transformers:
  - Holds an embedding model internally.
  - Ranks a paper pool by similarity across multiple queries.
  - Handles only retrieval + similarity ranking; tag logic is the caller's responsibility.
  """

  def __init__(
    self,
    model_name: str,
    top_k: int = 50,
    device: str | None = None,
    batch_size: int = 8,
    max_length: int | None = None,
  ):
    self.model_name = model_name
    self.top_k = top_k
    self.batch_size = batch_size
    self.max_length = max_length

    remote_mode = is_remote_embedding_enabled()
    if device is None:
      if remote_mode:
        self.device = "remote"
      else:
        try:
          import torch
          self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
          self.device = "cpu"
    else:
      self.device = device if not remote_mode else "remote"

    if remote_mode:
      print(f"[INFO] Initializing remote embedding service: {self.model_name}, device={self.device}")
    else:
      print(f"[INFO] Loading local embedding model: {self.model_name}, device={self.device}")
      debug_hf_runtime("before SentenceTransformer()")
    self.model = load_sentence_transformer(self.model_name, device=self.device)
    if not remote_mode:
      debug_hf_runtime("after SentenceTransformer()")
    _set_max_seq_length(self.model, self.max_length)

  def filter(self, items: List[Any], queries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Coarse-filter the given item list against queries using the internal embedding model.

    Conventions:
    - items: must expose `text_for_embedding` for vector construction.
    - queries: each entry must contain at least `query_text`; all other fields are passed through.
    Return structure:
    {
      "queries": [ { ... original query fields ..., "top_indices": [int, ...] }, ... ],
      "embeddings": np.ndarray  # embeddings corresponding to items
    }
    """
    if not items:
      print("[WARN] items list is empty, skipping coarse filter.")
      return {"queries": [], "embeddings": None}
    if not queries:
      print("[WARN] Query list is empty, skipping coarse filter.")
      return {"queries": [], "embeddings": None}

    item_embeddings = compute_embeddings(
      self.model,
      items,
      batch_size=self.batch_size,
      max_length=self.max_length,
    )

    results_per_query: List[Dict[str, Any]] = []

    for q in queries:
      q_text = (q.get("query_text") or "").strip()
      if not q_text:
        continue

      print(f"[INFO] Embedding coarse filter: query_text={q_text[:40]}...")

      # Apply E5 query prefix on the query side
      q_emb = encode_queries(
        self.model,
        [q_text],
        batch_size=self.batch_size,
        max_length=self.max_length,
      )[0]

      sims = np.dot(item_embeddings, q_emb)

      if self.top_k <= 0 or self.top_k > sims.shape[0]:
        k = sims.shape[0]
      else:
        k = self.top_k

      indices = np.argsort(-sims)[:k]

      enriched = dict(q)
      enriched["top_indices"] = indices.tolist()
      results_per_query.append(enriched)

    return {
      "queries": results_per_query,
      "embeddings": item_embeddings,
    }
