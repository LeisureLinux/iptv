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
                    "tvgid": attrs.get("tvg-id", ""),
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


def tidy_name(n):
    """清理显示名：去掉 [Geo-blocked]/[Not 24/7]/（备注）等杂质"""
    n = re.sub(r"\[[^\]]*\]", "", n)          # [Geo-blocked] [Not 24/7]
    n = re.sub(r"（[^）]*(替代|备注)[^）]*）", "", n)  # （MSNBC 免费替代）
    n = re.sub(r"\([^)]*\)$", "", n)
    return n.strip(" -·")



# ── 语言分类 ──────────────────────────────────────────────
# 目标：english.m3u 只保留【英语】频道。
# 判据优先级：显式非英语关键词 > 显式英语关键词 > 国家/地区默认语言。
#
# 非英语（按名称关键词剔除）：这些台虽可能带英文名，但播出语言非英语
NON_ENGLISH_KEYWORDS = [
    "arabiya", "arabic", "العربية",          # 阿拉伯语
    "sky news arabia",                       # 阿语台（名字里带 sky news，易误判）
    "marathi", "kannada", "tamil", "telugu",  # 印度地方语言
    "hindi", "awaaz", "bajar", "zee ",        # 印地语
    "madhya pradesh", "chhattisgarh",         # NDTV 地方版（印地语）
    "rajasthan", "uttar pradesh", "bihar",    # NDTV 地方版
    "gujarat", "punjab", "bengal",            # 地方版
    "kannada", "malayalam",                   # 南印度语言
    "spanish", "español", "espanol",          # 西班牙语
    "português", "portuguese",                # 葡萄牙语
    "français", "french", "bfm business",     # 法语
    "deutsch", "german",                      # 德语
    "russian", "русский", "rt doc",           # 俄语
    "turkish", "cnbc-e",                      # 土耳其语
    "mongolia", "mongolian",                  # 蒙古语
    "atameken",                               # 哈萨克语
    "中文", "汉语",                            # 汉语
    "quran", "islamic",                       # 宗教/阿语
]

# 明确英语（即使来源国非英语国家）
ENGLISH_MARKERS = [
    "english", "news live", "news now",
    "sky news", "gb news", "fox news", "cnbc", "bloomberg",
    "al jazeera english", "cna", "wion", "arirang", "dw english",
    "france 24 english", "reuters", "yahoo",
    # 明确的国际英文台（名字里没有 "english" 但确为英语播出）
    "abc news", "cbc news", "wild earth", "trace sports",
    "arirang", "channel news asia",
]

# 允许列入 english.m3u 的国家/地区来源（英文广播为主）
ENGLISH_REGIONS = {
    "美国", "英国", "加拿大", "澳大利亚", "新西兰", "爱尔兰",
    "南非", "新加坡", "国际", "印度", "菲律宾", "肯尼亚", "尼日利亚",
}



# 按用户要求整体排除的地区（印度台）
EXCLUDE_REGIONS = ["印度"]

# 按名称排除（这些是印度台，或与其它台重复）
EXCLUDE_NAMES = [
    "wion", "wionews",           # 印度 WION
    "ndtv",                      # 印度 NDTV
    "republic tv",               # 印度 Republic
    "cnbc tv18",                 # 印度 CNBC（区别于 CNBC US/UK）
    "zee business",              # 印度 Zee
    "cnbc awaaz", "cnbc bajar",  # 印度 CNBC 地方语言
]


def is_excluded(e):
    """用户指定排除的频道（印度台等）"""
    text = (e.get("name", "") + " " + e.get("grp", "")).lower()
    for r in EXCLUDE_REGIONS:
        if r in e.get("grp", ""):
            return True
    for kw in EXCLUDE_NAMES:
        if kw in text:
            return True
    return False


# 中文/港澳台标识：这些属于 china.m3u，不算"外国台"
CHINESE_MARKERS = ["央视频道", "卫视", "· suxuang", "芒果", "港澳", "中文",
                   "春晚", "电视剧", "虎牙", "动画频道", "地方频道", "数字频道",
                   "4K频道", ".cn@"]


def is_foreign(e):
    """判断是否为外国（非中文）频道"""
    grp = e.get("grp", "")
    # 明确的国际/英文/财经/新闻分类 → 外国
    if any(k in grp for k in ("国际频道", "英文新闻", "财经", "新闻 ·")):
        return True
    # 港澳台属中文区，不算外国
    if "港澳" in grp:
        return False
    # iptv-org 分组基本都是中国台（.cn）
    return False


def is_english(e):
    """判断该频道是否以英语播出（用于 english.m3u）"""
    text = (e.get("name", "") + " " + e.get("grp", "")).lower()

    # 1) 显式非英语 → 排除
    for kw in NON_ENGLISH_KEYWORDS:
        if kw in text:
            return False

    # 2) 显式英语标记 → 通过
    for kw in ENGLISH_MARKERS:
        if kw in text:
            return True

    # 3) 按地区判断（形如 "英文新闻 · 美国 · Fox · 直连" / "新闻 · 国际 · 直连"）
    m = re.search(r"·\s*([^·]+?)\s*·", e.get("grp", ""))
    if m and m.group(1).strip() in ENGLISH_REGIONS:
        return True

    # 4) "国际频道" 组：该组混有各语种，非英语已在第 1 步剔除，
    #    走到这里说明没命中非英语关键词，视为英语
    if "国际频道" in e.get("grp", ""):
        return True

    return False


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

    # 外国频道池 = news(财经/英文新闻) + china 里的「国际频道」组
    foreign = list(news) + [e for e in china if is_foreign(e)]
    foreign = [e for e in foreign if e not in news] + list(news)
    # english.m3u = 外国台中纯英语的
    english = prefer_one_per_channel(
        [e for e in foreign if is_english(e) and not is_excluded(e)])

    return china, news, english


def copy_ningbo(src_dir, out_dir):
    """ningbo.m3u 指向 Cloudflare Worker 的实时签名端点
    （https://iptv.freelamp.com/live/<ch>.m3u8），订阅地址永不过期，
    因此【不需要任何定时刷新】—— 只校验文件存在与格式。

    历史：曾由 ningbo_live.py 定时重签（auth_key 仅 30 分钟有效），
    依赖 Orange Pi cron；Worker 实时签名上线后二者均已停用。
    """
    out = os.path.join(out_dir, "ningbo.m3u")
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            return sum(1 for l in fh if l.startswith("#EXTINF"))
    print(f"  警告: 缺少 {out}", file=sys.stderr)
    return 0


def gen_fm(out_dir):
    """fm.m3u：宁波 4 个 FM 已改走 Worker 实时签名（永不过期），
    21 个城市 FM 是静态源 —— 故本表实际也不需要刷新，
    保留生成步骤仅为初始化/应急重建用。"""
    import subprocess
    gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ningbo_live.py")
    out = os.path.join(out_dir, "fm.m3u")
    if not os.path.exists(gen):
        return 0
    r = subprocess.run([sys.executable, gen, "--fm-only", "--probe", "--fm-output", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  警告: fm 生成失败", file=sys.stderr)
        return 0
    with open(out, encoding="utf-8") as fh:
        return sum(1 for l in fh if l.startswith("#EXTINF"))


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


def gen_finance_podcast(out_dir):
    """财经播客（路透/WSJ/FT/Bloomberg/HBS）由 finance_podcast.py 生成。
    依赖外网 RSS，失败时保留已有文件、不阻断整体构建。返回条目数。"""
    import subprocess
    gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finance_podcast.py")
    out = os.path.join(out_dir, "finance-podcast.m3u")
    if not os.path.exists(gen):
        return 0
    r = subprocess.run([sys.executable, gen, "--out", out], capture_output=True, text=True)
    if r.returncode != 0:
        print("  警告: finance_podcast.py 生成失败（保留原有文件）", file=sys.stderr)
        if not os.path.exists(out):
            return 0
    with open(out, encoding="utf-8") as fh:
        return sum(1 for l in fh if l.startswith("#EXTINF"))


def prefer_one_per_channel(rows):
    """同一频道有多个源时只保留 votes/位置最靠前的一个。
    归一化名称：去 HD/竖屏/Not24/7 等后缀、去空格与括号。"""
    def norm(n):
        n = re.sub(r"[（(].*?[)）]", "", n)
        n = re.sub(r"\[.*?\]", "", n)
        n = re.sub(r"\b(HD|SD|FHD|UHD|4K|Vertical|Extra\s*\d+|TV|Channel)\b",
                   "", n, flags=re.I)
        return re.sub(r"[\s_\-]+", "", n).lower()

    seen, out = {}, []
    for e in rows:
        k = norm(e["name"])
        if k in seen:
            continue
        seen[k] = True
        out.append(e)
    return out


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
    """按分组名、频道名排序（分组名做自然排序，让 CCTV-2 在 CCTV-10 前面）"""
    def natkey(t):
        return [int(p) if p.isdigit() else p.lower()
                for p in re.split(r"(\d+)", t or "")]

    rows = sorted(rows, key=lambda x: (natkey(clean_group(x["grp"])), natkey(x["name"])))
    lines = [
        "#EXTM3U",
        f"# {title}",
        "# FreeLAMP.com (LeisureLinux) | 仅聚合公开列表, 不提供任何内容 | 源会随时失效",
        "# iOS / Android 通用: 纯 URL 直连, 不依赖自定义请求头",
        "",
    ]
    for e in rows:
        e["name"] = tidy_name(NAME_FIXUP.get(e["name"], e["name"]))
        parts = ["#EXTINF:-1"]
        # tvg-id 优先（多数 App 用它做主键与 EPG 匹配）；
        # 源里没有 tvg-id 时，用名称哈希兜底生成 —— 绝不能留空：
        # 空 tvg-id 会让按它建索引的 App 把多个频道塌缩成 1 个。
        tid = e.get("tvgid") or ""
        if not tid:
            import hashlib as _h
            _n = e.get("tvg") or e.get("name") or ""
            tid = "H-" + _h.md5(_n.encode("utf-8")).hexdigest()[:12]
        if tid:
            parts.append(f'tvg-id="{tidy_name(tid)}"')
        if e["tvg"]:
            parts.append(f'tvg-name="{tidy_name(e["tvg"])}"')
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

    china, news, english = load_entries(src_dir)
    china, news, english = dedupe(china), dedupe(news), dedupe(english)
    allrows = dedupe(china + news)

    write(os.path.join(out_dir, "china.m3u"),
          render(china, "中文频道 (iOS / Android 通用)"))
    write(os.path.join(out_dir, "news.m3u"),
          render(news, "外国频道 (含各语种)"))
    write(os.path.join(out_dir, "english.m3u"),
          render(english, "国外英语频道 (English only)"))
    write(os.path.join(out_dir, "all.m3u"),
          render(allrows, "全量 (中文 + 外国频道)"))

    nb = copy_ningbo(src_dir, out_dir)
    fm = gen_fm(out_dir)
    yy = gen_yuyao(out_dir)
    pc = gen_finance_podcast(out_dir)
    print(f"  生成: all.m3u={len(allrows)}  china.m3u={len(china)}  "
          f"news.m3u={len(news)}  english.m3u={len(english)}  "
          f"ningbo.m3u={nb}  fm.m3u={fm}  yuyao.m3u={yy}  "
          f"finance-podcast.m3u={pc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
