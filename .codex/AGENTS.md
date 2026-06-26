# Branch collaboration conventions for this project

## Branch roles

- `main`
  - Used only as the **fork run branch / default branch / auto-sync branch**.
  - Not used as a day-to-day feature development branch.
  - Kept consistent with the hardcoded `target_sync_branch: main` in `.github/workflows/sync.yml`.

- `main-openai-compatible`
  - Used only as a **local mirror of the upstream PR target branch**.
  - Mainly for aligning with upstream, comparing diffs, and organizing pending changes.
  - No scattered debugging/development on this branch.

- `work/openai-compatible`
  - The **single day-to-day development branch for OpenAI-compatible features**.
  - Local debugging, commits, pushing to the fork, and opening PRs are all done here by default.

- `work/safe-all`
  - A work branch for other independent topics.
  - Same rules as `work/openai-compatible`.

- `archive/*`
  - Kept for history only; no new development.

## GitHub Actions debugging rules

- When debugging on the GitHub repository, prefer `workflow_dispatch` and explicitly specify the work branch.
- As long as a workflow supports manual triggering, do not temporarily turn `main` into a development branch just to test.
- Prefer pushing to `work/openai-compatible` first, then triggering tests via the GitHub UI or `gh workflow run --ref work/openai-compatible`.

## When to use `main`

- Bringing changes to `main` is only allowed in these scenarios:
  - Verifying **default-branch-related behavior**
  - Verifying **scheduled tasks**
  - Verifying the **fork auto-sync pipeline**
  - Verifying **repo-level behavior explicitly bound to the default branch**

- For plain feature development, frontend debugging, API integration, or manual workflow triggering, do not touch `main` by default.

## Recommended workflow

1. Branch off or update `work/openai-compatible` from `main-openai-compatible`.
2. Do development, local debugging, and commits on `work/openai-compatible`.
3. Push to the corresponding branch on the fork.
4. For repo-side verification, prefer manual workflow triggering with the work branch explicitly specified.
5. To open an upstream PR, go from the fork's `work/openai-compatible` to upstream's `main-openai-compatible`.

## Commit attribution rules

- Commits created by Agent/Codex in this repository must append the following co-author trailers at the end of the commit message:

```text
Co-Authored-By: lilmortyj <781113402@qq.com>
Co-Authored-By: xixi <3495302215@qq.com>
Co-Authored-By: wy <345619498@qq.com>
```

- This rule applies only to Git commit messages and does not require changes to `CITATION.cff`, `README.md`, or other project author metadata.

## Prohibitions

- Do not use `main` as a long-lived feature development branch.
- Do not carry the same set of unorganized changes simultaneously across `main`, `main-openai-compatible`, and `work/openai-compatible`.
- Do not repeatedly point `main` at some feature state for temporary testing; if truly necessary, explain the purpose first, then do a one-off sync or cherry-pick.
