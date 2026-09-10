<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="git-ship turns working-tree changes into a reviewed squash merge through a guarded Git workflow">
</p>

<p align="center">
  <a href="./README.zh-CN.md">简体中文</a>
</p>

完成代码检查、分支整理、提交、推送、创建 PR 和合并，处理流程中的冲突与验证失败。

```text
working tree → latest main → new branch → commit → local checks → PR → squash merge
```

Invoking `ship` authorizes the full workflow. It generates the branch name, Conventional Commit, and PR content, resolves conflicts, fixes validation or CI failures, and continues until the PR is merged.

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="The seven guarded stages of the git-ship workflow">
</p>

## Why use it

- Keeps local changes safe while synchronizing with the latest `main`.
- Uses a fresh, descriptive branch for every shipment.
- Creates a Conventional Commit and a readable pull request summary.
- Runs the repository's existing checks and fixes failures before pushing.
- Resolves conflicts while preserving both current production behavior and the new feature.
- Reads CI logs, fixes failures, and retries until required checks pass.
- Squash-merges the PR, deletes the remote branch, and returns to an up-to-date `main`.
- Pauses only for external blockers such as missing authentication, permissions, or required human approval.

## Install

Clone the repository into a directory where your agent discovers skills:

```bash
git clone https://github.com/oil-oil/git-ship.git ~/.agents/skills/git-ship
```

If your client uses another skills directory, clone it there instead. The important entry point is `SKILL.md`.

## Use

Finish your change, leave it uncommitted in the working tree, then ask your agent:

```text
ship
```

You can also provide the branch and commit up front:

```text
Ship this as feat/add-export with commit "feat(export): add markdown export"
```

`git-ship` shows the resolved plan and then continues immediately:

```text
📦 Ready to ship:
  Branch: feat/add-export
  Commit: feat(export): add markdown export
  Target: main ← feat/add-export (squash merge)
```

It does not ask for confirmation of the branch name, commit message, PR title, or PR body. Provide explicit names in the initial request when needed.

## How it works

| Stage | Action | Guard |
| --- | --- | --- |
| Inspect | Read working-tree changes and unpushed commits | Stops only when there is nothing to ship |
| Sync | Stash changes and fetch the latest `origin/main` | Preserves local-only commits |
| Branch | Create a unique branch or reuse the feature branch | Never duplicates the same change |
| Commit | Restore changes and commit all files | Resolves stash conflicts |
| Verify | Run documented repository checks | Fixes root causes and reruns checks |
| Publish | Push and create a PR with `gh` | Requires GitHub authentication |
| CI | Wait for checks and inspect failed logs | Fixes, pushes, and waits again |
| Merge | Resync main, squash, and delete the branch | Resolves newly introduced conflicts |
| Finish | Confirm the merge and return to `main` | Never force-pushes or hard-resets |

## Requirements

- Git
- [GitHub CLI](https://cli.github.com/) authenticated with `gh auth login`
- A repository whose primary branch is `main`
- Repository validation commands documented in files such as `AGENTS.md`, `README.md`, `package.json`, `pyproject.toml`, or `Makefile`

When no trustworthy validation command exists, the Skill reports that clearly instead of inventing one.

## Safety model

Invoking `ship` authorizes the complete publishing workflow, conflict resolution, and related validation fixes. The Skill preserves current production behavior and the new feature while repairing test, lint, type, build, and CI failures. It never force-pushes, hard-resets, skips checks, or weakens valid tests. It asks for help only when an external blocker such as authentication, permissions, or required human approval cannot be resolved locally.

## Customize

Fork the repository and edit `SKILL.md` to match your team's branch naming, merge strategy, PR template, or required checks. Keep the non-destructive recovery rules and external permission boundaries intact.

## Contributing

Issues and pull requests are welcome. Please keep changes focused, explain any new Git behavior, and include the failure path for every new action.

## License

[MIT](./LICENSE)

## 配置、依赖与使用边界

需要 Git、GitHub CLI 与目标仓库写权限；复用 gh 的官方认证，不收集聊天中的密钥。命令中的主分支名以真实默认分支为准。

调用 ship 即授权约定发布流程；先保留原分支与 HEAD，检查待提交内容。不把密钥、无关改动或失败检查一起发布。

使用示例：

```text
ship 当前改动。
```

## GitHub 安装

把 [仓库地址](https://github.com/oil-oil/git-ship) 交给 Agent，要求按 README 安装；也可运行：

```bash
npx skills add oil-oil/git-ship
```

安装后由宿主重新加载 Skill。
