# 免费无广告 Android TV M3U 播放器（含中文界面）

以下均为 **免费、无广告、开源（或免费无广告）** 的 IPTV 播放器「壳」，自身不提供任何频道源，需要配合本仓库的 M3U 列表使用。全部支持 **简体中文界面**，适合在 Android TV / Google TV / 盒子（如小米、当贝、NVIDIA Shield）上用遥控器操作。

> 安装方式：把 APK 拷到 U 盘用电视文件管理器安装，或用 `adb install xxx.apk` 侧载。
> 下列链接为本站 **`iptv.freelamp.com/apks/` 短链**，由 Cloudflare 边缘 302 跳转到各项目 **GitHub Releases 最新稳定版**（arm64-v8a 架构，适配绝大多数现代电视/盒子）。仓库本身**不托管任何二进制 APK**，链接永不过期（GitHub 每次点击即时签发下载凭证）。

| 应用 | 中文界面 | 特点 | 最新版本 | TV 版 APK 下载 |
|---|---|---|---|---|
| **M3UAndroid** | ✅ 简体中文（核心语言） | 开源 GPLv3、零广告、自适应手机/电视 UI，支持 M3U/M3U8 + Xtream + EPG + DLNA | v1.15.0 | [apks/m3uandroid.apk](https://iptv.freelamp.com/apks/m3uandroid.apk) |
| **LiteTV** | ✅ 中文原生（国产） | 超轻量（~9MB）、无追踪、ExoPlayer 直出，内置 Web 远程配置服务器，遥控器深度优化 | v1.4.0 | [apks/litetv.apk](https://iptv.freelamp.com/apks/litetv.apk) |
| **极简TV (Easy TV Live)** | ✅ 中文原生（国产） | 轻量、全平台 + 电视大屏，M3U/TXT、数字换台、远程配置推送，社区活跃 | 2.9.9 | [apks/easytv.apk](https://iptv.freelamp.com/apks/easytv.apk) |
| **我的电视 (MyTV)** | ✅ 中文原生（国产） | 国产电视直播播放器，多播放器内核（Media3/VLC/IJK）、Web 远程配置，内置多种源 | V2.2.0.219 | [apks/mytv.apk](https://iptv.freelamp.com/apks/mytv.apk) |

## 选用建议

- **想要最「原生中文 + 遥控器友好」**：LiteTV、极简TV、我的电视（均为国产项目，文档/配置全中文，支持浏览器远程配置，免去用遥控器输 URL）。
- **想要更国际化的开源精品**：M3UAndroid，自带简体中文，且同时支持手机和电视。

## 配套播放列表

- `all.m3u` 全量（中文 + 财经 + 英文新闻）：`https://iptv.freelamp.com/all.m3u`
- `china.m3u` 中文频道：`https://iptv.freelamp.com/china.m3u`
- `news.m3u` 国际财经 / 英文新闻：`https://iptv.freelamp.com/news.m3u`
- `ningbo.m3u` 宁波本地台：`https://iptv.freelamp.com/ningbo.m3u`

> 短链说明：`iptv.freelamp.com/apks/*.apk` 由 Cloudflare **Redirect Rules（302）** 转发至上游 GitHub Releases，仓库不存储 APK 文件。若某项发布新版本，只需在 Cloudflare 后台改一条规则指向即可，无需改动本仓库。

> 提示：在中国大陆直接打开 GitHub Releases（`github.com/.../releases/download/...`）通常可用；若下载缓慢或被限，可挂代理或用 Downloader 类工具输入上方链接。
