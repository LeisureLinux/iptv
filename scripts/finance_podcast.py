#!/usr/bin/env python3
"""生成财经播客列表（finance-podcast.m3u）。

来源：路透 / 华尔街日报(WSJ) / 金融时报(FT) / 彭博(Bloomberg) / 经济学人(The Economist)
      CNBC / 巴伦周刊(Barron's) / 哈佛商学院(HBS/HBR)
      各播客官方 RSS 的 <enclosure> 音频直链（audio/mpeg）。

与直播列表分开：这是【音频点播】，不是电视频道。

用法:
  ./finance_podcast.py                # 生成 finance-podcast.m3u（每档取最新 12 集）
  ./finance_podcast.py --limit 30     # 每档取最新 N 集
  ./finance_podcast.py --probe        # 额外逐条探测音频可播放性（慢）
  ./finance_podcast.py --list         # 只打印各节目状态（最新日期/条数），不写文件

每集标题一律带日期前缀 [YYYY-MM-DD]，否则同名节目（如 Reuters/CNBC 的日更）
在播放器里看起来完全一样。

⚠️ 网络说明（2026-10-08 实测，大陆直连）：
  · 直连可用：路透(megaphone)、WSJ、HBS、HBR(audio.hbr.org)、
              CNBC(podtrac)、Barron's(dowjones.simplecastaudio)
  · 需代理  ：Bloomberg(traffic.omny.fm)、FT 与 The Economist(sphinx.acast.com)
  生成脚本本身按「先直连，失败再走 wpad.lan:8888 代理」取 feed。
"""
import argparse
import email.utils
import hashlib
import html
import http.client
import os
import re
import sys
import urllib.request

# 代理可用环境变量覆盖：GitHub Actions 跑在美国，直连即可达 acast/omny，
# 不需要（也访问不到）内网 wpad.lan。设 FPA_PROXY= 空值即完全禁用代理。
PROXY = os.environ.get("FPA_PROXY", "http://wpad.lan:8888").strip() or None
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
# 分档超时：直连快速失败（被墙的 6~7s 内就断），代理给足（FT 的 11MB feed 需 ~40s）
TIMEOUT_DIRECT = 12
TIMEOUT_PROXY = 75
TIMEOUT_SMALL = 25   # 探测音频直链用
WORKERS = 8          # 并发取 feed 数
# 安全闸：只有「真的取失败」才启用。若某次抓取失败过多、条数不足预期的 60%，
# 宁可不写、保留上一版，避免 cron 在供应商抖动时把好文件写成残缺版。
MIN_RATIO = 0.6

OUT = "finance-podcast.m3u"

# (显示名, RSS 地址, 分组, 是否需代理)
SHOWS = [
    # ---- 路透 Reuters ----
    ("Reuters World News", "https://feeds.megaphone.fm/reutersworldnews",
     "播客 · 路透 Reuters", False),

    # ---- 华尔街日报 WSJ ----
    ("WSJ The Journal", "https://video-api.wsj.com/podcast/rss/wsj/the-journal",
     "播客 · WSJ 华尔街日报", False),
    ("WSJ What's News", "https://feeds.simplecast.com/BA5QWI2p",
     "播客 · WSJ 华尔街日报", False),
    ("WSJ Tech News Briefing", "https://feeds.simplecast.com/ui_HbBma",
     "播客 · WSJ 华尔街日报", False),
    ("WSJ Take On the Week", "https://feeds.simplecast.com/4LDzav57",
     "播客 · WSJ 华尔街日报", False),

    # ---- 金融时报 FT ----
    # 注：rss.acast.com 在本机 DNS 无法解析（getent 无结果），改用 feeds.acast.com 形式
    ("FT News Briefing", "https://feeds.acast.com/public/shows/73fe3ede-5c5c-4850-96a8-30db8dbae8bf",
     "播客 · FT 金融时报 [需代理]", True),

    # ---- 彭博 Bloomberg ----
    ("Bloomberg Big Take", "https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1"
                           "/825d4e29-b616-46f4-afd7-ae2b0013005c/8b1dd624-a026-43e9-8b57-ae2b00130066/podcast.rss",
     "播客 · Bloomberg 彭博 [需代理]", True),
    ("Bloomberg Odd Lots", "https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1"
                           "/8A94442E-5A74-4FA2-8B8D-AE27003A8D6B/982F5071-765C-403D-969D-AE27003A8D83/podcast.rss",
     "播客 · Bloomberg 彭博 [需代理]", True),
    ("Bloomberg Surveillance", "https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1"
                               "/8e704079-ca57-4eac-9741-ae27003e2b7f/9739700c-72c3-4176-ae55-ae27003e2b96/podcast.rss",
     "播客 · Bloomberg 彭博 [需代理]", True),

    # ---- 经济学人 The Economist ----
    # 注：Money Talks / Checks and Balance 两个独立 feed 已停更（正片分别停在
    #     2025-04 / 2024-11，2026 年只剩 trailer），故不收录；其内容已并入
    #     The Intelligence 与综合 feed。
    ("The Economist: The Intelligence", "https://access.acast.com/rss/d556eb54-6160-4c85-95f4-47d9f5216c49",
     "播客 · The Economist 经济学人 [需代理]", True),
    ("The Economist: 综合（各栏目）", "https://access.acast.com/rss/ec380acc-fe13-46a0-991f-a1e508d126f8",
     "播客 · The Economist 经济学人 [需代理]", True),

    # ---- CNBC ----
    ("CNBC Mad Money", "https://feeds.simplecast.com/TkQfZXMD",
     "播客 · CNBC", False),
    ("CNBC Fast Money", "https://feeds.simplecast.com/szW8tJ16",
     "播客 · CNBC", False),
    ("CNBC Closing Bell", "https://feeds.simplecast.com/Nh1wIaXT",
     "播客 · CNBC", False),
    ("CNBC Power Lunch", "https://feeds.simplecast.com/_qvRgwME",
     "播客 · CNBC", False),
    ("CNBC Squawk on the Street", "https://feeds.simplecast.com/GcylmXl7",
     "播客 · CNBC", False),
    ("CNBC Halftime Report", "https://feeds.simplecast.com/qltQrd_8",
     "播客 · CNBC", False),
    ("CNBC Worldwide Exchange", "https://feeds.simplecast.com/Bt3ITxGl",
     "播客 · CNBC", False),
    ("CNBC The Exchange", "https://feeds.simplecast.com/tc4zxWgX",
     "播客 · CNBC", False),

    # ---- 巴伦周刊 Barron's ----
    ("Barron's Streetwise", "https://video-api.barrons.com/podcast/rss/barrons/streetwise",
     "播客 · Barron's 巴伦周刊", False),
    ("Barron's Live", "https://video-api.barrons.com/podcast/rss/barrons/barrons-live",
     "播客 · Barron's 巴伦周刊", False),
    ("Barron's Advisor", "https://video-api.barrons.com/podcast/rss/barrons/barrons-advisor",
     "播客 · Barron's 巴伦周刊", False),

    # ---- 哈佛 HBS / HBR ----
    ("HBR IdeaCast", "http://feeds.harvardbusiness.org/harvardbusiness/ideacast",
     "播客 · 哈佛商学院 HBS", False),
    ("HBS Cold Call", "http://feeds.harvardbusiness.org/harvardbusiness/cold-call",
     "播客 · 哈佛商学院 HBS", False),
    ("HBS Managing the Future of Work", "https://feeds.megaphone.fm/TPG2056865494",
     "播客 · 哈佛商学院 HBS", False),
]


# --------------------------------------------------------------------------
# 取数据：先直连，失败再走代理（遵循 AGENTS.md 网络宪法）
# --------------------------------------------------------------------------

def _get(url, proxy=None, timeout=TIMEOUT_DIRECT):
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy \
        else [urllib.request.ProxyHandler({})]
    opener = urllib.request.build_opener(*handlers)
    # 不要 gzip：否则大 feed 经代理易被截断成 IncompleteRead
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"})
    with opener.open(req, timeout=timeout) as r:
        try:
            return r.read()
        except http.client.IncompleteRead as e:
            # 已收到的部分常常已包含最新若干集，够用
            if e.partial:
                print(f"      (响应被截断，使用已收到的 {len(e.partial)} 字节)", file=sys.stderr)
                return e.partial
            raise


def fetch(url, tries=2, proxy_only=False):
    """先直连（短超时、快速失败），不通再走代理（长超时）。
    proxy_only=True 时直接走代理——被墙的源（acast/omny）在大陆直连必然超时，
    跳过可省下每次十几秒的无谓等待。
    但若未配置代理（如 GitHub Actions 跑在美国，直连即可达），
    则忽略 proxy_only 提示，一律直连，否则会白等超时。"""
    last = None
    if not proxy_only or not PROXY:
        for _ in range(tries):
            try:
                return _get(url, None, TIMEOUT_DIRECT)
            except http.client.IncompleteRead as e:
                if e.partial:
                    return e.partial
                last = e
            except Exception as e:
                last = e
        # 无代理可用时，直连是唯一出路，把直连超时放宽再试一轮
        # （美国 runner 拉 FT 的 11MB feed 可能超过 12s）
        if not PROXY:
            try:
                return _get(url, None, TIMEOUT_PROXY)
            except http.client.IncompleteRead as e:
                if e.partial:
                    return e.partial
                last = e
            except Exception as e:
                last = e
            raise RuntimeError(f"直连失败（无代理可用）: {last}")
    for _ in range(tries):
        try:
            return _get(url, PROXY, TIMEOUT_PROXY)
        except http.client.IncompleteRead as e:
            if e.partial:
                return e.partial
            last = e
        except Exception as e:
            last = e
    raise RuntimeError(f"取 feed 失败（各 {tries} 次）: {last}")


# --------------------------------------------------------------------------
# 解析 RSS：容错（acast 的 feed 含未转义 & 字符，标准 XML 解析器会挂）
# --------------------------------------------------------------------------

def _unescape(s):
    return html.unescape(s).strip()


def _pubdate(chunk):
    m = re.search(r"<pubDate>([^<]+)</pubDate>", chunk)
    if not m:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(m.group(1).strip())
        return dt.date()
    except Exception:
        return None


def parse_items(raw):
    """返回 [(日期, 标题, 音频URL), ...]，按 feed 原始顺序（新→旧）。
    优先标准 XML；失败则退化为正则（容忍未转义 & 等畸形）。"""
    text = raw.decode("utf-8", "replace")
    items = []
    try:
        import xml.etree.ElementTree as ET
        ch = ET.fromstring(text).find("channel")
        if ch is None:
            raise ValueError("no channel")
        for it in ch.findall("item"):
            enc = it.find("enclosure")
            url = enc.get("url") if enc is not None else None
            if not url:
                continue
            pd = it.findtext("pubDate")
            try:
                d = email.utils.parsedate_to_datetime(pd.strip()).date() if pd else None
            except Exception:
                d = None
            items.append((d, _unescape(it.findtext("title") or ""), url))
        if not items:
            raise ValueError("no enclosure in xml path")
    except Exception:
        items = []
        for chunk in re.split(r"<item[\s>]", text)[1:]:
            m_u = re.search(r'<enclosure[^>]*\burl="([^"]+)"', chunk)
            if not m_u:
                continue
            m_t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", chunk, re.S)
            items.append((_pubdate(chunk),
                          _unescape(m_t.group(1)) if m_t else "",
                          _unescape(m_u.group(1))))
    return items


def audio_ok(url, timeout=TIMEOUT_SMALL):
    """探测音频直链是否可播（Range 请求，期望 200/206）。
    先直连；若配了代理且直连失败，再用代理试（大陆环境下 omny/acast 必需）。"""
    for proxy in ([None, PROXY] if PROXY else [None]):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*", "Range": "bytes=0-2047"})
            ph = {"http": proxy, "https": proxy} if proxy else {}
            opener = urllib.request.build_opener(urllib.request.ProxyHandler(ph))
            with opener.open(req, timeout=timeout) as r:
                if r.status in (200, 206):
                    return True
        except Exception:
            continue
    return False


def host_of(url):
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def esc(s):
    """标题清洗：去掉会干扰 m3u 解析的字符（ASCII 逗号→全角，收窄空白）。"""
    s = re.sub(r"\s+", " ", s or "").strip()
    return s.replace(",", "，").replace('"', "'")


TRAILER_RE = re.compile(r"^\s*(trailer|teaser|preview)\b|:\s*(trailer|teaser)\b", re.I)


def eps_id(name, url):
    """稳定的 tvg-id：节目名 + 音频 URL 指纹。"""
    return "PC-" + hashlib.sha1((name + url).encode()).hexdigest()[:12]


def build(out_path, limit, probe=False, listing=False):
    import concurrent.futures as cf

    def load(show):
        name, feed, grp, needs_proxy = show
        try:
            return show, parse_items(fetch(feed, proxy_only=needs_proxy)), None
        except Exception as e:
            return show, [], e

    blocks, total, proxied, rows = [], 0, [], []
    # 并发取 feed（串行时被墙的节目各卡 60s+，总耗时会到十几分钟）
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(load, SHOWS))

    for (name, feed, grp, needs_proxy), items, err in results:
        if err is not None:
            print(f"  ⚠️  {name}: 取 feed 失败 — {err}", file=sys.stderr)
            continue
        # 去掉 trailer/预告（无收听价值，且常把正片挤掉）
        items = [x for x in items if not TRAILER_RE.search(x[1] or "")]
        items = items[:limit]
        newest = next((d for d, _, _ in items if d), None)
        rows.append((name, len(items), newest))
        lines = [f"# ===== {name} ====="]
        for d, title, url in items:
            if probe and not audio_ok(url):
                print(f"      ✗ 探测失败，跳过: {title[:50]}", file=sys.stderr)
                continue
            t = esc(title) or "(无标题)"
            # 日期前缀：否则日更节目（Reuters/CNBC）在播放器里标题全一样
            label = f"{name}: [{d.isoformat()}] {t}" if d else f"{name}: {t}"
            lines.append(
                f'#EXTINF:-1 tvg-id="{eps_id(name, url)}" '
                f'tvg-name="{esc(name)}" group-title="{grp}",{esc(label)}')
            lines.append(url)
            total += 1
            if needs_proxy and host_of(url) not in proxied:
                proxied.append(host_of(url))
        blocks.append("\n".join(lines))

    if listing:
        print(f"\n{'节目':38s} {'集数':>4s}  最新")
        for n, c, d in rows:
            print(f"  {n:36s} {c:4d}  {d or '?'}")
        print(f"\n  合计 {total} 集（limit={limit}）")
        return

    # 安全闸：仅当真的抓取失败、且条数明显不足时才拒绝写入
    # （limit 小是用户自选，不算异常；失败才是异常）
    failed = len(SHOWS) - len(rows)
    expected = limit * len(SHOWS)
    if failed and total < expected * MIN_RATIO:
        print(f"  ❌ 仅取到 {total} 集（预期 {expected}，{failed}/{len(SHOWS)} 档失败），"
              f"低于 {MIN_RATIO:.0%} 下限，保留原文件不覆盖", file=sys.stderr)
        return 1

    header = [
        "#EXTM3U",
        "# 财经播客（音频点播）—— 路透 / WSJ / FT / Bloomberg / 经济学人 / CNBC / Barron's / 哈佛商学院",
        "# FreeLAMP.com (LeisureLinux) | 仅聚合各播客官方公开 RSS，不提供、不托管任何内容",
        "# 由 scripts/finance_podcast.py 自动生成；音频为各节目 enclosure 直链（audio/mpeg）",
        "# 每集标题格式：节目名: [YYYY-MM-DD] 单集标题",
        "#",
        "# ⚠️ 网络说明（实测）：路透 / WSJ / HBS / HBR / CNBC / Barron's 大陆可直连；",
        "#    标 [需代理] 的两组（Bloomberg=omny、FT 与经济学人=acast）大陆直连超时，需走代理/VPN。",
        "#",
        "",
    ]
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n")
    print(f"\n  ✅ 写入 {out_path}：{total} 集（{len(rows)}/{len(SHOWS)} 档）")
    if failed:
        print(f"  ⚠️  {failed} 档失败，已跳过", file=sys.stderr)
    if proxied:
        print(f"  ⚠️  需代理的主机: {', '.join(sorted(proxied))}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12, help="每档取最新 N 集（默认 12）")
    ap.add_argument("--probe", action="store_true", help="逐条探测音频可播放性（慢）")
    ap.add_argument("--list", dest="listing", action="store_true",
                    help="只打印各节目状态（最新日期/条数），不写文件")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    return build(out_path, args.limit, args.probe, args.listing)


if __name__ == "__main__":
    sys.exit(main())
