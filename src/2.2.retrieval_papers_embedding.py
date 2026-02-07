#!/usr/bin/env python
# 基于全量 ArXiv 元数据池做二次筛选：
# 1. 读取 arxiv_fetch_raw.py 生成的 JSON（所有论文）；
# 2. 使用 sentence-transformers 将「标题 + 摘要」编码为向量；
# 3. 使用 config.yaml 中的 keywords / llm_queries 作为查询，计算相似度；
# 4. 每个查询保留前 top_k 篇论文，并为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
# 5. 将带 tag 的论文列表和每个查询的 top_k arxiv_id 写回到一个新的 JSON 文件中。

import argparse
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional

import numpy as np

from filter import EmbeddingCoarseFilter, encode_queries
from subscription_plan import build_pipeline_inputs


# 当前脚本位于 src/ 下，config.yaml 在上一级目录
SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))
ROOT_DIR = os.path.dirname(CONFIG_FILE)
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RAW_DIR = os.path.join(ARCHIVE_DIR, "raw")
FILTERED_DIR = os.path.join(ARCHIVE_DIR, "filtered")

def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
  print(f"::group::{title}", flush=True)


def group_end() -> None:
  print("::endgroup::", flush=True)


@dataclass
class Paper:
  """用于向量检索阶段的论文结构（只关心元数据和 tag）"""

  id: str
  title: str
  abstract: str
  authors: List[str]
  primary_category: str | None = None
  categories: List[str] = field(default_factory=list)
  published: str | None = None
  link: str | None = None
  source: str = "arxiv"
  embedding: Optional[np.ndarray] = None
  embedding_model: str = ""
  tags: Set[str] = field(default_factory=set)

  @property
  def text_for_embedding(self) -> str:
    """用于向量化的文本：E5 passage 前缀 + 标题/摘要"""
    title = (self.title or "").strip()
    abstract = (self.abstract or "").strip()
    if title and abstract:
      return f"passage: Title: {title}\n\nAbstract: {abstract}"
    if title:
      return f"passage: Title: {title}"
    if abstract:
      return f"passage: Abstract: {abstract}"
    return ""

  def to_dict(self) -> Dict[str, Any]:
    """转换为可 JSON 序列化的字典"""
    return {
      "id": self.id,
      "title": self.title,
      "abstract": self.abstract,
      "authors": self.authors,
      "primary_category": self.primary_category,
      "categories": self.categories,
      "published": self.published,
      "link": self.link,
      # tags 输出为去重后的列表
      "tags": sorted(self.tags),
    }


def load_config() -> dict:
  """
  从仓库根目录读取 config.yaml。
  只要能拿到 subscriptions.keywords / subscriptions.llm_queries 即可。
  """
  if not os.path.exists(CONFIG_FILE):
    log(f"[WARN] config.yaml 不存在：{CONFIG_FILE}")
    return {}

  try:
    import yaml  # type: ignore
  except Exception:
    log("[WARN] 未安装 PyYAML，无法解析 config.yaml。")
    return {}

  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      data = yaml.safe_load(f) or {}
      if isinstance(data, dict):
        return data
      log("[WARN] config.yaml 顶层结构不是字典，将忽略该配置文件。")
      return {}
  except Exception as e:
    log(f"[WARN] 读取 config.yaml 失败：{e}")
    return {}


def load_paper_pool(path: str) -> List[Paper]:
  """
  读取 arxiv_fetch_raw.py 生成的 JSON：
  期望结构为 [ { id, title, abstract, authors, primary_category, categories, published, link }, ... ]
  """
  if not os.path.exists(path):
    raise FileNotFoundError(f"找不到论文池文件：{path}")

  with open(path, "r", encoding="utf-8") as f:
    raw = json.load(f)

  papers: List[Paper] = []
  for item in raw:
    try:
      emb = parse_embedding_value(item.get("embedding"))
      p = Paper(
        id=str(item.get("id") or "").strip(),
        source=str(item.get("source") or "arxiv").strip() or "arxiv",
        title=str(item.get("title") or "").strip(),
        abstract=str(item.get("abstract") or "").strip(),
        authors=[str(a) for a in (item.get("authors") or [])],
        primary_category=str(item.get("primary_category") or "") or None,
        categories=[str(c) for c in (item.get("categories") or [])],
        published=str(item.get("published") or "") or None,
        link=str(item.get("link") or "") or None,
        embedding=emb,
        embedding_model=str(item.get("embedding_model") or "").strip(),
      )
      if p.id:
        papers.append(p)
    except Exception as e:
      log(f"[WARN] 解析论文条目失败，将跳过：{e}")

  log(f"[INFO] 从 {path} 读取到 {len(papers)} 篇论文。")
  return papers


def parse_embedding_value(value: Any) -> Optional[np.ndarray]:
  if isinstance(value, np.ndarray):
    vec = value.astype(np.float32)
  elif isinstance(value, list):
    try:
      vec = np.array([float(x) for x in value], dtype=np.float32)
    except Exception:
      return None
  elif isinstance(value, str):
    text = value.strip()
    if not text:
      return None
    if text.startswith("[") and text.endswith("]"):
      text = text[1:-1]
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
      return None
    try:
      vec = np.array([float(p) for p in parts], dtype=np.float32)
    except Exception:
      return None
  else:
    return None

  if vec.ndim != 1 or vec.size == 0:
    return None
  norm = float(np.linalg.norm(vec))
  if norm <= 0:
    return None
  return vec / norm


def try_use_precomputed_embeddings(
  papers: List[Paper],
  expected_model: str,
) -> np.ndarray | None:
  if not papers:
    return None

  vectors: List[np.ndarray] = []
  dims: Set[int] = set()
  models: Set[str] = set()

  for p in papers:
    if p.embedding is None:
      return None
    vectors.append(p.embedding)
    dims.add(int(p.embedding.shape[0]))
    m = (p.embedding_model or "").strip().lower()
    if m:
      models.add(m)

  if len(dims) != 1:
    log("[WARN] 预置 embedding 维度不一致，回退本地重算论文 embedding。")
    return None

  expect = (expected_model or "").strip().lower()
  if models and expect and models != {expect}:
    log(
      "[WARN] 预置 embedding 模型与当前模型不一致："
      f"precomputed={sorted(models)} current={expect}，回退本地重算论文 embedding。"
    )
    return None

  return np.vstack(vectors)


def rank_papers_for_queries(
  model,
  papers: List[Paper],
  paper_embeddings: np.ndarray,
  queries: List[dict],
  top_k: int = 50,
) -> dict:
  """
  对每个查询分别进行相似度排序：
  - 使用 query_text 编码为向量，与所有论文向量做点积；
  - 取相似度最高的前 top_k 篇论文，记录 arxiv_id；
  - 为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
  - 返回结构包含：
    {
      "queries": [ { type, tag, query_text, paper_tag, top_ids: [...] }, ... ],
      "papers": { paper_id: Paper(...) }
    }
  """
  if not queries:
    log("[WARN] 未从 config.yaml 中解析到任何查询（keywords / llm_queries），将直接返回空结果。")
    return {"queries": [], "papers": {}}

  paper_ids = [p.id for p in papers]
  id_to_paper: Dict[str, Paper] = {p.id: p for p in papers}

  results_per_query: List[dict] = []

  for q in queries:
    q_text = q.get("query_text") or ""
    paper_tag = q.get("paper_tag") or ""
    if not q_text:
      continue

    log(f"[INFO] 正在处理查询（{q.get('type')}）：tag={q.get('tag') or ''}")

    # 查询向量编码：若底层模型（如 Qwen3-Embedding）支持 "query" prompt，则自动使用
    q_emb = encode_queries(
      model,
      [q_text],
    )[0]  # 形状为 (D,)

    # 相似度 = 归一化向量的点积
    sims = np.dot(paper_embeddings, q_emb)  # 形状 (N,)

    # 从大到小排序，取前 top_k
    if top_k <= 0 or top_k > sims.shape[0]:
      k = sims.shape[0]
    else:
      k = top_k

    indices = np.argsort(-sims)[:k]
    # sim_scores: 以 paper_id 为键，记录该 query 下的相似度与排名
    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, idx in enumerate(indices, start=1):
      pid = paper_ids[idx]
      score = float(sims[idx])
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      if paper_tag:
        id_to_paper[pid].tags.add(paper_tag)

    results_per_query.append(
        {
          "type": q.get("type"),
          "tag": q.get("tag"),
          "paper_tag": q.get("paper_tag"),
          "query_text": q_text,
          # sim_scores 为字典：paper_id -> { score, rank }
          "sim_scores": sim_scores,
        }
    )

  return {
    "queries": results_per_query,
    "papers": id_to_paper,
  }


def save_tagged_results(
  result: dict,
  output_path: str,
) -> None:
  """
  将结果写入 JSON：
  {
    "top_k": ...,
    "generated_at": "...",
    "queries": [ { type, tag, paper_tag, query_text, top_ids: [...] }, ... ],
    "papers": [ { id, title, abstract, ..., tags: [...] }, ... ]  // 仅保留至少有一个 tag 的论文
  }
  """
  from datetime import datetime, timezone

  os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

  id_to_paper: Dict[str, Paper] = result.get("papers") or {}

  tagged_papers = [p.to_dict() for p in id_to_paper.values() if p.tags]

  # 根据第一个查询推断 top_k：优先使用 sim_scores，其次兼容旧版 top_ids
  q_list = result.get("queries") or []
  if q_list:
    q0 = q_list[0]
    sim_scores = q0.get("sim_scores") or {}
    if isinstance(sim_scores, dict) and sim_scores:
      inferred_top_k = len(sim_scores)
    else:
      top_ids = q0.get("top_ids") or []
      inferred_top_k = len(top_ids)
  else:
    inferred_top_k = 0

  payload = {
    "top_k": inferred_top_k,
    # 使用带时区的 UTC 时间，避免 DeprecationWarning
    "generated_at": datetime.now(timezone.utc).isoformat(),
    # 先输出 papers，再输出 queries，方便阅读和消费
    "papers": tagged_papers,
    "queries": result.get("queries") or [],
  }

  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

  log(f"[INFO] 已将带 tag 的论文和每个查询的 top_k 结果写入：{output_path}")
  log(f"[INFO] 其中带 tag 的论文数：{len(tagged_papers)}")


def main() -> None:
  parser = argparse.ArgumentParser(
    description="基于 sentence-transformers 对 ArXiv 论文池做关键词 / LLM 查询相似度筛选，并为论文打 tag。",
  )
  parser.add_argument(
    "--input",
    type=str,
    default=None,
    help="可选：只处理指定的原始 JSON 文件；省略时将批量处理 archive/YYYYMMDD/raw 目录下所有 .json 文件。",
  )
  parser.add_argument(
    "--output",
    type=str,
    default=None,
    help="可选：当使用 --input 处理单个文件时，自定义输出 JSON 路径；批处理模式下将自动写入 archive/YYYYMMDD/filtered 目录，默认后缀 .embedding.json。",
  )
  parser.add_argument(
    "--top-k",
    type=int,
    default=None,
    help="每个查询保留的 Top K 论文数；未指定时根据原始论文总数自适应：<=1000 篇取 50，每增加 1000 篇增加 50。",
  )
  parser.add_argument(
    "--model",
    type=str,
    default="BAAI/bge-small-en-v1.5",
    help="用于向量检索的 sentence-transformers 模型名称（默认 BAAI/bge-small-en-v1.5）",
  )
  parser.add_argument(
    "--batch-size",
    type=int,
    default=8,
    help="向量编码批大小，显存不足时可降低（默认 8）。",
  )
  parser.add_argument(
    "--max-length",
    type=int,
    default=None,
    help="向量编码的最大 token 长度，过长文本可截断以节省显存（默认不截断）。",
  )
  parser.add_argument(
    "--device",
    type=str,
    default="cpu",
    help="向量模型运行设备，例如 cuda 或 cpu（默认 cpu）。",
  )

  args = parser.parse_args()

  config = load_config()
  pipeline_inputs = build_pipeline_inputs(config)
  queries = pipeline_inputs.get("embedding_queries") or []
  comparison = pipeline_inputs.get("comparison") or {}
  if comparison:
    log(
      "[INFO] 迁移阶段A输入对比："
      f"embedding_only_new={comparison.get('embedding_only_new_count', 0)} "
      f"embedding_only_legacy={comparison.get('embedding_only_legacy_count', 0)}"
    )
  if not queries:
    log("[ERROR] 未能从订阅配置中解析到 Embedding 查询，退出。")
    return

  # 使用 EmbeddingCoarseFilter 类进行粗筛（模型只加载一次）
  coarse_filter = EmbeddingCoarseFilter(
    model_name=args.model,
    top_k=50,  # 实际 top_k 会在每个文件内根据数据量动态调整
    device=args.device,
    batch_size=args.batch_size,
    max_length=args.max_length,
  )

  def process_single_file(input_path: str, output_path: str) -> None:
    papers = load_paper_pool(input_path)
    if not papers:
      log(f"[ERROR] 论文池为空，跳过文件：{input_path}")
      return

    total_papers = len(papers)

    # 自适应计算 Top K：<=1000 篇取 50；每增加 1000 篇增加 50
    if args.top_k is None or args.top_k <= 0:
      if total_papers <= 0:
        dynamic_top_k = 50
      else:
        blocks = (total_papers - 1) // 1000  # 0: <=1000, 1: 1001~2000, ...
        dynamic_top_k = 50 * (blocks + 1)
      log(
        f"[INFO] 文件 {os.path.basename(input_path)} 原始论文数为 {total_papers} 篇，"
        f"自适应设置每个查询 Top K = {dynamic_top_k}。"
      )
    else:
      dynamic_top_k = args.top_k
      log(
        f"[INFO] 文件 {os.path.basename(input_path)} 使用命令行指定的 Top K = {dynamic_top_k}，"
        f"原始论文数为 {total_papers} 篇。"
      )

    # 更新粗筛器的 top_k
    coarse_filter.top_k = dynamic_top_k

    # 1) 优先使用 Supabase 下发的论文 embedding（本地仅算 query embedding）；
    #    若缺失/不一致，再回退本地重算论文 embedding。
    paper_embeddings = try_use_precomputed_embeddings(papers, expected_model=args.model)
    if paper_embeddings is not None:
      group_start(f"Step 2.2 - use precomputed embeddings ({os.path.basename(input_path)})")
      log(
        f"[INFO] 使用预置论文 embedding：{paper_embeddings.shape[0]} 篇，"
        f"dim={paper_embeddings.shape[1]}。"
      )
      group_end()
    else:
      group_start(f"Step 2.2 - compute embeddings ({os.path.basename(input_path)})")
      coarse_result = coarse_filter.filter(items=papers, queries=queries)
      group_end()
      paper_embeddings = coarse_result["embeddings"]

    # 2) 再用当前文件中的 rank_papers_for_queries 做「打 tag + 生成 top_ids」
    group_start(f"Step 2.2 - rank queries ({os.path.basename(input_path)})")
    result = rank_papers_for_queries(
      model=coarse_filter.model,
      papers=papers,
      paper_embeddings=paper_embeddings,
      queries=queries,
      top_k=dynamic_top_k,
    )
    group_end()

    save_tagged_results(result, output_path)

  # 决定处理哪些输入文件：
  # - 如果指定了 --input，则只处理该文件；
  # - 否则遍历 archive/YYYYMMDD/raw 目录下所有 .json 文件。
  if args.input:
    input_path = args.input
    if not os.path.isabs(input_path):
      input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))
    if not os.path.exists(input_path):
      log(f"[ERROR] 指定的输入文件不存在：{input_path}")
      return

    if args.output:
      output_path = args.output
      if not os.path.isabs(output_path):
        output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))
    else:
      # 单文件模式下，如未指定输出路径，则写入 archive/YYYYMMDD/filtered，文件名与原始 JSON 保持一致
      base = os.path.basename(input_path)
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.embedding.json")

    process_single_file(input_path, output_path)
  else:
    if not os.path.isdir(RAW_DIR):
      log(f"[INFO] 原始目录不存在：{RAW_DIR}（今天没有新论文，将跳过 Embedding 检索）")
      return

    raw_files = sorted(
      f for f in os.listdir(RAW_DIR) if f.lower().endswith(".json")
    )
    if not raw_files:
      log(f"[INFO] 在 {RAW_DIR} 下未找到任何 .json 原始文件。（今天没有新论文，将跳过 Embedding 检索）")
      return

    log(f"[INFO] 批量模式：将在 {RAW_DIR} 下处理 {len(raw_files)} 个 JSON 文件。")
    for name in raw_files:
      input_path = os.path.join(RAW_DIR, name)
      # 批量模式下，输出文件名与原始文件名保持一致，但目录变为 archive/YYYYMMDD/filtered
      base = name
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.embedding.json")
      process_single_file(input_path, output_path)


if __name__ == "__main__":
  main()
