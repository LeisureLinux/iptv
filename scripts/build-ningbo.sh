#!/usr/bin/env bash
# 【已废弃 / 一般不再需要】
#
# ningbo.m3u 现指向 Cloudflare Worker 实时签名端点，订阅永不过期，
# 不需要定期重跑。若确实要重建（如首次初始化），可执行本脚本。
#
# 保留原因：Worker 万一失效时，可由此回到「本地重签」的应急路径。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "注意：ningbo.m3u 已由 Cloudflare Worker 实时签名，通常无需重建。" >&2
python3 "$REPO_DIR/scripts/ningbo_live.py" --tv-only -o "$REPO_DIR/ningbo.m3u"
