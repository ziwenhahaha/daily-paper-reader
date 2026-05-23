# 仓库级 Agent 规则

## 提交共同作者规则

- 本仓库内由 Agent/Codex 创建、提交或推送的 commit，提交信息末尾必须追加以下共同作者 trailer：

```text
Co-Authored-By: lilmortyj <781113402@qq.com>
Co-Authored-By: xixi <3495302215@qq.com>
Co-Authored-By: wy <345619498@qq.com>
```

- 以上规则仅用于 Git commit message，不代表需要修改 `CITATION.cff`、`README.md` 或其它项目作者元数据。

## 合并主分支规则

- 将工作分支合并到 `main` / `origin/main` 前，必须先确认本次提交只包含可上游同步的代码、模板与测试改动，避免破坏用户通过 GitHub 网页 `Sync fork` 的既有使用习惯。
- 合并前必须执行并检查：

```bash
git diff --name-only origin/main..HEAD
git status --short
```

- 允许合并到主分支的典型路径：
  - `.github/workflows/`
  - `app/`
  - `scripts/`
  - `src/`
  - `sql/`
  - `tests/`
  - `requirements*.txt`
  - `.env.example`
  - `.gitignore`
  - `README.md`
  - `AGENTS.md`
- 默认不得合并以下用户运行态/每日生成产物路径，除非用户明确要求且已说明会影响 fork 用户的 `Sync fork` 风险：
  - `config.yaml`
  - `docs/config.yaml`
  - `docs/README.md`
  - `docs/_sidebar.md`
  - `docs/<日期>/`
  - `docs/assets/`
  - `archive/`
  - `secret.private`
- 若工作分支中混入了上述运行态产物，必须先从提交中剥离这些文件，只保留代码改动后再合并主分支。
- 推荐的主分支合并方式是快进合并：

```bash
git switch main
git merge --ff-only <work-branch>
git push origin main
```

- 若无法 `--ff-only`，必须先说明原因和冲突范围，不得直接创建包含用户运行态产物的 merge commit。
