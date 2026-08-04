<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="git-ship turns working-tree changes into a reviewed squash merge through a guarded Git workflow">
</p>

<p align="center">
  <a href="./README.zh-CN.md">简体中文</a>
</p>

`git-ship` is an Agent Skill for completing the repetitive Git handoff around a finished change:

```text
working-tree snapshot → isolated worktree → commit → local checks → PR → squash merge
```

Invoking `ship` authorizes the full workflow. It automatically generates the branch name, Conventional Commit, and PR content, then runs without routine confirmation. It stops only on conflicts, failed validation, or another blocking command.

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="The seven guarded stages of the git-ship workflow">
</p>

## Why use it

- Leaves the original working tree, branch, and index untouched.
- Ships an isolated snapshot from a temporary worktree based on the latest `origin/main`.
- Uses a fresh, descriptive branch for every shipment.
- Creates a Conventional Commit and a readable pull request summary.
- Runs the repository's existing checks before anything is pushed.
- Squash-merges the PR, deletes the remote branch, and cleans up the temporary worktree.
- Stops on conflicts, missing authentication, failed checks, or ambiguous destructive actions.

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
| Inspect | Read status and diff | Stops when there is nothing to ship |
| Sync | Fetch the latest `origin/main` without switching branches | Stops when fetch fails |
| Isolate | Create a temporary worktree and apply the change snapshot | Keeps the original workspace untouched |
| Commit | Review and commit the snapshot in the temporary worktree | Stops on snapshot conflicts |
| Verify | Run documented repository checks | Never pushes failed validation |
| Publish | Push and create a PR with `gh` | Requires GitHub authentication |
| Merge | Squash, delete branch, and clean up the worktree | Never force-pushes or hard-resets |

## Requirements

- Git
- [GitHub CLI](https://cli.github.com/) authenticated with `gh auth login`
- A repository whose primary branch is `main`
- Repository validation commands documented in files such as `AGENTS.md`, `README.md`, `package.json`, `pyproject.toml`, or `Makefile`

When no trustworthy validation command exists, the Skill reports that clearly instead of inventing one.

## Safety model

Invoking `ship` is the authorization gate for the complete publishing workflow. The Skill does not ask again for routine naming decisions. It snapshots the current changes into a temporary worktree without switching branches, stashing files, or changing the original index. It stops immediately on conflicts, failed validation, missing authentication, repository protection, or command failure. It does not use force push, `reset --hard`, or automatic conflict resolution.

## Customize

Fork the repository and edit `SKILL.md` to match your team's branch naming, merge strategy, PR template, or required checks. Keep the conflict and failure gates intact when adding automation.

## Contributing

Issues and pull requests are welcome. Please keep changes focused, explain any new Git behavior, and include the failure path for every new action.

## License

[MIT](./LICENSE)
