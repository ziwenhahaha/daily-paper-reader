# Frontend third-party static dependencies

These files replace the CDN requests made during the first-screen load, so GitHub Pages and local deployments are not affected by external CDN latency.

Currently pinned versions:

- Docsify `4`
- KaTeX `0.16.9`
- js-yaml `4.1.0`
- libsodium `0.7.10`
- libsodium-wrappers `0.7.9`

When upgrading, update the local paths in `index.html` accordingly and keep the KaTeX `dist/fonts` font files.
