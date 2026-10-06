#!/usr/bin/env bash
# 从源播放列表目录生成面向 iOS/Android 的通用 m3u 文件。
#
#   ./scripts/build.sh           生成 all.m3u / china.m3u / news.m3u
#   ./scripts/build.sh --check   仅校验现有文件的格式合规性
#
# 环境变量:
#   SRC_DIR   源列表目录 (默认 ~/iptv-playlists)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${SRC_DIR:-$HOME/iptv-playlists}"
MODE="${1:-build}"

if [[ "$MODE" == "--check" ]]; then
    exec python3 "$REPO_DIR/scripts/validate.py" "$REPO_DIR"
fi

if [[ ! -d "$SRC_DIR" ]]; then
    echo "错误: 源目录不存在: $SRC_DIR" >&2
    echo "可用 SRC_DIR=/path/to/playlists $0 指定" >&2
    exit 1
fi

echo "源目录: $SRC_DIR"
python3 "$REPO_DIR/scripts/make.py" "$SRC_DIR" "$REPO_DIR"
echo
echo "--- 校验生成结果 ---"
python3 "$REPO_DIR/scripts/validate.py" "$REPO_DIR"
