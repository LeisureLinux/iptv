#!/usr/bin/env python3
"""生成财经播客列表（finance-podcast.m3u）。

来源：路透 / 华尔街日报(WSJ) / 金融时报(FT) / 彭博(Bloomberg) / 哈佛商学院(HBS/HBR)
      各播客官方 RSS 的 <enclosure> 音频直链（audio/mpeg）。

与直播列表分开：这是【音频点播】，不是电视频道。

用法:
  ./finance_podcast.py                # 生成 finance-podcast.m3u（每档取最新 15 集）
  ./finance_podcast.py --limit 30     # 每档取最新 N 集
  ./finance_podcast.py --probe        # 额外逐条探测音频可播放性（慢）
  ./finance_podcast.py --audit        # 只打印各音频主机直连/需代理，不写文件

⚠️ 网络说明（2026-10-08 实测，大陆直连）：
  · 直连可用：路透(megaphone)、WSJ(megaphone/simplecast)、HBS、HBR(audio.hbr.org)
  · 需代理  ：Bloomberg(traffic.omny.fm)、FT(sphinx.acast.com)
  生成脚本本身按「先直连，失败再走 wpad.lan:8888 代理」取 feed。
"""
import argparse
import html
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request

PROXY = "http://wpad.lan:8888"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
TIMEOUT = 30

OUT = "finance-podcast.m3u"

# (显示名, RSS 地址, 分组, 音频主机是否需代理)
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
    ("FT News Briefing", "https://rss.acast.com/ftnewsbriefing",
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

def _get(url, proxy=None, timeout=TIMEOUT):
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


def fetch(url, timeout=TIMEOUT):
    """直连优先；超时/被重置/被墙 → 走代理重试。"""
    try:
        return _get(url, None, timeout)
    except Exception as e1:
        try:
            return _get(url, PROXY, timeout)
        except http.client.IncompleteRead as e2:
            if e2.partial:
                return e2.partial
            raise RuntimeError(f"直连失败({e1}) 代理也失败({e2})")
        except Exception as e2:
            raise RuntimeError(f"直连失败({e1}) 代理也失败({e2})")


# --------------------------------------------------------------------------
# 解析 RSS：容错（FT 的 acast feed 含未转义 & 字符，标准 XML 解析器会挂）
# --------------------------------------------------------------------------

def _unescape(s):
    return html.unescape(s).strip()


def parse_items(raw):
    """返回 [(标题, 音频URL), ...]，按 feed 原始顺序（新→旧）。
    优先用标准 XML；失败则退化为正则（容忍未转义 & 等畸形）。"""
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
            title = it.findtext("title") or ""
            if url:
                items.append((_unescape(title), url))
    except Exception:
        for chunk in re.split(r"<item[\s>]", text)[1:]:
            m_u = re.search(r'<enclosure[^>]*\burl="([^"]+)"', chunk)
            m_t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", chunk, re.S)
            if m_u:
                items.append((_unescape(m_t.group(1)) if m_t else "", _unescape(m_u.group(1))))
    return items


def audio_ok(url, timeout=25):
    """探测音频直链是否可播（Range 请求，期望 200/206）。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "*/*", "Range": "bytes=0-2047"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return r.status in (200, 206)
    except Exception:
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


def eps_id(name, url):
    """稳定的 tvg-id：节目名 + 音频 URL 指纹。"""
    import hashlib
    return "PC-" + hashlib.sha1((name + url).encode()).hexdigest()[:12]


def build(out_path, limit, probe=False, audit=False):
    blocks, total, proxied = [], 0, []
    for name, feed, grp, needs_proxy in SHOWS:
        try:
            items = parse_items(fetch(feed))
        except Exception as e:
            print(f"  ⚠️  {name}: 取 feed 失败 — {e}", file=sys.stderr)
            continue
        items = items[:limit]
        print(f"  {name}: {len(items)} 集")
        lines = [f"# ===== {name} ====="]
        for title, url in items:
            if probe and not audio_ok(url):
                print(f"      ✗ 探测失败，跳过: {title[:50]}", file=sys.stderr)
                continue
            t = esc(title) or "(无标题)"
            lines.append(
                f'#EXTINF:-1 tvg-id="{eps_id(name, url)}" '
                f'tvg-name="{esc(name)}" group-title="{grp}",{esc(name)}: {t}')
            lines.append(url)
            total += 1
            if needs_proxy and host_of(url) not in proxied:
                proxied.append(host_of(url))
        blocks.append("\n".join(lines))

    if audit:
        return

    header = [
        "#EXTM3U",
        "# 财经播客（音频点播）—— 路透 / WSJ / FT / Bloomberg / 哈佛商学院",
        "# FreeLAMP.com (LeisureLinux) | 仅聚合各播客官方公开 RSS，不提供、不托管任何内容",
        "# 由 scripts/finance_podcast.py 自动生成；音频为各节目 enclosure 直链（audio/mpeg）",
        "#",
        "# ⚠️ 网络说明（实测）：路透 / WSJ / HBS / HBR 大陆可直连；",
        "#    标 [需代理] 的两组（Bloomberg=omny 、FT=acast）大陆直连超时，需走代理/VPN。",
        "",
    ]
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n")
    print(f"\n  ✅ 写入 {out_path}：{total} 集")
    if proxied:
        print(f"  ⚠️  需代理的主机: {', '.join(sorted(proxied))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15, help="每档取最新 N 集（默认 15）")
    ap.add_argument("--probe", action="store_true", help="逐条探测音频可播放性（慢）")
    ap.add_argument("--audit", action="store_true", help="只审计不写文件")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    build(out_path, args.limit, args.probe, args.audit)


if __name__ == "__main__":
    main()
