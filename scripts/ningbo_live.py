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
# 电视（直播）
CHANNELS = [
    ("nbtv1", "宁波新闻综合", "宁波 · 电视"),
    ("nbtv2", "宁波经济生活", "宁波 · 电视"),
    ("nbtv3", "宁波都市文体", "宁波 · 电视"),
    ("nbtv4", "宁波影视剧",   "宁波 · 电视"),
]

# 广播（FM）—— 独立成表，见 gen_fm()，写入 fm.m3u
#
# 频率映射经维基百科「宁波广播电视集团」与去听网双源核对：
#   FM92.0  综合广播（新闻）—— 1953 年，宁波第一个广播频率
#   FM102.9 经济广播（财经）
#   FM93.9  交通广播（路况/驾车）
#   FM98.6  音乐广播
# 注：早期版本把 92.0 与 102.9 的名称写反了，此处已修正。
FM_CHANNELS = [
    ("fm920",  "宁波新闻综合广播 FM92.0",  "宁波 · FM"),
    ("fm1029", "宁波经济广播 FM102.9",     "宁波 · FM"),
    ("fm939",  "宁波交通广播 FM93.9",      "宁波 · FM"),
    ("fm986",  "宁波音乐广播 FM98.6",      "宁波 · FM"),
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


def build(channels, title, header_lines, probe_them):
    """生成 m3u 文本 + 条目数"""
    lines = ["#EXTM3U"] + header_lines + [""]
    ok = 0
    for ch, name, grp in channels:
        url = get_live(ch)
        if not url:
            print(f"  ✗ {name} ({ch}) 未返回地址")
            continue
        if probe_them and not probe(url):
            print(f"  ✗ {name} ({ch}) 分片不可用")
            continue
        lines += [
            f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}',
            url,
        ]
        ok += 1
        print(f"  ✓ {name} ({ch})")
    return "\n".join(lines).rstrip("\n") + "\n", ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="生成前验证每条可用性")
    ap.add_argument("--tv-only", action="store_true", help="只生成电视表")
    ap.add_argument("--fm-only", action="store_true", help="只生成 FM 表")
    ap.add_argument("-o", "--output", default="ningbo.m3u", help="电视表输出路径")
    ap.add_argument("--fm-output", default="fm.m3u", help="FM 表输出路径")
    args = ap.parse_args()

    TV_HDR = [
        "# 宁波电视台（直播）—— 由 scripts/ningbo_live.py 自动生成",
        "# 源：宁波广电 App「宁聚」公开 CMS 接口 (cms.nj.nbtv.cn)",
        "# auth_key 有效期约 30 分钟 —— Orange Pi cron 每 15 分钟自动刷新。",
    ]
    FM_HDR = [
        "# 调频广播（FM）—— 由 scripts/ningbo_live.py 自动生成",
        "# 源：宁波广电 App「宁聚」公开 CMS 接口 (cms.nj.nbtv.cn)",
        "# auth_key 有效期约 30 分钟 —— Orange Pi cron 每 15 分钟自动刷新。",
        "#",
        "# 宁波人民广播电台 4 个频率（经维基百科 + 去听网双源核对）：",
        "#   FM92.0  综合广播（新闻）   FM102.9 经济广播",
        "#   FM93.9  交通广播           FM98.6  音乐广播",
    ]

    rc = 0
    if not args.fm_only:
        text, ok = build(CHANNELS, "TV", TV_HDR, args.probe)
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"\n生成 {args.output}：{ok}/{len(CHANNELS)} 条")
        rc = rc or (0 if ok else 1)

    if not args.tv_only:
        text, ok = build(FM_CHANNELS, "FM", FM_HDR, args.probe)
        with open(args.fm_output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"生成 {args.fm_output}：{ok}/{len(FM_CHANNELS)} 条")
        rc = rc or (0 if ok else 1)

    return rc


if __name__ == "__main__":
    sys.exit(main())
