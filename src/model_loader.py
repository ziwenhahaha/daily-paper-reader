"""统一模型加载器：按顺序尝试下载源，按重试次数回退。"""

from __future__ import annotations

from contextlib import contextmanager
import os
import time
from typing import Callable, Optional

import numpy as np
import requests

from sentence_transformers import SentenceTransformer


HUGGINGFACE_ENDPOINT = "https://huggingface.co"
MODELSCOPE_ENDPOINT = "https://modelscope.cn/hf"
_DEFAULT_RETRIES = 3
_DEFAULT_HF_BACKOFF_RETRIES = 1
_DEFAULT_REMOTE_TIMEOUT_SECONDS = 60
_DEFAULT_REMOTE_EMBED_ENDPOINT = "https://embed.zwwen.online/embed"
_DEFAULT_REMOTE_EMBED_API_KEY = "dpr-embed-public"


def _log_default(message: str) -> None:
  print(message, flush=True)


class RemoteSentenceTransformer:
  """兼容 SentenceTransformer.encode 接口的远程 embedding 包装器。"""

  is_remote = True

  def __init__(
    self,
    model_name: str,
    endpoint: str,
    api_key: str = "",
    timeout: int = _DEFAULT_REMOTE_TIMEOUT_SECONDS,
    default_batch_size: int = 8,
    log: Callable[[str], None] = _log_default,
  ):
    self.model_name = model_name
    self.endpoint = self._normalize_endpoint(endpoint)
    self.api_key = str(api_key or "").strip()
    self.timeout = max(int(timeout or _DEFAULT_REMOTE_TIMEOUT_SECONDS), 1)
    self.default_batch_size = max(int(default_batch_size or 1), 1)
    self.max_seq_length = None
    self._log = log

  @staticmethod
  def _normalize_endpoint(endpoint: str) -> str:
    text = str(endpoint or "").strip().rstrip("/")
    if not text:
      raise ValueError("远程 embedding 服务地址不能为空（DPR_EMBED_API_URL）")
    if text.endswith("/embed"):
      return text
    return f"{text}/embed"

  def _headers(self) -> dict[str, str]:
    headers = {
      "Content-Type": "application/json",
    }
    if self.api_key:
      headers["Authorization"] = f"Bearer {self.api_key}"
    return headers

  def encode(
    self,
    texts,
    convert_to_numpy: bool = True,
    normalize_embeddings: bool = True,
    batch_size: int = 8,
    show_progress_bar: bool = False,
    **kwargs,
  ):
    del show_progress_bar, kwargs
    if isinstance(texts, str):
      texts = [texts]
    if not isinstance(texts, list):
      texts = list(texts or [])
    if not texts:
      empty = np.zeros((0, 0), dtype=np.float32)
      return empty if convert_to_numpy else empty.tolist()

    safe_batch_size = max(int(batch_size or self.default_batch_size), 1)
    chunks = [texts[i : i + safe_batch_size] for i in range(0, len(texts), safe_batch_size)]
    outputs: list[np.ndarray] = []

    self._log(
      f"[INFO] 远程 embedding：model={self.model_name} "
      f"endpoint={self.endpoint} total={len(texts)} batch={safe_batch_size}"
    )

    for chunk_index, chunk in enumerate(chunks, start=1):
      response = requests.post(
        self.endpoint,
        headers=self._headers(),
        json={"texts": chunk},
        timeout=self.timeout,
      )
      response.raise_for_status()
      data = response.json()
      embeddings = data.get("embeddings")
      if not isinstance(embeddings, list):
        raise RuntimeError("远程 embedding 服务返回缺少 embeddings 字段")
      try:
        arr = np.asarray(embeddings, dtype=np.float32)
      except Exception as exc:
        raise RuntimeError(f"远程 embedding 返回无法转换为 float32：{exc}") from exc

      if arr.ndim != 2:
        raise RuntimeError(f"远程 embedding 返回维度异常：shape={getattr(arr, 'shape', None)}")
      if arr.shape[0] != len(chunk):
        raise RuntimeError(
          f"远程 embedding 返回条数异常：expected={len(chunk)} actual={arr.shape[0]}"
        )
      if normalize_embeddings:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / np.clip(norms, 1e-12, None)
      outputs.append(arr)
      self._log(
        f"[INFO] 远程 embedding 批次完成：{chunk_index}/{len(chunks)} "
        f"count={len(chunk)} dim={arr.shape[1]}"
      )

    merged = np.vstack(outputs) if outputs else np.zeros((0, 0), dtype=np.float32)
    return merged if convert_to_numpy else merged.tolist()

  def start_multi_process_pool(self, target_devices=None):
    del target_devices
    return None

  def encode_multi_process(
    self,
    texts,
    pool=None,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    **kwargs,
  ):
    del pool
    return self.encode(
      texts,
      convert_to_numpy=True,
      normalize_embeddings=normalize_embeddings,
      batch_size=batch_size,
      **kwargs,
    )

  def stop_multi_process_pool(self, pool):
    del pool
    return None


@contextmanager
def _hf_http_backoff(max_retries: int):
  """临时覆盖 huggingface_hub 的 http_backoff 重试次数。

  仅用于抑制单次请求内置重试次数（日志中通常体现为 `Retry x/5`）。
  """
  if max_retries <= 0:
    yield
    return

  try:
    from huggingface_hub.utils import _http as hf_http
  except Exception:
    yield
    return

  origin_http_backoff = hf_http.http_backoff

  def http_backoff_with_retry_limit(*args, **kwargs):
    kwargs.setdefault("max_retries", max_retries)
    return origin_http_backoff(*args, **kwargs)

  hf_http.http_backoff = http_backoff_with_retry_limit
  try:
    yield
  finally:
    hf_http.http_backoff = origin_http_backoff


@contextmanager
def _hf_endpoint(endpoint: Optional[str] = None):
  had_endpoint = "HF_ENDPOINT" in os.environ
  old_endpoint = os.environ.get("HF_ENDPOINT")
  had_base_url = "HF_HUB_BASE_URL" in os.environ
  old_base_url = os.environ.get("HF_HUB_BASE_URL")
  if endpoint:
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HF_HUB_BASE_URL"] = endpoint
  elif had_endpoint:
    if "HF_ENDPOINT" in os.environ:
      del os.environ["HF_ENDPOINT"]
    if "HF_HUB_BASE_URL" in os.environ:
      del os.environ["HF_HUB_BASE_URL"]

  try:
    yield
  finally:
    if had_endpoint:
      if old_endpoint is None:
        del os.environ["HF_ENDPOINT"]
      else:
        os.environ["HF_ENDPOINT"] = old_endpoint
    elif "HF_ENDPOINT" in os.environ:
      del os.environ["HF_ENDPOINT"]
    if had_base_url:
      if old_base_url is None:
        del os.environ["HF_HUB_BASE_URL"]
      else:
        os.environ["HF_HUB_BASE_URL"] = old_base_url
    elif "HF_HUB_BASE_URL" in os.environ:
      del os.environ["HF_HUB_BASE_URL"]


def load_sentence_transformer(
  model_name: str,
  *,
  device: str,
  retries: int | None = None,
  log: Callable[[str], None] = _log_default,
  providers: tuple[tuple[str, str], ...] = (
    ("huggingface", HUGGINGFACE_ENDPOINT),
    ("modelscope", MODELSCOPE_ENDPOINT),
  ),
):
  remote_endpoint = _DEFAULT_REMOTE_EMBED_ENDPOINT
  remote_api_key = _DEFAULT_REMOTE_EMBED_API_KEY
  if remote_endpoint:
    remote_timeout_text = os.getenv("DPR_EMBED_API_TIMEOUT", str(_DEFAULT_REMOTE_TIMEOUT_SECONDS))
    try:
      remote_timeout = int(remote_timeout_text)
    except ValueError:
      log(
        f"[WARN] 环境变量 DPR_EMBED_API_TIMEOUT 无效：{remote_timeout_text}，"
        f"回退默认 {_DEFAULT_REMOTE_TIMEOUT_SECONDS}"
      )
      remote_timeout = _DEFAULT_REMOTE_TIMEOUT_SECONDS
    log(
      f"[INFO] 使用远程 embedding 服务：model={model_name} "
      f"endpoint={str(remote_endpoint).strip()} timeout={remote_timeout}s device={device}"
    )
    return RemoteSentenceTransformer(
      model_name=model_name,
      endpoint=str(remote_endpoint).strip(),
      api_key=remote_api_key,
      timeout=remote_timeout,
      log=log,
    )

  if retries is None:
    env_retries = os.getenv("LLM_EMBED_MODEL_RETRIES")
    if env_retries is None:
      retries = _DEFAULT_RETRIES
    else:
      try:
        retries = int(env_retries)
      except ValueError:
        print(f"[WARN] 环境变量 LLM_EMBED_MODEL_RETRIES 无效：{env_retries}，回退默认 {_DEFAULT_RETRIES}")
        retries = _DEFAULT_RETRIES
  hf_backoff_retries = _DEFAULT_HF_BACKOFF_RETRIES
  env_hf_backoff_retries = os.getenv("HF_HUB_HTTP_BACKOFF_RETRIES")
  if env_hf_backoff_retries is not None:
    try:
      hf_backoff_retries = int(env_hf_backoff_retries)
    except ValueError:
      print(
        f"[WARN] 环境变量 HF_HUB_HTTP_BACKOFF_RETRIES 无效：{env_hf_backoff_retries}，"
        f"回退默认 {_DEFAULT_HF_BACKOFF_RETRIES}"
      )
      hf_backoff_retries = _DEFAULT_HF_BACKOFF_RETRIES
    if hf_backoff_retries < 0:
      hf_backoff_retries = 0

  attempts = max(int(retries or _DEFAULT_RETRIES), 1)
  last_err: Exception | None = None

  for round_idx in range(1, attempts + 1):
    for provider_name, endpoint in providers:
      try:
        log(
          f"[INFO] 尝试加载模型（第 {round_idx}/{attempts} 轮）：{model_name}"
          f"（provider={provider_name}，device={device}）"
        )
        with _hf_endpoint(endpoint), _hf_http_backoff(max_retries=hf_backoff_retries):
          return SentenceTransformer(model_name, device=device)
      except Exception as e:  # pragma: no cover - 仅异常路径
        last_err = e
        msg = str(e)
        if len(msg) > 260:
          msg = msg[:260]
        log(
          f"[WARN] 模型加载失败（provider={provider_name}，round={round_idx}/{attempts}）："
          f"{msg}"
        )

    if round_idx < attempts:
      wait_seconds = 1
      log(f"[INFO] 重试间隔：{wait_seconds}s")
      time.sleep(wait_seconds)

  if last_err is not None:
    raise last_err
  raise RuntimeError(f"加载模型失败：{model_name}")
