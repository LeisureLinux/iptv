#!/usr/bin/env python3
"""生成宁波电视台(NBTV1-4)可用播放列表。

原理：宁波广电 App「宁聚」(com.cutv.ningbo) 的公开 CMS 接口
  https://cms.nj.nbtv.cn/?task=get-live&channelName=<ch>
会返回带 auth_key 签名的直播地址。auth_key 有效期约 30 分钟，
因此本脚本动态获取并写入 m3u。

用法:
  ./ningbo_live.py            # 生成 ningbo.m3u
  ./ningbo_live.py --probe    # 先探测各频道可用性再生成
"""
import argparse, json, subprocess, sys, urllib.parse, urllib.request

API = "https://cms.nj.nbtv.cn/"
UA = "Mozilla/5.0 (Linux; Android 13) okhttp/4.9.0"

# channelName -> (显示名, 分组)
CHANNELS = [
    ("nbtv1", "宁波新闻综合", "宁波 · 电视"),
    ("nbtv2", "宁波经济生活", "宁波 · 电视"),
    ("nbtv3", "宁波都市文体", "宁波 · 电视"),
    ("nbtv4", "宁波影视剧",   "宁波 · 电视"),
    ("fm1029", "宁波新闻广播 FM102.9", "宁波 · 广播"),
    ("fm920",  "宁波经济广播 FM92.0",  "宁波 · 广播"),
    ("fm939",  "宁波交通广播 FM93.9",  "宁波 · 广播"),
    ("fm986",  "宁波音乐广播 FM98.6",  "宁波 · 广播"),
]


def get_live(ch: str):
    """调用 CMS 接口取签名直播地址；失败返回 None"""
    qs = urllib.parse.urlencode({"task": "get-live", "channelName": ch})
    req = urllib.request.Request(API + "?" + qs, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        return d.get("liveUrl") or None
    except Exception as e:
        print(f"    获取失败 {ch}: {e}", file=sys.stderr)
        return None


def probe(url: str) -> bool:
    """拉 playlist 并确认有分片"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
        return any(l and not l.startswith("#") and ".ts" in l for l in body.splitlines())
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="生成前验证每条可用性")
    ap.add_argument("-o", "--output", default="ningbo.m3u")
    args = ap.parse_args()

    lines = [
        "#EXTM3U",
        "# 宁波电视台 —— 由 scripts/ningbo_live.py 自动生成",
        "# 源：宁波广电 App「宁聚」公开 CMS 接口 (cms.nj.nbtv.cn)",
        "# auth_key 有效期约 30 分钟 —— 重新运行本脚本即可刷新。",
        "",
    ]
    ok = 0
    for ch, name, grp in CHANNELS:
        url = get_live(ch)
        if not url:
            print(f"  ✗ {name} ({ch}) 未返回地址")
            continue
        if args.probe and not probe(url):
            print(f"  ✗ {name} ({ch}) 分片不可用")
            continue
        lines += [
            f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}',
            url,
        ]
        ok += 1
        print(f"  ✓ {name} ({ch})")

    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    print(f"\n生成 {args.output}：{ok}/{len(CHANNELS)} 条")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
