---
name: git-ship
description: |
  自动化 Git 工作流一键发布助手，执行完整的「ship」流程：
  基于最新 main 切新分支 → commit → 推送 → 创建 PR → squash merge → 回 main。

  仅在用户明确表达「ship」意图时触发，例如：
  - 直接说「ship」「/ship」「git ship」
  - 明确要求完整走完 git 流程：「帮我走一遍 git 流程」「拉 main、切分支、提 PR、合并」
  - 使用类似「发布这次改动」「把这些改动提成 PR 并合并」的表达

  不应触发的情况：
  - 只是想 commit
  - 只是想创建 PR
  - 只是想 push 代码
  - 讨论 git 相关问题或解释 git 概念
---

# git-ship — 一键 Git 工作流

## 目标

把当前工作区的改动，完整走完这条路径：

```text
当前改动 → 基于最新 main 切新分支 → commit → PR → squash merge → 回 main
```

## 第 0 步：信息收集

开始前先检查现状：

```bash
git status
git diff --stat
git remote -v
gh auth status
```

如果没有未提交改动，提示用户检查现状并停止。

需要确认两件事：

**1. 分支名**

- 用户已经提供时直接使用。
- 否则根据 `git diff --stat` 推断，格式为 `<type>/<short-desc>`。
- 向用户展示推断结果，允许确认或修改。

**2. Commit message**

- 用户已经提供时直接使用。
- 否则根据 `git diff` 生成 Conventional Commits 格式：`<type>(<scope>): <description>`。
- 向用户展示推断结果，允许确认或修改。

收集完毕后打印：

```text
📦 准备 ship：
  分支名：feat/xxx
  Commit：feat(xxx): add xxx
  目标：main ← feat/xxx（squash merge）

继续？(y/n)
```

得到明确确认后再继续。

## 第 1 步：同步主分支

```bash
git stash push --include-untracked -m "git-ship: temp stash"
git checkout main
git pull origin main
```

告知用户最新 `main` 的 commit hash。`git pull` 失败时立即停止，不要自动处理冲突。

## 第 2 步：创建分支

```bash
git checkout -b <branch-name>
```

分支名已存在时停止，请用户提供新名称。

## 第 3 步：恢复改动并提交

```bash
git stash pop
git add -A
git commit -m "<commit-message>"
```

如果 `stash pop` 发生冲突，立即停止，列出冲突文件并给出人工处理步骤。不要自动解决冲突。

## 第 3.5 步：本地验证

根据当前改动和仓库说明，寻找已有验证命令：

1. 优先读取 `AGENTS.md`、`CONTRIBUTING.md` 和 `README.md`。
2. 再检查 `package.json`、`pyproject.toml`、`Makefile`、CI 配置等项目文件。
3. 运行与改动范围直接相关的最小检查，例如 lint、typecheck、test 或 build。
4. 找不到可信命令时，明确告知用户跳过了哪些验证以及原因，不要自行编造命令。

验证失败时立即停止，不要 push 未通过验证的提交。

## 第 4 步：推送并创建 PR

```bash
git push -u origin <branch-name>
```

使用 `gh pr create` 创建 PR：

- base 为 `main`
- head 为新分支
- 标题使用 commit message
- 正文包含 2–3 条 Summary、改动文件概览和 `🤖 Shipped via git-ship`

创建成功后向用户展示 PR URL。

## 第 5 步：Squash 合并

本地验证通过后直接合并：

```bash
gh pr merge <pr-number> --squash --delete-branch
```

如果仓库规则阻止合并，停止并展示 GitHub 返回的信息，不要绕过保护规则。

## 第 6 步：回到 main

```bash
git checkout main
git pull origin main
```

打印最终状态：

```text
🚀 Ship 完成！
  ✓ 分支 <branch-name> 已合并到 main
  ✓ 当前在 main，已同步最新代码（<commit-hash>）
```

## 错误处理原则

- 每步操作前简短说明正在做什么。
- 任何命令失败后立即停止。
- 不使用 force push、`reset --hard` 或其他破坏性恢复方式。
- 不自动解决冲突。
- 给出明确、可执行的下一步。

## 常见边界情况

| 情况 | 处理方式 |
| --- | --- |
| 当前在非 main 分支 | stash → 切 main → pull → 新分支 → pop |
| 没有未提交改动 | 提示用户检查是否已 commit，然后停止 |
| 分支名已存在 | 停止并请用户提供新名称 |
| `gh` 未登录 | 提示运行 `gh auth login` |
| 用户指定 `--no-squash` | 使用 `--merge` |
