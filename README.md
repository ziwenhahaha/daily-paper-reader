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



## 🖼️ 界面预览
<p align="center">
  <img src="others/demo1.png" alt="Daily Paper Reader 界面预览 1" width="80%" />
</p>
<p align="center">
  <img src="others/demo2.png" alt="Daily Paper Reader 界面预览 2" width="40%" />
  <img src="others/demo3.png" alt="Daily Paper Reader 界面预览 3" width="40%" />
</p>

## 📰 News

- **2026-07-07** 🎛️ 微调会议与侧边栏显示（`f202c703` / `a12d6d2b`）：ACL 2026 与 ICML 2026 年份按钮右上角增加星标提示，并将新版 sidebar 默认宽度从 373px 收窄到 298px，旧默认宽度会自动迁移到新宽度。
- **2026-07-07** 🏛️ 接入 ICML 2026 会议论文（`69a55296`）：从 OpenReview 同步 accepted 与公开 reject 共 6,555 篇论文，其中官方录取 6,341 篇，并补齐 PDF 链接、向量索引、统一会议检索与前端年份统计。
- **2026-07-07** 🏛️ 接入 ACL 2026 会议论文（`89351061`）：从 ACL Anthology 同步 Long / Short / Findings 共 4,459 篇公开论文，补齐 PDF 直链、向量索引与会议年份统计，并开放前端 ACL 2026 年份按钮。
- **2026-07-01** 🧭 修复侧边栏 v2 收起与冻结层细节（`adaa0dab` / `9384abb4` / `5b9c807a`）：大屏收起后侧边栏真正归零，正文重新居中；论文页 AI 输入框、模型选择、底部工具区与问题面板随正文一起居中，并修复冻结标题遮罩压住首篇论文的问题。
- **2026-07-01** 🔄 支持 Sync Fork 后再更新自有静态资源（`19ceb63a`）：项目自有 `app/*.js` / `app/*.css` 默认从当前站点本地加载，只有显式配置版本时才走不可变 CDN 路径，避免 CDN 自动部署后用户立即拿到未同步资源。
- **2026-07-01** 🏛️ 打通统一会议年份检索（`801c1c1b` / `4de71724` / `13154da5`）：新增统一会议论文入口与 RPC 过滤能力，前端可把多个会议年份组合成一次检索，并按所选论文总数限制在 3 万篇以内，同时按论文数量线性估算费用与耗时。
- **2026-07-01** 🎛️ 微调会议年份按钮展示（`8dcc05c0` / `91e02269`）：设置页会议面板改为双列滚动布局，并统一年份统计数字颜色。
- **2026-06-30** 📊 展示会议年份统计（`7ea7204b`）：会议年份按钮直接展示库内数量 / 官方录取数量，并将统计快照写入前端静态数据。
- **2026-06-29** 🏛️ 接入系统与安全会议数据源（`e00d82aa` / `9412598a` / `92c9705f`）：新增 OSDI / SOSP / IEEE S&P / NDSS 的本地 SQL、抓取维护入口、Supabase 同步与公开 PDF 回退抓取。
- **2026-06-24** 🛡️ 修复侧边栏跨运行覆盖问题：日报 Step 6 的 `update_sidebar` 改为在同一日期 marker 下按 `paper_id` 去重合并而非整块替换；会议侧边栏写入加文件锁、`conference-paper-retrieval` workflow 改为按"会议+年份"独立 concurrency group 并用重试式 push（rebase 冲突时重跑 `conference_sidebar.py` 合并），避免多次时间窗 / 多会议并行触发互相覆盖。
- **2026-06-23** 🔑 支持自定义域名部署：CI 自动写入 `.repo-owner.json`，前端优先读取该文件检测仓库归属，Token 验证阶段即校验用户与站点所有者是否一致；未同步此改动的用户（非自定义域名）仍走原有检测逻辑，完全灰度兼容。
- **2026-06-23** 🎛️ 会议检索面板改为双列布局，减少纵向滚动。
- **2026-06-22** 🏷️ 新增侧边栏未读 badge 与拖拽消除：论文分组显示未读计数红点，拖拽红点即可批量标记已读；阅读状态支持跨设备同步到 Supabase。
- **2026-06-21** 🏛️ 前端接入 9 大会议检索：支持 NeurIPS / ICLR / ICML / AAAI / CVPR / ECCV / IJCAI / ACL / EMNLP，按年份筛选并提供费用与时间预估。
- **2026-06-20** 📎 所有 SQL RPC 新增 `pdf_url` 字段返回，会议论文支持 CVF / ECVA / ACL Anthology 等多来源 PDF 直链跳转。
- **2026-06-19** 🧮 修复论文页 LaTeX 公式渲染：保护 `\\[...\\]` 和 `\\(...\\)` 块不被 Markdown 解析器破坏。
- **2026-05-31** 💬 优化论文页 AI 对话输入体验：输入框支持随内容自动增高，超过上限后在输入区内部滚动；同时调整按钮布局与点击层级，避免底部工具条遮挡发送和最近提问按钮。
- **2026-05-30** ⚙️ 提升 Step 6 文档生成稳定性：结构化输出 `max_tokens` 提升到 16k，并让每个并发论文处理线程使用独立 LLM Client，避免共享客户端参数互相覆盖。
- **2026-05-30** 🧹 精简图表提取依赖链路：移除 Java / `pdffigures2` 依赖，修复 GitHub Actions 中 `setup-java` 相关失败，并统一 PaperCropper 图表提取降级日志。
- **2026-05-25** 🎛️ 重构后台管理体验：日常与会议面板统一词条卡片、批量选择、底部操作区与危险操作分区；新增仅会议临时词条，优化候选生成、关键词编辑、最近提问与模型选择弹窗样式。
- **2026-05-25** 🖼️ 优化论文阅读页媒体展示：为 Attention 示例补充图片轮播，并固定轮播展示高度，避免切图时按钮位置跳动。
- **2026-05-24** ⚡ 优化 GitHub Pages 首屏加载：本地化/延迟加载非首屏脚本，移除 Google Fonts 阻塞，并支持 CDN 静态资源加速与失败回退。
- **2026-05-24** 🔐 修复静态密钥解锁链路：Pages 环境优先读取项目根目录 `secret.private`，避免已有密钥时误进入初始化向导。
- **2026-05-24** 🧾 收紧会议论文展示规则：会议检索结果只保留并展示 4 分及以上论文，统一进入精读页生成与图片提取流程。
- **2026-05-23** 🏛️ 打通会议论文阅读闭环：会议检索结果写入侧边栏，点击后进入本地介绍页；会议正文页对齐日常论文页的标题、元数据、标签、摘要与排版。
- **2026-05-23** 🧠 强化远端模型链路：默认使用 `zwwen` 远端 embedding 与 rerank，补齐 DeepSeek V4 长输出、JSON 截断恢复和前端探活兼容处理。
- **2026-05-23** 🔧 完善本地调试与密钥保存：本地后端支持触发 GitHub Actions 对应工作流，配置保存会同步写入本地 dotenv / `secret.private`，并修复密钥入口、弹窗与日志刷新问题。
- **2026-05-22** 🚀 新增本地一键部署与调试入口：支持局域网本地页面触发后端任务，默认 CPU 依赖与远端 embedding，降低本机运行门槛。
- **2026-05-22** 🌐 接入公益向量与重排服务：新增 `zwwen.online` embedding / rerank 链路，并让前端 reranker 测试在公益模式下免 API Key。
- **2026-05-21** 🧩 重整本地初始化与模型配置：支持本地 dotenv 调试配置，更新 DeepSeek 默认模型到 V4，并移除旧的柏拉图 / BLT 配置链路。

<details>
<summary>Earlier 2026 updates</summary>

- **2026-05-19** 🧪 补充 rerank 预算实验工具，便于对不同模型、候选池规模与调用预算做离线评估。
- **2026-05-03** 🎚️ 支持前端选择 reranker，并补充硅基流动 rerank 的限速重试与实验随机种子固定。
- **2026-05-02** 🧩 收敛模型配置入口：工作流只保留 DeepSeek API，重排改为本地 `Qwen/Qwen3-Reranker-0.6B`。
- **2026-04-08** 🏷️ 推荐状态改为按 tag 独立维护：`carryover` 时间与历史 `seen_ids` 不再跨词条互相污染，单词条 `10 天` / `30 天` 抓取、回补与复跑更稳定。
- **2026-03-28** 🧬 补齐多源论文维护链路：新增并打通 `bioRxiv`、`medRxiv`、`ChemRxiv` 以及多类会议论文的抓取、向量编码、Supabase 同步与检索 SQL，支持将多源论文纳入统一推荐与阅读流。
- **2026-03-28** 🎯 后台管理支持按词条单独触发抓取：可对指定 tag 直接运行 `10 天`、`30 天速览`、`30 天标准` 等任务，便于灰度验证、单主题回补与问题排查。
- **2026-03-28** 🛡️ 提升 embedding 与多源检索稳定性：修复多源 embedding 查询分组时机问题，并在远程 embedding 首次失败后对整轮任务熔断回退到本地模型，避免分片阶段反复超时。
- **2026-03-28** 🖼️ 优化论文详情页阅读体验：支持 `bioRxiv` 论文插图提取与展示，并改进元信息区域中长 PDF 链接的换行与布局表现。
- **2026-03-17** ⚙️ 修复 GitHub Actions 对 Python patch 版本路径的硬编码依赖，并将 `actions/checkout`、`actions/setup-python`、`actions/cache` 升级到 Node 24 对应版本，消除 runner 升级与 Node 20 弃用带来的工作流告警。
- **2026-03-13** 🔌 接入固定远程 embedding 服务入口：query embedding 缓存下沉到每条 `keyword` / `intent_query` 并按 hash 复用；同时收紧 Upstream Sync 工作流与触发面板的非 Fork 场景提示，对齐相关测试断言并恢复全量 `pytest` 通过。
- **2026-03-12** 🧠 调整统一候选池进入重排的策略：支持各 lane 保底候选进入统一池，并将统一池预算改为按论文规模与 `intent_query` 数量动态计算。
- **2026-03-11** 🛡️ 完善 Supabase 召回与推荐链路：BM25 / exact 增加时间分片与递归细分兜底，Supabase-only 召回改为动态 Top K；前端收紧关键词与意图 Query 选择数量并补充已选数量展示。
- **2026-03-10** 📝 更新 README 快速启动指引与 Fork 按钮样式，优化新手进入项目时的操作路径与展示细节。
- **2026-03-09** 📚 对齐 Zotero 一键保存链路到当前摘要结构，补齐聊天区写入，并清理 Attention 样本里的旧版摘要结构。
- **2026-03-09** 🖼️ 更新 README 多图界面预览与新手引导文案，并修复 gist 分享时摘要前的格式异常。
- **2026-03-08** 🛡️ 优化 `daily pipeline` 提交与推送逻辑，提交后先同步远端再 push，降低用户更新配置时的冲突概率。
- **2026-03-07** 🎨 更新首页与 README 展示文案，补充界面预览图，完善项目对外说明。
- **2026-03-06** 🛠️ 修复 LLM refine 补分与组合 query 打分逻辑，并补上回归测试；新增首页使用教程入口并修复移动端导航与教程路由。
- **2026-03-05** 🚀 后台面板新增 30 天标准快速抓取入口，加入指定 arXiv 论文逐阶段命中追踪；向量召回改为 exact 优先并增加 ANN 低密度回退。
- **2026-03-04** 🧹 新增内容重置工作流入口，后台支持更安全地重建初始内容与站点数据。
- **2026-02-20** ✨ 日报输出新增 AI 简报与评分展示；Zotero Action 改进为支持批量处理与 Better Notes 公式来源。
- **2026-02-08** 🔗 支持 Supabase 向量同步，并优先复用用户侧预置 embedding，补齐公开数据同步链路。
- **2026-02-07** 🎛️ 优化后台管理面板交互与布局，订阅面板向单路多关键词召回演进。
- **2026-02-06** 🧠 重构推荐链路，引入 smart query、布尔检索与订阅规划模块，并补上对应测试。
- **2026-01-24** 👀 新增 workflow 监视面板，便于直接查看后台任务运行状态。
- **2026-01-11** 📝 补齐第 6 步论文总结模块，打通每日推荐结果到文档生成的闭环。
- **2026-01-10** 🧱 推荐系统大改版，alias 统一为 tag，召回、排序与 LLM refine 链路拆分成独立步骤。

</details>

<details>
<summary>Earlier project milestones</summary>

- **2025-12-31** 🧭 新增统一引导面板，把主要设置集中到同一个入口。
- **2025-12-29** 🌐 项目切换到纯前端架构，订阅、配置与 GitHub Token 管理前置到浏览器端。
- **2025-12-23** 🧩 首页与侧边栏完成模块化拆分，同时将大模型接口迁到前端，界面交互开始成型。
- **2025-12-22** 🍴 调整为 Fork 即用版本，进一步降低自部署门槛。
- **2025-12-17** 🌱 最小可运行版本落地，并完成早期 Zotero Connector 集成。

</details>

## ✨ Why Daily Paper Reader?

- **🔎 Daily Paper Radar**：每日自动抓取 arXiv / OpenReview 新论文，持续追踪研究前沿。
- **🎯 Personalized Feed**：基于关键词、研究方向与兴趣生成个性化推荐流。
- **📖 Read in Context**：支持摘要、原文、速览、长总结在同一页面串联阅读。
- **💬 Ask While Reading**：支持 AI 论文问答，边读边问，沉淀私人讨论记录。
- **🚀 Zero-Server Deployment**：依托 GitHub Actions 自动更新、GitHub Pages 部署，无需额外服务器。
- **🛠️ Fork-and-Run**：Fork 后完成少量配置，即可上线自己的论文主页。

## 🧭 适用场景

- **🎓 个人论文雷达**：持续追踪自己研究方向的新论文。
- **🧪 实验室论文主页**：沉淀团队关注的论文脉络与阅读结果。
- **📚 日常阅读工作台**：把发现、阅读、问答、总结集中到一个入口。



## ⚙️ Workflow Architecture

![Daily Paper Reader 双链路工作流图](others/structure.png)

## 🚀 5 分钟快速启动

> [!TIP]
> 先准备一个大模型 API Key 和一个 GitHub PAT，然后依次完成 Fork、开启 Actions、开启 Pages，即可跑通完整流程。

### 1) 🔑 准备大模型 API Key

当前 README 默认以 **DeepSeek 官方 API** 为示例，建议先按默认配置跑通。

- 🌐 打开 [DeepSeek 平台](https://platform.deepseek.com/)
- 📝 完成注册 / 登录
- 🔐 充值并创建密钥

### 2) 🪪 准备 GitHub PAT

打开 [GitHub 新建 PAT 页面](https://github.com/settings/tokens/new?type=beta&scopes=repo,workflow,gist)，勾选以下权限（默认已勾选）：

- ✅ `repo`
- ✅ `workflow`
- ✅ `gist`

### 3) 🍴 Fork 本仓库
- Fork 到自己的 GitHub 账号下 <a href="https://github.com/ziwenhahaha/daily-paper-reader/fork"><img src="https://img.shields.io/badge/Fork%20on-GitHub-24292f?style=flat&logo=github" alt="Fork on GitHub" height="20" align="absmiddle" /></a>
- 建议仓库名保持 `daily-paper-reader` 不变

### 4) ▶️ 开启 GitHub Actions

进入你 Fork 的仓库，点击顶部 [`Actions`](../../actions)，启用 `daily-paper-reader` 工作流。

### 5) 🌍 开启 GitHub Pages

进入你 Fork 的仓库，进入 `Settings → Pages`：

- ⚙️ Source 选择 `Deploy from a branch`
- 🌿 Branch 选择 `main`
- 📁 Folder 选择 `/(root)`

保存后等待约 1 分钟，站点地址会显示在页面顶部。

### 6) ✅ 打开站点验收

访问：

```text
https://<你的用户名>.github.io/daily-paper-reader
```

完成以上步骤后，后续大多数日常使用和配置都可以直接在网页端完成。后续教程参考：[daily-paper-reader 指引](https://ziwenhahaha.github.io/daily-paper-reader/#/tutorial/README)

## 🧪 本地调试模式

如果你在本机开发，不想点击按钮后触发 GitHub Actions，可以启动本地调试后端：

```bash
scripts/bootstrap_local.sh
```

这个脚本会自动创建 `.venv`、安装远程服务模式依赖、按需从 `.env.example` 生成 `.env`，然后启动本地后端。默认不会下载 `torch` 等重依赖。启动完成后访问：

```text
http://127.0.0.1:8567
```

如果你已经准备好了 Python 环境，也可以只启动后端：

```bash
scripts/local_debug.sh
```

也可以手动指定监听地址和端口：

```bash
python src/local_debug_server.py --host 127.0.0.1 --port 8567
```

如果需要跳过依赖安装，可以使用：

```bash
DPR_SKIP_INSTALL=1 scripts/bootstrap_local.sh
```

如果只想启动并明确跳过依赖安装，也可以使用旧的快速部署模式：

```bash
DPR_INSTALL_MODE=minimal scripts/bootstrap_local.sh
```

如果要一次性安装完整运行依赖，可以使用：

```bash
DPR_INSTALL_MODE=full scripts/bootstrap_local.sh
```

完整依赖模式默认先安装 **CPU 版 PyTorch**，避免普通本机部署时误下载 CUDA 大包。如果你确实需要自定义 PyTorch 源，可以设置：

```bash
DPR_INSTALL_MODE=full DPR_TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu scripts/bootstrap_local.sh
```

在 `localhost / 127.0.0.1` 页面里点击“触发工作流”时，前端会自动调用本地后端 `/api/local/workflows/dispatch`，把 `daily-paper-reader.yml`、`conference-paper-retrieval.yml` 等映射为本地 Python 子进程执行，不会上 GitHub，也不会要求启用 Actions。运行日志会显示在工作流面板里，并保存在 `.local-runs/`。

如果前端和本地后端不是同一个地址，可以在页面加载前设置：

```html
<script>
  window.DPR_LOCAL_API_BASE = 'http://127.0.0.1:8567';
</script>
```

如果要部署到自己的服务器上调试，请同时启动这个后端，并对内网或受信任网络开放端口：

```bash
DPR_LOCAL_HOST=0.0.0.0 DPR_LOCAL_PORT=8567 scripts/local_debug.sh
```

然后访问 `http://<服务器地址>:8567`。这样页面和后端同源，点击触发按钮会在服务器本机执行工作流命令，而不是调用 GitHub Actions。

## 🙏 致谢

Daily Paper Reader 的论文发现、重排与阅读增强链路受益于以下开源项目、模型与服务：

- **[PaperCropper](https://github.com/fake-learn/PaperCropper)**：为论文 PDF 中的图表检测与裁剪提供了重要参考和能力基础，让论文详情页可以更自然地展示图表内容。
- **[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)**：作为默认 embedding 模型之一，支撑语义召回、会议论文检索与查询向量复用。
- **[Qwen/Qwen3-Reranker](https://huggingface.co/Qwen)**：作为重排链路的重要开源模型基础，用于提升候选论文排序质量。
- **zwwen.online 公益服务**：提供默认远端 embedding / rerank 接入，降低普通用户本地部署时的模型下载、显存和算力门槛。
- **硅基流动（SiliconFlow）**：提供可选的 rerank API 接入方式，便于在不同模型尺寸和调用预算之间做实验与切换。
- **DeepSeek**：为候选过滤、论文精读摘要与问答等 LLM 环节提供模型能力支持。

## ❓ FAQ

### 💻 需要服务器吗？

不需要。项目基于 **GitHub Actions + GitHub Pages** 运行和部署。

### 🎛️ 可以做哪些个性化配置？

你可以调整订阅关键词、研究方向、查询意图与日常阅读偏好，构建自己的论文推荐流。

### 👨‍🔬 适合实验室或团队一起用吗？

可以。它很适合做实验室公共论文面板，或者作为团队内部的论文发现与阅读入口。

## 💬 欢迎交流

QQ 群：583867967（欢迎交流，已有：1151 人）


## ⭐ Star History

<a href="https://www.star-history.com/?type=date&repos=ziwenhahaha%2Fdaily-paper-reader">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ziwenhahaha/daily-paper-reader&type=date&theme=dark&legend=top-left&sealed_token=HZNlFXt8xbwRv5OoiqbjkjDPJoOuXlfSMxuVmHWAdDqfd9IVMab3xcK4VxF3DlJAvaO71PL3smUpfEw-NjNT83w8NqNJ0UPIhoNcxbiPhTMQkoMhkawF1w" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ziwenhahaha/daily-paper-reader&type=date&legend=top-left&sealed_token=HZNlFXt8xbwRv5OoiqbjkjDPJoOuXlfSMxuVmHWAdDqfd9IVMab3xcK4VxF3DlJAvaO71PL3smUpfEw-NjNT83w8NqNJ0UPIhoNcxbiPhTMQkoMhkawF1w" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ziwenhahaha/daily-paper-reader&type=date&legend=top-left&sealed_token=HZNlFXt8xbwRv5OoiqbjkjDPJoOuXlfSMxuVmHWAdDqfd9IVMab3xcK4VxF3DlJAvaO71PL3smUpfEw-NjNT83w8NqNJ0UPIhoNcxbiPhTMQkoMhkawF1w" />
 </picture>
</a>
