#!/usr/bin/env python
# 基于 BM25 对 ArXiv 元数据池做二次筛选：
# 1. 读取 arxiv_fetch_raw.py 生成的 JSON（所有论文）；
# 2. 对标题 + 摘要做 BM25 索引；
# 3. 使用 config.yaml 中的 keywords / llm_queries 作为查询，计算相似度；
# 4. 每个查询保留前 top_k 篇论文，并为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
# 5. 将带 tag 的论文列表和每个查询的 top_k 结果写回到一个新的 JSON 文件中。

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Iterable

from query_boolean import (
  parse_boolean_expr,
  split_or_branches,
  evaluate_expr,
  collect_unique_positive_terms,
  clean_expr_for_embedding,
  match_term,
)
from subscription_plan import build_pipeline_inputs


# 当前脚本位于 src/ 下，config.yaml 在上一级目录
SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))
ROOT_DIR = os.path.dirname(CONFIG_FILE)
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RAW_DIR = os.path.join(ARCHIVE_DIR, "raw")
FILTERED_DIR = os.path.join(ARCHIVE_DIR, "filtered")


TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
MAIN_TERM_WEIGHT = 1.0
RELATED_TERM_WEIGHT = 0.5
QUERY_TEXT_WEIGHT = 0
DEFAULT_OR_SOFT_WEIGHT = 0.3


def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
  print(f"::group::{title}", flush=True)


def group_end() -> None:
  print("::endgroup::", flush=True)


def tokenize(text: str) -> List[str]:
  """简单分词：英文按词，中文按单字。"""
  if not text:
    return []
  return TOKEN_RE.findall(text.lower())


@dataclass
class Paper:
  """用于 BM25 检索阶段的论文结构（只关心元数据和 tag）"""

  id: str
  title: str
  abstract: str
  authors: List[str]
  primary_category: str | None = None
  categories: List[str] = field(default_factory=list)
  published: str | None = None
  link: str | None = None
  source: str = "arxiv"
  tags: Set[str] = field(default_factory=set)

  @property
  def text_for_bm25(self) -> str:
    """用于 BM25 的文本：标题 + 摘要（带标签，便于结构化）"""
    title = (self.title or "").strip()
    abstract = (self.abstract or "").strip()
    if title and abstract:
      return f"Title: {title}\n\nAbstract: {abstract}"
    if title:
      return f"Title: {title}"
    if abstract:
      return f"Abstract: {abstract}"
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
      "tags": sorted(self.tags),
    }


class BM25Index:
  """轻量 BM25 实现，避免额外依赖。"""

  def __init__(self, tokenized_docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
    self.k1 = k1
    self.b = b

    self.doc_len = [len(tokens) for tokens in tokenized_docs]
    self.avgdl = sum(self.doc_len) / max(len(self.doc_len), 1)
    self.doc_freqs: List[Dict[str, int]] = []
    self.idf: Dict[str, float] = {}
    self.inverted: Dict[str, List[tuple[int, int]]] = {}

    df: Dict[str, int] = {}
    for idx, tokens in enumerate(tokenized_docs):
      freqs: Dict[str, int] = {}
      for t in tokens:
        freqs[t] = freqs.get(t, 0) + 1
      self.doc_freqs.append(freqs)
      for t in freqs.keys():
        df[t] = df.get(t, 0) + 1
        self.inverted.setdefault(t, []).append((idx, freqs[t]))

    total_docs = len(tokenized_docs)
    for t, dfn in df.items():
      # 标准 BM25 IDF
      self.idf[t] = math.log(1 + (total_docs - dfn + 0.5) / (dfn + 0.5))

  def score(self, query_tokens: Iterable[str]) -> List[float]:
    scores = [0.0] * len(self.doc_len)
    if not self.doc_len:
      return scores

    q_tf: Dict[str, int] = {}
    for t in query_tokens:
      q_tf[t] = q_tf.get(t, 0) + 1

    for term, q_count in q_tf.items():
      idf = self.idf.get(term)
      if idf is None:
        continue
      postings = self.inverted.get(term, [])
      for doc_idx, tf in postings:
        dl = self.doc_len[doc_idx]
        denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
        score = idf * (tf * (self.k1 + 1) / denom) * q_count
        scores[doc_idx] += score

    return scores


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


def build_queries_from_config(config: dict) -> List[dict]:
  """
  基于 config.yaml 中的 subscriptions.keywords / subscriptions.llm_queries
  构造查询列表：
  - 对于 keywords：使用 keyword 作为查询文本，tag 作为标签；
  - 对于 llm_queries：使用 query 作为查询文本，tag 作为标签。
  """
  subs = (config or {}).get("subscriptions") or {}

  queries: List[dict] = []

  cfg_keywords = subs.get("keywords")
  if isinstance(cfg_keywords, list):
    for item in cfg_keywords:
      if not isinstance(item, dict):
        continue
      kw = (item.get("keyword") or "").strip()
      tag_label = (item.get("tag") or item.get("alias") or "").strip()
      related = item.get("related") or []
      if not kw:
        continue
      base = tag_label or kw
      paper_tag = f"keyword:{base}"
      query_terms = [{"text": kw, "weight": MAIN_TERM_WEIGHT}]

      if isinstance(related, list):
        for term in related:
          t = (str(term) or "").strip()
          if t:
            query_terms.append({"text": t, "weight": RELATED_TERM_WEIGHT})

      queries.append(
        {
          "type": "keyword",
          "query_text": kw,
          "tag": tag_label,
          "paper_tag": paper_tag,
          "query_terms": query_terms,
        }
      )

  cfg_llm = subs.get("llm_queries")
  if isinstance(cfg_llm, list):
    for item in cfg_llm:
      if not isinstance(item, dict):
        continue
      q = (item.get("query") or "").strip()
      tag_label = (item.get("tag") or item.get("alias") or "").strip()
      if not q:
        continue
      base = tag_label or (q[:30] + "..." if len(q) > 30 else q)
      paper_tag = f"query:{base}"
      queries.append(
        {
          "type": "llm_query",
          "query_text": q,
          "tag": tag_label,
          "paper_tag": paper_tag,
        }
      )

  return queries


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
      )
      if p.id:
        papers.append(p)
    except Exception as e:
      log(f"[WARN] 解析论文条目失败，将跳过：{e}")

  log(f"[INFO] 从 {path} 读取到 {len(papers)} 篇论文。")
  return papers


def build_bm25_index(papers: List[Paper], k1: float = 1.5, b: float = 0.75) -> BM25Index:
  docs = [p.text_for_bm25 for p in papers]
  tokenized = [tokenize(d) for d in docs]
  return BM25Index(tokenized_docs=tokenized, k1=k1, b=b)


def score_boolean_mixed_for_query(
  bm25: BM25Index,
  papers: List[Paper],
  expr: str,
  or_soft_weight: float = DEFAULT_OR_SOFT_WEIGHT,
  must_have: List[str] | None = None,
  optional: List[str] | None = None,
  exclude: List[str] | None = None,
) -> List[float]:
  """
  BM25 布尔混合模式：
  - AND/NOT：硬约束（不过滤则直接淘汰）；
  - OR：同一论文命中多个分支时做软增强。
  """
  parsed = parse_boolean_expr(expr)
  if parsed is None:
    fallback_text = clean_expr_for_embedding(expr) or expr
    return bm25.score(tokenize(fallback_text))

  branches = split_or_branches(parsed)
  if not branches:
    fallback_text = clean_expr_for_embedding(expr) or expr
    return bm25.score(tokenize(fallback_text))

  branch_terms: List[List[str]] = [collect_unique_positive_terms(b) for b in branches]
  term_score_cache: Dict[str, List[float]] = {}
  for terms in branch_terms:
    for term in terms:
      key = term.lower()
      if key in term_score_cache:
        continue
      term_score_cache[key] = bm25.score(tokenize(term))

  must_list = [str(x).strip() for x in (must_have or []) if str(x).strip()]
  optional_list = [str(x).strip() for x in (optional or []) if str(x).strip()]
  exclude_list = [str(x).strip() for x in (exclude or []) if str(x).strip()]

  scores = [-1.0] * len(papers)
  for idx, paper in enumerate(papers):
    title = paper.title or ""
    abstract = paper.abstract or ""
    authors = paper.authors or []

    if must_list:
      if not all(match_term(t, title, abstract, authors) for t in must_list):
        continue
    if exclude_list:
      if any(match_term(t, title, abstract, authors) for t in exclude_list):
        continue

    passed_branch_scores: List[float] = []
    for b_idx, branch in enumerate(branches):
      if not evaluate_expr(branch, title, abstract, authors):
        continue
      terms = branch_terms[b_idx]
      if terms:
        branch_score = sum(term_score_cache[t.lower()][idx] for t in terms) / max(len(terms), 1)
      else:
        branch_score = 1.0
      passed_branch_scores.append(float(branch_score))

    if not passed_branch_scores:
      continue

    base = max(passed_branch_scores)
    extra = max(sum(passed_branch_scores) - base, 0.0)
    score = base + float(or_soft_weight) * extra

    if optional_list:
      hits = sum(1 for t in optional_list if match_term(t, title, abstract, authors))
      if hits > 0:
        score += 0.1 * hits / len(optional_list)

    scores[idx] = float(score)

  return scores


def rank_papers_for_queries(
  bm25: BM25Index,
  papers: List[Paper],
  queries: List[dict],
  top_k: int = 50,
) -> dict:
  """
  对每个查询分别进行 BM25 排序：
  - 使用 query_text 分词，与所有论文做 BM25 打分；
  - 取分数最高的前 top_k 篇论文，记录 arxiv_id；
  - 为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
  - 返回结构包含：
    {
      "queries": [ { type, tag, query_text, paper_tag, sim_scores: {paper_id: {score, rank}} }, ... ],
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
    q_text = (q.get("query_text") or "").strip()
    paper_tag = q.get("paper_tag") or ""
    if not q_text:
      continue

    log(f"[INFO] BM25 处理查询（{q.get('type')}）：tag={q.get('tag') or ''}")

    scores: List[float] | None = None
    total_weight = 0.0
    query_terms = q.get("query_terms") or []
    boolean_expr = (q.get("boolean_expr") or "").strip()
    is_boolean_query = bool(boolean_expr) and (q.get("type") == "keyword")
    query_mode = "normal"

    if is_boolean_query:
      query_mode = "boolean_mixed"
      scores = score_boolean_mixed_for_query(
        bm25=bm25,
        papers=papers,
        expr=boolean_expr,
        or_soft_weight=float(q.get("or_soft_weight") or DEFAULT_OR_SOFT_WEIGHT),
        must_have=q.get("must_have") or [],
        optional=q.get("optional") or [],
        exclude=q.get("exclude") or [],
      )
      valid_candidates = sum(1 for s in scores if s >= 0)
      log(
        f"[INFO] BM25 布尔混合模式：valid_candidates={valid_candidates}/{len(scores)}"
      )

    if (not is_boolean_query) and isinstance(query_terms, list) and query_terms:
      for term in query_terms:
        if not isinstance(term, dict):
          continue
        term_text = (term.get("text") or "").strip()
        weight = float(term.get("weight", 1.0))
        if not term_text or weight <= 0:
          continue
        term_scores = bm25.score(tokenize(term_text))
        if scores is None:
          scores = [0.0] * len(term_scores)
        for i, s in enumerate(term_scores):
          scores[i] += weight * s
        total_weight += weight

    if (not is_boolean_query) and scores is None:
      scores = bm25.score(tokenize(q_text))
      total_weight = 1.0

    if (not is_boolean_query) and total_weight > 0:
      scores = [s / total_weight for s in scores]

    if is_boolean_query:
      candidate_indices = [i for i, s in enumerate(scores) if s >= 0]
    else:
      candidate_indices = list(range(len(scores)))

    if top_k <= 0 or top_k > len(candidate_indices):
      k = len(candidate_indices)
    else:
      k = top_k

    indices = sorted(candidate_indices, key=lambda i: scores[i], reverse=True)[:k]
    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, idx in enumerate(indices, start=1):
      pid = paper_ids[idx]
      score = float(scores[idx])
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      if paper_tag:
        id_to_paper[pid].tags.add(paper_tag)

    results_per_query.append(
      {
        "type": q.get("type"),
        "tag": q.get("tag"),
        "paper_tag": q.get("paper_tag"),
        "query_text": q_text,
        "logic_cn": q.get("logic_cn") or "",
        "boolean_expr": boolean_expr if is_boolean_query else "",
        "bm25_mode": query_mode,
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
    "queries": [ { type, tag, paper_tag, query_text, sim_scores: {...} }, ... ],
    "papers": [ { id, title, abstract, ..., tags: [...] }, ... ]  // 仅保留至少有一个 tag 的论文
  }
  """
  from datetime import datetime, timezone

  os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

  id_to_paper: Dict[str, Paper] = result.get("papers") or {}
  tagged_papers = [p.to_dict() for p in id_to_paper.values() if p.tags]

  q_list = result.get("queries") or []
  if q_list:
    q0 = q_list[0]
    sim_scores = q0.get("sim_scores") or {}
    inferred_top_k = len(sim_scores) if isinstance(sim_scores, dict) else 0
  else:
    inferred_top_k = 0

  payload = {
    "top_k": inferred_top_k,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "papers": tagged_papers,
    "queries": result.get("queries") or [],
  }

  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

  log(f"[INFO] 已将带 tag 的论文和每个查询的 top_k 结果写入：{output_path}")
  log(f"[INFO] 其中带 tag 的论文数：{len(tagged_papers)}")


def main() -> None:
  parser = argparse.ArgumentParser(
    description="步骤 2.1：使用 BM25 对 ArXiv 论文池做关键词 / LLM 查询检索并打 tag。",
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
    help="可选：当使用 --input 处理单个文件时，自定义输出 JSON 路径；批处理模式下将自动写入 archive/YYYYMMDD/filtered 目录，默认后缀 .bm25.json。",
  )
  parser.add_argument(
    "--top-k",
    type=int,
    default=None,
    help="每个查询保留的 Top K 论文数；未指定时根据原始论文总数自适应：<=1000 篇取 50，每增加 1000 篇增加 50。",
  )
  parser.add_argument(
    "--k1",
    type=float,
    default=1.5,
    help="BM25 k1 参数（默认 1.5）。",
  )
  parser.add_argument(
    "--b",
    type=float,
    default=0.75,
    help="BM25 b 参数（默认 0.75）。",
  )

  args = parser.parse_args()

  config = load_config()
  pipeline_inputs = build_pipeline_inputs(config)
  queries = pipeline_inputs.get("bm25_queries") or []
  comparison = pipeline_inputs.get("comparison") or {}
  if comparison:
    log(
      "[INFO] 迁移阶段A输入对比："
      f"bm25_only_new={comparison.get('bm25_only_new_count', 0)} "
      f"bm25_only_legacy={comparison.get('bm25_only_legacy_count', 0)} "
      f"embedding_only_new={comparison.get('embedding_only_new_count', 0)} "
      f"embedding_only_legacy={comparison.get('embedding_only_legacy_count', 0)}"
    )
  if not queries:
    log("[ERROR] 未能从订阅配置中解析到 BM25 查询，退出。")
    return

  def process_single_file(input_path: str, output_path: str) -> None:
    papers = load_paper_pool(input_path)
    if not papers:
      log(f"[ERROR] 论文池为空，跳过文件：{input_path}")
      return

    total_papers = len(papers)
    if args.top_k is None or args.top_k <= 0:
      if total_papers <= 0:
        dynamic_top_k = 50
      else:
        blocks = (total_papers - 1) // 1000
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

    group_start(f"Step 2.1 - build BM25 index ({os.path.basename(input_path)})")
    log(f"[INFO] 正在为 {total_papers} 篇论文构建 BM25 索引...")
    bm25 = build_bm25_index(papers, k1=float(args.k1), b=float(args.b))
    group_end()

    group_start(f"Step 2.1 - rank queries ({os.path.basename(input_path)})")
    result = rank_papers_for_queries(
      bm25=bm25,
      papers=papers,
      queries=queries,
      top_k=dynamic_top_k,
    )
    group_end()

    save_tagged_results(result, output_path)

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
      base = os.path.basename(input_path)
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.bm25.json")

    process_single_file(input_path, output_path)
  else:
    if not os.path.isdir(RAW_DIR):
      log(f"[INFO] 原始目录不存在：{RAW_DIR}（今天没有新论文，将跳过 BM25 检索）")
      return

    raw_files = sorted(f for f in os.listdir(RAW_DIR) if f.lower().endswith(".json"))
    if not raw_files:
      log(f"[INFO] 在 {RAW_DIR} 下未找到任何 .json 原始文件。（今天没有新论文，将跳过 BM25 检索）")
      return

    log(f"[INFO] 批量模式：将在 {RAW_DIR} 下处理 {len(raw_files)} 个 JSON 文件。")
    for name in raw_files:
      input_path = os.path.join(RAW_DIR, name)
      base = name
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.bm25.json")
      process_single_file(input_path, output_path)


if __name__ == "__main__":
  main()
