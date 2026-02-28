#!/usr/bin/env python
# Step 6：根据推荐结果生成 Docs（精读区 / 速读区），并更新侧边栏。

import argparse
import html
import json
import math
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
import requests
from llm import BltClient

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
RANGE_DATE_RE = re.compile(r"^(\d{8})-(\d{8})$")

# LLM 配置（使用 llm.py 内的 BLT 客户端）
BLT_API_KEY = os.getenv("BLT_API_KEY")
BLT_MODEL = os.getenv("BLT_SUMMARY_MODEL", "gemini-3-flash-preview")
LLM_CLIENT = None
if BLT_API_KEY:
    LLM_CLIENT = BltClient(api_key=BLT_API_KEY, model=BLT_MODEL)


def call_blt_text(
    client: BltClient,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: Dict[str, Any] | None = None,
) -> str:
    client.kwargs.update(
        {
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
    )
    resp = client.chat(messages=messages, response_format=response_format)
    return (resp.get("content") or "").strip()


def strip_json_wrappers(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def repair_json_suffix(text: str) -> str:
    if not text:
        return text
    stack: List[str] = []
    in_str = False
    escaped = False
    for ch in text:
        if in_str:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            stack.append("}")
        elif ch == '[':
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
    repaired = text
    if in_str:
        repaired += '"'
    if stack:
        repaired += "".join(reversed(stack))
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def parse_llm_json(content: str) -> Dict[str, Any] | list[Any] | None:
    raw = strip_json_wrappers(content)
    if not raw:
        return None
    candidates: List[str] = []
    decoder = json.JSONDecoder()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1:
        candidates.append(raw[start:])
        if end != -1 and end > start:
            candidates.append(raw[start : end + 1])
    else:
        candidates.append(raw)
    seen = set()
    last_exc: Exception | None = None
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            obj, _idx = decoder.raw_decode(candidate)
            if isinstance(obj, (dict, list)):
                return obj
        except Exception as exc:
            last_exc = exc
            repaired = repair_json_suffix(candidate)
            if repaired != candidate:
                try:
                    obj = json.loads(repaired)
                    if isinstance(obj, (dict, list)):
                        return obj
                except Exception as exc2:
                    last_exc = exc2
    if last_exc:
        raise last_exc
    return None


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)

def log_substep(code: str, name: str, phase: str) -> None:
    """
    用于前端解析的子步骤标记。
    格式： [SUBSTEP] 6.1 - xxx START/END
    """
    phase = str(phase or "").strip().upper()
    if phase not in ("START", "END"):
        phase = "INFO"
    log(f"[SUBSTEP] {code} - {name} {phase}")


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] 未安装 PyYAML，无法解析 config.yaml。")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as e:
        log(f"[WARN] 读取 config.yaml 失败：{e}")
        return {}


def resolve_docs_dir() -> str:
    docs_dir = os.getenv("DOCS_DIR")
    config = load_config()
    paper_setting = (config or {}).get("arxiv_paper_setting") or {}
    crawler_setting = (config or {}).get("crawler") or {}
    cfg_docs = paper_setting.get("docs_dir") or crawler_setting.get("docs_dir")
    if not docs_dir and cfg_docs:
        if os.path.isabs(cfg_docs):
            docs_dir = cfg_docs
        else:
            docs_dir = os.path.join(ROOT_DIR, cfg_docs)
    if not docs_dir:
        docs_dir = os.path.join(ROOT_DIR, "docs")
    return docs_dir


def slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    return s or "paper"


def extract_pdf_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    texts = []
    try:
        for page in doc:
            texts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n\n".join(texts)


def fetch_paper_markdown_via_jina(pdf_url: str, max_retries: int = 3) -> str | None:
    if not pdf_url:
        return None
    base = "https://r.jina.ai/"
    full_url = base + pdf_url
    for attempt in range(1, max_retries + 1):
        try:
            log(f"[JINA] 第 {attempt} 次请求：{full_url}")
            resp = requests.get(full_url, timeout=60)
            if resp.status_code != 200:
                log(f"[JINA][WARN] 状态码 {resp.status_code}，响应前 100 字符：{(resp.text or '')[:100]}")
            else:
                text = (resp.text or "").strip()
                if text:
                    log("[JINA] 获取到结构化 Markdown 文本，将直接用作 .txt 内容。")
                    return text
        except Exception as e:
            log(f"[JINA][WARN] 请求失败（第 {attempt} 次）：{e}")
        time.sleep(2 * attempt)
    log("[JINA][ERROR] 多次请求失败，将回退到 PyMuPDF 抽取。")
    return None


def normalize_arxiv_id(value: str) -> str:
    """
    统一将可能携带 URL 的 arXiv 输入转换为 id。
    兼容：
    - 1706.03762
    - 1706.03762v1
    - https://arxiv.org/abs/1706.03762v1
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        raw = raw.rsplit("/", 1)[-1]
    raw = raw.split("?")[0]
    if raw.startswith("abs/"):
        raw = raw[len("abs/") :]
    if raw.startswith("pdf/"):
        raw = raw[len("pdf/") :].replace(".pdf", "")
    return raw.strip().lower()


def parse_arxiv_xml_feed(xml_text: str) -> Dict[str, Any]:
    """
    从 arXiv API XML feed 中解析第一条 paper 元数据，返回内部统一字典。
    """
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise RuntimeError("未从 arXiv 返回中解析到论文条目")

    def _text(tag: str) -> str:
        elem = entry.find(tag, ns)
        return (elem.text or "").strip() if elem is not None else ""

    arxiv_id = _text("atom:id")
    if arxiv_id:
        arxiv_id = arxiv_id.rsplit("/", 1)[-1]

    title = " ".join(_text("atom:title").split())
    abstract = " ".join(_text("atom:summary").split())
    published = _text("atom:published")
    published_date = ""
    if published:
        published_date = published.split("T", 1)[0].replace("-", "")

    authors = []
    for a in entry.findall("atom:author", ns):
        name_elem = a.find("atom:name", ns)
        if name_elem is not None:
            name = (name_elem.text or "").strip()
            if name and name not in authors:
                authors.append(name)

    pdf_url = ""
    for link in entry.findall("atom:link", ns):
        href = (link.attrib.get("href") or "").strip()
        if href.endswith(".pdf"):
            pdf_url = href
            break
        if link.attrib.get("title") == "pdf" and href:
            pdf_url = href
            break

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "published": published_date,
        "authors": authors,
        "link": pdf_url,
        "pdf_url": pdf_url,
        "llm_tags": ["query:transformer", "query:attention"],
    }


def fetch_arxiv_paper_meta(arxiv_id: str) -> Dict[str, Any]:
    """
    通过 arXiv API 拉取单篇论文元数据，用于单篇补生成。
    """
    pid = normalize_arxiv_id(arxiv_id)
    if not pid:
        raise ValueError("paper id 不能为空")
    url = f"https://export.arxiv.org/api/query?id_list={quote_plus(pid)}"
    log(f"[INFO] 拉取 arXiv 元数据：{url}")
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"arXiv API 请求失败，status={resp.status_code}")
    return parse_arxiv_xml_feed(resp.text)


def translate_title_and_abstract_to_zh(title: str, abstract: str) -> Tuple[str, str]:
    if LLM_CLIENT is None:
        return "", ""
    title = title.strip() if title else ""
    abstract = abstract.strip() if abstract else ""
    if not title and not abstract:
        return "", ""

    system_prompt = (
        "你是一名熟悉机器学习与自然科学论文的专业翻译，请将英文标题和摘要翻译为自然、准确的中文。"
        "保持学术风格，尽量保留专有名词，不要额外添加评论。"
    )
    payload = {"title": title, "abstract": abstract}
    user_text = json.dumps(payload, ensure_ascii=False)

    user_prompt = (
        "请将上面的 JSON 中的 title 与 abstract 翻译成中文，并严格输出 JSON：\n"
        "{\"title_zh\": \"...\", \"abstract_zh\": \"...\"}\n"
        "要求：只输出 JSON，不要输出任何其它说明文字。\n"
        "Output must be strict JSON only, no markdown, no fences, no extra text."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
        {"role": "user", "content": user_prompt},
    ]
    try:
        schema = {
            "type": "object",
            "properties": {
                "title_zh": {"type": "string"},
                "abstract_zh": {"type": "string"},
            },
            "required": ["title_zh", "abstract_zh"],
            "additionalProperties": False,
        }
        use_json_object = "gemini" in (getattr(LLM_CLIENT, "model", "") or "").lower()
        if use_json_object:
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": "translate_zh", "schema": schema, "strict": True},
            }

        content = call_blt_text(
            LLM_CLIENT,
            messages,
            temperature=0.2,
            max_tokens=4000,
            response_format=response_format,
        )
    except Exception:
        return "", ""

    try:
        parsed = parse_llm_json(content)
        if not isinstance(parsed, dict):
            return "", ""
        obj = parsed
        if not isinstance(obj, dict):
            return "", ""
        zh_title = str(obj.get("title_zh") or "").strip()
        zh_abstract = str(obj.get("abstract_zh") or "").strip()
    except Exception:
        return "", ""
    return zh_title, zh_abstract


def extract_section_tail(md_text: str, heading: str) -> str:
    """
    从 md 中提取某个自动生成段落（heading）后的尾部内容。
    返回不含 heading 的文本（strip 后）。
    """
    if not md_text:
        return ""
    key = f"## {heading}"
    idx = md_text.rfind(key)
    if idx == -1:
        return ""
    return md_text[idx + len(key) :].strip()


def strip_auto_sections(md_text: str) -> str:
    """
    发送给 LLM 的“论文 Markdown 元数据”只保留正文前半段，避免把旧的自动总结/速览再喂回模型。
    """
    if not md_text:
        return ""
    markers = [
        "\n\n---\n\n## 论文详细总结（自动生成）",
        "\n\n---\n\n## 速览摘要（自动生成）",
    ]
    cut_points = [md_text.find(m) for m in markers if md_text.find(m) != -1]
    if not cut_points:
        return md_text
    cut = min(cut_points)
    return md_text[:cut].rstrip()


def normalize_meta_tldr_line(md_text: str) -> Tuple[str, bool]:
    """
    兼容历史版本：元信息区 TLDR 行曾被写成 '**TLDR**: xxx \\'。
    这里把“元信息区”的 TLDR 行末尾反斜杠去掉。
    注意：`## 速览` 区块中会使用 `\\` 表达强制换行，不能误伤。
    """
    if not md_text:
        return md_text, False
    changed = False
    lines = md_text.splitlines()
    out: List[str] = []
    for line in lines:
        # 只处理元信息区 TLDR（使用英文冒号 `:` 的格式）
        if line.startswith("**TLDR**:"):
            new_line = line.rstrip()
            if new_line.endswith("\\"):
                new_line = new_line[:-1].rstrip()
            if new_line != line:
                changed = True
            out.append(new_line)
        else:
            out.append(line)
    return "\n".join(out), changed


def normalize_glance_block_format(md_text: str) -> Tuple[str, bool]:
    """
    规范 `## 速览` 区块的换行符号：
    - TLDR/Motivation/Method/Result 行末尾应带 ` \\`（强制换行）
    - Conclusion 行末尾不应带 `\\`
    """
    if not md_text:
        return md_text, False

    lines = md_text.splitlines()
    out: List[str] = []
    changed = False
    in_glance = False

    def ensure_line_break(s: str) -> str:
        ss = s.rstrip()
        if ss.endswith("\\"):
            return ss
        return ss + " \\"

    def remove_line_break(s: str) -> str:
        ss = s.rstrip()
        if ss.endswith("\\"):
            return ss[:-1].rstrip()
        return ss

    for line in lines:
        stripped = line.strip()
        if stripped == "## 速览":
            in_glance = True
            out.append(line)
            continue

        if in_glance:
            # 速览块结束条件：分隔线或下一个二级标题
            if stripped == "---" or stripped.startswith("## "):
                in_glance = False
                out.append(line)
                continue

            if stripped.startswith("**TLDR**：") or stripped.startswith("**TLDR**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Motivation**：") or stripped.startswith("**Motivation**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Method**：") or stripped.startswith("**Method**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Result**：") or stripped.startswith("**Result**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Conclusion**：") or stripped.startswith("**Conclusion**:"):
                new_line = remove_line_break(line)
            else:
                new_line = line

            if new_line != line:
                changed = True
            out.append(new_line)
            continue

        out.append(line)

    return "\n".join(out), changed


def ensure_single_sentence_end(text: str) -> str:
    """
    给 TLDR/短句补一个句末标点（避免重复 '。。'）。
    """
    s = (text or "").strip()
    if not s:
        return s
    s = s.rstrip("。.!?！？")
    return s + "。"


def upsert_auto_block(md_path: str, heading: str, content: str) -> None:
    """
    将自动生成内容写入 md：
    - 若已存在同名 heading，则替换从该块开始到文件末尾
    - 否则追加到文件末尾
    """
    key = f"## {heading}"
    block = f"\n\n---\n\n{key}\n\n{content}".rstrip() + "\n"

    with open(md_path, "r", encoding="utf-8") as f:
        txt = f.read()

    idx = txt.rfind(key)
    if idx == -1:
        new_txt = txt.rstrip() + block
    else:
        start = txt.rfind("\n\n---\n\n", 0, idx)
        if start == -1:
            start = idx
        new_txt = txt[:start].rstrip() + block

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_txt)


def upsert_glance_block_in_text(md_text: str, glance: str) -> str:
    """
    在 Markdown 文本中插入/替换 `## 速览` 区块：
    - 若已存在 `## 速览`，则替换其内容直到下一个分隔线 `---` 或下一个二级标题 `## `
    - 否则在 `## Abstract` 之前插入；若找不到则追加到末尾
    """
    if not glance:
        return md_text

    txt = md_text or ""
    key = "## 速览"
    if key in txt:
        # 替换现有速览块
        pattern = re.compile(r"(^## 速览\\s*\\n)(.*?)(?=\\n---\\n|\\n##\\s|\\Z)", re.S | re.M)
        return pattern.sub(rf"\\1{glance}\n", txt, count=1)

    abstract_idx = txt.find("## Abstract")
    if abstract_idx != -1:
        before = txt[:abstract_idx].rstrip()
        after = txt[abstract_idx:]
        return f"{before}\n\n## 速览\n{glance}\n\n---\n\n{after}"
    return (txt.rstrip() + f"\n\n## 速览\n{glance}\n").rstrip() + "\n"


def generate_deep_summary(md_file_path: str, txt_file_path: str, max_retries: int = 3) -> str | None:
    if LLM_CLIENT is None:
        log("[WARN] 未配置 BLT_API_KEY，跳过精读总结。")
        return None
    if not os.path.exists(md_file_path):
        return None

    with open(md_file_path, "r", encoding="utf-8") as f:
        paper_md_content = strip_auto_sections(f.read())

    paper_txt_content = ""
    if os.path.exists(txt_file_path):
        with open(txt_file_path, "r", encoding="utf-8") as f:
            paper_txt_content = f.read()

    system_prompt = (
        "你是一名资深学术论文分析助手，请使用中文、以 Markdown 形式，"
        "对给定论文做结构化、深入、客观的总结。"
    )
    user_prompt = (
        "请基于下面提供的论文内容，生成一段详细的中文总结，要求按照如下要点依次展开：\n"
        "1. 论文的核心问题与整体含义（研究动机和背景）。\n"
        "2. 论文提出的方法论：核心思想、关键技术细节、公式或算法流程（用文字说明即可）。\n"
        "3. 实验设计：使用了哪些数据集 / 场景，它的 benchmark 是什么，对比了哪些方法。\n"
        "4. 资源与算力：如果文中有提到，请总结使用了多少算力（GPU 型号、数量、训练时长等）。若未明确说明，也请指出这一点。\n"
        "5. 实验数量与充分性：大概做了多少组实验（如不同数据集、消融实验等），这些实验是否充分、是否客观、公平。\n"
        "6. 论文的主要结论与发现。\n"
        "7. 优点：方法或实验设计上有哪些亮点。\n"
        "8. 不足与局限：包括实验覆盖、偏差风险、应用限制等。\n\n"
        "请用分层标题和项目符号（Markdown 格式）组织上述内容，语言尽量简洁但信息要尽量完整。\n"
        "要求：最后单独输出一行“（完）”作为结束标记。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    if paper_txt_content:
        messages.append({"role": "user", "content": f"### 论文 PDF 提取文本 ###\n{paper_txt_content}"})
    messages.append({"role": "user", "content": f"### 论文 Markdown 元数据 ###\n{paper_md_content}"})
    messages.append({"role": "user", "content": user_prompt})

    last = ""
    for attempt in range(1, max_retries + 1):
        try:
            summary = call_blt_text(LLM_CLIENT, messages, temperature=0.3, max_tokens=4096)
            summary = (summary or "").strip()
            if not summary:
                continue
            last = summary
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] deep_summary attempt={attempt} len={len(summary)} tail={summary[-20:]!r}")
            if "（完）" in summary:
                return summary
            # 续写一次：避免输出被截断
            cont_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "你上一次的总结可能被截断了，请从中断处继续补全，不要重复已输出内容。"},
                {"role": "user", "content": f"上一次输出如下：\n\n{summary}\n\n请继续补全，最后以一行“（完）”结束。"},
            ]
            cont = call_blt_text(LLM_CLIENT, cont_messages, temperature=0.3, max_tokens=2048)
            cont = (cont or "").strip()
            merged = f"{summary}\n\n{cont}".strip()
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] deep_summary_cont attempt={attempt} len={len(cont)} merged_tail={merged[-20:]!r}")
            if "（完）" in merged:
                return merged
        except Exception as e:
            log(f"[WARN] 精读总结失败（第 {attempt} 次）：{e}")
            time.sleep(2 * attempt)
    return last or None


def generate_glance_overview(title: str, abstract: str, max_retries: int = 3) -> str | None:
    """
    生成论文速览（包含 TLDR、Motivation、Method、Result、Conclusion）。
    使用 JSON 结构化输出，确保返回完整的五个字段。
    """
    if LLM_CLIENT is None:
        log("[WARN] 未配置 LLM_CLIENT，跳过速览生成。")
        return None

    system_prompt = "你是论文速览助手，请用中文简洁地总结论文的关键信息。"
    payload = {"title": title, "abstract": abstract}
    user_text = json.dumps(payload, ensure_ascii=False)
    user_prompt = (
        "请基于上面的 JSON 中的 title 和 abstract，输出一个中文速览摘要，严格返回 JSON（不要输出任何其它文字）：\n"
        "{\"tldr\":\"...\",\"motivation\":\"...\",\"method\":\"...\",\"result\":\"...\",\"conclusion\":\"...\"}\n"
        "要求：\n"
        "- tldr：100字左右的完整概述，涵盖研究背景、方法和主要贡献\n"
        "- motivation/method/result/conclusion：每个字段一句话概括，简洁明了\n"
        "Output must be strict JSON only, no markdown, no fences, no extra text."
    )

    schema = {
        "type": "object",
        "properties": {
            "tldr": {"type": "string"},
            "motivation": {"type": "string"},
            "method": {"type": "string"},
            "result": {"type": "string"},
            "conclusion": {"type": "string"},
        },
        "required": ["tldr", "motivation", "method", "result", "conclusion"],
        "additionalProperties": False,
    }
    use_json_object = "gemini" in (getattr(LLM_CLIENT, "model", "") or "").lower()
    if use_json_object:
        response_format = {"type": "json_object"}
    else:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "glance_overview", "schema": schema, "strict": True},
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(1, max_retries + 1):
        try:
            content = call_blt_text(
                LLM_CLIENT,
                messages,
                temperature=0.2,
                max_tokens=2048,
                response_format=response_format,
            )
            parsed = parse_llm_json(content)
            if not isinstance(parsed, dict):
                continue
            obj = parsed
            tldr = str(obj.get("tldr") or "").strip()
            motivation = str(obj.get("motivation") or "").strip()
            method = str(obj.get("method") or "").strip()
            result = str(obj.get("result") or "").strip()
            conclusion = str(obj.get("conclusion") or "").strip()
            if not (tldr and motivation and method and result and conclusion):
                continue
            return "\n".join(
                [
                    f"**TLDR**：{ensure_single_sentence_end(tldr)} \\",
                    f"**Motivation**：{ensure_single_sentence_end(motivation)} \\",
                    f"**Method**：{ensure_single_sentence_end(method)} \\",
                    f"**Result**：{ensure_single_sentence_end(result)} \\",
                    f"**Conclusion**：{ensure_single_sentence_end(conclusion)}",
                ]
            )
        except Exception as e:
            # 额度不足等“硬失败”不必重试，直接降级
            msg = str(e)
            if (
                "insufficient_user_quota" in msg
                or "额度不足" in msg
                or "insufficient quota" in msg
                or ("403" in msg and "Forbidden" in msg)
            ):
                log(f"[WARN] 速览生成失败（额度不足，停止重试）：{e}")
                break
            log(f"[WARN] 速览生成失败（第 {attempt} 次）：{e}")
            time.sleep(2 * attempt)
    return None


def build_glance_fallback(paper: Dict[str, Any]) -> str:
    """
    当 LLM 额度不足/不可用时的降级速览：
    - TLDR 优先用 llm_tldr_cn/llm_tldr；否则用摘要首句；
    - 其余字段用“基于摘要的启发式”生成，保证 5 段齐全。
    """
    abstract = str(paper.get("abstract") or "").strip()
    tldr = (
        str(paper.get("llm_tldr_cn") or paper.get("llm_tldr") or paper.get("llm_tldr_en") or "").strip()
    )
    evidence = (
        str(paper.get("llm_evidence_cn") or paper.get("llm_evidence") or paper.get("llm_evidence_en") or "").strip()
    )

    def first_sentence(text: str) -> str:
        s = (text or "").strip()
        if not s:
            return ""
        parts = re.split(r"(?<=[。！？.!?])\\s+", s)
        return (parts[0] if parts else s).strip()

    if not tldr:
        tldr = first_sentence(abstract)
    if not tldr and evidence:
        tldr = evidence
    tldr = ensure_single_sentence_end(tldr or "基于摘要生成的速览信息。")

    motivation = ensure_single_sentence_end(
        first_sentence(evidence) or "本文关注一个具有代表性的研究问题，并尝试提升现有方法的效果或可解释性。"
    )

    method_hint = ""
    if abstract:
        m = re.search(r"(we (?:propose|present|introduce|develop)[^\\.]{0,200})\\.", abstract, re.I)
        if m:
            method_hint = m.group(1).strip()
    method = ensure_single_sentence_end(method_hint or "方法与实现细节请参考摘要与正文。")

    result_hint = ""
    if abstract:
        m = re.search(r"(experiments? (?:show|demonstrate)[^\\.]{0,200})\\.", abstract, re.I)
        if m:
            result_hint = m.group(1).strip()
    result = ensure_single_sentence_end(result_hint or "结果与对比结论请参考摘要与正文。")

    conclusion = ensure_single_sentence_end("总体而言，该工作在所述任务上展示了有效性，并提供了可复用的思路或工具。")

    return "\n".join(
        [
            f"**TLDR**：{tldr} \\",
            f"**Motivation**：{motivation} \\",
            f"**Method**：{method} \\",
            f"**Result**：{result} \\",
            f"**Conclusion**：{conclusion}",
        ]
    )


def build_tags_html(section: str, llm_tags: List[str]) -> str:
    tags_html: List[str] = []
    # 新链路按 query 标签展示；历史 keyword:* 统一折叠为 query:*，避免重复。
    seen = set()
    for tag in llm_tags:
        raw = str(tag).strip()
        if not raw:
            continue
        kind, label = split_sidebar_tag(raw)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # 前台主标签统一使用 query（蓝色），paper 为预留类型。
        css = {
            "query": "tag-blue",
            "paper": "tag-pink",
        }.get(kind, "tag-pink")
        tags_html.append(
            f'<span class="tag-label {css}">{html.escape(label)}</span>'
        )
    return " ".join(tags_html)


def normalize_meta_tags_line(content: str) -> Tuple[str, bool]:
    """
    兼容历史格式：文章页 `**Tags**` 不再展示“精读区/速读区”标签。
    只删除标签内容严格为“精读区/速读区”的 span，避免误伤关键词标签。
    """
    if not content:
        return content, False
    pattern = re.compile(
        r'<span\s+class="tag-label\s+tag-(?:blue|green)">\s*(?:精读区|速读区)\s*</span>\s*',
        re.IGNORECASE,
    )
    fixed = pattern.sub("", content)
    return fixed, fixed != content


def replace_meta_line(md_text: str, label: str, value: str, add_slash: bool = True) -> Tuple[str, bool]:
    """
    替换形如 `**Label**: xxx \\` 的元数据行。
    - 仅替换第一处匹配
    - 若不存在则不插入（避免意外改写用户自定义元信息结构）
    """
    txt = md_text or ""
    v = (value or "").strip()
    if not v:
        return txt, False
    line = f"**{label}**: {v}"
    if add_slash:
        line += " " + "\\"
    pattern = re.compile(f"^\\*\\*{re.escape(label)}\\*\\*:\\s*.*$", re.M)
    # 使用函数替换，避免 replacement string 中的反斜杠被当作转义序列解析
    new_txt, n = pattern.subn(lambda _m: line, txt, count=1)
    return new_txt, n > 0 and new_txt != txt


def format_date_str(date_str: str) -> str:
    s = str(date_str or "").strip()
    m = RANGE_DATE_RE.match(s)
    if m:
        a, b = m.group(1), m.group(2)
        return f"{a[:4]}-{a[4:6]}-{a[6:]} ~ {b[:4]}-{b[4:6]}-{b[6:]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return date_str


def prepare_paper_paths(docs_dir: str, date_str: str, title: str, arxiv_id: str) -> Tuple[str, str, str]:
    slug = slugify(title)
    basename = f"{arxiv_id}-{slug}" if arxiv_id else slug
    if RANGE_DATE_RE.match(date_str):
        target_dir = os.path.join(docs_dir, date_str)
        paper_id = f"{date_str}/{basename}"
    else:
        ym = date_str[:6]
        day = date_str[6:]
        target_dir = os.path.join(docs_dir, ym, day)
        paper_id = f"{ym}/{day}/{basename}"
    md_path = os.path.join(target_dir, f"{basename}.md")
    txt_path = os.path.join(target_dir, f"{basename}.txt")
    return md_path, txt_path, paper_id


def prepare_day_report_paths(docs_dir: str, date_str: str) -> Tuple[str, str]:
    if RANGE_DATE_RE.match(date_str):
        day_dir = os.path.join(docs_dir, date_str)
    else:
        ym = date_str[:6]
        day = date_str[6:]
        day_dir = os.path.join(docs_dir, ym, day)
    day_readme = os.path.join(day_dir, "README.md")
    return day_dir, day_readme


def prepare_home_module_paths(docs_dir: str) -> Tuple[str, str]:
    notice_path = os.path.join(docs_dir, "_home_notice.md")
    promo_path = os.path.join(docs_dir, "_home_promo.md")
    return notice_path, promo_path


def ensure_home_module_files(docs_dir: str) -> Tuple[str, str]:
    notice_path, promo_path = prepare_home_module_paths(docs_dir)
    if not os.path.exists(notice_path):
        with open(notice_path, "w", encoding="utf-8") as f:
            f.write("────────────────────────────────────────\n")
            f.write("（公告占位）欢迎使用 Daily Paper Reader。\n")
            f.write("（公告占位）可在此放置本周更新、维护通知等。\n")
            f.write("────────────────────────────────────────\n")
    if not os.path.exists(promo_path):
        with open(promo_path, "w", encoding="utf-8") as f:
            f.write("════════════════════════════════════════\n")
            f.write("（宣传占位）欢迎 Star / Fork 本项目。\n")
            f.write("（宣传占位）欢迎提交 Issue 与 PR。\n")
            f.write("════════════════════════════════════════\n")
    return notice_path, promo_path


def _read_module_markdown(path: str) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return (f.read() or "").strip()
    except Exception:
        return ""


def _format_entry_tags(tags: List[Tuple[str, str]]) -> str:
    labels: List[str] = []
    for kind, label in tags or []:
        k = (kind or "").strip()
        v = (label or "").strip()
        if k == "score":
            try:
                score_num = float(v)
                labels.append(f"评分：{score_num:.1f}/10")
            except Exception:
                labels.append(f"评分：{v}")
            continue
        if not v:
            continue
        if k in ("keyword", "query", "paper"):
            labels.append(f"{k}:{v}")
        else:
            labels.append(v)
    return "、".join(labels) if labels else "无标签"


def _entry_score_text(tags: List[Tuple[str, str]]) -> str:
    for kind, label in tags or []:
        if (kind or "").strip() == "score":
            v = (label or "").strip()
            if not v:
                return ""
            try:
                return f"{float(v):.1f}/10"
            except Exception:
                return v
    return ""


def build_daily_brief_summary(
    date_label: str,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    total_count: int,
    run_status: str,
) -> str:
    if total_count == 0:
        return "> 今日无新推荐，系统未产出可展示论文。"

    def _format_preview_item(paper_id: str, title: str, tags: List[Tuple[str, str]]) -> str:
        name = ((title or "").strip() or paper_id)
        score = _entry_score_text(tags)
        return f"《{name}》（{score}）" if score else f"《{name}》"

    deep_preview = [_format_preview_item(paper_id, title, tags) for paper_id, title, tags in deep_entries[:2] if (title or paper_id)]
    quick_preview = [_format_preview_item(paper_id, title, tags) for paper_id, title, tags in quick_entries[:3] if (title or paper_id)]
    highlight = []
    if deep_preview:
        highlight.append(f"- 精读：{', '.join(deep_preview)}")
    if quick_preview:
        highlight.append(f"- 速读：{', '.join(quick_preview)}")
    if not highlight:
        return (
            f"- 状态：{run_status}。\n"
            f"- 已完成今日生成，共收录 {total_count} 篇（精读 {len(deep_entries)} 篇，速读 {len(quick_entries)} 篇）。"
        )

    fallback = (
        f"- 今日共生成 {total_count} 篇推荐（精读 {len(deep_entries)} 篇，速读 {len(quick_entries)} 篇）\n"
        + "\n".join(highlight)
        + "\n- 这些结果覆盖了当下较热的方向，建议先看精读区论文的关键问题与方法。"
    )

    if LLM_CLIENT is None:
        return fallback

    system_prompt = (
        "你是日报编辑，请输出 3 句以内、吸引人、简洁但具体的中文总结。"
        "内容必须基于给定的推荐数据，不要编造论文信息。"
    )
    user_prompt = (
        f"日报日期：{date_label}\n"
        f"状态：{run_status}\n"
        f"总数：{total_count} 篇\n"
        f"精读：{len(deep_entries)} 篇\n"
        f"速读：{len(quick_entries)} 篇\n"
        f"精读列表（含分数）：{json.dumps(deep_preview, ensure_ascii=False)}\n"
        f"速读列表（含分数）：{json.dumps(quick_preview, ensure_ascii=False)}\n\n"
        "请按以下格式输出：\n"
        "1) 一句概括今天做了什么，适合标题感官。\n"
        "2) 一句给出最值得看的 1~2 个方向/结论。\n"
        "3) 一句给出下步建议（面向普通读者）。\n"
        "直接输出 1-3 行文本，不要 Markdown 标题，也不要 JSON。"
    )
    try:
        content = call_blt_text(
            LLM_CLIENT,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.45,
            max_tokens=768,
        )
        content = (content or "").strip()
        if content:
            return content
    except Exception as e:
        log(f"[WARN] 生成日报简报失败：{e}")

    return fallback


def build_docsify_id_href(path_no_ext: str) -> str:
    """
    统一生成 Docsify Markdown 内链格式：`/...`。
    注意：在 Markdown 中使用 `(#/...)` 会被 Docsify 当作页内锚点，触发 querySelector 报错。
    """
    p = str(path_no_ext or "").strip()
    p = p.replace("\\", "/").strip()
    p = re.sub(r"\.md$", "", p, flags=re.IGNORECASE)
    if not p:
        return "/"
    p = p.lstrip("/")
    return f"/{p}"


def build_latest_report_section(
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
) -> str:
    effective_label = (date_label or "").strip() or format_date_str(date_str)
    run_status = "成功" if recommend_exists else "未产出 recommend 文件（视为无结果）"
    total = len(deep_entries) + len(quick_entries)
    summary = build_daily_brief_summary(
        date_label=effective_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        total_count=total,
        run_status=run_status,
    )

    lines: List[str] = []
    lines.append(f"- 最新运行日期：{effective_label}")
    lines.append(f"- 运行时间：{generated_at}")
    lines.append(f"- 运行状态：{run_status}")
    lines.append(f"- 本次总论文数：{total}")
    lines.append(f"- 精读区：{len(deep_entries)}")
    lines.append(f"- 速读区：{len(quick_entries)}")
    if summary:
        lines.append("")
        lines.append("### 今日简报（AI）")
        lines.append(summary)
    if RANGE_DATE_RE.match(date_str):
        report_href = build_docsify_id_href(f"{date_str}/README")
    else:
        ym = date_str[:6]
        day = date_str[6:]
        report_href = build_docsify_id_href(f"{ym}/{day}/README")
    lines.append(f"- 详情：[{report_href}]({report_href})")
    lines.append("")
    lines.append("### 精读区论文标签")
    if deep_entries:
        for idx, (paper_id, title, tags) in enumerate(deep_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)})  ")
            lines.append(f"   标签：{_format_entry_tags(tags)}")
    else:
        lines.append("- 本次无精读推荐。")
    lines.append("")
    lines.append("### 速读区论文标签")
    if quick_entries:
        for idx, (paper_id, title, tags) in enumerate(quick_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)})  ")
            lines.append(f"   标签：{_format_entry_tags(tags)}")
    else:
        lines.append("- 本次无速读推荐。")
    lines.append("")
    return "\n".join(lines)


def normalize_sidebar_tag(tag: str) -> str:
    text = (tag or "").strip()
    if not text:
        return ""
    for prefix in ("keyword:", "query:", "paper:", "ref:", "cite:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def split_sidebar_tag(tag: str) -> Tuple[str, str]:
    """
    将 tag 解析为 (kind, label)：
    - keyword:xxx -> ("keyword", "xxx")
    - query:xxx   -> ("query", "xxx")
    - paper/ref/cite:xxx -> ("paper", "xxx")  # 预留：论文引用/跟踪标签
    - 其它 -> ("other", 原文本)
    """
    raw = (tag or "").strip()
    if not raw:
        return ("other", "")
    for prefix, kind in (
        ("keyword:", "keyword"),
        ("query:", "query"),
        ("paper:", "paper"),
        ("ref:", "paper"),
        ("cite:", "paper"),
    ):
        if raw.startswith(prefix):
            return (kind, raw[len(prefix) :].strip())
    return ("other", raw)


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def score_to_star_rating(score: Any) -> float:
    """
    将 10 分制评分映射为 5 星制，并四舍五入到 0.5 星。
    例：10->5，9->4.5，8->4，7->3.5
    """
    try:
        s = float(score)
    except Exception:
        return 0.0
    if not math.isfinite(s):
        return 0.0
    s = max(0.0, min(10.0, s))
    return round_half_up(s) / 2.0


def build_sidebar_stars_html(score: Any) -> str:
    rating = score_to_star_rating(score)
    try:
        score_str = f"{float(score):.1f}"
    except Exception:
        score_str = ""

    if score_str:
        title = f"评分：{score_str}/10（{rating:.1f}/5）"
    else:
        title = "评分：无"

    pct = max(0.0, min(100.0, (rating / 5.0) * 100.0))
    pct_str = f"{pct:.0f}%"

    # 使用“背景星 + 填充星”的方式支持半星/小数显示
    return (
        f'<span class="dpr-stars" title="{html.escape(title)}" '
        f'aria-label="{rating:.1f} out of 5">'
        f'<span class="dpr-stars-bg">☆☆☆☆☆</span>'
        f'<span class="dpr-stars-fill" style="width:{pct_str}">★★★★★</span>'
        f"</span>"
    )


def extract_sidebar_tags(paper: Dict[str, Any], max_tags: int = 6) -> List[Tuple[str, str]]:
    """
    侧边栏展示的标签：
    - 只使用 llm_tags（与文章页 `**Tags**` 保持一致），避免出现“侧边栏与正文不对应”
    - 去重 + 限制数量，避免侧边栏过长
    """
    raw: List[str] = []
    if isinstance(paper.get("llm_tags"), list):
        raw.extend([str(t) for t in (paper.get("llm_tags") or [])])

    # 历史 keyword:* 统一折叠到 query:*，避免同名重复。
    seen_labels = set()
    q: List[Tuple[str, str]] = []
    paper_tags: List[Tuple[str, str]] = []
    other: List[Tuple[str, str]] = []

    for t in raw:
        kind, label = split_sidebar_tag(t)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen_labels:
            continue
        seen_labels.add(dedup_key)
        if kind == "query":
            q.append((kind, label))
        elif kind == "paper":
            paper_tags.append((kind, label))
        else:
            other.append((kind, label))

        if max_tags > 0 and len(seen_labels) >= max_tags:
            break

    # 展示顺序：评分 -> query -> 论文引用(paper) -> 其它
    tags = q + paper_tags + other
    score = paper.get("llm_score")
    score_tag = []
    if score is not None:
        try:
            score_tag.append(("score", str(float(score))))
        except Exception:
            score_tag.append(("score", str(score)))
    return score_tag + tags


def ensure_text_content(pdf_url: str, txt_path: str) -> str:
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()
    text_content = fetch_paper_markdown_via_jina(pdf_url)
    if text_content is None and pdf_url:
        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
            tmp_pdf.write(resp.content)
            tmp_pdf.flush()
            text_content = extract_pdf_text(tmp_pdf.name)
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_content or "")
    return text_content or ""


def build_markdown_content(
    paper: Dict[str, Any],
    section: str,
    zh_title: str,
    zh_abstract: str,
    tags_list: List[str],
) -> str:
    """
    生成论文 Markdown 内容，使用 YAML front matter 存储元数据。
    前端通过解析 front matter 渲染页面布局。
    """
    title = (paper.get("title") or "").strip()
    authors = paper.get("authors") or []
    published = str(paper.get("published") or "").strip()
    if published:
        published = published[:10]
    pdf_url = str(paper.get("link") or paper.get("pdf_url") or "").strip()
    score = paper.get("llm_score")
    evidence = (
        paper.get("llm_evidence_cn")
        or paper.get("llm_evidence")
        or paper.get("llm_evidence_en")
        or ""
    ).strip()
    tldr = (
        paper.get("llm_tldr_cn")
        or paper.get("llm_tldr")
        or paper.get("llm_tldr_en")
        or ""
    ).strip()
    abstract_en = (paper.get("abstract") or "").strip()
    if not abstract_en:
        abstract_en = "arXiv did not provide an abstract for this paper."

    # 解析速览内容
    glance = paper.get("_glance_overview", "").strip()
    glance_tldr = ""
    glance_motivation = ""
    glance_method = ""
    glance_result = ""
    glance_conclusion = ""

    if glance:
        for line in glance.split("\n"):
            line = line.strip().rstrip("\\").strip()
            if line.startswith("**TLDR**：") or line.startswith("**TLDR**:"):
                glance_tldr = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Motivation**：") or line.startswith("**Motivation**:"):
                glance_motivation = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Method**：") or line.startswith("**Method**:"):
                glance_method = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Result**：") or line.startswith("**Result**:"):
                glance_result = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Conclusion**：") or line.startswith("**Conclusion**:"):
                glance_conclusion = line.split("：", 1)[-1].split(":", 1)[-1].strip()

    # 优先使用速览生成的 TLDR（100字左右），否则使用原来的 TLDR
    display_tldr = glance_tldr if glance_tldr else tldr

    # 辅助函数：转义 YAML 字符串中的特殊字符
    def yaml_escape(s: str) -> str:
        if not s:
            return '""'
        # 如果包含特殊字符，用双引号包裹并转义内部双引号
        if any(c in s for c in [':', '#', '"', "'", '\n', '[', ']', '{', '}', ',', '&', '*', '!', '|', '>', '%', '@', '`']):
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
        return s

    # 构建 YAML front matter
    lines = ["---"]
    lines.append(f"title: {yaml_escape(title)}")
    if zh_title:
        lines.append(f"title_zh: {yaml_escape(zh_title)}")
    lines.append(f"authors: {yaml_escape(', '.join(authors) if authors else 'Unknown')}")
    lines.append(f"date: {yaml_escape(published or 'Unknown')}")
    if pdf_url:
        lines.append(f"pdf: {yaml_escape(pdf_url)}")
    if tags_list:
        # 保留完整的 kind:label 格式，前端渲染时再处理
        lines.append(f"tags: [{', '.join(yaml_escape(t) for t in tags_list)}]")
    if score is not None:
        lines.append(f"score: {score}")
    if evidence:
        lines.append(f"evidence: {yaml_escape(evidence)}")
    if display_tldr:
        lines.append(f"tldr: {yaml_escape(display_tldr)}")

    # 速览字段
    if glance_motivation:
        lines.append(f"motivation: {yaml_escape(glance_motivation)}")
    if glance_method:
        lines.append(f"method: {yaml_escape(glance_method)}")
    if glance_result:
        lines.append(f"result: {yaml_escape(glance_result)}")
    if glance_conclusion:
        lines.append(f"conclusion: {yaml_escape(glance_conclusion)}")

    lines.append("---")
    lines.append("")

    # 正文部分：摘要
    if zh_abstract:
        lines.append("## 摘要")
        lines.append(zh_abstract)
        lines.append("")

    lines.append("## Abstract")
    lines.append(abstract_en)

    return "\n".join(lines)


def build_tags_list(section: str, llm_tags: List[str]) -> List[str]:
    """
    构建标签列表，保留 kind:label 格式。
    """
    tags: List[str] = []
    seen = set()
    for tag in llm_tags:
        raw = str(tag).strip()
        if not raw:
            continue
        kind, label = split_sidebar_tag(raw)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        tags.append(dedup_key)
    return tags


def process_paper(
    paper: Dict[str, Any],
    section: str,
    date_str: str,
    docs_dir: str,
    glance_only: bool = False,
    force_glance: bool = False,
) -> Tuple[str, str]:
    title = (paper.get("title") or "").strip()
    arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
    md_path, txt_path, paper_id = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
    abstract_en = (paper.get("abstract") or "").strip()
    pdf_url = str(paper.get("link") or paper.get("pdf_url") or "").strip()

    glance = ""

    if os.path.exists(md_path):
        # 即使是 glance-only，也要确保生成/补齐 .txt（用于前端聊天上下文等）
        if glance_only and pdf_url:
            try:
                ensure_text_content(pdf_url, txt_path)
            except Exception:
                # 不阻塞文档生成流程：txt 拉取失败时继续（避免因为网络/源站问题导致整批中断）
                pass

        # 修复模式：若自动总结/速览存在“被截断”的迹象，则仅重生成该段落，不改动前面正文
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""

        # 若已存在 Markdown，但缺少中文标题/中文摘要，则在“重新跑 Step6”时自动补齐
        # （历史上 --glance-only 或部分修复流程不会写入中文标题/摘要）
        if not glance_only and existing:
            try:
                lines = existing.splitlines()
                # 判断顶部是否已有两行 H1（英文+中文）
                h1_count = 0
                for line in lines[:6]:
                    if line.startswith("# "):
                        h1_count += 1
                    elif line.strip() == "":
                        # 允许空行，但一旦遇到非 H1 非空行就停止
                        continue
                    else:
                        break

                has_zh_title = h1_count >= 2
                has_zh_abstract = "## 摘要" in existing
                need_zh = (not has_zh_title) or (not has_zh_abstract)

                if need_zh:
                    zh_title, zh_abstract = translate_title_and_abstract_to_zh(
                        title, abstract_en
                    )
                    updated = existing

                    if (not has_zh_title) and zh_title:
                        # 插入到第一行英文标题之后
                        out_lines: List[str] = []
                        inserted = False
                        for i, line in enumerate(lines):
                            out_lines.append(line)
                            if i == 0 and line.startswith("# "):
                                out_lines.append(f"# {zh_title}")
                                inserted = True
                        if inserted:
                            updated = "\n".join(out_lines)

                    if (not has_zh_abstract) and zh_abstract:
                        # 插入到 `## Abstract` 之前（若不存在则追加在末尾）
                        if "## Abstract" in updated:
                            updated = updated.replace(
                                "## Abstract",
                                "## 摘要\n" + zh_abstract.strip() + "\n\n## Abstract",
                                1,
                            )
                        else:
                            updated = (
                                updated.rstrip()
                                + "\n\n## 摘要\n"
                                + zh_abstract.strip()
                                + "\n"
                            )

                    if updated != existing:
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(updated + ("\n" if not updated.endswith("\n") else ""))
                        existing = updated
            except Exception:
                # 补齐中文标题/摘要失败时不影响其它生成逻辑
                pass

        # 已存在速览则默认不重复生成（避免重复 LLM 调用），除非 force_glance=true
        has_glance = "## 速览" in existing
        if force_glance or not has_glance:
            glance = generate_glance_overview(title, abstract_en) or build_glance_fallback(paper)
            if glance:
                paper["_glance_overview"] = glance

        # 修复历史格式：TLDR 行末尾不应带反斜杠
        fixed, changed = normalize_meta_tldr_line(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
            existing = fixed
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] fixed TLDR trailing slash: {os.path.basename(md_path)}")

        # 修复历史格式：文章页 Tags 不再显示“精读区/速读区”
        fixed, changed = normalize_meta_tags_line(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
            existing = fixed
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] removed section tag from Tags: {os.path.basename(md_path)}")

        # 同步 Tags 行（例如 keyword:SR 与 query:SR 同名时也要都展示）
        tags_html = build_tags_html(section, paper.get("llm_tags") or [])
        if tags_html:
            updated, changed = replace_meta_line(existing, "Tags", tags_html, add_slash=True)
            if changed:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(updated + ("\n" if not updated.endswith("\n") else ""))
                existing = updated

        # 规范速览块格式：TLDR/Motivation/Method/Result 末尾应带 `\\`
        updated, changed = normalize_glance_block_format(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(updated + ("\n" if not updated.endswith("\n") else ""))
            existing = updated

        # 插入/替换速览内容
        if glance and (force_glance or "## 速览" not in existing):
            updated = upsert_glance_block_in_text(existing, glance)
            if updated != existing:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(updated)
                existing = updated

        if glance_only:
            # 只生成速览：不拉取 PDF、不做精读总结
            return paper_id, title

        if section == "deep":
            # 精读区：检查是否已有详细总结
            tail = extract_section_tail(existing, "论文详细总结（自动生成）")
            if tail:
                return paper_id, title

            # 生成详细总结
            pdf_url = str(paper.get("link") or paper.get("pdf_url") or "").strip()
            ensure_text_content(pdf_url, txt_path)
            summary = generate_deep_summary(md_path, txt_path)
            if summary:
                upsert_auto_block(md_path, "论文详细总结（自动生成）", summary)
            return paper_id, title
        else:
            # 速读区：不生成详细总结，只保留速览和摘要
            return paper_id, title

    # 新文件：如果只需要速览，则不拉取 PDF/Jina 文本，直接用元数据生成页面
    if glance_only:
        # 速览模式也需要生成/补齐全文 txt（优先 jina，失败则 pymupdf 兜底）
        if pdf_url:
            try:
                ensure_text_content(pdf_url, txt_path)
            except Exception:
                pass
        glance = generate_glance_overview(title, abstract_en) or build_glance_fallback(paper)
        if glance:
            paper["_glance_overview"] = glance
        tags_list = build_tags_list(section, paper.get("llm_tags") or [])
        content = build_markdown_content(paper, section, "", "", tags_list)
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        return paper_id, title

    # 新文件：生成完整内容
    pdf_url = str(paper.get("link") or paper.get("pdf_url") or "").strip()
    ensure_text_content(pdf_url, txt_path)

    zh_title, zh_abstract = translate_title_and_abstract_to_zh(title, abstract_en)
    tags_list = build_tags_list(section, paper.get("llm_tags") or [])
    glance = generate_glance_overview(title, abstract_en) or build_glance_fallback(paper)
    if glance:
        paper["_glance_overview"] = glance
    content = build_markdown_content(paper, section, zh_title, zh_abstract, tags_list)

    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 精读区：生成详细总结
    if section == "deep":
        summary = generate_deep_summary(md_path, txt_path)
        if summary:
            upsert_auto_block(md_path, "论文详细总结（自动生成）", summary)
    # 速读区：不生成额外的总结，只保留速览和摘要

    return paper_id, title


def update_sidebar(
    sidebar_path: str,
    date_str: str,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    date_label: str | None = None,
) -> None:
    def render_sidebar_tag(kind: str, label: str) -> str:
        safe_kind = html.escape(kind or "other")
        if kind == "score":
            star_html = build_sidebar_stars_html(label)
            return f'<span class="dpr-sidebar-tag dpr-sidebar-tag-{safe_kind}">{star_html}</span>'
        return f'<span class="dpr-sidebar-tag dpr-sidebar-tag-{safe_kind}">{html.escape(label)}</span>'

    effective_label = (date_label or "").strip() or format_date_str(date_str)
    # 用隐藏 marker 做稳定定位，避免“展示标题”变更导致无法覆盖更新
    marker = f"<!--dpr-date:{date_str}-->"
    day_heading = f"  * {effective_label} {marker}\n"
    legacy_day_heading = f"  * {format_date_str(date_str)}\n"

    lines: List[str] = []
    if os.path.exists(sidebar_path):
        with open(sidebar_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    daily_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("* Daily Papers"):
            daily_idx = i
            break
    if daily_idx == -1:
        if not any("[首页]" in line for line in lines):
            lines.append("* [首页](/)\n")
        lines.append("* Daily Papers\n")
        daily_idx = len(lines) - 1

    day_idx = -1
    for i in range(daily_idx + 1, len(lines)):
        line = lines[i]
        if line.startswith("* "):
            break
        # 优先按 marker 精准匹配
        if marker in line:
            day_idx = i
            break
        # 兼容历史格式（没有 marker）
        if line == legacy_day_heading:
            day_idx = i
            break

    if day_idx != -1:
        end = day_idx + 1
        while end < len(lines):
            if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
                break
            end += 1
        del lines[day_idx:end]

    block: List[str] = [day_heading]
    if deep_entries:
        block.append("    * 精读区\n")
        for paper_id, title, tags in deep_entries:
            safe_title = html.escape((title or "").strip() or paper_id)
            href = f"#/{paper_id}"
            tag_html = " ".join(render_sidebar_tag(kind, label) for kind, label in (tags or []))
            tags_block = f'<div class="dpr-sidebar-tags">{tag_html}</div>' if tag_html else ""
            block.append(
                "      * "
                f'<a class="dpr-sidebar-item-link" href="{href}"><div class="dpr-sidebar-title">{safe_title}</div>'
                f"{tags_block}</a>\n"
            )
    if quick_entries:
        block.append("    * 速读区\n")
        for paper_id, title, tags in quick_entries:
            safe_title = html.escape((title or "").strip() or paper_id)
            href = f"#/{paper_id}"
            tag_html = " ".join(render_sidebar_tag(kind, label) for kind, label in (tags or []))
            tags_block = f'<div class="dpr-sidebar-tags">{tag_html}</div>' if tag_html else ""
            block.append(
                "      * "
                f'<a class="dpr-sidebar-item-link" href="{href}"><div class="dpr-sidebar-title">{safe_title}</div>'
                f"{tags_block}</a>\n"
            )

    insert_idx = daily_idx + 1
    lines[insert_idx:insert_idx] = block

    # 清理历史 Sidebar 中遗留的“日报”入口
    i = daily_idx + 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("* "):
            break
        if lines[i].startswith("    * [日报]("):
            del lines[i]
            continue
        i += 1

    with open(sidebar_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def build_day_report_markdown(
    date_str: str,
    date_label: str | None,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    recommend_exists: bool,
) -> str:
    effective_label = (date_label or "").strip() or format_date_str(date_str)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(deep_entries) + len(quick_entries)
    run_status = "成功" if recommend_exists else "未产出 recommend 文件（视为无结果）"
    summary = build_daily_brief_summary(
        date_label=effective_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        total_count=total,
        run_status=run_status,
    )

    lines: List[str] = []
    lines.append(f"# 日报 · {effective_label}")
    lines.append("")
    lines.append(f"- 生成时间：{generated_at}")
    lines.append(f"- 当次推荐总数：{total}")
    lines.append(f"- 精读区：{len(deep_entries)}")
    lines.append(f"- 速读区：{len(quick_entries)}")
    if summary:
        lines.append("")
        lines.append("## 今日简报（AI）")
        lines.append(summary)
    lines.append("")

    if not recommend_exists:
        lines.append("> 本次未找到 recommend 结果文件。")
        lines.append("")
    elif total == 0:
        lines.append("> 本次触发没有产出可推荐论文。")
        lines.append("")

    lines.append("## 精读区")
    if deep_entries:
        for idx, (paper_id, title, _tags) in enumerate(deep_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            score = _entry_score_text(_tags)
            suffix = f"（{score}）" if score else ""
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)}) {suffix}")
    else:
        lines.append("- 本次无精读推荐。")
    lines.append("")

    lines.append("## 速读区")
    if quick_entries:
        for idx, (paper_id, title, _tags) in enumerate(quick_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            score = _entry_score_text(_tags)
            suffix = f"（{score}）" if score else ""
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)}) {suffix}")
    else:
        lines.append("- 本次无速读推荐。")
    lines.append("")

    lines.append("---")
    lines.append("使用键盘方向键可在日报/论文之间快速切换。")
    lines.append("")
    return "\n".join(lines)


def write_day_report_readme(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    recommend_exists: bool,
) -> str:
    day_dir, day_readme = prepare_day_report_paths(docs_dir, date_str)
    os.makedirs(day_dir, exist_ok=True)
    content = build_day_report_markdown(
        date_str=date_str,
        date_label=date_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        recommend_exists=recommend_exists,
    )
    with open(day_readme, "w", encoding="utf-8") as f:
        f.write(content)
    return day_readme


def list_day_report_links(docs_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(docs_dir):
        return out
    # 1) 区间目录：YYYYMMDD-YYYYMMDD
    range_dirs = sorted(
        [d for d in os.listdir(docs_dir) if RANGE_DATE_RE.fullmatch(d)],
        reverse=True,
    )
    for rd in range_dirs:
        readme = os.path.join(docs_dir, rd, "README.md")
        if not os.path.exists(readme):
            continue
        out.append((format_date_str(rd), build_docsify_id_href(f"{rd}/README")))

    # 2) 单日目录：docs/YYYYMM/DD
    ym_dirs = sorted([d for d in os.listdir(docs_dir) if re.fullmatch(r"\d{6}", d)], reverse=True)
    for ym in ym_dirs:
        ym_path = os.path.join(docs_dir, ym)
        if not os.path.isdir(ym_path):
            continue
        day_dirs = sorted([d for d in os.listdir(ym_path) if re.fullmatch(r"\d{2}", d)], reverse=True)
        for day in day_dirs:
            readme = os.path.join(ym_path, day, "README.md")
            if not os.path.exists(readme):
                continue
            date8 = f"{ym}{day}"
            label = format_date_str(date8)
            href = build_docsify_id_href(f"{ym}/{day}/README")
            out.append((label, href))
    return out


def build_home_readme_content(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
) -> str:
    notice_path, promo_path = ensure_home_module_files(docs_dir)
    notice_md = _read_module_markdown(notice_path)
    promo_md = _read_module_markdown(promo_path)
    latest_report_md = build_latest_report_section(
        date_str=date_str,
        date_label=date_label,
        generated_at=generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
    )

    lines: List[str] = []
    lines.append(notice_md or "（公告模块为空）")
    lines.append("")
    lines.append("## 每次日报")
    lines.append(latest_report_md)
    lines.append("")
    lines.append(promo_md or "（宣传模块为空）")
    lines.append("")
    return "\n".join(lines)


def sync_home_readme_from_day_report(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
) -> str:
    home_readme = os.path.join(docs_dir, "README.md")
    # 首页由三段模块拼接：公告栏（独立 md）+ 本次日报 + 宣传栏（独立 md）
    content = build_home_readme_content(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=date_label,
        generated_at=generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
    )
    with open(home_readme, "w", encoding="utf-8") as f:
        f.write(content)
    return home_readme


def write_run_daily_log(
    date_str: str,
    mode: str,
    recommend_path: str,
    recommend_exists: bool,
    deep_count: int,
    quick_count: int,
    docs_dir: str,
    day_readme: str,
) -> str:
    log_dir = os.path.join(ROOT_DIR, "archive", date_str, "logs")
    os.makedirs(log_dir, exist_ok=True)
    out_path = os.path.join(log_dir, "daily_report.json")
    payload = {
        "date": format_date_str(date_str),
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommend_path": recommend_path,
        "recommend_exists": bool(recommend_exists),
        "deep_count": int(deep_count),
        "quick_count": int(quick_count),
        "total_count": int(deep_count + quick_count),
        "docs_dir": docs_dir,
        "day_readme": day_readme,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def backfill_history_day_reports(docs_dir: str) -> int:
    """
    为历史日期目录补齐 README.md（若不存在），便于首页左右切换日报。
    该补齐不依赖 LLM，只基于已存在的论文 markdown 文件生成简版日报。
    """
    if not os.path.isdir(docs_dir):
        return 0

    created = 0
    ym_dirs = sorted(
        [d for d in os.listdir(docs_dir) if re.fullmatch(r"\d{6}", d)],
        reverse=True,
    )
    for ym in ym_dirs:
        ym_path = os.path.join(docs_dir, ym)
        if not os.path.isdir(ym_path):
            continue
        day_dirs = sorted(
            [d for d in os.listdir(ym_path) if re.fullmatch(r"\d{2}", d)],
            reverse=True,
        )
        for day in day_dirs:
            day_path = os.path.join(ym_path, day)
            if not os.path.isdir(day_path):
                continue
            readme_path = os.path.join(day_path, "README.md")
            if os.path.exists(readme_path):
                continue

            paper_files = sorted(
                [
                    fn
                    for fn in os.listdir(day_path)
                    if fn.lower().endswith(".md")
                    and fn.upper() != "README.MD"
                    and not fn.startswith("_")
                ]
            )

            date8 = f"{ym}{day}"
            date_label = format_date_str(date8)
            lines = [f"# 日报 · {date_label}", ""]
            lines.append("- 该日报为历史补齐版本（由已有文档自动生成）。")
            lines.append(f"- 论文数量：{len(paper_files)}")
            lines.append("")
            lines.append("## 论文列表")
            if paper_files:
                for idx, fn in enumerate(paper_files, start=1):
                    base = fn[:-3]
                    # 尽量从文件名恢复标题（保留 slug，可点击）
                    title_guess = re.sub(r"^[0-9]{4}\.[0-9]{5}v[0-9]-", "", base).replace("-", " ").strip()
                    title_guess = title_guess or base
                    lines.append(f"{idx}. [{title_guess}]({build_docsify_id_href(f'{ym}/{day}/{base}')})")
            else:
                lines.append("- 当天目录暂无论文文档。")
            lines.append("")

            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            created += 1

    return created


def _extract_md_section(md_text: str, heading: str) -> str:
    """
    从 Markdown 文本中提取 `## {heading}` 小节内容（直到下一个二级标题）。
    """
    if not md_text:
        return ""
    marker = f"## {heading}\n"
    start = md_text.find(marker)
    if start == -1:
        return ""
    after = md_text[start + len(marker) :]
    # 下一个二级标题
    m = re.search(r"\n##\s+", after)
    return (after if not m else after[: m.start()]).strip()


def _parse_generated_md_to_meta(md_path: str, paper_id: str, section: str) -> Dict[str, Any]:
    """
    从 Step6 已生成的论文 Markdown 中提取可导出的元信息（不引入额外 LLM 调用）。
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        text = ""

    lines = (text or "").splitlines()

    # 标题：开头连续的 `# ` 行（英文/中文）
    h1s: List[str] = []
    for line in lines:
        m = re.match(r"^#\s+(.*)$", line)
        if not m:
            break
        h1s.append((m.group(1) or "").strip())
        if len(h1s) >= 2:
            break
    title_en = h1s[0] if len(h1s) >= 1 else ""

    meta: Dict[str, str] = {}
    for line in lines:
        m = re.match(r"^\*\*([^*]+)\*\*:\s*(.*?)(?:\s*\\\s*)?$", line.strip())
        if not m:
            continue
        k = (m.group(1) or "").strip()
        v = (m.group(2) or "").strip()
        if k:
            meta[k] = v

    # Tags：正文里是 HTML span，导出时提供纯文本版本 + typed 版本（keyword/query/paper）
    tags_html = meta.get("Tags") or ""
    tags_typed: List[Dict[str, str]] = []
    if tags_html:
        for m in re.finditer(
            r'<span\s+class="tag-label\s+([^"]+)"[^>]*>(.*?)</span>',
            tags_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            cls = m.group(1) or ""
            label = re.sub(r"<[^>]+>", "", (m.group(2) or "")).strip()
            if not label:
                continue
            kind = "paper"
            if "tag-green" in cls:
                kind = "keyword"
            elif "tag-blue" in cls:
                kind = "query"
            tags_typed.append({"kind": kind, "label": label})

    abstract_en = _extract_md_section(text, "Abstract")

    # 作者：兼容英文逗号与中文逗号
    authors_raw = meta.get("Authors") or ""
    authors = [a.strip() for a in re.split(r",|，", authors_raw) if a.strip()]
    authors_line = ", ".join(authors)

    # tags：输出为更“短”的一行形式（字符串），避免 JSON pretty-print 时每个 tag 独占一行
    tags_compact: List[str] = []
    for t in tags_typed:
        kind = (t.get("kind") or "").strip() or "paper"
        label = (t.get("label") or "").strip()
        if not label:
            continue
        tags_compact.append(f"{kind}:{label}")

    return {
        "paper_id": paper_id,
        "section": section,
        "title_en": title_en,
        "authors": authors_line,
        "date": (meta.get("Date") or "").strip(),
        "pdf": (meta.get("PDF") or "").strip(),
        "score": (meta.get("Score") or "").strip(),
        "evidence": (meta.get("Evidence") or "").strip(),
        "tldr": (meta.get("TLDR") or "").strip(),
        "tags": ", ".join(tags_compact),
        "abstract_en": abstract_en,
    }


def write_day_meta_index_json(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    deep_list: List[Dict[str, Any]],
    quick_list: List[Dict[str, Any]],
) -> str:
    """
    在对应的 docs 日期目录下生成索引 JSON 文件，供前端一键下载。
    """
    if RANGE_DATE_RE.match(date_str):
        target_dir = os.path.join(docs_dir, date_str)
    else:
        ym = date_str[:6]
        day = date_str[6:]
        target_dir = os.path.join(docs_dir, ym, day)
    os.makedirs(target_dir, exist_ok=True)
    out_path = os.path.join(target_dir, "papers.meta.json")

    effective_label = (date_label or "").strip() or format_date_str(date_str)

    papers: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for section, lst in (("deep", deep_list), ("quick", quick_list)):
        for paper in lst:
            try:
                title = (paper.get("title") or "").strip()
                arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
                md_path, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
                item = _parse_generated_md_to_meta(md_path, pid, section)
                papers.append(item)
            except Exception as e:
                errors.append(
                    {
                        "paper_id": str(paper.get("id") or paper.get("paper_id") or ""),
                        "error": str(e),
                    }
                )

    payload = {
        "label": effective_label,
        "date": format_date_str(date_str),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "papers": papers,
        "errors": errors,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        # 索引文件用于下载：保持可读的 JSON pretty 格式（每个 paper 一个对象块）
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6: generate docs for deep/quick sections.")
    parser.add_argument("--date", type=str, default=TODAY_STR, help="date string YYYYMMDD.")
    parser.add_argument("--mode", type=str, default=None, help="mode for recommend file.")
    parser.add_argument("--docs-dir", type=str, default=None, help="override docs dir.")
    parser.add_argument(
        "--sidebar-date-label",
        type=str,
        default=None,
        help="侧边栏日期标题展示文本（例如：2026-01-01 ~ 2026-01-27）。不填则使用单日日期。",
    )
    parser.add_argument(
        "--glance-only",
        action="store_true",
        help="只生成/补齐 `## 速览`（基于 title+abstract），不下载 PDF/Jina 文本，不生成精读总结。",
    )
    parser.add_argument(
        "--force-glance",
        action="store_true",
        help="强制重生成 `## 速览` 并覆盖写入（即使文件里已存在该块）。",
    )
    parser.add_argument(
        "--sidebar-only",
        action="store_true",
        help="只更新 docs/_sidebar.md（不生成/不重写论文 Markdown，避免触发 LLM 调用）。",
    )
    parser.add_argument(
        "--fix-tags-only",
        action="store_true",
        help="仅修复已生成文章里的 `**Tags**`（移除“精读区/速读区”标签），不触发 LLM。",
    )
    parser.add_argument(
        "--paper-id",
        type=str,
        default=None,
        help="单篇模式：填写 arXiv id（如 1706.03762v1 / https://arxiv.org/abs/1706.03762v1）。",
    )
    parser.add_argument(
        "--paper-date",
        type=str,
        default="",
        help="单篇模式：论文输出目录日期（YYYYMMDD），默认使用论文发布时间。",
    )
    parser.add_argument(
        "--paper-section",
        type=str,
        default="quick",
        help="单篇模式：deep 或 quick（默认 quick）。",
    )
    parser.add_argument(
        "--paper-title",
        type=str,
        default=None,
        help="单篇模式：可选，手动覆盖论文标题。",
    )
    args = parser.parse_args()

    date_str = args.date or TODAY_STR
    mode = args.mode
    if not mode:
        config = load_config()
        setting = (config or {}).get("arxiv_paper_setting") or {}
        mode = str(setting.get("mode") or "standard").strip()
    if "," in mode:
        mode = mode.split(",", 1)[0].strip()

    docs_dir = args.docs_dir or resolve_docs_dir()
    created_reports = backfill_history_day_reports(docs_dir)
    if created_reports > 0:
        log(f"[INFO] 已补齐历史日报 README：{created_reports} 个")

    if args.paper_id:
        log_substep("6.p", "单篇论文生成", "START")
        try:
            paper = fetch_arxiv_paper_meta(args.paper_id)
            if args.paper_title:
                paper["title"] = args.paper_title.strip()
            single_date = (args.paper_date or "").strip()
            if not single_date:
                single_date = (paper.get("published") or "").strip()
            if not single_date:
                single_date = TODAY_STR

            section = (args.paper_section or "quick").strip().lower()
            if section not in ("deep", "quick"):
                section = "quick"

            paper_id = str(paper.get("id") or args.paper_id).strip()
            paper["paper_id"] = paper_id
            _, paper_title = process_paper(
                paper,
                section,
                single_date,
                docs_dir,
                glance_only=args.glance_only,
                force_glance=args.force_glance,
            )
            log(f"[OK] 单篇论文已生成：{paper_title}（{paper_id}），date={single_date}，section={section}")
            log_substep("6.p", "单篇论文生成", "END")
            return
        except Exception as e:
            log(f"[ERROR] 单篇论文生成失败：{e}")
            log_substep("6.p", "单篇论文生成", "END")
            return

    archive_dir = os.path.join(ROOT_DIR, "archive", date_str, "recommend")
    recommend_path = os.path.join(archive_dir, f"arxiv_papers_{date_str}.{mode}.json")
    recommend_exists = os.path.exists(recommend_path)
    if not recommend_exists:
        log(f"[WARN] recommend 文件不存在（今天可能没有新论文）：{recommend_path}。将生成空日报并更新首页。")

    log_substep("6.1", "读取 recommend 结果", "START")
    payload = {}
    try:
        if recommend_exists:
            with open(recommend_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
    finally:
        log_substep("6.1", "读取 recommend 结果", "END")
    deep_list = payload.get("deep_dive") or []
    quick_list = payload.get("quick_skim") or []

    def _paper_score(p: dict) -> float:
        try:
            return float(p.get("llm_score", 0) or 0)
        except Exception:
            return 0.0

    def _paper_id(p: dict) -> str:
        return str(p.get("id") or p.get("paper_id") or "").strip()

    # 侧边栏展示按分数降序（同分按 id 稳定排序），避免“高分被埋在下面”
    deep_list = sorted(deep_list, key=lambda p: (-_paper_score(p), _paper_id(p)))
    quick_list = sorted(quick_list, key=lambda p: (-_paper_score(p), _paper_id(p)))

    if args.fix_tags_only:
        changed_files = 0
        total_files = 0
        for section, lst in (("deep", deep_list), ("quick", quick_list)):
            for paper in lst:
                title = (paper.get("title") or "").strip()
                arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
                md_path, _, _ = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
                if not os.path.exists(md_path):
                    continue
                total_files += 1
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue
                fixed, changed = normalize_meta_tags_line(content)
                if not changed:
                    continue
                try:
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
                    changed_files += 1
                except Exception:
                    continue
        log(f"[OK] fix-tags-only: scanned={total_files}, updated={changed_files}")
        return

    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []

    if args.sidebar_only:
        log_substep("6.2", "跳过生成文章（仅更新侧边栏）", "SKIP")
        for paper in deep_list:
            title = (paper.get("title") or "").strip()
            arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
            _, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
            deep_entries.append((pid, title, extract_sidebar_tags(paper)))

        for paper in quick_list:
            title = (paper.get("title") or "").strip()
            arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
            _, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
            quick_entries.append((pid, title, extract_sidebar_tags(paper)))
        log_substep("6.3", "跳过生成文章（仅更新侧边栏）", "SKIP")
    else:
        log_substep("6.2", "生成精读区文章", "START")
        for paper in deep_list:
            pid, title = process_paper(
                paper,
                "deep",
                date_str,
                docs_dir,
                glance_only=args.glance_only,
                force_glance=args.force_glance,
            )
            deep_entries.append((pid, title, extract_sidebar_tags(paper)))
        log_substep("6.2", "生成精读区文章", "END")

        log_substep("6.3", "生成速读区文章", "START")
        for paper in quick_list:
            pid, title = process_paper(
                paper,
                "quick",
                date_str,
                docs_dir,
                glance_only=args.glance_only,
                force_glance=args.force_glance,
            )
            quick_entries.append((pid, title, extract_sidebar_tags(paper)))
        log_substep("6.3", "生成速读区文章", "END")

    log_substep("6.4", "生成当日日报并同步首页 README", "START")
    run_generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    day_readme = write_day_report_readme(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=args.sidebar_date_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        recommend_exists=recommend_exists,
    )
    home_readme = sync_home_readme_from_day_report(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=args.sidebar_date_label,
        generated_at=run_generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
    )
    log(f"[OK] day report saved: {day_readme}")
    log(f"[OK] home README synced: {home_readme}")
    log_substep("6.4", "生成当日日报并同步首页 README", "END")

    sidebar_path = os.path.join(docs_dir, "_sidebar.md")
    if deep_entries or quick_entries:
        log_substep("6.5", "更新侧边栏", "START")
        update_sidebar(
            sidebar_path,
            date_str,
            deep_entries,
            quick_entries,
            date_label=args.sidebar_date_label,
        )
        log_substep("6.5", "更新侧边栏", "END")
    else:
        log_substep("6.5", "更新侧边栏", "SKIP")
        log("[INFO] 本次无推荐论文，不写入 Sidebar 日期目录。")

    log_substep("6.6", "生成可下载元数据索引（JSON）", "START")
    try:
        out_path = write_day_meta_index_json(
            docs_dir,
            date_str,
            args.sidebar_date_label,
            deep_list,
            quick_list,
        )
        log(f"[OK] meta index saved: {out_path}")
    except Exception as e:
        log(f"[WARN] 生成元数据索引失败：{e}")
    log_substep("6.6", "生成可下载元数据索引（JSON）", "END")

    log_substep("6.7", "写入运行日志（日报）", "START")
    run_log = write_run_daily_log(
        date_str=date_str,
        mode=mode,
        recommend_path=recommend_path,
        recommend_exists=recommend_exists,
        deep_count=len(deep_entries),
        quick_count=len(quick_entries),
        docs_dir=docs_dir,
        day_readme=day_readme,
    )
    log(f"[OK] daily report log saved: {run_log}")
    log_substep("6.7", "写入运行日志（日报）", "END")

    log(f"[OK] docs updated: {docs_dir}")


if __name__ == "__main__":
    main()
