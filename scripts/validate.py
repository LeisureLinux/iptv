#!/usr/bin/env python3
"""校验 m3u 文件的 iOS/Android 兼容性。

用法: validate.py <目录> [文件名...]
退出码: 0=全部通过, 1=有错误
"""
import os
import re
import sys

CHECK_FILES = ["all.m3u", "china.m3u", "news.m3u"]
HTTP_RE = re.compile(r"^https?://")
BAD_PROTO_RE = re.compile(r"^(rtmp|rtsp|udp|rtp|mms|ftp)://", re.I)
IPV6_LITERAL_RE = re.compile(r"^https?://\[")
MAX_LINE = 2000


def check(path):
    """返回 (errors, warnings, stats)"""
    errors, warnings = [], []
    raw = open(path, "rb").read()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return [f"非 UTF-8 编码: {e}"], [], {}

    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("文件含 UTF-8 BOM（部分播放器会解析失败）")
    if b"\r\n" in raw:
        errors.append("含 CRLF 行尾（应为 LF）")

    lines = text.splitlines()
    if not lines:
        return ["文件为空"], [], {}
    if lines[0].strip() != "#EXTM3U":
        errors.append(f"首行必须是 #EXTM3U，实际为 {lines[0][:40]!r}")

    extinf = [l for l in lines if l.startswith("#EXTINF")]
    urls = [l for l in lines if HTTP_RE.match(l)]
    bad_proto = [l for l in lines if BAD_PROTO_RE.match(l)]
    ipv6_lit = [l for l in lines if IPV6_LITERAL_RE.match(l)]
    long_lines = [l for l in lines if len(l) > MAX_LINE]
    ua_lines = [l for l in lines if "http-user-agent" in l.lower()]

    if len(extinf) != len(urls):
        errors.append(f"#EXTINF({len(extinf)}) 与 URL({len(urls)}) 数量不匹配")
    if bad_proto:
        errors.append(f"含 iOS/Android 不支持的非 HTTP 协议 {len(bad_proto)} 条")
    if ua_lines:
        errors.append(f"含自定义 User-Agent 行 {len(ua_lines)} 条（iOS 端不支持）")
    if ipv6_lit:
        warnings.append(f"含 IPv6 字面量 URL {len(ipv6_lit)} 条（仅 IPv4 环境不可用）")
    if long_lines:
        warnings.append(f"含超长行 {len(long_lines)} 条（>{MAX_LINE} 字符）")

    # 检查每条 EXTINF 是否紧跟 URL
    orphan = 0
    for i, l in enumerate(lines):
        if l.startswith("#EXTINF"):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not (HTTP_RE.match(nxt) or nxt.startswith("#EXTVLCOPT")):
                orphan += 1
    if orphan:
        errors.append(f"有 {orphan} 条 #EXTINF 后面没跟 URL")

    stats = {
        "条目": len(extinf),
        "分组数": len({re.search(r'group-title="([^"]*)"', l).group(1)
                       for l in extinf
                       if re.search(r'group-title="([^"]*)"', l)}),
        "HTTPS": sum(1 for u in urls if u.startswith("https://")),
        "大小": f"{len(raw) / 1024:.0f} KB",
    }
    return errors, warnings, stats


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    targets = sys.argv[2:] or CHECK_FILES

    failed = False
    for name in targets:
        path = os.path.join(root, name)
        print(f"\n=== {name} ===")
        if not os.path.exists(path):
            print("  ❌ 文件不存在")
            failed = True
            continue
        errors, warnings, stats = check(path)
        info = "  ".join(f"{k}={v}" for k, v in stats.items())
        print(f"  {info}")
        for e in errors:
            print(f"  ❌ {e}")
        for w in warnings:
            print(f"  ⚠️  {w}")
        if errors:
            failed = True
        elif warnings:
            print("  ✅ 通过（有警告）")
        else:
            print("  ✅ 完全合规")

    print()
    print("校验结果:", "❌ 存在问题" if failed else "✅ 全部通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
