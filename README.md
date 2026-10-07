# IPTV Playlists

面向 **iOS / Android 通用** 的 IPTV 播放列表（M3U）。

全部条目均为 **纯 URL 直连、不依赖自定义请求头** —— iOS 端主流 IPTV 应用普遍不支持自定义 User-Agent，因此本仓库在生成时已剔除所有依赖 UA 的源。

## 订阅地址

```
https://iptv.freelamp.com/all.m3u       全量（中文 + 财经 + 英文新闻）
https://iptv.freelamp.com/china.m3u     中文频道
https://iptv.freelamp.com/news.m3u      国际财经 / 英文新闻
https://iptv.freelamp.com/ningbo.m3u    宁波本地台
```

## 播放器 APK（免费 / 无广告 / 中文界面）

本仓库只提供播放列表，不含播放器。Android TV 上可用的 **免费、无广告、带简体中文界面** 的 M3U 播放器（含 GitHub Releases 最新 APK 下载），见：

👉 **[apks.md](apks.md)** — 4 款推荐：M3UAndroid、LiteTV、极简TV、我的电视

## 包含内容

| 文件 | 条目 | 说明 |
|---|---|---|
| `all.m3u` | ~258 | 全量，日常用这一个即可 |
| `china.m3u` | ~205 | 央视、卫视、省市台、少儿动画等 |
| `news.m3u` | ~52 | CNBC / Bloomberg / Fox News / NDTV / DW / France 24 / Sky News 等 |
| `ningbo.m3u` | 15 | 宁波本地台（象山 1080p/720p + 余姚广播 + 失效参考，分档标注） |

## 为什么不用 `raw.githubusercontent.com`

**在中国大陆，`raw.githubusercontent.com` 不可直连**（连接超时／被重置）。而且以下地址最终都会 302 跳转到它，因此同样不可用：

- `github.com/<user>/<repo>/raw/...`
- `cdn.jsdelivr.net/gh/<user>/<repo>@<ref>/...`

实测只有 **GitHub Pages（`*.github.io`）** 在国内可直连且带有效 HTTPS 证书，所以本仓库通过 Pages 发布。

> 如果你的环境访问 `github.io` 也有问题，可自建反代，或使用 `Orange Pi + nginx` 之类自托管方案。

## iOS / Android 兼容性

生成时强制保证：

- 首行为 `#EXTM3U`
- 行尾为 **LF**（不使用 CRLF）
- **UTF-8 无 BOM**
- 每条 `#EXTINF` 与 URL 严格配对
- 仅保留 `http://` / `https://`（剔除 rtmp / rtsp / udp / rtp / mms）
- 无 IPv6 字面量 URL（避免仅 IPv4 环境不可用）
- 无超长行

## 更新

```bash
./scripts/build.sh              # 从 ~/iptv-playlists 重新生成三个列表
./scripts/build.sh --check      # 仅校验现有文件格式合规性（不写入）
```

脚本会自动完成：剔除依赖 UA 的条目 → 剔除需代理的条目 → 去重 → 格式化 → 输出报告。

来源目录可用环境变量覆盖：

```bash
SRC_DIR=/path/to/playlists ./scripts/build.sh
```

## 免责声明

- 本仓库**只聚合公开可访问的播放列表**，不提供、不托管、不销售任何频道、内容或订阅。
- 所有流地址均来自公开来源，版权归各自权利人所有。
- 列表中的源**随时可能失效**（免费公开源属正常现象），本仓库不保证长期可用。
- 请自行确认在你的所在地使用这些流是否符合当地法律法规。

Maintained by [FreeLAMP.com](https://freelamp.com) · [LeisureLinux](https://github.com/LeisureLinux)
