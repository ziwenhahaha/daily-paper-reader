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



<details>
<summary>Earlier news</summary>

- **2026-01-11** 📝 补齐第 6 步论文总结模块，打通每日推荐结果到文档生成的闭环。
- **2026-01-10** 🧱 推荐系统大改版，alias 统一为 tag，召回、排序与 LLM refine 链路拆分成独立步骤。
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

当前 README 默认以 **柏拉图 API 平台** 为示例，建议先按默认配置跑通。

- 🌐 打开 [柏拉图 API 平台](https://api.bltcy.ai/)
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

[![Star History Chart](https://api.star-history.com/svg?repos=ziwenhahaha/daily-paper-reader&type=Date)](https://star-history.com/#ziwenhahaha/daily-paper-reader&Date)
