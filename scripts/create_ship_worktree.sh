#!/usr/bin/env bash

set -euo pipefail

branch_name="${1:-}"

if [[ -z "$branch_name" ]]; then
  echo "用法：create_ship_worktree.sh <branch-name>" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
source_head="$(git -C "$repo_root" rev-parse HEAD)"
skill_tmp_root="${TMPDIR:-/tmp}"
patch_file="$(mktemp "$skill_tmp_root/git-ship-patch.XXXXXX")"
untracked_file="$(mktemp "$skill_tmp_root/git-ship-untracked.XXXXXX")"
worktree_path="$(mktemp -d "$skill_tmp_root/git-ship-worktree.XXXXXX")"
rmdir "$worktree_path"

cleanup_snapshot_files() {
  rm -f "$patch_file" "$untracked_file"
}

trap cleanup_snapshot_files EXIT

if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
  echo "本地分支已存在：$branch_name" >&2
  exit 3
fi

if git -C "$repo_root" show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
  echo "远端分支已存在：origin/$branch_name" >&2
  exit 3
fi

if git -C "$repo_root" ls-remote \
  --exit-code \
  --heads \
  origin \
  "$branch_name" >/dev/null 2>&1; then
  echo "远端分支已存在：origin/$branch_name" >&2
  exit 3
fi

if ! git -C "$repo_root" rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "找不到 origin/main，请先执行 git fetch origin main" >&2
  exit 4
fi

git -C "$repo_root" diff \
  --binary \
  --full-index \
  "$source_head" \
  -- . >"$patch_file"

git -C "$repo_root" ls-files \
  --others \
  --exclude-standard \
  -z >"$untracked_file"

if [[ ! -s "$patch_file" && ! -s "$untracked_file" ]]; then
  echo "没有检测到未提交改动" >&2
  exit 5
fi

git -C "$repo_root" worktree add \
  -b "$branch_name" \
  "$worktree_path" \
  origin/main >/dev/null

if [[ -s "$patch_file" ]]; then
  if ! git -C "$worktree_path" apply --3way --index "$patch_file"; then
    echo "应用已跟踪改动时发生冲突。" >&2
    echo "隔离 worktree 已保留：$worktree_path" >&2
    exit 6
  fi
fi

while IFS= read -r -d '' relative_path; do
  source_path="$repo_root/$relative_path"
  target_path="$worktree_path/$relative_path"

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    echo "未跟踪文件与最新 main 冲突：$relative_path" >&2
    echo "隔离 worktree 已保留：$worktree_path" >&2
    exit 7
  fi

  mkdir -p "$(dirname "$target_path")"
  cp -pP "$source_path" "$target_path"
done <"$untracked_file"

git -C "$worktree_path" add -A

if git -C "$worktree_path" diff --cached --quiet; then
  echo "快照应用后没有可提交改动。" >&2
  echo "隔离 worktree 已保留：$worktree_path" >&2
  exit 8
fi

printf '%s\n' "$worktree_path"
