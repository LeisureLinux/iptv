#!/usr/bin/env python3
"""生成余姚点播/广播列表（yuyao.m3u）。

与 ningbo.m3u 分开：宁波是直播，余姚是【点播 + 广播】。

数据来源（均为余姚市融媒体中心公开页面）：
  · 点播：姚界 App 的「看电视」栏目 Nuxt SSR 页面
      https://vapp.tmuyun.com/webChannels/normal?id=628eebd357851f04b87b49a3&tenantId=50
    页面内嵌 window.__NUXT__，含 标题 + 封面 + mp4 地址（720p H.264/AAC）。
  · 广播：余姚新闻网「听广播」入口（趣看 quklive）
      https://www.qukanvideo.com/h5/w/getPlayUrl?id=1709282355347178
    auth_key 约 30 分钟过期，故每次运行都重新取。

⚠️ 已知限制：
  · 点播 mp4 位于 mc-public.yynews.com.cn（腾讯 EdgeOne WAF）
    - 正常播放器（VLC / mpv / FredTV）可直接播放
    - curl 会被 WAF 拦（567），故本脚本用玩家 UA 做探测
    - 高频请求会触发限流，探测时务必限速

用法:
  ./yuyao_vod.py                 # 生成 yuyao.m3u（不逐条探测，快）
  ./yuyao_vod.py --probe         # 逐条探测可用性（慢，且可能触发限流）
  ./yuyao_vod.py --limit 10      # 只取最近 N 条
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request

TV_PAGE = ("https://vapp.tmuyun.com/webChannels/normal"
           "?id=628eebd357851f04b87b49a3&tenantId=50")
RADIO_API = "https://www.qukanvideo.com/h5/w/getPlayUrl?id=1709282355347178"

# 用播放器 UA，避免被 EdgeOne 当成爬虫拦截
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36"
UA_PLAYER = "VLC/3.0.20 LibVLC/3.0.20"


def fetch(url, ua=UA, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_vod():
    """解析「看电视」页面的 NUXT 数据，返回 [(标题, mp4url, 时长秒, 大小字节)]"""
    html = fetch(TV_PAGE).decode("utf-8", "replace")
    s = html.replace("\\u002F", "/")
    pat = re.compile(
        r',(\d{8}),"([^"]{4,100})",'
        r'"(https?://[^"]+\.(?:jpeg|jpg|png)[^"]*)",'
        r'"(https?://[^"]+\.mp4[^"]*)"'
    )
    out = []
    for _aid, title, _cover, url in pat.findall(s):
        dur = re.search(r"duration=([\d.]+)", url)
        size = re.search(r"fsize=(\d+)", url)
        out.append((
            title.strip(),
            url,
            float(dur.group(1)) if dur else 0.0,
            int(size.group(1)) if size else 0,
        ))
    return out


def get_radio():
    """取余姚广播（仅音频）的签名直播地址"""
    try:
        d = json.loads(fetch(RADIO_API, timeout=20))
        return d.get("value") or None
    except Exception as e:
        print(f"  广播地址获取失败: {e}", file=sys.stderr)
        return None


def probe(url, timeout=20):
    """用播放器 UA 探测，确认返回 200（避免高频，调用方负责 sleep）"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_PLAYER, "Accept": "*/*", "Range": "bytes=0-2047",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def fmt_dur(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="逐条探测（慢，可能触发限流）")
    ap.add_argument("--limit", type=int, default=0, help="只取最近 N 条")
    ap.add_argument("-o", "--output", default="yuyao.m3u")
    args = ap.parse_args()

    print("拉取余姚点播列表…")
    try:
        vod = get_vod()
    except Exception as e:
        print(f"  失败: {e}", file=sys.stderr)
        return 1
    if args.limit:
        vod = vod[: args.limit]
    print(f"  点播 {len(vod)} 条")

    radio = get_radio()
    print(f"  广播 {'已获取' if radio else '获取失败'}")

    lines = [
        "#EXTM3U",
        "# 余姚 —— 点播 + 广播（由 scripts/yuyao_vod.py 自动生成）",
        "# 来源：余姚市融媒体中心（姚界 App / 余姚新闻网）",
        "#",
        "# 说明：这不是直播台。余姚电视台无公开直播源，此处为节目点播 + 广播直播。",
        "# 主列表见 ningbo.m3u（宁波市台直播）。",
        "",
    ]

    if radio:
        lines += [
            "# ===== 广播（直播，仅音频）=====",
            "# auth_key 约 30 分钟过期，重跑本脚本刷新",
            '#EXTINF:-1 tvg-name="余姚广播" group-title="余姚 · 广播",余姚广播',
            radio,
            "",
        ]

    lines += ["# ===== 节目点播（姚界「看电视」栏目）====="]
    ok = 0
    for title, url, dur, size in vod:
        if args.probe:
            if not probe(url):
                print(f"  ✗ {title}")
                time.sleep(2)          # 限速，避免触发 EdgeOne
                continue
            time.sleep(2)
        mb = size / 1048576 if size else 0
        label = f"{title} ({fmt_dur(dur)}, {mb:.0f}MB)" if dur else title
        # 点播条目：用 vod 分组，便于播放器区分
        lines += [
            f'#EXTINF:-1 tvg-name="{title}" group-title="余姚 · 点播",{label}',
            url,
        ]
        ok += 1
        if args.probe:
            print(f"  ✓ {title}")

    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")

    total = ok + (1 if radio else 0)
    print(f"\n生成 {args.output}：{total} 条（点播 {ok} + 广播 {1 if radio else 0}）")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
