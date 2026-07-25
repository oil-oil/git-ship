<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="git-ship turns working-tree changes into a reviewed squash merge through a guarded Git workflow">
</p>

<p align="center">
  <a href="./README.zh-CN.md">简体中文</a>
</p>

`git-ship` is an Agent Skill for completing the repetitive Git handoff around a finished change:

```text
working tree → latest main → new branch → commit → local checks → PR → squash merge
```

It pauses before publishing, proposes a branch name and Conventional Commit message, and stops on conflicts or failed validation.

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="The seven guarded stages of the git-ship workflow">
</p>

## Why use it

- Keeps local changes safe while synchronizing with the latest `main`.
- Uses a fresh, descriptive branch for every shipment.
- Creates a Conventional Commit and a readable pull request summary.
- Runs the repository's existing checks before anything is pushed.
- Squash-merges the PR, deletes the remote branch, and returns to an up-to-date `main`.
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

Before changing branches or publishing anything, `git-ship` shows the resolved plan:

```text
📦 Ready to ship:
  Branch: feat/add-export
  Commit: feat(export): add markdown export
  Target: main ← feat/add-export (squash merge)
```

The workflow continues only after confirmation.

## How it works

| Stage | Action | Guard |
| --- | --- | --- |
| Inspect | Read status and diff | Stops when there is nothing to ship |
| Sync | Stash tracked and untracked changes, then pull `main` | Stops when pull fails |
| Branch | Create a new branch | Stops when the name already exists |
| Commit | Restore changes and commit all files | Stops on stash conflicts |
| Verify | Run documented repository checks | Never pushes failed validation |
| Publish | Push and create a PR with `gh` | Requires GitHub authentication |
| Merge | Squash, delete branch, return to `main` | Never force-pushes or hard-resets |

## Requirements

- Git
- [GitHub CLI](https://cli.github.com/) authenticated with `gh auth login`
- A repository whose primary branch is `main`
- Repository validation commands documented in files such as `AGENTS.md`, `README.md`, `package.json`, `pyproject.toml`, or `Makefile`

When no trustworthy validation command exists, the Skill reports that clearly instead of inventing one.

## Safety model

`git-ship` treats publishing as a gated operation. It asks for confirmation before the workflow, keeps the current working tree in a temporary stash during synchronization, and stops immediately when a command fails. It does not use force push, `reset --hard`, or automatic conflict resolution.

## Customize

Fork the repository and edit `SKILL.md` to match your team's branch naming, merge strategy, PR template, or required checks. Keep the confirmation and failure gates intact when adding automation.

## Contributing

Issues and pull requests are welcome. Please keep changes focused, explain any new Git behavior, and include the failure path for every new action.

## License

[MIT](./LICENSE)
