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
import urllib.parse
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


def ua_works_without(url, timeout=12):
    """实测该地址在不带自定义 UA 时是否可用（playlist 200 且含分片）。
    许多源只是"建议"UA，实际无需——这类源应保留给 iOS/Android 通用播放器。"""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return False
            body = r.read(64 * 1024).decode("utf-8", "replace")
        # master playlist 的话再下一层
        segs = [l for l in body.splitlines() if l and not l.startswith("#")]
        if not segs:
            return False
        if segs[0].endswith(".m3u8"):
            sub = urllib.parse.urljoin(url, segs[0])
            req2 = urllib.request.Request(sub, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req2, timeout=timeout) as r2:
                b2 = r2.read(64 * 1024).decode("utf-8", "replace")
            return any(l and not l.startswith("#") for l in b2.splitlines())
        return True
    except Exception:
        return False


# 频道名校正：源列表里的名字与实际不符时在此修正
NAME_FIXUP = {
    "东方卫视4K": "东方卫视",   # 实际 1080p，非 4K
}


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
                # 带 UA 提示的源：实测无 UA 是否可用，可用则保留（iOS 端不支持自定义头）
                if ua_works_without(e["url"]):
                    e["ua"] = ""   # 清掉 UA 要求，纯直连
                    e["grp"] = (e["grp"] + " · 免UA").strip(" ·")
                    china.append(e)
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
    """宁波列表由 ningbo_live.py 生成（auth_key 会过期，需实时签名）。
    此处只做兜底：若生成失败则复制静态源文件。返回条目数。"""
    import subprocess
    gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ningbo_live.py")
    out = os.path.join(out_dir, "ningbo.m3u")
    if os.path.exists(gen):
        fm_out = os.path.join(out_dir, "fm.m3u")
        r = subprocess.run([sys.executable, gen, "--probe",
                            "-o", out, "--fm-output", fm_out],
                           capture_output=True, text=True)
        if r.returncode == 0:
            with open(out, encoding="utf-8") as fh:
                return sum(1 for l in fh if l.startswith("#EXTINF"))
        print("  警告: ningbo_live.py 生成失败, 回退静态源", file=sys.stderr)

    src = os.path.join(src_dir, "ningbo-cn.m3u")
    if not os.path.exists(src):
        print(f"  警告: 缺少 {src}", file=sys.stderr)
        return 0
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return sum(1 for l in text.splitlines() if l.startswith("#EXTINF"))


def gen_yuyao(out_dir):
    """余姚列表（点播+广播）由 yuyao_vod.py 生成。返回条目数。"""
    import subprocess
    gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yuyao_vod.py")
    out = os.path.join(out_dir, "yuyao.m3u")
    if not os.path.exists(gen):
        return 0
    r = subprocess.run([sys.executable, gen, "-o", out], capture_output=True, text=True)
    if r.returncode != 0:
        print("  警告: yuyao_vod.py 生成失败", file=sys.stderr)
        return 0
    with open(out, encoding="utf-8") as fh:
        return sum(1 for l in fh if l.startswith("#EXTINF"))


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
        e["name"] = NAME_FIXUP.get(e["name"], e["name"])
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
    yy = gen_yuyao(out_dir)
    print(f"  生成: all.m3u={len(allrows)}  china.m3u={len(china)}  news.m3u={len(news)}  ningbo.m3u={nb}  yuyao.m3u={yy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
