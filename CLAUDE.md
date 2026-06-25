# CLAUDE.md — Daily Paper Reader Project Guide

> This file provides project context for AI assistants (Claude, Codex, etc.) to help them understand the codebase quickly.

## 1. Project Overview

**Daily Paper Reader** is a fork-and-run personal/lab daily paper recommendation and reading system.

- **Zero server**: GitHub Actions runs the backend pipeline on a schedule; GitHub Pages deploys the frontend site
- **Fork and run**: After forking, configure a DeepSeek API key + GitHub PAT and go live in ~5 minutes
- **End-to-end automation**: arXiv/conference paper fetch → personalized recall → rerank → LLM refine scoring → generate a readable daily digest
- **Pure frontend architecture**: subscription management, secret storage, AI Q&A, and Zotero integration all run in the browser

## 2. Architecture Layers

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (app/)     docsify paper site + subscriptions    │
│                      + AI Q&A + Zotero + workflow panel    │
├────────────────────────────────────────────────────────────┤
│  Orchestration       GitHub Actions (8 workflows)          │
│  (.github/)          + local debug backend                 │
│                      (local_debug_server.py)                 │
├────────────────────────────────────────────────────────────┤
│  Pipeline (src/)     main.py orchestrates Steps 0→6        │
│                      config→fetch→recall→rank→refine→      │
│                      select→generate docs                  │
├────────────────────────────────────────────────────────────┤
│  Data maintenance    maintain/ multi-source fetch +        │
│  (src/maintain/)     vector encoding + Supabase sync       │
│                      arxiv/bioRxiv/medRxiv/ChemRxiv/conf   │
├────────────────────────────────────────────────────────────┤
│  Storage (sql/)      Supabase (PostgREST + pgvector + FTS) │
│                      11 isomorphic paper tables +          │
│                      vector/BM25 RPCs                      │
└────────────────────────────────────────────────────────────┘
```

## 3. End-to-End Data Flow (runs once daily)

```
Scheduled trigger (UTC 18:30 / Beijing 02:30)
  │
  ├─ [Step 0] 0.enrich_config_queries.py   (optional) LLM keyword expansion
  │
  ├─ [Step 1] fetch_arxiv.py              (skippable) fetch new arXiv papers
  │       ↓ skip entirely when Supabase is fully in charge
  │
  ├─ [Step 2.1] BM25 keyword recall       Supabase RPC match_*_bm25
  ├─ [Step 2.2] vector semantic recall    Supabase RPC match_*_exact
  ├─ [Step 2.3] RRF fusion                merge two ranked lists → unified pool
  │       ↓ archive/<date>/filtered/
  │
  ├─ [Step 3] Reranker rerank             Qwen3-Reranker local/remote
  │       ↓ archive/<date>/rank/
  │
  ├─ [Step 4] LLM refine scoring          DeepSeek 0–10 relevance score
  │       ↓ archive/<date>/rank/*.llm.json
  │
  ├─ [Step 5] paper selection             deep-read (≥8) + quick skim (6–8)
  │       ↓ archive/<date>/recommend/
  │
  └─ [Step 6] generate docs               docsify markdown + digest + figures
          ↓ docs/<date>/ + docs/_sidebar.md + docs/README.md
          ↓ git commit + push → GitHub Pages auto-deploy
```

**Key design**: Steps share archive paths implicitly via the `DPR_RUN_DATE` env var (`archive/<date_token>/{raw,filtered,rank,recommend,logs}/`). `main.py` sets it once; each script recomputes paths at the top independently.

## 4. Subsystem Details

### 1. Pipeline orchestration `src/main.py`

- **Pure sequential orchestrator**: `run_step()` = `subprocess.run(check=True)`; any failure aborts the whole run
- **Three modes**:
  - **standard** (default, ≤9-day window): normal deep-read recommendations
  - **skims** (≥11-day window): skim mode; everything goes through `quick_skim`, ignores `seen_ids`
  - **long-range** (≥10 days): produces interval token `YYYYMMDD-YYYYMMDD`
- **Skip fetch**: automatically skips Step 1 when Supabase fully takes over (both BM25 + vector RPCs enabled)
- **Key functions**: `should_skip_fetch()`, `resolve_run_date_token()`, `use_skims_mode()`, `resolve_summary_step_env()`

### 2. Subscriptions and query planning `src/subscription_plan.py`

- **Single source of truth**: translates `config.yaml` → `subscriptions.intent_profiles` (each research direction has `keywords` + `intent_queries`) into a retrieval plan
- **keywords → BM25 recall, intent_query → vector recall** — deliberate split between recall terms vs semantic sentences
- **paper_tag namespace**: `keyword:<tag>` / `query:<tag>`; hits tag papers accordingly
- **Output**: `build_pipeline_inputs()` → `{bm25_queries, embedding_queries, context_queries}`

### 3. Triple-path recall and fusion `src/2.1` + `2.2` + `2.3`

| Step | Method | Implementation |
|------|--------|----------------|
| 2.1 | BM25 keywords | Supabase FTS RPC `match_*_bm25`; fallback to local on 0 hits |
| 2.2 | Vector semantic | Supabase exact cosine RPC `match_*_exact`, bge-small-en-v1.5 |
| 2.3 | RRF fusion | `1/(60+rank)` cross-path score merge, Top-200 cutoff |

- **Adaptive top_k**: +50 per 1000 papers in window (base 50)
- **Timeout fallback**: PG `statement_timeout` 57014 → recursive time-window bisection retry
- **Multi-source routing**: `source_backend_router.group_queries_by_source` fans out by `paper_sources` to different Supabase tables

### 4. Ranking / Rerank `src/3.rank_papers.py`

- **Two-level RRF**: inter-lane pool merge + intra-query cross-batch fusion, both use `1/(60+rank)`
- **Reranker (pick one)**:
  - Local `Qwen3-Reranker-0.6B` (yes/no token logits → P(yes) as score)
  - Remote SiliconFlow API (`src/reranker_api.py`)
  - Remote zwwen.online public service
- **Stars are relative**: min-max normalization; every query must have one 5★ and one 1★
- **Dynamic budget**: `lane_top_k = min(30 + 10 * ((total-1) // 1000), 120)`
- **Offline evaluation**: `rerank_budget_experiment.py` (budget profile comparison), `rerank_model_size_experiment.py` (model size comparison)

### 5. LLM refine + selection `src/4.llm_refine_papers.py` + `src/5.select_papers.py`

- **Step 4**: only processes ≥4★ candidates (~RRF ≥0.5); DeepSeek gives 0–10 refine score + bilingual summaries
- **Step 5**: tiered selection — ≥8 → deep-read, 6–8 → quick skim; ≥9 prioritized and can break cap
- **Quota** = base + tag_count (more subscription tags → larger quota)
- **Carryover**: `archive/carryover.json` carries high-scoring papers across days

### 6. LLM client wrapper `src/llm.py`

- **OpenAI-compatible**: `LLMClient` / `DeepSeekClient`
- **Structured output three-tier fallback**: `json_schema → json_object → prompt_only`
- **JSON truncation auto-repair**: `_repair_json_suffix` handles `max_tokens` truncation
- **Multi base_url retry**: `_iter_retry_bases` iterates candidate endpoints
- **Note**: one client instance per paper to avoid `client.kwargs` races under multithreading

### 7. Document generation `src/6.generate_docs.py` + `src/paper_figures.py`

- **One markdown per paper**: YAML front matter (frontend contract) + five skim sections + deep-read long summary + PDF figures
- **Concurrent generation**: `ThreadPoolExecutor`; independent `DeepSeekClient` per paper to avoid thread races
- **Figure extraction**: PaperCropper + DocLayout-YOLO → PyMuPDF fallback; full chain `continue-on-error`
- **Idempotent / re-entrant**: `upsert_auto_block` / `upsert_front_matter_field` update target sections only, not the full file
- **Output paths**: `docs/<date>/<paper_id>.md`, `docs/<date>/figures/`, `docs/README.md`, `docs/_sidebar.md`

### 8. Multi-source backend abstraction `src/source_config.py` + `source_backend_router.py` + `supabase_source.py`

- **Unified backend resolution**: `get_source_backend(config, source_key)` → `{url, table, rpc_exact, rpc_bm25, ...}`
- **Three-tier priority**: `source_backends` > legacy `supabase:` block > env var overrides
- **Query-level routing**: `group_queries_by_source` fans out by `paper_sources` to different Supabase tables
- **Config migration**: `0.migrate_source_config.py` normalizes legacy format; `0.enrich_config_queries.py` expands keywords via LLM

### 9. Data maintenance layer `src/maintain/`

**Three-layer subprocess structure**:

```
<source>.py (thin dispatcher) → init_<source>.py (orchestration) → fetchers/fetch_<source>.py (fetch)
                                                                  → sync.py (vector encode + upsert)
```

- **Supported sources**: arXiv, bioRxiv, medRxiv, ChemRxiv, NeurIPS, ICLR, ICML, ACL, EMNLP, AAAI
- **Vector encoding centralized in sync.py**: `sentence-transformers` encodes `'passage: Title:...\n\nAbstract:...'`, 384-dim
- **Incremental sync**: `seen.json` state file + PostgREST upsert `on_conflict=id`
- **Retention cleanup**: `cleanup.py` deletes `published < now - retention_days`
- **Adding a new source**: create `<source>.py` (thin dispatcher) + `init_<source>.py` (orchestration) + `fetchers/fetch_<source>.py` (fetch); reuse `sync.py`

### 10. Conference retrieval pipeline `src/conference_*.py`

- **Independent of daily pipeline**: manual trigger (`conference-paper-retrieval.yml`); reuses `intent_profiles` but forces `paper_sources=conference`
- **Supabase-first**: query conference RPCs for small top-k directly; no full-table pull
- **Display threshold**: only papers ≥4.0 (DeepSeek 0–10 scale) are written to the sidebar
- **Temporary profiles**: profiles with `scope:conference/temporary` only apply in the conference pipeline
- **Key files**: `conference_retrieval.py` (recall), `conference_pipeline.py` (orchestration), `conference_sidebar.py` (sidebar writes)

### 11. Supabase storage layer `sql/`

- **11 isomorphic tables**: `{source}_papers`, unified schema (`embedding vector(384)` + `jsonb authors/categories`)
- **Three RPC families**:
  - `_exact`: exact cosine distance (all sources)
  - Unsuffixed ANN: HNSW index (arxiv/papers table only)
  - `_bm25`: PostgreSQL FTS `ts_rank_cd` (all sources)
- **Conference tables have no HNSW**: only `_exact` + `_bm25`
- **Time-window filtering**: `filter_published_start/end` narrows range before vector computation to avoid full-scan timeouts

### 12. Frontend core `app/`

- **Docsify single-plugin mode**: `docsify-plugin.js` (~4686 lines) handles paper rendering, sidebar, Zotero, navigation
- **Subscription management**: `SubscriptionsManager` (admin panel controller) + `SubscriptionsSmartQuery` (conversational LLM candidate profile generation, ~2919 lines)
- **Workflow trigger panel**: `workflows.runner.js`; auto-switches GitHub Actions / local backend by hostname
- **Zero-server secrets**: `secret.session.js`; AES-GCM(PBKDF2) encrypted `secret.private`; plaintext only in memory; three states `locked/guest/full`
- **AI Q&A**: `chat.discussion.js`; browser-direct OpenAI-compatible API, SSE streaming; conversations stored in IndexedDB
- **Zotero integration**: injects `citation_*` meta tags for Zotero Connector; `zotero-meta-utils.js` / `zotero-chat-utils.js` are pure utilities
- **Gist sharing**: `gist-share-utils.js`; one-click GitHub Gist publish
- **Entry**: `index.html` two-phase asset loading (CDN/local), splash + secret gate

### 13. CI/CD + local debugging

| Workflow file | Trigger | Purpose |
|--------------|---------|---------|
| `daily-paper-reader.yml` | cron daily + dispatch | Main pipeline |
| `conference-paper-retrieval.yml` | dispatch | Conference retrieval |
| `maintain-supabase.yml` | cron 3×/day | arXiv/conference ingest |
| `maintain-biorxiv.yml` | cron | bioRxiv ingest |
| `maintain-medrxiv.yml` | cron | medRxiv ingest |
| `maintain-chemrxiv.yml` | cron | ChemRxiv ingest |
| `sync.yml` | cron daily | Fork sync upstream |
| `reset-content.yml` | dispatch | Content reset |

**Local debugging**:
- `scripts/bootstrap_local.sh`: one-shot venv creation + dependency install + local backend start
- `src/local_debug_server.py`: HTTP backend; `/api/local/workflows/dispatch` maps workflows to local Python subprocesses
- `.local-runs/<run_id>/`: per-run working directory (`run.log` + optional `config.yaml` snapshot)
- `src/local_env.py`: loads `.env` file
- `src/sitecustomize.py`: auto-loads `.env` (requires `PYTHONPATH` to include `src`)

## 5. Key Configuration Files

- **`config.yaml`** (repo root): runtime config — `arxiv_paper_setting`, `supabase` connection, `subscriptions.intent_profiles`
- **`.env` / `.env.example`**: environment variables (API keys, Supabase credentials, etc.)
- **`secret.private`**: AES-GCM encrypted secrets file; decrypted in the browser
- **`docs/config.yaml`**: read-only frontend snapshot (CI copies `config.yaml` → `docs/config.yaml` after runs)

## 6. External Dependencies

```
DeepSeek API ←── Step 4 refine + Step 6 summaries + Step 0 query expansion + frontend AI Q&A
Supabase     ←── end-to-end storage and recall (PostgREST + pgvector + FTS)
zwwen.online ←── public embedding / rerank service
SiliconFlow  ←── optional rerank API
arXiv API    ←── paper fetch (maintenance layer)
OpenReview   ←── conference paper fetch (requires account credentials)
GitHub API   ←── frontend read/write config / trigger Actions / manage Secrets / Gist sharing
Zotero       ←── browser Connector captures citation meta
```

## 7. Notable Design Choices and Known Issues

1. **`DPR_RUN_DATE` implicit bus**: main sets it once; each step recomputes paths — both must use the same token or artifacts land in the wrong place
2. **Vector dimension hardcoded to 384**: SQL column `vector(384)` matches `bge-small-en-v1.5`; changing models requires updating all SQL
3. **`sync.normalize_paper` drops fields**: fetcher output like `pdf_url`/`doi`/`decision` is discarded on ingest (only 10 columns kept)
4. **Hardcoded fallback API keys**: `model_loader`/`reranker_api` embed plaintext fallback keys; `or 'hardcoded-key'` pattern makes them almost always active
5. **`LLMClient.tokens` concurrency race**: class attribute `+=` is non-atomic; token counts may be inaccurate under multithreading (does not affect recommendation correctness)
6. **`boolean_expr` dead code**: `subscription_plan` always emits empty `boolean_expr`; AND/NOT parsing logic never runs
7. **Testing gaps**: no pgTAP tests for SQL itself; RRF fusion logic untested; end-to-end orchestration fully mocked
8. **Legacy leftovers**: `subscriptions.keywords.js` / `tracked-papers.js` still loaded but have no UI entry
9. **Code duplication**: `init_*.py` / `fetch_*.py` each reimplement `run_step`/`log`/`TODAY_STR`/seen-state instead of reusing `common.py`
10. **Two confusing "4-point thresholds"**: `llm-min-star`(4) is the 0–5 star rerank gate; `display-min-score`(4.0) is the 0–10 DeepSeek display gate

## 8. Testing

- **Python tests**: `pytest` (`pytest.ini`); ~38 test files cover most Python modules
- **JS tests**: 6 `test_*.js` files cover frontend pure functions (subscriptions, zotero, gist, llm-config)
- **Run**: `pytest` or `python -m pytest` (from repo root)
- **Better-covered paths**: subscription planning, LLM structured output, reranker API, per-source init/fetch
- **Thinly-covered paths**: RRF fusion logic, SQL/RPC, end-to-end orchestration, filter.py

## 9. Development Conventions

### Co-authored commit trailer rule

Commits created, committed, or pushed by Agent/Codex in this repository must append the following co-author trailers at the end of the commit message:

```text
Co-Authored-By: lilmortyj <781113402@qq.com>
Co-Authored-By: xixi <3495302215@qq.com>
Co-Authored-By: wy <345619498@qq.com>
```

This rule applies only to Git commit messages and does not require changes to `CITATION.cff`, `README.md`, or other project author metadata.

### Main branch merge rules

Before merging a work branch into `main` / `origin/main`, confirm the branch contains only upstream-syncable code, templates, and test changes — avoid breaking the existing `Sync fork` workflow for users on GitHub.

Before merging, run and review:

```bash
git diff --name-only origin/main..HEAD
git status --short
```

**Paths allowed on main**:
- `.github/workflows/`, `app/`, `scripts/`, `src/`, `sql/`, `tests/`
- `requirements*.txt`, `.env.example`, `.gitignore`
- `README.md`, `AGENTS.md`, `CLAUDE.md`

**Runtime / artifact paths that must NOT be merged by default** (unless the user explicitly requests it and understands the `Sync fork` risk for fork users):
- `config.yaml`, `docs/config.yaml`, `docs/README.md`, `docs/_sidebar.md`
- `docs/<date>/`, `docs/assets/`, `archive/`, `secret.private`

If a work branch mixes in the above runtime artifacts, strip those files from the commit first and merge only code changes to main.

**Recommended main merge** — fast-forward:

```bash
git switch main
git merge --ff-only <work-branch>
git push origin main
```

If `--ff-only` is not possible, explain why and the conflict scope first; do not create a merge commit that includes user runtime artifacts.
