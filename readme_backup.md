# 📖 Daily Paper Reader：3 分钟搭建你的智能论文推荐站

一个开箱即用的学术论文推荐系统，通过关键词或自然语言描述你的研究兴趣，每天自动从 arXiv 筛选、重排、精读相关论文，并生成精美的在线阅读站点。

- **零成本部署**：基于 GitHub Actions + Pages，无需服务器，Fork 即用
- **智能推荐**：BM25 + Embedding 双路召回 + Reranker 重排 + LLM 评分，精准匹配你的研究方向
- **沉浸式阅读**：双语标题、论文速览、AI 精读总结、私人研讨区，一站式学术体验
- **实时交互**：站内订阅管理、工作流触发、论文分享、本地聊天记忆，所有操作都在浏览器完成

---

## ✨ 核心功能

### 📊 智能推荐流水线
- **多路召回**：BM25（词法匹配）+ Qwen3-Embedding（语义理解）双引擎检索，RRF 融合扩大覆盖
- **精准重排**：本地 Qwen3-Reranker-0.6B 对候选集重排序，提升推荐准确度
- **LLM 评分**：自动生成双语证据（Evidence）、一句话总结（TLDR）及 0-10 分评分
- **Carryover 机制**：高分论文跨日保留，避免遗漏重要成果

### 🎨 现代化阅读界面
- **双语标题栏**：中英文标题智能布局，响应式适配
- **论文速览卡片**：Motivation / Method / Result / Conclusion 四维快速浏览
- **AI 精读总结**：自动生成结构化深度总结（需配置 DeepSeek API）
- **私人研讨区**：基于 Gemini 的论文问答，支持上下文对话，本地 IndexedDB 存储记忆

### 🔧 站内后台管理
- **订阅关键词**：支持高级搜索语法（`||` / `&&` / `author:`）
- **智能订阅（LLM Query）**：用自然语言描述研究兴趣，自动扩展查询
- **论文引用追踪**：通过 Semantic Scholar ID 订阅论文的新引用
- **工作流触发**：站内一键刷新推荐结果，实时查看运行状态
- **密钥配置**：本地加密存储 DeepSeek API Key

### 🎯 辅助功能
- **Zotero 集成**：一键导入论文元数据，包含 AI 总结和聊天历史
- **GitHub Gist 分享**：生成论文分享链接，方便团队协作
- **最近提问**：记录并快速复用常用问题（仅本地存储）

---

## 🚀 快速开始（Fork 即用，3 步出站）

### 1) Fork 本仓库
点击右上角 `Fork`，复制到你的账号下。

### 2) 启用 Actions 并首次运行（只需一次）
Fork 后 Actions 默认暂停，需要手动激活：

1. 进入你 Fork 后的仓库 → 顶部 **Actions**
2. 点击 **I understand my workflows, go ahead and enable them**
3. 左侧选择 **daily-paper-reader**
4. 点击 **Run workflow** → 再点绿色 **Run workflow** 确认

> 这一步会生成 `docs/` 与 `archive/*/recommend` 并自动提交回 `main` 分支。首次一般需要 3–8 分钟。

### 3) 开启 GitHub Pages
1. 仓库顶部 **Settings** → 左侧 **Pages**
2. **Source** 选择 `Deploy from a branch`
3. **Branch** 选择 `main`，目录选择 `/docs`
4. 点击 **Save**

等待约 30 秒后，你会看到站点地址，例如：`https://你的ID.github.io/项目名/`。

---

## 🔑 必须：配置 DeepSeek（用于评分/总结）

本项目默认工作流会调用 DeepSeek 来完成核心能力，Step 3 重排改为本地模型：
- Step 3 本地重排（Qwen/Qwen3-Reranker-0.6B）
- Step 4 LLM 精炼评分（双语证据 + 双语 TLDR）
- Step 6 翻译/总结（可选能力，默认实现依赖 DeepSeek）

### 1) 注册 / 充值 / 创建 API Key
- 注册：https://platform.deepseek.com/
- 充值：右上角头像 → 立即充值（建议先充 5 元体验）
- 创建令牌：左侧 **令牌** → **新建令牌**（名称随意，默认即可）

> 工作流默认会使用 `LOCAL_RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B` 与 DeepSeek chat 模型（见 `/.github/workflows/daily-paper-reader.yml`）。

---

## 🪪 必须：GitHub Token 申请（用于站内面板与 Gist 分享）

站点前端会调用 GitHub API 来完成这些能力，因此需要 GitHub Token：
- **一键写入仓库 Secrets**（保存 `DEEPSEEK_API_KEY` 等）
- **站内触发 Actions 工作流**（立即刷新 / 同步上游）
- **生成 GitHub Gist 分享链接**（论文页面“分享”按钮）

### 推荐：Classic PAT（最省心）
1. 打开创建页面（已预填权限）：  
   https://github.com/settings/tokens/new?description=Daily%20Paper%20Reader&scopes=repo,workflow,gist
2. 过期时间建议选一个你能接受的（例如 30/90 天），到期可重新生成
3. 生成后复制一次（GitHub 不会再次展示）

**所需最小权限：**
- `repo`：用于写入仓库 Secrets
- `workflow`：用于触发 GitHub Actions 工作流
- `gist`：用于“分享（生成 GitHub Gist 链接）”功能

---

---
## 🔧 目录与更新规则（避免踩坑）

### 用户区（你可自由改）
- `config.yaml`：你的订阅与偏好配置（上游不会覆盖）

### 每日产出区（每天会更新）
- `docs/`：网页内容（GitHub Pages 的发布目录）
- `archive/*/recommend`：推荐结果（按日期存档）
- `archive/carryover.json`、`archive/arxiv_seen.json`、`archive/crawl_state.json`：运行状态（用于增量抓取与跨日保留）

### 代码区（上游可能更新）
除 `archive/` 和 `docs/` 外，其它都视为代码区（建议不要在 Fork 里大改核心代码，以免将来同步上游冲突）。

---

## ❓常见问题（FAQ）

- **为什么今天没有更新？**  
  先看仓库 Actions 里 `daily-paper-reader` 是否成功；也可能当天窗口内确实无新论文或被过滤后为空。

- **站点能打开但没有内容？**  
  通常是首次 Actions 没跑成功，或 Pages 没指向 `/docs`。按“快速开始”第 2/3 步检查。

- **我想立刻刷新一次，而不是等定时任务**  
  进入仓库 Actions → `daily-paper-reader` → `Run workflow`；或在站点里使用“工作流触发面板”（需要 GitHub Token）。

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ziwenhahaha/daily-paper-reader&type=date&legend=top-left)](https://www.star-history.com/#ziwenhahaha/daily-paper-reader&type=date&legend=top-left)
