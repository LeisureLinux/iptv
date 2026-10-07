#!/usr/bin/env bash
# 刷新宁波列表（auth_key 30 分钟过期，需定期重跑）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO_DIR/scripts/ningbo_live.py" --probe -o "$REPO_DIR/ningbo.m3u"
