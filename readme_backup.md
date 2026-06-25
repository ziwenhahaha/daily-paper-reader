# 📖 Daily Paper Reader: Build Your Smart Paper Recommendation Site in 3 Minutes

An out-of-the-box academic paper recommendation system. Describe your research interests with keywords or natural language, and it automatically filters, reranks, and deep-reads relevant papers from arXiv each day—then publishes a polished online reading site.

- **Zero-cost deployment**: Runs on GitHub Actions + Pages—no server required, fork and go
- **Smart recommendations**: BM25 + embedding dual-path recall + reranker + LLM scoring, precisely matched to your research directions
- **Immersive reading**: Bilingual titles, paper quick skims, AI deep-read summaries, and a private discussion area—all in one academic workflow
- **Real-time interaction**: In-site subscription management, workflow triggers, paper sharing, and local chat memory—everything happens in the browser

---

## ✨ Core Features

### 📊 Smart Recommendation Pipeline
- **Multi-path recall**: BM25 (lexical matching) + Qwen3-Embedding (semantic understanding) dual-engine retrieval, fused with RRF for broader coverage
- **Precise reranking**: Local Qwen3-Reranker-0.6B reranks the candidate set to improve recommendation accuracy
- **LLM scoring**: Automatically generates bilingual evidence, one-line TLDR summaries, and 0–10 relevance scores
- **Carryover mechanism**: High-scoring papers carry over across days so you don't miss important work

### 🎨 Modern Reading Interface
- **Bilingual title bar**: Smart Chinese/English title layout with responsive design
- **Quick skim cards**: Four dimensions—Motivation / Method / Result / Conclusion—for fast browsing
- **AI deep-read summaries**: Automatically generates structured in-depth summaries (requires DeepSeek API configuration)
- **Private discussion area**: Gemini-based paper Q&A with contextual conversation; memories stored locally in IndexedDB

### 🔧 In-Site Admin Panel
- **Subscription keywords**: Advanced search syntax supported (`||` / `&&` / `author:`)
- **Smart subscription (LLM Query)**: Describe research interests in natural language; queries are expanded automatically
- **Citation tracking**: Subscribe to new citations of a paper via Semantic Scholar ID
- **Workflow triggers**: One-click refresh of recommendations from the site, with live run status
- **Secret configuration**: DeepSeek API key stored locally with encryption

### 🎯 Additional Features
- **Zotero integration**: One-click import of paper metadata, including AI summaries and chat history
- **GitHub Gist sharing**: Generate paper share links for team collaboration
- **Recent questions**: Record and quickly reuse common prompts (local storage only)

---

## 🚀 Quick Start (Fork and Go — 3 Steps to Launch)

### 1) Fork this repository
Click **Fork** in the top-right corner and copy the repo to your account.

### 2) Enable Actions and run once (one-time setup)
Actions are paused by default after forking—you need to activate them manually:

1. Open your forked repository → **Actions** at the top
2. Click **I understand my workflows, go ahead and enable them**
3. Select **daily-paper-reader** on the left
4. Click **Run workflow** → confirm with the green **Run workflow** button

> This step generates `docs/` and `archive/*/recommend` and auto-commits back to `main`. The first run usually takes 3–8 minutes.

### 3) Enable GitHub Pages
1. **Settings** at the top of the repo → **Pages** on the left
2. **Source**: `Deploy from a branch`
3. **Branch**: `main`, folder: `/docs`
4. Click **Save**

After about 30 seconds you'll see your site URL, e.g. `https://<your-id>.github.io/<repo-name>/`.

---

## 🔑 Required: Configure DeepSeek (for scoring / summaries)

The default workflow calls DeepSeek for core capabilities; Step 3 reranking uses a local model:
- Step 3 local rerank (`Qwen/Qwen3-Reranker-0.6B`)
- Step 4 LLM refine scoring (bilingual evidence + bilingual TLDR)
- Step 6 translation / summarization (optional capability; default implementation depends on DeepSeek)

### 1) Sign up / add credits / create an API key
- Sign up: https://platform.deepseek.com/
- Add credits: top-right avatar → add credits (¥5 is enough to try it out)
- Create a token: left sidebar **API Keys** → **Create API Key** (name optional, defaults are fine)

> The workflow defaults to `LOCAL_RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B` and DeepSeek chat models (see `/.github/workflows/daily-paper-reader.yml`).

---

## 🪪 Required: GitHub Token (for in-site panel and Gist sharing)

The site frontend calls the GitHub API for these capabilities, so a GitHub token is required:
- **One-click write to repository Secrets** (save `DEEPSEEK_API_KEY`, etc.)
- **Trigger Actions workflows from the site** (refresh now / sync upstream)
- **Generate GitHub Gist share links** (paper page **Share** button)

### Recommended: Classic PAT (easiest)
1. Open the creation page (scopes pre-filled):  
   https://github.com/settings/tokens/new?description=Daily%20Paper%20Reader&scopes=repo,workflow,gist
2. Pick an expiration you're comfortable with (e.g. 30/90 days); regenerate when it expires
3. Copy the token once after generation (GitHub won't show it again)

**Minimum required scopes:**
- `repo`: write repository Secrets
- `workflow`: trigger GitHub Actions workflows
- `gist`: **Share** feature (generate GitHub Gist links)

---

---
## 🔧 Directory Layout and Update Rules (avoid common pitfalls)

### User zone (free to edit)
- `config.yaml`: your subscriptions and preferences (upstream won't overwrite this)

### Daily output zone (updated each day)
- `docs/`: web content (GitHub Pages publish directory)
- `archive/*/recommend`: recommendation results (archived by date)
- `archive/carryover.json`, `archive/arxiv_seen.json`, `archive/crawl_state.json`: runtime state (incremental fetch and cross-day carryover)

### Code zone (may be updated by upstream)
Everything except `archive/` and `docs/` is treated as code (avoid large edits to core code in your fork to reduce upstream sync conflicts).

---

## ❓ FAQ

- **Why didn't it update today?**  
  Check whether `daily-paper-reader` succeeded in repository Actions; it's also possible there were no new papers in the window, or everything was filtered out.

- **Site loads but has no content?**  
  Usually the first Actions run didn't succeed, or Pages isn't pointed at `/docs`. Re-check Quick Start steps 2 and 3.

- **I want to refresh now instead of waiting for the schedule**  
  Go to repository Actions → `daily-paper-reader` → `Run workflow`; or use the **workflow trigger panel** on the site (requires a GitHub token).

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ziwenhahaha/daily-paper-reader&type=date&legend=top-left)](https://www.star-history.com/#ziwenhahaha/daily-paper-reader&type=date&legend=top-left)
