#!/usr/bin/env bash
# Vercel's Ignored Build Step for esp-atlas (apps/web/vercel.json `ignoreCommand`): exit 0 skips this
# deployment, exit 1 builds it (Vercel's documented contract).
#
# Why (2026-11-21): 40 production deploys in 24 h, most of them Jr's hourly bookkeeping merges
# (jr/proposed_ledger.json, docs/telemetry/). Each new deployment starts with an empty page cache ("each new
# deployment uses its own ISR cache", Vercel's ISR docs), so Googlebot kept meeting 2-4 s uncached pages
# and, by Google's own wording, held back crawling ("expected to overload the site"): 3 of the 38 firmware
# pages added in November were indexed.
#
# The rule: skip only when nothing the site is built from changed since the LAST SUCCESSFUL deployment of
# this branch (VERCEL_GIT_PREVIOUS_SHA, so a failed or skipped content change is never lost). The site is
# built from apps/web (the project's Root Directory) plus what its `vercel-build` script copies into the API
# bundle: data/, schema/, apps/core/src, apps/api/src; and the root llms.txt its /llms.txt route reads at build
# time. Every doubt builds.
set -u
top=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "ignore-build: not a git checkout: build"; exit 1; }
cd "$top" || exit 1
prev=${VERCEL_GIT_PREVIOUS_SHA:-}
if [ -z "$prev" ]; then
  echo "ignore-build: no previous successful deployment of this branch: build"
  exit 1
fi
if ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  # Vercel's clone is shallow; the last good deployment may be older than it
  git fetch --quiet --depth=1 origin "$prev" 2>/dev/null || true
fi
if ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  echo "ignore-build: cannot read the last deployed commit $prev: build"
  exit 1
fi
if git diff --quiet "$prev" HEAD -- apps/web data schema apps/core/src apps/api/src llms.txt; then
  echo "ignore-build: nothing the site is built from changed since $prev: skip"
  exit 0
fi
echo "ignore-build: the site's sources changed since $prev (or the diff failed): build"
exit 1
