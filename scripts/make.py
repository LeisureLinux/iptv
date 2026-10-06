#!/usr/bin/env python3
"""从源播放列表生成 iOS/Android 通用 m3u。

用法: make.py <源目录> <输出目录>

筛选规则:
  1. 剔除依赖自定义 User-Agent 的条目  (iOS 端 IPTV 应用普遍不支持自定义请求头)
  2. 剔除标记为「需代理」的条目        (大陆直连不通)
  3. 仅保留 http:// / https:// 协议
  4. 按 名称+URL 去重
"""
import os
import re
import sys

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
UA_LINE_RE = re.compile(r"http-user-agent=(\S+)")

# 芒果官方 CDN: 实测无需任何 UA, 直接可用(4K)
MANGOCDN = ("http://hlsal-ldvt.qing.mgtv.com/nn_live/nn_x64/"
            "dWlwPTEyNy4wLjAuMSZ1aWQ9cWluZy1jbXMmbm5fdGltZXpvbmU9OCZjZG5leF9pZD1hbF9obHNfbGR2"
            "dCZ1dWlkPTliODY4NmU5ZTM2YzYwMmMmZT02OTE0NjA0JnY9MSZpZD1ITldTWkdTVCZzPTcwN2RiYTc2"
            "YzJjNmJmMTQ4MmUyZGYzOWU2NWM3YWFi/HNWSZGST.m3u8")


def parse(path):
    """解析 m3u -> list[dict]"""
    out, cur = [], None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            ln = raw.rstrip("\r\n")
            if ln.startswith("#EXTINF"):
                attrs = dict(ATTR_RE.findall(ln))
                cur = {
                    "name": ln.split(",")[-1].strip(),
                    "grp": attrs.get("group-title", ""),
                    "logo": attrs.get("tvg-logo", ""),
                    "tvg": attrs.get("tvg-name", "") or attrs.get("tvg-id", ""),
                    "ua": attrs.get("http-user-agent", ""),
                }
            elif ln.startswith("#EXTVLCOPT"):
                m = UA_LINE_RE.search(ln)
                if m and cur:
                    cur["ua"] = m.group(1)
            elif ln.startswith("http") and cur:
                cur["url"] = ln
                out.append(cur)
                cur = None
    return out


def clean_group(g):
    """去掉 (直连)/(需代理) 之类的标注"""
    return re.sub(r"\s*[（(](直连|需代理|proxy|direct)[)）]", "", g).strip()


def is_proxy_only(e):
    return "需代理" in e["grp"]


def load_entries(src_dir):
    """返回 (china 候选, news 候选)，均为已剔除 UA / 需代理 的条目"""
    china, news = [], []

    # 中文
    p = os.path.join(src_dir, "verified-CN.m3u")
    if os.path.exists(p):
        for e in parse(p):
            if e["ua"]:
                continue
            china.append(e)
    else:
        print(f"  警告: 缺少 {p}", file=sys.stderr)

    # 芒果 4K (用无需 UA 的 CDN 地址)
    china.append({
        "name": "湖南卫视 4K",
        "grp": "芒果/湖南",
        "logo": "https://parco-zh.github.io/demo/HNWS.png",
        "tvg": "湖南卫视",
        "ua": "",
        "url": MANGOCDN,
    })

    # 财经 + 英文新闻 (仅直连)
    for fn in ("finance-news.m3u", "english-news.m3u"):
        p = os.path.join(src_dir, fn)
        if not os.path.exists(p):
            print(f"  警告: 缺少 {p}", file=sys.stderr)
            continue
        for e in parse(p):
            if e["ua"] or is_proxy_only(e):
                continue
            news.append(e)

    return china, news


def copy_ningbo(src_dir, out_dir):
    """宁波列表含特殊分档注释, 直接复制不重写"""
    src = os.path.join(src_dir, "ningbo-cn.m3u")
    if not os.path.exists(src):
        print(f"  警告: 缺少 {src}", file=sys.stderr)
        return 0
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    with open(os.path.join(out_dir, "ningbo.m3u"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return sum(1 for l in text.splitlines() if l.startswith("#EXTINF"))


def dedupe(rows):
    seen, out = set(), []
    for e in rows:
        k = (e["name"], e["url"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def render(rows, title):
    rows = sorted(rows, key=lambda x: (clean_group(x["grp"]), x["name"]))
    lines = [
        "#EXTM3U",
        f"# {title}",
        "# FreeLAMP.com (LeisureLinux) | 仅聚合公开列表, 不提供任何内容 | 源会随时失效",
        "# iOS / Android 通用: 纯 URL 直连, 不依赖自定义请求头",
        "",
    ]
    for e in rows:
        parts = ["#EXTINF:-1"]
        if e["tvg"]:
            parts.append(f'tvg-name="{e["tvg"]}"')
        if e["logo"]:
            parts.append(f'tvg-logo="{e["logo"]}"')
        parts.append(f'group-title="{clean_group(e["grp"])}"')
        lines.append(" ".join(parts) + f',{e["name"]}')
        lines.append(e["url"])
    return "\n".join(lines).rstrip("\n") + "\n"


def write(path, text):
    # newline="\n" 确保 LF, encoding utf-8 无 BOM
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src_dir, out_dir = sys.argv[1], sys.argv[2]

    china, news = load_entries(src_dir)
    china, news = dedupe(china), dedupe(news)
    allrows = dedupe(china + news)

    write(os.path.join(out_dir, "china.m3u"),
          render(china, "中文频道 (iOS / Android 通用)"))
    write(os.path.join(out_dir, "news.m3u"),
          render(news, "国际财经 / 英文新闻 (iOS / Android 通用)"))
    write(os.path.join(out_dir, "all.m3u"),
          render(allrows, "全量 (中文 + 财经 + 英文新闻)"))

    nb = copy_ningbo(src_dir, out_dir)
    print(f"  生成: all.m3u={len(allrows)}  china.m3u={len(china)}  news.m3u={len(news)}  ningbo.m3u={nb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
