#!/usr/bin/env bash
set -euo pipefail

target=${1:?usage: setup_official_webarena.sh TARGET_DIRECTORY}
commit=dce04686a56253aefba7b18a4fa0937cf1dc987b

if [[ ! -d "$target/.git" ]]; then
  git clone https://github.com/web-arena-x/webarena.git "$target"
fi
git -C "$target" fetch origin "$commit"
git -C "$target" checkout --detach "$commit"
git -C "$target" rev-parse HEAD
