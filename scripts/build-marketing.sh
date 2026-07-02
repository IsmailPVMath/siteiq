#!/usr/bin/env bash
# Build static marketing site for Cloudflare Pages (pvmath.com).
# Copies only public website files — not api/, frontend/, pages/, etc.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/website-dist"

rm -rf "$OUT"
mkdir -p "$OUT"

for f in index.html impressum.html privacy.html terms.html sitemap.xml; do
  cp "$ROOT/$f" "$OUT/"
done

for d in assets services guides; do
  cp -R "$ROOT/$d" "$OUT/"
done

count="$(find "$OUT" -type f | wc -l | tr -d ' ')"
echo "Marketing site built → website-dist/ ($count files)"
