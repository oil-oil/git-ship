<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="git-ship 通过带安全检查的 Git 工作流，把工作区改动送进 main">
</p>

<p align="center">
  <a href="./README.md">English</a>
</p>

`git-ship` 是一个 Agent Skill，用来完成改动写完之后那段重复的 Git 流程：

```text
工作区改动 → 最新 main → 新分支 → commit → 本地验证 → PR → squash merge
```

它会先给出分支名和 Conventional Commit 建议，得到确认后才发布；遇到冲突或验证失败会立即停止。

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="git-ship 七个带安全检查的工作阶段">
</p>

## 它解决什么问题

- 同步最新 `main` 时，先妥善暂存当前改动。
- 每次发布都使用新的语义化分支。
- 自动生成 Conventional Commit 和清楚的 PR 摘要。
- 推送前运行目标仓库已经定义好的检查。
- PR squash 合并后删除远端分支，并回到最新 `main`。
- 遇到冲突、未登录、验证失败或高风险歧义时立即停止。

## 安装

把仓库克隆到 Agent 能发现 Skill 的目录：

```bash
git clone https://github.com/oil-oil/git-ship.git ~/.agents/skills/git-ship
```

如果你的客户端使用其他 Skill 目录，请克隆到对应位置。真正的入口文件是 `SKILL.md`。

## 使用

完成改动并保留在工作区，然后告诉 Agent：

```text
ship
```

也可以提前指定分支和 commit：

```text
把这次改动 ship 为 feat/add-export，commit 用 "feat(export): add markdown export"
```

切换分支和发布之前，`git-ship` 会先展示最终方案：

```text
📦 准备 ship：
  分支名：feat/add-export
  Commit：feat(export): add markdown export
  目标：main ← feat/add-export（squash merge）
```

只有得到确认后，流程才会继续。

## 工作流程

| 阶段 | 动作 | 安全检查 |
| --- | --- | --- |
| 检查 | 读取 status 和 diff | 没有改动时停止 |
| 同步 | stash 已跟踪和未跟踪改动，再拉取 `main` | pull 失败时停止 |
| 分支 | 创建新分支 | 分支名已存在时停止 |
| 提交 | 恢复改动并提交全部文件 | stash 冲突时停止 |
| 验证 | 运行仓库已有检查 | 验证失败绝不推送 |
| 发布 | push 并通过 `gh` 创建 PR | 需要完成 GitHub 登录 |
| 合并 | squash、删分支、回到 `main` | 不使用强推或硬重置 |

## 运行要求

- Git
- 已通过 `gh auth login` 登录的 [GitHub CLI](https://cli.github.com/)
- 主分支为 `main` 的 Git 仓库
- 在 `AGENTS.md`、`README.md`、`package.json`、`pyproject.toml` 或 `Makefile` 等文件中记录验证命令

如果找不到可信的验证命令，Skill 会明确说明跳过，不会自行猜测。

## 安全边界

`git-ship` 把发布视为需要确认的操作。它会在流程开始前等待确认，同步主分支时用临时 stash 保护工作区，并在任何命令失败时立刻停止。它不会使用 force push、`reset --hard` 或自动解决冲突。

## 自定义

你可以 fork 仓库并修改 `SKILL.md`，接入团队自己的分支命名、合并策略、PR 模板或必跑检查。增加自动化时，建议保留确认和失败停止机制。

## 参与贡献

欢迎提交 Issue 和 PR。请保持改动聚焦，说明新增的 Git 行为，并为每个新增动作写清楚失败处理。

## 开源协议

[MIT](./LICENSE)
