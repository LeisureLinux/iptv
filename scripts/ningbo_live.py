#!/usr/bin/env python3
"""生成宁波电视台(NBTV1-4) 与宁波 FM 播放列表。

⚠️ ningbo.m3u（电视）已改为指向 Cloudflare Worker 的实时签名端点
   （https://iptv.freelamp.com/live/<ch>.m3u8），订阅地址永不过期，
   【不需要也不能用本脚本重新生成】—— 重跑只会把文件头覆盖成旧说明。
   本脚本现在只用于生成 fm.m3u（--fm-only）。

背景：早期 CBC 接口返回的 auth_key 仅 30 分钟有效，故需 cron 定期重签。
     改用 Worker 实时签名后，签名在请求时完成，cron 已无必要（已移除）。

用法:
  ./ningbo_live.py --fm-only   # 生成 fm.m3u（当前唯一用途）
  ./ningbo_live.py             # 生成 ningbo.m3u + fm.m3u（niche，一般不跑）
"""
import argparse, hashlib, json, subprocess, sys, urllib.parse, urllib.request

API = "https://cms.nj.nbtv.cn/"
UA = "Mozilla/5.0 (Linux; Android 13) okhttp/4.9.0"

# channelName -> (显示名, 分组)
# 电视（直播）
CHANNELS = [
    # (流ID, 显示名, 分组, tvg-id, tvg-logo)
    ("nbtv1", "宁波新闻综合", "宁波 · 电视", "NBTV1.cn", ""),
    ("nbtv2", "宁波经济生活", "宁波 · 电视", "NBTV2.cn", ""),
    ("nbtv3", "宁波都市文体", "宁波 · 电视", "NBTV3.cn", ""),
    ("nbtv4", "宁波影视剧",   "宁波 · 电视", "NBTV4.cn", ""),
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
    ("fm920",  "宁波新闻综合广播 FM92.0",  "宁波 · FM", "NBTV-FM920",  ""),
    ("fm1029", "宁波经济广播 FM102.9",     "宁波 · FM", "NBTV-FM1029", ""),
    ("fm939",  "宁波交通广播 FM93.9",      "宁波 · FM", "NBTV-FM939",  ""),
    ("fm986",  "宁波音乐广播 FM98.6",      "宁波 · FM", "NBTV-FM986",  ""),
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


def probe(url: str, timeout: float = 8.0) -> bool:
    """拉 playlist 并确认有分片（.ts 或下级 .m3u8）。
    注意：只用于宁波本地源（响应快）；城市 FM 是静态长期源，不做探测
    —— 21 条国外流逐个探测会拖慢数分钟并导致 cron 超时。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(64 * 1024).decode("utf-8", "replace")
        for l in body.splitlines():
            l = l.strip()
            if l and not l.startswith("#") and (".ts" in l or ".m3u8" in l):
                return True
        return False
    except Exception:
        return False



# 城市 FM（上海/北京/广州/成都 + 旧金山/纽约/温哥华/珀斯/悉尼）
# 数据来自 ~/iptv-playlists/fm-cities.txt（格式：名称|URL），为无需签名的长期源。
FM_CITIES_FILE = "fm-cities.txt"


def load_city_fm(src_dir=None):
    """读取城市 FM 静态源。格式：分组|名称|URL（兼容旧的两字段 名称|URL）。
    返回 [(分组, 名称, url)]"""
    import os
    d = src_dir or os.environ.get("SRC_DIR") or os.path.expanduser("~/iptv-playlists")
    path = os.path.join(d, FM_CITIES_FILE)
    if not os.path.exists(path):
        print(f"  警告: 缺少 {path}", file=sys.stderr)
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [x.strip() for x in ln.split("|")]
            if len(parts) >= 3:
                out.append((parts[0], parts[1], parts[2]))
            elif len(parts) == 2:
                out.append(("城市 · FM", parts[0], parts[1]))
    return out


def build_city_fm(src_dir=None, probe_them=False):
    """生成城市 FM 段落"""
    items = load_city_fm(src_dir)
    lines, ok = [], 0
    for grp, name, url in items:
        if probe_them and not probe(url):
            print(f"  ✗ {name}")
            continue
        # tvg-id 必须唯一非空：部分 App 以它为键建索引，全空会把多台塌缩成 1 台
        # tvg-id 用名称的稳定哈希，保证唯一且不含特殊字符
        tid = "FM-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
        lines += [f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{name}" '
                  f'group-title="{grp}",{name}', url]
        ok += 1
    return lines, ok


def build(channels, title, header_lines, probe_them):
    """生成 m3u 文本 + 条目数"""
    lines = ["#EXTM3U"] + header_lines + [""]
    ok = 0
    for item in channels:
        ch, name, grp = item[0], item[1], item[2]
        tvgid = item[3] if len(item) > 3 else ""
        logo = item[4] if len(item) > 4 else ""
        # 宁波本地频道改走 Cloudflare Worker 实时签名端点（永不过期）；
        # ch 形如 nbtv1 / fm920，与 Worker 的频道键一致。
        if ch in ("nbtv1", "nbtv2", "nbtv3", "nbtv4") or ch.startswith("fm"):
            url = f"https://iptv.freelamp.com/live/{ch}.m3u8"
        else:
            url = get_live(ch)
            if not url:
                print(f"  ✗ {name} ({ch}) 未返回地址")
                continue
            url = url.replace("http://", "https://", 1)
        if probe_them and not url.startswith("https://iptv.freelamp.com/"):
            if not probe(url):
                print(f"  ✗ {name} ({ch}) 分片不可用")
                continue
        # tvg-id 必须唯一非空：部分 App 以 tvg-id 为键建索引，
        # 若全为空字符串会把多个频道塌缩成 1 个（实测 4 台→1 台）。
        parts = ["#EXTINF:-1"]
        if tvgid:
            parts.append(f'tvg-id="{tvgid}"')
        parts.append(f'tvg-name="{name}"')
        if logo:
            parts.append(f'tvg-logo="{logo}"')
        parts.append(f'group-title="{grp}"')
        lines += [" ".join(parts) + f",{name}", url]
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
    ap.add_argument("--src-dir", default=None, help="源目录（含 fm-cities.txt）")
    args = ap.parse_args()

    TV_HDR = [
        "# 宁波电视台（直播）—— 由 Cloudflare Worker 实时签名",
        "#",
        "# 本文件是「指令列表」：地址指向 Worker 的实时签名端点，",
        "# 由 Worker 在每次请求时向宁波广电接口取新的 auth_key。",
        "#",
        "# 因此：",
        "#   · 订阅地址永不过期（不再有 30 分钟限制）",
        "#   · 不需要任何定时刷新任务",
        "#   · 不依赖自建主机（纯 Cloudflare）",
        "#",
        "# 广播（FM）见 fm.m3u；实现详见 ~/codex/nbtv-worker/worker.js",
    ]
    FM_HDR = [
        "# 调频广播（FM）—— 由 scripts/ningbo_live.py 自动生成",
        "#",
        "# 一、宁波本地 4 个频率",
        "#   源：宁波广电 App「宁聚」公开 CMS 接口 (cms.nj.nbtv.cn)",
        "#   本文件为指令列表：宁波频道指向 Worker 实时签名端点，永不过期。",
        "#   FM92.0 综合广播（新闻）  FM102.9 经济广播",
        "#   FM93.9 交通广播          FM98.6  音乐广播",
        "#",
        "# 二、城市 FM（上海/北京/广州/成都 + 旧金山/纽约/温哥华/珀斯/悉尼）",
        "#   源：见 ~/iptv-playlists/fm-cities.txt（公开直连，无需签名）",
        "#   国内每城最多 5、国外每城最多 3（均为主流电台）",
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
        # 城市 FM 为静态长期源，不逐条探测（会拖慢 cron 并超时）
        city_lines, city_ok = build_city_fm(args.src_dir, probe_them=False)
        if city_lines:
            text = text.rstrip("\n") + "\n\n# ===== 城市 FM（上海/北京/广州/成都/旧金山/纽约/温哥华/珀斯/悉尼）=====\n"
            text += "\n".join(city_lines) + "\n"
        with open(args.fm_output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        total = ok + city_ok
        print(f"生成 {args.fm_output}：{total} 条（宁波 {ok} + 城市 {city_ok}）")
        rc = rc or (0 if total else 1)

    return rc


if __name__ == "__main__":
    sys.exit(main())
