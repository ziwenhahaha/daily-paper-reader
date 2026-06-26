<p align="center">
  <img src="others/LOGO.png" alt="Daily Paper Reader Logo" width="720" />
</p>

<h2 align="center">Your Daily Companion for Discovering and Reading AI Papers</h2>

<p align="center">
  <a href="https://github.com/ziwenhahaha/daily-paper-reader/stargazers">
    <img src="https://img.shields.io/github/stars/ziwenhahaha/daily-paper-reader?style=flat-square" alt="Stars" />
  </a>
  <a href="https://github.com/ziwenhahaha/daily-paper-reader/network/members">
    <img src="https://img.shields.io/github/forks/ziwenhahaha/daily-paper-reader?style=flat-square" alt="Forks" />
  </a>
  <a href="https://github.com/ziwenhahaha/daily-paper-reader/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/ziwenhahaha/daily-paper-reader?style=flat-square" alt="License" />
  </a>
  <a href="https://ziwenhahaha.github.io/daily-paper-reader">
    <img src="https://img.shields.io/badge/Demo-GitHub%20Pages-2ea44f?style=flat-square" alt="Demo" />
  </a>
  <a href="https://ziwenhahaha.github.io/daily-paper-reader/#/tutorial/README">
    <img src="https://img.shields.io/badge/Docs-Quick%20Start-blue?style=flat-square" alt="Docs" />
  </a>
</p>



## 🖼️ UI Preview
<p align="center">
  <img src="others/demo1.png" alt="Daily Paper Reader UI preview 1" width="80%" />
</p>
<p align="center">
  <img src="others/demo2.png" alt="Daily Paper Reader UI preview 2" width="40%" />
  <img src="others/demo3.png" alt="Daily Paper Reader UI preview 3" width="40%" />
</p>

## 📰 News

- **2026-06-24** 🛡️ Fixed sidebar cross-run overwrite issues: daily Step 6 `update_sidebar` now deduplicates and merges by `paper_id` under the same date marker instead of replacing the whole block; conference sidebar writes use file locking, and the `conference-paper-retrieval` workflow uses independent concurrency groups per "conference + year" with retry-based push (re-runs `conference_sidebar.py` merge on rebase conflicts), preventing parallel multi-window / multi-conference triggers from overwriting each other.
- **2026-06-23** 🔑 Custom domain deployment support: CI auto-writes `.repo-owner.json`; the frontend reads it first to detect repo ownership, and the token verification step checks that the user matches the site owner; users who haven't synced this change (non-custom domains) still use the original detection logic—fully backward compatible.
- **2026-06-23** 🎛️ Conference retrieval panel switched to a two-column layout to reduce vertical scrolling.
- **2026-06-22** 🏷️ Added sidebar unread badges and drag-to-dismiss: paper groups show unread count badges; drag a badge to batch-mark papers as read; read state syncs across devices via Supabase.
- **2026-06-21** 🏛️ Frontend integration for 9 major conference retrievals: NeurIPS / ICLR / ICML / AAAI / CVPR / ECCV / IJCAI / ACL / EMNLP, with year filtering plus cost and time estimates.
- **2026-06-20** 📎 All SQL RPCs now return a `pdf_url` field; conference papers support direct PDF links from CVF / ECVA / ACL Anthology and other sources.
- **2026-06-19** 🧮 Fixed LaTeX formula rendering on paper pages: protects `\\[...\\]` and `\\(...\\)` blocks from being broken by the Markdown parser.
- **2026-05-31** 💬 Improved AI chat input on paper pages: the input box auto-grows with content and scrolls internally after hitting the max height; adjusted button layout and click layering to prevent the bottom toolbar from blocking send and recent-question buttons.
- **2026-05-30** ⚙️ Improved Step 6 document generation stability: structured output `max_tokens` raised to 16k, and each concurrent paper-processing thread uses its own LLM client to avoid shared client parameter races.
- **2026-05-30** 🧹 Streamlined figure extraction dependencies: removed Java / `pdffigures2` dependency, fixed GitHub Actions `setup-java` failures, and unified PaperCropper figure extraction fallback logging.
- **2026-05-25** 🎛️ Refactored admin panel UX: daily and conference panels share unified profile cards, batch selection, bottom action area, and danger-zone partitioning; added conference-only temporary profiles; improved candidate generation, keyword editing, recent questions, and model selection modal styling.
- **2026-05-25** 🖼️ Improved paper page media display: added image carousel for Attention examples with fixed carousel height to prevent button position jumps when switching images.
- **2026-05-24** ⚡ Optimized GitHub Pages first-screen load: localized / lazy-loaded non-critical scripts, removed Google Fonts blocking, and added CDN static asset acceleration with fallback on failure.
- **2026-05-24** 🔐 Fixed static secret unlock flow: Pages environment reads project-root `secret.private` first, avoiding the init wizard when a secret already exists.
- **2026-05-24** 🧾 Tightened conference paper display rules: conference retrieval results only keep and display papers scoring 4+ points, unified into the deep-read page generation and image extraction flow.
- **2026-05-23** 🏛️ Closed the conference paper reading loop: conference retrieval results write to the sidebar; clicking opens a local intro page; conference content pages align with daily paper pages for title, metadata, tags, abstract, and layout.
- **2026-05-23** 🧠 Strengthened remote model pipeline: default to `zwwen` remote embedding and rerank; added DeepSeek V4 long-output support, JSON truncation recovery, and frontend health-check compatibility.
- **2026-05-23** 🔧 Improved local debugging and secret saving: local backend can trigger corresponding GitHub Actions workflows; config saves sync to local dotenv / `secret.private`; fixed secret entry, modal, and log refresh issues.
- **2026-05-22** 🚀 Added one-click local deploy and debug entry: supports triggering backend tasks from a LAN-local page, with default CPU dependencies and remote embedding to lower the local run barrier.
- **2026-05-22** 🌐 Integrated public embedding and rerank service: added `zwwen.online` embedding / rerank pipeline; frontend reranker test works without API key in public-service mode.
- **2026-05-21** 🧩 Reorganized local init and model config: supports local dotenv debug config, updated default DeepSeek model to V4, and removed legacy Baidu / BLT config paths.

<details>
<summary>Earlier 2026 updates</summary>

- **2026-05-19** 🧪 Added rerank budget experiment tooling for offline evaluation across models, candidate pool sizes, and call budgets.
- **2026-05-03** 🎚️ Frontend reranker selection support; added rate-limit retry for SiliconFlow rerank and fixed experiment random seeds.
- **2026-05-02** 🧩 Consolidated model config entry points: workflows only keep DeepSeek API; reranking moved to local `Qwen/Qwen3-Reranker-0.6B`.
- **2026-04-08** 🏷️ Recommendation state now maintained per tag: `carryover` timing and historical `seen_ids` no longer cross-contaminate between profiles; per-profile `10-day` / `30-day` fetch, backfill, and re-runs are more stable.
- **2026-03-28** 🧬 Completed multi-source paper maintenance pipeline: added and wired `bioRxiv`, `medRxiv`, `ChemRxiv`, and multiple conference paper sources for fetch, vector encoding, Supabase sync, and retrieval SQL—supporting unified recommendation and reading across sources.
- **2026-03-28** 🎯 Admin panel supports per-profile fetch triggers: run `10-day`, `30-day skim`, `30-day standard`, and other tasks for a specific tag—useful for gray testing, single-topic backfill, and troubleshooting.
- **2026-03-28** 🛡️ Improved embedding and multi-source retrieval stability: fixed multi-source embedding query grouping timing; circuit-breaker fallback to local model for the whole task round after first remote embedding failure, avoiding repeated timeouts during sharding.
- **2026-03-28** 🖼️ Improved paper detail page reading experience: supports `bioRxiv` figure extraction and display; improved wrapping and layout for long PDF links in the metadata area.
- **2026-03-17** ⚙️ Fixed GitHub Actions hardcoded Python patch version paths; upgraded `actions/checkout`, `actions/setup-python`, and `actions/cache` to Node 24 compatible versions, eliminating runner upgrade and Node 20 deprecation workflow warnings.
- **2026-03-13** 🔌 Integrated fixed remote embedding service endpoint: query embedding cache moved to each `keyword` / `intent_query` and reused by hash; tightened Upstream Sync workflow and trigger panel non-fork hints; aligned related test assertions and restored full `pytest` pass.
- **2026-03-12** 🧠 Adjusted unified candidate pool rerank entry strategy: supports guaranteed per-lane candidates entering the unified pool; unified pool budget now computed dynamically from paper scale and `intent_query` count.
- **2026-03-11** 🛡️ Improved Supabase recall and recommendation pipeline: BM25 / exact added time slicing and recursive subdivision fallback; Supabase-only recall uses dynamic Top K; frontend tightened keyword and intent query selection limits with selected-count display.
- **2026-03-10** 📝 Updated README quick-start guide and Fork button styling; improved onboarding path and presentation for new users.
- **2026-03-09** 📚 Aligned Zotero one-click save to current summary structure; added chat-area writes; cleaned legacy summary structure in Attention samples.
- **2026-03-09** 🖼️ Updated README multi-image UI preview and onboarding copy; fixed gist share formatting issue before abstracts.
- **2026-03-08** 🛡️ Optimized `daily pipeline` commit and push logic: sync remote before push after commit to reduce conflict probability when users update config.
- **2026-03-07** 🎨 Updated homepage and README copy; added UI preview images; improved public project description.
- **2026-03-06** 🛠️ Fixed LLM refine score backfill and combined query scoring logic with regression tests; added homepage tutorial entry; fixed mobile navigation and tutorial routing.
- **2026-03-05** 🚀 Admin panel added 30-day standard quick-fetch entry; added per-stage hit tracking for specified arXiv papers; vector recall switched to exact-first with ANN low-density fallback.
- **2026-03-04** 🧹 Added content reset workflow entry; admin supports safer rebuild of initial content and site data.
- **2026-02-20** ✨ Daily digest output added AI briefing and score display; Zotero Action improved with batch processing and Better Notes formula source support.
- **2026-02-08** 🔗 Supabase vector sync support; prioritizes reusing user-side precomputed embeddings; completed public data sync pipeline.
- **2026-02-07** 🎛️ Improved admin panel interaction and layout; subscription panel evolved toward single-path multi-keyword recall.
- **2026-02-06** 🧠 Refactored recommendation pipeline: introduced smart query, boolean retrieval, and subscription planning modules with corresponding tests.
- **2026-01-24** 👀 Added workflow monitor panel for direct backend task status viewing.
- **2026-01-11** 📝 Completed Step 6 paper summary module; closed the loop from daily recommendations to document generation.
- **2026-01-10** 🧱 Major recommendation system overhaul: alias unified to tag; recall, ranking, and LLM refine split into independent steps.

</details>

<details>
<summary>Earlier project milestones</summary>

- **2025-12-31** 🧭 Added unified onboarding panel, centralizing main settings in one entry point.
- **2025-12-29** 🌐 Project switched to pure frontend architecture; subscriptions, config, and GitHub Token management moved to the browser.
- **2025-12-23** 🧩 Homepage and sidebar modularized; LLM API moved to frontend; UI interactions took shape.
- **2025-12-22** 🍴 Adjusted to fork-and-run version, further lowering self-deployment barrier.
- **2025-12-17** 🌱 Minimum viable version shipped; early Zotero Connector integration completed.

</details>

## ✨ Why Daily Paper Reader?

- **🔎 Daily Paper Radar**: Automatically fetches new papers from arXiv / OpenReview daily, keeping you on top of the research frontier.
- **🎯 Personalized Feed**: Generates a personalized recommendation stream based on keywords, research directions, and interests.
- **📖 Read in Context**: Read abstracts, originals, quick skims, and long summaries in one connected page.
- **💬 Ask While Reading**: AI paper Q&A while you read—build a private discussion history as you go.
- **🚀 Zero-Server Deployment**: Runs on GitHub Actions and deploys via GitHub Pages—no extra server needed.
- **🛠️ Fork-and-Run**: Fork, complete a few configuration steps, and launch your own paper homepage.

## 🧭 Use Cases

- **🎓 Personal paper radar**: Continuously track new papers in your research areas.
- **🧪 Lab paper homepage**: Curate papers your team cares about and share reading outcomes.
- **📚 Daily reading workspace**: Bring discovery, reading, Q&A, and summarization into one place.



## ⚙️ Workflow Architecture

![Daily Paper Reader dual-pipeline workflow diagram](others/structure.png)

## 🚀 5-Minute Quick Start

> [!TIP]
> Prepare an LLM API key and a GitHub PAT, then fork the repo, enable Actions, and enable Pages—in that order—to run the full pipeline.

### 1) 🔑 Prepare an LLM API Key

This README defaults to the **DeepSeek official API** as the example. We recommend getting the default setup working first.

- 🌐 Open the [DeepSeek platform](https://platform.deepseek.com/)
- 📝 Sign up / log in
- 🔐 Add credits and create an API key

### 2) 🪪 Prepare a GitHub PAT

Open the [GitHub new PAT page](https://github.com/settings/tokens/new?type=beta&scopes=repo,workflow,gist) and grant the following scopes (selected by default):

- ✅ `repo`
- ✅ `workflow`
- ✅ `gist`

### 3) 🍴 Fork this repository
- Fork to your own GitHub account <a href="https://github.com/ziwenhahaha/daily-paper-reader/fork"><img src="https://img.shields.io/badge/Fork%20on-GitHub-24292f?style=flat&logo=github" alt="Fork on GitHub" height="20" align="absmiddle" /></a>
- We recommend keeping the repository name as `daily-paper-reader`

### 4) ▶️ Enable GitHub Actions

In your forked repository, click [`Actions`](../../actions) at the top and enable the `daily-paper-reader` workflow.

### 5) 🌍 Enable GitHub Pages

In your forked repository, go to `Settings → Pages`:

- ⚙️ Source: `Deploy from a branch`
- 🌿 Branch: `main`
- 📁 Folder: `/(root)`

Save and wait about one minute—the site URL will appear at the top of the page.

### 6) ✅ Open the site and verify

Visit:

```text
https://<your-username>.github.io/daily-paper-reader
```

After these steps, most day-to-day use and configuration can be done entirely in the web UI. For follow-up tutorials, see: [daily-paper-reader guide](https://ziwenhahaha.github.io/daily-paper-reader/#/tutorial/README)

## 🧪 Local Debug Mode

If you're developing locally and don't want button clicks to trigger GitHub Actions, start the local debug backend:

```bash
scripts/bootstrap_local.sh
```

This script automatically creates `.venv`, installs remote-service-mode dependencies, generates `.env` from `.env.example` when needed, and starts the local backend. By default it does not download heavy dependencies like `torch`. After startup, visit:

```text
http://127.0.0.1:8567
```

If you already have a Python environment ready, you can start only the backend:

```bash
scripts/local_debug.sh
```

You can also manually specify host and port:

```bash
python src/local_debug_server.py --host 127.0.0.1 --port 8567
```

To skip dependency installation:

```bash
DPR_SKIP_INSTALL=1 scripts/bootstrap_local.sh
```

To start while explicitly skipping dependency installation (legacy quick-deploy mode):

```bash
DPR_INSTALL_MODE=minimal scripts/bootstrap_local.sh
```

To install the full runtime dependency set in one go:

```bash
DPR_INSTALL_MODE=full scripts/bootstrap_local.sh
```

Full dependency mode installs **CPU-only PyTorch** by default, avoiding accidental CUDA package downloads on typical machines. To use a custom PyTorch index:

```bash
DPR_INSTALL_MODE=full DPR_TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu scripts/bootstrap_local.sh
```

On `localhost / 127.0.0.1`, clicking "Trigger workflow" calls the local backend at `/api/local/workflows/dispatch`, mapping `daily-paper-reader.yml`, `conference-paper-retrieval.yml`, and others to local Python subprocesses—no GitHub, no Actions required. Run logs appear in the workflow panel and are saved under `.local-runs/`.

If the frontend and local backend are on different hosts, set this before the page loads:

```html
<script>
  window.DPR_LOCAL_API_BASE = 'http://127.0.0.1:8567';
</script>
```

To debug on your own server, start the backend and expose the port on your LAN or trusted network:

```bash
DPR_LOCAL_HOST=0.0.0.0 DPR_LOCAL_PORT=8567 scripts/local_debug.sh
```

Then visit `http://<server-address>:8567`. Page and backend share the same origin; trigger buttons run workflow commands on the server locally instead of calling GitHub Actions.

## 🙏 Acknowledgments

Daily Paper Reader's paper discovery, reranking, and reading-enhancement pipeline benefits from the following open-source projects, models, and services:

- **[PaperCropper](https://github.com/fake-learn/PaperCropper)**: Important reference and capability foundation for figure detection and cropping in paper PDFs, enabling natural figure display on paper detail pages.
- **[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)**: Default embedding model supporting semantic recall, conference paper retrieval, and query vector reuse.
- **[Qwen/Qwen3-Reranker](https://huggingface.co/Qwen)**: Key open-source reranking model foundation for improving candidate paper ranking quality.
- **zwwen.online public service**: Default remote embedding / rerank integration, lowering model download, VRAM, and compute barriers for typical users.
- **SiliconFlow**: Optional rerank API integration for experimenting and switching between model sizes and call budgets.
- **DeepSeek**: Model support for candidate filtering, deep-read summaries, Q&A, and other LLM stages.

## ❓ FAQ

### 💻 Do I need a server?

No. The project runs and deploys on **GitHub Actions + GitHub Pages**.

### 🎛️ What can I customize?

You can adjust subscription keywords, research directions, query intents, and daily reading preferences to build your own paper feed.

### 👨‍🔬 Is it suitable for labs or teams?

Yes. It works well as a shared lab paper board or as a team-internal paper discovery and reading hub.

## 💬 Community

QQ group: 583867967 (welcome to join — 1151 members)


## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ziwenhahaha/daily-paper-reader&type=Date&showForks=true)](https://star-history.com/#ziwenhahaha/daily-paper-reader&Date)
