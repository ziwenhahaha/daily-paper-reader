# 前端第三方静态依赖

这些文件用于替代首屏加载时的 CDN 请求，避免 GitHub Pages 或本地部署受外部 CDN 延迟影响。

当前固定版本：

- Docsify `4`
- KaTeX `0.16.9`
- js-yaml `4.1.0`
- libsodium `0.7.10`
- libsodium-wrappers `0.7.9`

升级时请同步更新 `index.html` 中的本地路径，并保留 KaTeX `dist/fonts` 字体文件。
