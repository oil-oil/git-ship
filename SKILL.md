---
name: git-ship
description: |
  自动化 Git 工作流一键发布助手，执行完整的「ship」流程：
  隔离快照当前改动 → 基于最新 origin/main 创建临时 worktree 和新分支
  → commit → 推送 → 创建 PR → squash merge → 清理临时 worktree。
  原工作区全程不 stash、不切分支、不改索引，适合多个 Agent 或任务并行工作。
  调用 ship 本身就是对完整流程的授权；自动推断分支名、commit message 和 PR 内容，
  不为这些常规信息请求确认，只在冲突、验证失败或命令阻塞时暂停。

  仅在用户明确表达「ship」意图时触发，例如：
  - 直接说「ship」「/ship」「git ship」
  - 明确要求完整走完 git 流程：「帮我走一遍 git 流程」「拉 main、切分支、提 PR、合并」
  - 使用类似「发布这次改动」「把这些改动提成 PR 并合并」的表达

  不应触发的情况：
  - 只是想 commit（用 /commit skill）
  - 只是想创建 PR（不需要完整 ship 流程）
  - 只是想 push 代码
  - 讨论 git 相关问题或解释 git 概念
---

# git-ship — 隔离式一键 Git 工作流

## 目标

把调用 `ship` 时捕获到的当前工作区改动，完整走完这条路径：

```text
当前改动快照
  → 基于最新 origin/main 创建临时 worktree 和新分支
  → commit → PR → squash merge
  → 清理临时 worktree
```

核心原则：原工作区可能正被其他 Agent 或任务使用。全程不要在原工作区执行
`stash`、`checkout`、`switch`、`reset`、`clean`、`add` 或 `commit`，也不要改动它的索引。

## 第 0 步：信息收集

先在原工作区只读检查现状：

```bash
git status --short
git diff --stat HEAD
git diff HEAD
git ls-files --others --exclude-standard
```

待发布内容以这些命令执行时的快照为准。后续并行产生的新改动不自动纳入本次发布。

如果没有已跟踪改动，也没有未跟踪文件，提示「没有检测到未提交改动」并停止。

用户调用 `ship` 就表示已经授权执行整条工作流。不要为分支名、commit message、
PR 标题、PR 正文或是否继续等常规信息请求确认。

### 自动确定发布信息

1. **分支名**
   - 用户提供时直接使用。
   - 否则根据改动推断，格式为 `<type>/<short-desc>`，例如
     `feat/add-login-page`、`fix/null-pointer-crash`。
   - 自动推断的名称已存在时，追加简短时间戳或随机后缀并继续，避免并行 ship 撞名。
     用户明确指定的名称已存在时停止，不覆盖。

2. **Commit message**
   - 用户提供时直接使用。
   - 否则根据 diff 生成 Conventional Commits 格式：
     `<type>(<scope>): <description>`。

3. **PR 标题和正文**
   - PR 标题默认使用 commit message。
   - PR 正文根据快照生成 Summary 和改动文件概览。

简短告知用户即将使用的分支和 commit，然后立即继续，不等待回复。

## 第 1 步：同步远端主分支

只更新远端引用，不 checkout 或 pull 原工作区：

```bash
git fetch origin main --prune
```

记录：

```bash
git rev-parse --short origin/main
```

告知用户：`已获取最新 origin/main（commit: <hash>）`。

如果 fetch 失败，停止并报告认证或网络问题。

## 第 2 步：创建隔离 worktree 并复制改动快照

从 skill 目录调用快照脚本：

```bash
SHIP_WORKTREE="$(
  bash "<skill-directory>/scripts/create_ship_worktree.sh" "<branch-name>"
)"
```

脚本会：

- 从最新 `origin/main` 创建临时 worktree 和 `<branch-name>`；
- 把原工作区相对 `HEAD` 的已跟踪改动以三方合并方式应用进去；
- 复制未跟踪且未被 ignore 的文件；
- 暂存快照；
- 输出临时 worktree 的绝对路径。

后续所有 Git、验证和构建命令都必须在 `$SHIP_WORKTREE` 中执行。

如果脚本报告冲突，停止。原工作区不受影响；保留临时 worktree，明确告诉用户其路径，
让用户在隔离目录中解决冲突。不要回到原工作区修冲突。

告知用户：`已创建隔离分支 <branch-name>（worktree: <path>）`。

## 第 3 步：检查快照并 commit

在临时 worktree 中确认内容：

```bash
git -C "$SHIP_WORKTREE" status --short
git -C "$SHIP_WORKTREE" diff --cached --stat
git -C "$SHIP_WORKTREE" diff --cached
```

确认快照没有意外文件后提交：

```bash
git -C "$SHIP_WORKTREE" commit -m "<commit-message>"
```

commit 成功后告知用户 commit hash。

## 第 3.5 步：本地验证

根据本次提交涉及的项目，在临时 worktree 中运行对应检查：

- **apps/client 有改动**：
  `cd "$SHIP_WORKTREE/apps/client" && npx tsc --noEmit`
- **apps/api 有改动**：
  `cd "$SHIP_WORKTREE/apps/api" && uv run ruff check && uv run ruff format --check`

如果仓库提供更准确的 `AGENTS.md`、测试或构建命令，以仓库说明为准。

验证失败时停止，不 push。保留临时 worktree 和分支，报告路径及失败命令，方便继续修复；
不要改动原工作区。

## 第 4 步：推送并创建 PR

```bash
git -C "$SHIP_WORKTREE" push -u origin "<branch-name>"
```

然后创建 PR：

```bash
cd "$SHIP_WORKTREE"
gh pr create \
  --title "<PR title>" \
  --body "$(cat <<'EOF'
## Summary
<根据 diff 内容自动生成 2-3 条 bullet points>

## Changes
<文件改动列表>

🤖 Shipped via git-ship
EOF
)" \
  --base main \
  --head "<branch-name>"
```

打印 PR URL：`PR 已创建：<url>`。

## 第 5 步：直接合并

不等待 CI，创建 PR 后立即合并：

```bash
gh pr merge <pr-number> --squash --delete-branch
```

如果用户传入 `--no-squash`，改用 `--merge`。

合并命令成功后，再确认 PR 状态确实为 `MERGED`：

```bash
gh pr view <pr-number> --json state --jq '.state'
```

只有确认已合并，才进入清理步骤。

## 第 6 步：清理隔离 worktree

PR 合并成功后：

```bash
git worktree remove "$SHIP_WORKTREE"
git branch -D "<branch-name>"
git fetch origin main --prune
```

这里允许删除本次新建的本地分支，因为它已确认合并且远端分支已删除。不要删除其他分支。

不要在原工作区执行 `checkout main` 或 `pull`。原工作区保持调用前的分支、文件和索引状态；
它可能仍显示本次已发布的改动，这是隔离并行工作的预期结果。

最终输出：

```text
🚀 Ship 完成！
  ✓ 分支 <branch-name> 已合并到 main
  ✓ 临时 worktree 已清理
  ✓ 原工作区未切分支、未 stash、未改索引
  ✓ origin/main 已更新到 <commit-hash>
```

## 错误处理原则

- 每步操作前简短说明正在做什么。
- 出错立即停止，不执行 force push、reset --hard 或 clean。
- 合并前发生错误时，保留临时 worktree 和分支，报告其绝对路径和明确的下一步。
- 只有确认 PR 已合并，才删除临时 worktree 和本次创建的本地分支。
- 不为自动推断的分支名、commit message、PR 标题、PR 正文或继续执行请求确认。
- 只有发生冲突、验证失败、认证缺失、仓库保护阻止合并或确实需要用户选择时才暂停。

## 常见边界情况

| 情况 | 处理方式 |
|---|---|
| 原工作区位于非 main 分支 | 不切换；仍把相对当前 `HEAD` 的未提交改动应用到最新 `origin/main` |
| 原工作区已有 staged 内容 | 按 `HEAD` 总快照发布；不保留 staged/unstaged 边界，原索引不变 |
| 并行任务继续修改原工作区 | 本次只发布创建 worktree 时捕获的快照，后续改动留给下一次 ship |
| 没有未提交改动 | 提示没有检测到改动并停止 |
| 自动推断的分支名已存在 | 自动追加简短时间戳或随机后缀，不复用、不覆盖 |
| 用户指定的分支名已存在 | 停止并提示冲突 |
| 应用快照发生冲突 | 保留隔离 worktree，在其中解决；原工作区不受影响 |
| 验证失败 | 不 push，保留隔离 worktree并报告路径 |
| gh 未登录 | 提示执行 `gh auth login` |
| PR 合并失败或受保护规则阻止 | 保留 worktree 和分支，不清理 |
| `--no-squash` 参数 | 使用 `--merge` 而不是 `--squash` |
| 子模块内有未提交改动 | 不会被普通 Git diff 完整捕获；停止并提示用户单独处理 |
