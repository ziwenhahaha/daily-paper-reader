# 当前项目分支协作约定

## 分支角色

- `main`
  - 只作为 **fork 运行分支 / 默认分支 / 自动同步分支** 使用。
  - 不作为日常功能开发分支。
  - 与 `.github/workflows/sync.yml` 中写死的 `target_sync_branch: main` 保持一致。

- `main-openai-compatible`
  - 只作为 **上游 PR 目标分支的本地镜像** 使用。
  - 主要用于对齐上游、比较差异、整理待提交改动。
  - 不在该分支上做零散调试开发。

- `work/openai-compatible`
  - 作为 **OpenAI-compatible 相关功能的唯一日常开发分支**。
  - 本地调试、提交、推送到 fork、提 PR，默认都在此分支完成。

- `work/safe-all`
  - 作为其它独立主题的工作分支。
  - 规则与 `work/openai-compatible` 相同。

- `archive/*`
  - 仅作历史保留，不继续承载新开发。

## GitHub Actions 调试规则

- 需要在 GitHub 仓库上调试时，优先使用 `workflow_dispatch` 并显式指定工作分支。
- 只要 workflow 支持手动触发，就不要为了测试临时把 `main` 变成开发分支。
- 推荐优先在 `work/openai-compatible` 上推送后，通过 GitHub UI 或 `gh workflow run --ref work/openai-compatible` 触发测试。

## 什么时候才使用 `main`

- 只有在以下场景才允许把改动带到 `main`：
  - 需要验证 **默认分支相关行为**
  - 需要验证 **定时任务**
  - 需要验证 **fork 自动同步链路**
  - 需要验证 **明确绑定默认分支的仓库级行为**

- 若只是功能开发、前端调试、接口联调、手动触发 workflow，默认不要动 `main`。

## 推荐工作流

1. 从 `main-openai-compatible` 切出或更新 `work/openai-compatible`。
2. 在 `work/openai-compatible` 上完成开发、本地调试与提交。
3. 推送到 fork 对应分支。
4. 需要仓库侧验证时，优先手动触发 workflow，并显式指定该工作分支。
5. 需要给上游提 PR 时，从 fork 的 `work/openai-compatible` 提到上游的 `main-openai-compatible`。

## 禁止事项

- 不要把 `main` 当成功能开发分支长期使用。
- 不要在 `main`、`main-openai-compatible`、`work/openai-compatible` 三条分支上同时承载同一组未整理改动。
- 不要为了临时测试频繁把 `main` 指向某个功能状态；如确有需要，应先说明用途，再做一次性同步或 cherry-pick。

