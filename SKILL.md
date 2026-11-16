---
name: git-ship
description: |
  自动化 Git 工作流一键发布助手，执行完整的「ship」流程：
  基于最新 main 切新分支 → commit → 推送 → 创建 PR → 限时等待检查 → squash merge → 回 main。
  调用 ship 本身就是对完整流程的授权；自动推断分支名、commit message 和 PR 内容，
  并主动解决 Git 冲突、测试、lint、类型检查、构建和 CI 失败，持续修复和重试，
  直到 PR 实测状态为 MERGED。不要因可自行修复的失败暂停，只在认证、权限、仓库保护等
  无法由当前环境解决的外部阻塞出现时请求用户介入。

  仅在用户明确表达完整发布/合入意图时触发，例如：
  - 直接说「ship」「/ship」「git ship」
  - 直接表达上线或发布意图：「上线」「上线吧」「可以上线了」「上线这个课程」「发布这次改动」「修完之后合入上线」
  - 明确要求完整走完 git 流程：「帮我走一遍 git 流程」「拉 main、切分支、提 PR、合并」

  不应触发的情况：
  - 只是想 commit
  - 只是想创建 PR（不合并）
  - 只是想 push 代码
  - 讨论 git 相关问题或解释 git 概念
license: MIT
compatibility: 需要 Git、已通过 gh auth login 认证的 GitHub CLI 与 Python 3.10+；可选读取本机已登录的 Vercel CLI 核验预览构建真实状态。
metadata:
  version: "1.1.0"
---

# git-ship — 一键 Git 工作流

## 目标与成功标准

把当前工作区的改动，完整走完这条路径：

```text
当前改动 → 基于最新 main 切新分支 → commit → PR → squash merge → 回 main
```

用户调用 `ship` 就表示已经授权执行整条工作流。流程应连续完成，不要为分支名、
commit message、PR 标题、PR 正文、冲突解决方案、验证修复或是否继续等信息请求确认。

这份授权包括：

- 修改当前功能代码，使它与最新 `main` 的线上功能兼容。
- 修改由本次改动或冲突引起的测试、lint、类型、构建和 CI 问题。
- 创建必要的修复提交并重复推送。
- 在合并前同步最新 `main`，解决新产生的冲突并重新验证。

只有同时满足以下条件才算完成：

1. PR 已成功合并到 `main`，不能把“PR 已创建”或“已开启自动合并”当作完成。
2. 必需检查已经通过，或仓库没有可运行的检查。
3. 本地回到 `main` 并尽可能快进到合并后的提交。

## 核心执行原则

- `ship` 的默认结果是“发布成功”，不是“发现问题后把问题交还给用户”。
- 命令失败后先判断原因并恢复流程；不要机械重复同一个失败命令。
- 以最新 `origin/main` 的现有线上能力和当前改动的产品目标为共同约束，优先保留两者。
- 修复根因，不通过跳过测试、删除断言、关闭规则或使用 `--no-verify` 制造假通过。
- 不使用 force push、`reset --hard`、丢弃提交或覆盖用户改动等破坏性手段。
- 只有缺少认证/权限、必须由他人审批、平台或网络持续不可用、需求意图确实无法从代码和上下文判断时，才暂停并说明唯一需要用户处理的事项。

## 第 0 步：信息收集

开始前先检查现状：

```bash
git status --short --branch
git branch --show-current
git diff --stat
git diff --cached --stat
git remote -v
gh auth status
```

同时记录当前分支、未提交改动和未推送提交，防止遗漏用户工作。没有未提交改动时，
继续检查当前分支相对 `origin/main` 是否存在待发布提交；两者都没有才提示没有可发布内容并停止。

自动确定以下信息：

**1. 分支名**

- 用户已经提供时直接使用。
- 否则根据改动内容推断，格式为 `<type>/<short-desc>`。
- 遵循目标仓库已有分支前缀或命名规则；没有规则时使用语义化名称。
- 本地或远端同名分支已存在时，自动增加简短后缀，避免因命名冲突中断。

**2. Commit message**

- 用户已经提供时直接使用。
- 否则根据完整 diff 生成 Conventional Commits 格式：`<type>(<scope>): <description>`。

**3. PR 标题和正文**

- PR 标题默认使用 commit message。
- PR 正文根据 diff 自动生成 2–3 条 Summary、改动文件概览和验证结果。
- 不单独询问 PR 名称或正文。

确定后简短告知用户即将使用的分支和 commit，然后立即继续，不等待回复。

## 第 1 步：同步主分支

有工作区改动时先创建带唯一标识的 stash，并记录对应引用；没有改动时不要创建空 stash。

```bash
git stash push --include-untracked -m "git-ship: <timestamp>"
git fetch --prune origin
```

fetch 后以第 0 步记录的原分支和原 HEAD 为基准检查待发布提交。原功能分支已有提交时保留该分支，直接合并 `origin/main`，随后恢复本次 stash；不能先切到 main 再决定原分支是否有提交。只有原分支没有待发布提交时才从 `origin/main` 新建发布分支。

先从远端 HEAD 或仓库配置核对目标主分支；下文 `main` 是占位名称，仓库使用 `master` 等名称时全部替换为实际分支。

告知用户最新主分支的 commit hash。

如果本地 `main` 无法 fast-forward：

1. 检查本地独有提交，不能删除或覆盖它们。
2. 直接从最新 `origin/main` 创建发布分支，继续发布流程。
3. 在最终回到 `main` 时保留这些本地提交，并明确说明本地 `main` 未被覆盖；这不影响已经完成的线上合并。

## 第 2 步：创建分支

```bash
git checkout -b <branch-name> origin/main
```

如果当前工作已经位于包含待发布提交的功能分支，可以继续使用它；先合并最新
`origin/main` 并按“冲突处理流程”解决问题。不要把相同改动重复提交。

## 第 3 步：恢复改动并提交

```bash
git stash apply <recorded-stash>
git add -A
git commit -m "<commit-message>"
```

若工作区同时包含与本次发布无关的其他未完成草稿（如未定稿文章或实验文件），严禁因此绕开 `git-ship` 直接提交 `main`，也不要把无关草稿一并 `git add -A`：在发布分支上仅 `git add` 本次发布范围内的文件并 `git checkout -- .` / 清理未暂存的无关草稿，待第 6 步回到 `main` 后再从 `<recorded-stash>` 恢复那些无关本地草稿并删除本次 stash。

`stash apply` 发生冲突时，按“冲突处理流程”自行解决。确认所有目标改动已经提交（且需要保留的无关本地草稿已在回到 `main` 后恢复）后，再删除本次创建的 stash；不要误删用户已有 stash。

提交钩子失败属于验证失败：修复根因、重新暂存并再次提交，不要使用 `--no-verify`。

## 冲突处理流程

以下流程适用于 `stash apply`、合并最新 `main`、远端分支非 fast-forward 和 PR 合并冲突。

1. 获取事实：

   ```bash
   git status
   git diff --name-only --diff-filter=U
   git log --oneline --left-right origin/main...HEAD
   ```

2. 逐个查看冲突文件的 base、当前分支和对方版本，并阅读相关调用方、测试、类型、
   配置和近期提交。不要只看冲突标记，也不要整文件盲选 `ours` 或 `theirs`。
3. 判断两边意图：
   - `origin/main` 代表当前线上行为，除非本次功能明确替换它，否则必须保留。
   - 当前分支代表本次功能目标，不能为了消除冲突而静默删除。
   - 两边都新增有效能力时，整合接口、数据流和边界条件，让它们同时成立。
   - 测试冲突按最终产品行为更新；锁文件和生成文件使用仓库规定的工具重新生成。
4. 编辑到没有冲突标记，执行 `git add`，确认
   `git diff --name-only --diff-filter=U` 为空。
5. 运行与冲突文件相关的最小验证，再运行仓库要求的完整验证。
6. 创建合并或修复提交，继续原流程。

如果无法仅凭冲突块判断，应继续从实现、测试、调用链、提交历史和项目文档收集证据。
只有两种行为互斥且产品意图仍无法判断时才询问用户，并把选项、影响和推荐结论一次说清。

## 第 3.5 步：本地验证

根据当前改动和仓库说明，寻找已有验证命令：

1. 优先读取 `AGENTS.md`、`CONTRIBUTING.md` 和 `README.md`。
2. 再检查 `package.json`、`pyproject.toml`、`Makefile`、CI 配置等项目文件。
3. 必要时按锁文件使用项目既有包管理器安装依赖，不擅自升级依赖。
4. 先运行与改动范围直接相关的检查，再运行仓库要求的 lint、typecheck、test 或 build。
5. 找不到可信命令时，明确告知用户跳过了哪些验证以及原因，不要自行编造命令。

### 验证失败修复循环

验证失败时不要暂停，按以下循环处理：

1. 保留完整错误输出，定位第一个根因，而不是只修最后一个连锁报错。
2. 判断失败来自产品代码、测试预期、类型、格式、依赖、配置还是环境。
3. 做满足线上功能与当前功能的最小正确修复：
   - 优先使用仓库已有的 formatter 或 lint autofix，再处理剩余问题。
   - 代码缺陷修代码。
   - 测试仅在本次功能有意改变行为、原预期已经过时时更新；不得弱化、跳过或删除有效测试。
   - 环境缺少依赖时按项目锁文件恢复环境；不得借机做无关升级。
4. 先重跑失败的最小检查，再重跑全部必需检查。
5. 发现新失败就继续诊断和修复，直到全部通过。

首次 push 前产生的修复可以纳入当前提交；首次 push 后产生的修复创建新提交并正常 push，
不要为了整理历史而 force push。只要每轮都有新证据或实质进展，就继续推进，不因失败次数多而放弃。

## 第 4 步：推送并创建 PR

```bash
git push -u origin <branch-name>
```

push 被拒绝时先分类处理：

- 远端同名分支是无关内容：自动换一个唯一分支名并推送。
- 远端同名分支属于同一功能且有新提交：fetch 后合并远端分支，解决冲突、验证并再次 push。
- 网络或 GitHub 临时失败：短暂重试并检查服务恢复情况。
- 认证或写权限缺失：保留完整工作现场并请求用户完成授权。

使用 `gh pr create` 创建 PR：

- base 为 `main`
- head 为新分支
- 标题使用 commit message
- 正文包含 2–3 条 Summary、改动文件概览、验证结果和 `🤖 Shipped via git-ship`

如果 PR 已存在则复用，不重复创建。创建成功后向用户展示 PR URL，然后继续，不等待回复。

## 第 5 步：同步最新 main、限时等待检查并合并

严禁裸跑无超时的 `gh pr checks <pr-number> --watch`：第三方 Commit Status（如 Vercel Webhook）偶发丢包会让 `--watch` 无限挂起并堵死后续流程。统一使用随附脚本执行带硬超时、真实部署状态兜底、远端分支清理与 `MERGED` 强校验的闭环。

合并前先同步主分支（有新提交时推送更新）：

```bash
git fetch origin main
git merge --no-edit origin/main
```

有冲突时按“冲突处理流程”解决、重跑本地验证并 `git push`。随后运行 `<skill-dir>/scripts/wait_and_merge.py`（用户指定 `--no-squash` 时把 `--strategy squash` 换为 `--strategy merge`）：

```bash
python3 <skill-dir>/scripts/wait_and_merge.py <pr-number> --strategy squash --timeout 240
```

按脚本退出码和输出 JSON 的 `status` 分支处理：

- `0`（`MERGED`）：已确认 GitHub 远端 PR 状态为 `MERGED` 并清理同仓远端头分支，直接进入第 6 步。若 `bypassReason` 为 `vercel_ready_webhook_stale`，说明脚本已通过 Vercel CLI 核实预览部署实际为 `Ready` 并绕过了丢失的 GitHub 状态回调。
- `4` 或 `5`（`CONFLICT` / `BEHIND`）：重新 `git fetch origin main && git merge --no-edit origin/main`，解决冲突、完成验证并 `git push` 后重跑脚本。
- `6`（`CHECKS_FAILED`）：用 `gh run view --log-failed` 或部署日志读取失败根因，按“验证失败修复循环”修复并 `git push`，重跑脚本。
- `7`（`CHECKS_TIMEOUT`）：检查 GitHub Actions 队列、并发阻塞或外部平台状态；可重跑卡死任务时自行重跑后再执行一次限时等待，外部平台持续故障时向用户说明情况。
- `8`（`MERGE_NOT_COMPLETED`）：仓库启用了合并队列或异步合并，继续按短间隔核查 `gh pr view <pr-number> --json state` 直至变为 `MERGED`，严禁在 `OPEN` 状态下提前宣布完成。
- `3`（`EXTERNAL_BLOCKER`）：缺少写权限、触发分支保护必需人工审批或签名，保留现场并展示 GitHub 返回的具体原因与用户唯一待办动作。

同时发布多个仓库时，严禁用无超时命令串行阻塞后续仓库；有数据库迁移等先后依赖时，上游 PR 确认 `MERGED` 并验证迁移生效后，再执行下游仓库的合并与部署。

## 第 6 步：回到 main 并确认结果

兼容普通仓库克隆与独立 Git Worktree（次级 Worktree 中 `main` 已被主工作树检出时，不能强行 `git checkout main`）：

```bash
git fetch --prune origin main
if git checkout main 2>/dev/null; then
  git pull --ff-only origin main
  git branch -d <branch-name> 2>/dev/null || true
else
  git checkout --detach origin/main
fi
git status --short --branch
gh pr view <pr-number> --json state,mergedAt,mergeCommit,url
```

必须亲眼核对 `state` 为 `"MERGED"` 且 `mergeCommit.oid` 非空。如果本地 `main` 存在预先独有提交无法 fast-forward，保留它们不做破坏性处理，同时如实说明远端已合并与本地分支状态。

打印最终状态：

```text
🚀 Ship 完成！
  ✓ 分支 <branch-name> 已合并到 main（远端分支已清理）
  ✓ 本地验证和必需检查已通过
  ✓ 当前已同步最新 origin/main（<commit-hash>）
  ✓ PR: <pr-url>
```

## 错误处理原则

- 每步操作前简短说明正在做什么。
- 任何命令失败后先诊断、修复并重试，继续以成功合并为目标。
- 不使用 force push、`reset --hard` 或其他破坏性恢复方式。
- 主动解决冲突，并同时保护最新线上功能和当前功能目标。
- 主动修复测试、lint、类型检查、构建、提交钩子和 CI 失败。
- 不为自动推断的分支名、commit message、PR 标题、PR 正文或继续执行请求确认。
- 不把可修复的失败、需要多轮调试或流程耗时当作阻塞。
- 只有当前环境确实无法解决的外部条件才暂停；保留可继续工作的分支、提交和日志。
- 暂停时只给出明确、最小、可执行的用户动作，完成后可从原位置继续。

## 常见边界情况

| 情况 | 处理方式 |
| --- | --- |
| 当前在非 main 分支且只有工作区改动 | stash → 基于 `origin/main` 新建分支 → apply → 解决冲突 |
| 当前分支已有待发布提交 | 保留提交，合并最新 `origin/main` 后继续 |
| 没有未提交改动 | 检查相对 `origin/main` 的待发布提交；都没有才停止 |
| 分支名已存在 | 自动生成唯一后缀；同功能远端分支则复用并整合 |
| `stash apply` 或合并冲突 | 分析两边功能意图，整合实现，验证后继续 |
| lint/test/typecheck/build 失败 | 修复根因并循环验证，不把失败交给用户 |
| CI 失败 | 读取日志、本地复现、修复、push，等待新一轮 CI |
| 合并前 main 更新 | 合并最新 `origin/main`，解决冲突并重新走验证闭环 |
| `gh` 未登录 | 提示运行 `gh auth login` |
| 必需人工审批或无写权限 | 保留现场，说明唯一需要用户完成的外部动作 |
| 用户指定 `--no-squash` | 使用 `--merge` |
