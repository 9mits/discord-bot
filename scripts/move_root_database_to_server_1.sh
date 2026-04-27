#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p servers/server-1/database

shopt -s nullglob
files=(database/*)

if (( ${#files[@]} == 0 )); then
  echo "No files found in root database/. Nothing to move."
  exit 0
fi

for path in "${files[@]}"; do
  name="$(basename "$path")"
  if [[ -e "servers/server-1/database/$name" ]]; then
    echo "Refusing to overwrite servers/server-1/database/$name"
    exit 1
  fi
done

mv "${files[@]}" servers/server-1/database/
echo "Moved root database files into servers/server-1/database/."
