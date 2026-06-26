# CLAUDE.md — Daily Paper Reader 项目导读

> 本文件为 AI 助手（Claude / Codex 等）提供项目上下文，帮助快速理解代码库。

## 一、项目定位

**Daily Paper Reader** 是一个 fork-and-run 的个人/实验室每日论文推荐+阅读器。

- **零服务器**：GitHub Actions 定时跑后端流水线，GitHub Pages 部署前端站点
- **Fork 即用**：Fork 后配好 DeepSeek API Key + GitHub PAT，5 分钟上线
- **全链路自动化**：arXiv/会议论文抓取 → 个性化召回 → 重排 → LLM 精炼打分 → 生成可阅读日报
- **纯前端架构**：订阅管理、密钥存储、AI 问答、Zotero 集成全在浏览器端完成

## 二、整体架构分层

```
┌────────────────────────────────────────────────────────────┐
│  前端层 (app/)     docsify 论文站点 + 订阅管理 + AI 问答    │
│                   + Zotero 集成 + workflow 触发面板          │
├────────────────────────────────────────────────────────────┤
│  编排层            GitHub Actions (8 个 workflow)           │
│  (.github/)        + 本地调试后端 (local_debug_server.py)    │
├────────────────────────────────────────────────────────────┤
│  流水线层          main.py 编排 Step 0→6                     │
│  (src/)            配置→抓取→召回→排序→精炼→选择→生成文档      │
├────────────────────────────────────────────────────────────┤
│  数据维护层         maintain/ 多源抓取+向量编码+Supabase 同步 │
│  (src/maintain/)   arxiv/bioRxiv/medRxiv/ChemRxiv/会议      │
├────────────────────────────────────────────────────────────┤
│  存储层            Supabase (PostgREST + pgvector + FTS)    │
│  (sql/)            11 张同构论文表 + 向量/BM25 RPC           │
└────────────────────────────────────────────────────────────┘
```

## 三、端到端数据流（每日运行一次）

```
定时触发 (UTC 18:30 / 北京 02:30)
  │
  ├─ [Step 0] 0.enrich_config_queries.py   (可选) LLM 扩充关键词
  │
  ├─ [Step 1] fetch_arxiv.py              (可跳过) 从 arXiv 抓新论文
  │       ↓ 若 Supabase 已接管 → 直接跳过
  │
  ├─ [Step 2.1] BM25 关键词召回            Supabase RPC match_*_bm25
  ├─ [Step 2.2] 向量语义召回               Supabase RPC match_*_exact
  ├─ [Step 2.3] RRF 融合                  两路排名融合 → 统一候选池
  │       ↓ archive/<date>/filtered/
  │
  ├─ [Step 3] Reranker 重排               Qwen3-Reranker 本地/远端
  │       ↓ archive/<date>/rank/
  │
  ├─ [Step 4] LLM 精炼打分                DeepSeek 0-10 相关性评分
  │       ↓ archive/<date>/rank/*.llm.json
  │
  ├─ [Step 5] 选择论文                    精读区(≥8分) + 速读区(6-8分)
  │       ↓ archive/<date>/recommend/
  │
  └─ [Step 6] 生成文档                    docsify markdown + 日报 + 图表
          ↓ docs/<date>/ + docs/_sidebar.md + docs/README.md
          ↓ git commit + push → GitHub Pages 自动部署
```

**关键设计**：各 Step 间通过 `DPR_RUN_DATE` 环境变量隐式共享 archive 路径（`archive/<date_token>/{raw,filtered,rank,recommend,logs}/`），`main.py` 只设一次这个 env，各脚本顶部独立重算路径。

## 四、各子系统详解

### 1. 流水线编排 `src/main.py`

- **纯顺序编排器**：`run_step()` = `subprocess.run(check=True)`，任一步失败整条中断
- **三种模式**：
  - **standard**（默认，≤9 天窗口）：正常精读推荐
  - **skims**（≥11 天窗口）：速览模式，全部走 quick_skim，忽略 seen_ids
  - **long-range**（≥10 天）：生成区间 token `YYYYMMDD-YYYYMMDD`
- **跳过抓取**：当 Supabase 完全接管（BM25 + 向量 RPC 均启用）时自动跳过 Step 1
- **关键函数**：`should_skip_fetch()`、`resolve_run_date_token()`、`use_skims_mode()`、`resolve_summary_step_env()`

### 2. 订阅与查询规划 `src/subscription_plan.py`

- **唯一真源**：把 `config.yaml` 的 `subscriptions.intent_profiles`（每个研究方向含 keywords + intent_queries）翻译成检索计划
- **keyword 走 BM25 召回，intent_query 走向量召回**——召回词 vs 语义句的刻意拆分
- **paper_tag 命名空间**：`keyword:<tag>` / `query:<tag>`，命中即给论文打 tag
- **输出**：`build_pipeline_inputs()` → `{bm25_queries, embedding_queries, context_queries}`

### 3. 三路召回与融合 `src/2.1` + `2.2` + `2.3`

| 步骤 | 方法 | 实现 |
|------|------|------|
| 2.1 | BM25 关键词 | Supabase FTS RPC `match_*_bm25`，0 命中回退本地 |
| 2.2 | 向量语义 | Supabase 精确余弦 RPC `match_*_exact`，bge-small-en-v1.5 |
| 2.3 | RRF 融合 | `1/(60+rank)` 跨路合分，Top-200 截断 |

- **自适应 top_k**：窗口每满 1000 篇 +50（基数 50）
- **超时兜底**：PG `statement_timeout` 57014 → 时间窗递归二分重试
- **多源路由**：`source_backend_router.group_queries_by_source` 按 `paper_sources` 扇出到不同 Supabase 表

### 4. 排序/Rerank `src/3.rank_papers.py`

- **双层 RRF**：lane 间合池 + query 内跨批融合，均用 `1/(60+rank)`
- **Reranker 三选一**：
  - 本地 `Qwen3-Reranker-0.6B`（yes/no token logits → P(yes) 为分数）
  - 远端 SiliconFlow API（`src/reranker_api.py`）
  - 远端 zwwen.online 公益服务
- **星级是相对量**：min-max 归一化，每个 query 必有一个 5★ 和 1★
- **动态预算**：`lane_top_k = min(30 + 10 * ((total-1) // 1000), 120)`
- **离线评估**：`rerank_budget_experiment.py`（预算 profile 对比）、`rerank_model_size_experiment.py`（模型尺寸对比）

### 5. LLM 精炼 + 选择 `src/4.llm_refine_papers.py` + `src/5.select_papers.py`

- **Step 4**：只处理 ≥4★ 候选（约 RRF ≥0.5），DeepSeek 给 0-10 精排分 + 中英文摘要
- **Step 5**：分层选片——≥8 进精读区，6-8 进速读区，≥9 优先且突破 cap
- **名额** = base + tag_count（订阅 tag 越多名额越大）
- **carryover 机制**：`archive/carryover.json` 跨天结转高分论文

### 6. LLM 客户端封装 `src/llm.py`

- **OpenAI 兼容**：`LLMClient` / `DeepSeekClient`
- **结构化输出三级回退**：`json_schema → json_object → prompt_only`
- **JSON 截断自动修复**：`_repair_json_suffix` 处理 max_tokens 截断
- **多 base_url 重试**：`_iter_retry_bases` 遍历候选端点
- **注意**：每篇论文独立 client 实例，避免多线程下 `client.kwargs` 竞争

### 7. 文档生成 `src/6.generate_docs.py` + `src/paper_figures.py`

- **每篇一个 markdown**：YAML front matter（前端契约）+ 速览五段 + 精读长总结 + PDF 图表
- **并发生成**：`ThreadPoolExecutor`，每篇独立 `DeepSeekClient` 避免多线程竞争
- **图表提取**：PaperCropper + DocLayout-YOLO → PyMuPDF 兜底，全链 `continue-on-error`
- **幂等可重入**：`upsert_auto_block` / `upsert_front_matter_field` 只改目标段不重写全文
- **产物路径**：`docs/<date>/<paper_id>.md`、`docs/<date>/figures/`、`docs/README.md`、`docs/_sidebar.md`

### 8. 多源后端抽象 `src/source_config.py` + `source_backend_router.py` + `supabase_source.py`

- **统一后端解析**：`get_source_backend(config, source_key)` → `{url, table, rpc_exact, rpc_bm25, ...}`
- **三级优先级**：`source_backends` > legacy `supabase:` 块 > 环境变量覆盖
- **查询级路由**：`group_queries_by_source` 按 `paper_sources` 扇出到不同 Supabase 表
- **配置迁移**：`0.migrate_source_config.py` 归一化旧格式，`0.enrich_config_queries.py` 用 LLM 扩充关键词

### 9. 数据维护层 `src/maintain/`

**三层 subprocess 结构**：

```
<source>.py (薄调度) → init_<source>.py (编排) → fetchers/fetch_<source>.py (抓取)
                                               → sync.py (向量编码 + upsert)
```

- **支持的数据源**：arXiv, bioRxiv, medRxiv, ChemRxiv, NeurIPS, ICLR, ICML, ACL, EMNLP, AAAI
- **向量编码统一在 sync.py**：`sentence-transformers` 编码 `'passage: Title:...\n\nAbstract:...'`，384 维
- **增量同步**：`seen.json` 状态文件 + PostgREST upsert `on_conflict=id`
- **保留期清理**：`cleanup.py` 删 `published < now - retention_days`
- **新增数据源模式**：新建 `<source>.py`（薄调度）+ `init_<source>.py`（编排）+ `fetchers/fetch_<source>.py`（抓取），复用 `sync.py`

### 10. 会议检索链路 `src/conference_*.py`

- **独立于日常流水线**：手动触发（`conference-paper-retrieval.yml`），复用 `intent_profiles` 但强制 `paper_sources=会议`
- **Supabase-first**：直接对会议 RPC 取小 top-k，不拉全表
- **展示门槛**：≥4.0 分（DeepSeek 0-10 分制）才写入侧边栏
- **临时词条**：`scope:conference/temporary` 的 profile 只在会议链路生效
- **关键文件**：`conference_retrieval.py`（召回）、`conference_pipeline.py`（编排）、`conference_sidebar.py`（侧边栏写入）

### 11. Supabase 存储层 `sql/`

- **11 张同构表**：`{source}_papers`，统一 schema（`embedding vector(384)` + `jsonb authors/categories`）
- **三族 RPC**：
  - `_exact`：精确余弦距离（所有源）
  - 无后缀 ANN：HNSW 索引（仅 arxiv/papers 表）
  - `_bm25`：PostgreSQL FTS `ts_rank_cd`（所有源）
- **会议表无 HNSW**：只有 `_exact` + `_bm25`
- **时间窗过滤**：`filter_published_start/end` 先收窄范围再算向量，绕开全表扫描 timeout

### 12. 前端核心 `app/`

- **docsify 单插件模式**：`docsify-plugin.js`（~4686 行）承载论文渲染、侧边栏、Zotero、导航
- **订阅管理**：`SubscriptionsManager`（后台面板总控）+ `SubscriptionsSmartQuery`（对话式 LLM 生成候选 profile，~2919 行）
- **workflow 触发面板**：`workflows.runner.js`，按 hostname 自动切换 GitHub Actions / 本地后端
- **密钥零服务器**：`secret.session.js`，AES-GCM(PBKDF2) 加密存 `secret.private`，明文只在内存中，三态 `locked/guest/full`
- **AI 问答**：`chat.discussion.js`，浏览器直连 OpenAI 兼容 API，SSE 流式，对话存 IndexedDB
- **Zotero 集成**：注入 `citation_*` meta 标签供 Zotero Connector 抓取；`zotero-meta-utils.js` / `zotero-chat-utils.js` 是纯工具
- **Gist 分享**：`gist-share-utils.js`，一键发 GitHub Gist
- **入口**：`index.html` 两阶段资源加载（CDN/本地），splash + secret gate

### 13. CI/CD + 本地调试

| Workflow 文件 | 触发方式 | 功能 |
|--------------|---------|------|
| `daily-paper-reader.yml` | cron 每日 + dispatch | 主流水线 |
| `conference-paper-retrieval.yml` | dispatch | 会议检索 |
| `maintain-supabase.yml` | cron 3 次/天 | arXiv/会议入库 |
| `maintain-biorxiv.yml` | cron | bioRxiv 入库 |
| `maintain-medrxiv.yml` | cron | medRxiv 入库 |
| `maintain-chemrxiv.yml` | cron | ChemRxiv 入库 |
| `sync.yml` | cron 每日 | Fork 同步上游 |
| `reset-content.yml` | dispatch | 内容重置 |

**本地调试**：
- `scripts/bootstrap_local.sh`：一键创建 venv + 安装依赖 + 启动本地后端
- `src/local_debug_server.py`：HTTP 后端，`/api/local/workflows/dispatch` 把 workflow 映射成本地 Python 子进程
- `.local-runs/<run_id>/`：每次本地运行的工作目录（`run.log` + 可选 `config.yaml` 快照）
- `src/local_env.py`：加载 `.env` 文件
- `src/sitecustomize.py`：自动加载 `.env`（需 `PYTHONPATH` 含 `src` 才生效）

## 五、关键配置文件

- **`config.yaml`**（根目录）：运行配置，含 `arxiv_paper_setting`、`supabase` 连接、`subscriptions.intent_profiles`
- **`.env` / `.env.example`**：环境变量（API Key、Supabase 凭据等）
- **`secret.private`**：AES-GCM 加密的密钥文件，浏览器端解密
- **`docs/config.yaml`**：前端只读快照（CI 运行后 `cp config.yaml docs/config.yaml`）

## 六、外部依赖

```
DeepSeek API ←── Step 4 精炼 + Step 6 摘要 + Step 0 查询扩充 + 前端 AI 问答
Supabase     ←── 全链路存储与召回（PostgREST + pgvector + FTS）
zwwen.online ←── 公益 embedding / rerank 服务
SiliconFlow  ←── 可选 rerank API
arXiv API    ←── 论文抓取（维护层）
OpenReview   ←── 会议论文抓取（需账号密码）
GitHub API   ←── 前端读写 config / 触发 Actions / 管理 Secrets / Gist 分享
Zotero       ←── 浏览器 Connector 抓取 citation meta
```

## 七、值得注意的设计与已知问题

1. **`DPR_RUN_DATE` 隐式总线**：main 设一次，各 step 各自重算路径——两者必须用同一 token，否则产物错位
2. **向量维度硬编码 384**：SQL 列 `vector(384)` 对应 `bge-small-en-v1.5`，换模型必须同步改全部 SQL
3. **sync.normalize_paper 丢字段**：fetcher 产出的 `pdf_url/doi/decision` 等在入库时被丢弃（只保留 10 列）
4. **硬编码兜底密钥**：`model_loader`/`reranker_api` 内置明文 fallback API key，`or '硬编码key'` 写法使其几乎永远生效
5. **LLMClient.tokens 并发竞态**：类属性 `+=` 非原子，多线程下 token 统计可能不准（不影响推荐正确性）
6. **boolean_expr 死代码**：`subscription_plan` 产出的 `boolean_expr` 恒为空串，AND/NOT 解析逻辑未生效
7. **测试盲区**：SQL 本体无 pgTAP 测试、RRF 融合逻辑未测、端到端编排全 mock
8. **Legacy 残留**：`subscriptions.keywords.js` / `tracked-papers.js` 仍被加载但 UI 无入口
9. **代码重复**：`init_*.py` / `fetch_*.py` 各自重实现了 `run_step/log/TODAY_STR/seen-state`，未复用 `common.py`
10. **两个「4 分门槛」易混淆**：`llm-min-star`(4) 是 0-5 星制 rerank 门，`display-min-score`(4.0) 是 0-10 分制 DeepSeek 展示门

## 八、测试

- **Python 测试**：`pytest`（`pytest.ini`），~38 个测试文件覆盖大部分 Python 模块
- **JS 测试**：6 个 `test_*.js` 覆盖前端纯函数（subscriptions、zotero、gist、llm-config）
- **运行**：`pytest` 或 `python -m pytest`（根目录）
- **覆盖较好的链路**：订阅规划、LLM 结构化输出、reranker API、各源初始化/fetch
- **覆盖薄弱的链路**：RRF 融合逻辑、SQL/RPC、端到端编排、filter.py

## 九、开发约定

### 提交共同作者规则

本仓库内由 Agent/Codex 创建、提交或推送的 commit，提交信息末尾必须追加以下共同作者 trailer：

```text
Co-Authored-By: lilmortyj <781113402@qq.com>
Co-Authored-By: xixi <3495302215@qq.com>
Co-Authored-By: wy <345619498@qq.com>
```

以上规则仅用于 Git commit message，不代表需要修改 `CITATION.cff`、`README.md` 或其它项目作者元数据。

### 合并主分支规则

将工作分支合并到 `main` / `origin/main` 前，必须先确认本次提交只包含可上游同步的代码、模板与测试改动，避免破坏用户通过 GitHub 网页 `Sync fork` 的既有使用习惯。

合并前必须执行并检查：

```bash
git diff --name-only origin/main..HEAD
git status --short
```

**允许合并到主分支的路径**：
- `.github/workflows/`、`app/`、`scripts/`、`src/`、`sql/`、`tests/`
- `requirements*.txt`、`.env.example`、`.gitignore`
- `README.md`、`AGENTS.md`、`CLAUDE.md`

**默认不得合并的运行态/产物路径**（除非用户明确要求且已说明对 fork 用户 `Sync fork` 的风险）：
- `config.yaml`、`docs/config.yaml`、`docs/README.md`、`docs/_sidebar.md`
- `docs/<日期>/`、`docs/assets/`、`archive/`、`secret.private`

若工作分支中混入了上述运行态产物，必须先从提交中剥离这些文件，只保留代码改动后再合并主分支。

**推荐的主分支合并方式**——快进合并：

```bash
git switch main
git merge --ff-only <work-branch>
git push origin main
```

若无法 `--ff-only`，必须先说明原因和冲突范围，不得直接创建包含用户运行态产物的 merge commit。
