# Zotero 使用说明

本页说明如何把 Daily Paper Reader 页面中的论文保存到 Zotero，并自动生成摘要笔记。

## 安装组件

1. 安装 [Zotero](https://www.zotero.org/)。
2. 安装 [Zotero Connector](https://www.zotero.org/download/connectors)，用于从浏览器保存论文条目。
3. 安装 `Actions & Tags` 插件：在插件发布页下载最新版 `.xpi`，然后在 Zotero 的插件管理中手动安装。
4. 可选安装 Better Notes。仓库脚本会优先调用 Better Notes 的 Markdown 转换能力；未安装时会自动退回到内置的简易 HTML 渲染。

## 导入脚本

1. 在项目页面打开 `others/actions-zotero.yml`，下载到本地。
2. 打开 Zotero 设置，进入 `Actions & Tags`。
3. 导入 `actions-zotero.yml`，确认其中的 `Process DPR Summary Note` 动作已启用。
4. 如果已存在旧版本脚本，建议先删除旧动作再导入，避免同名动作重复。

## 一键保存流程

1. 在 Daily Paper Reader 中打开任意论文详情页。
2. 使用浏览器 Zotero Connector 保存当前论文。
3. 保存完成后，脚本会读取页面中的标题、摘要、TLDR、速览和详细总结字段。
4. Zotero 条目下会自动生成一条摘要笔记，并带有自动生成标记，重复运行时会先清理旧的自动摘要笔记。

## 常见问题

- 若提示未读到摘要，先确认当前页面已经加载完成，再重新保存。
- 若笔记缺少公式渲染，通常是因为 Better Notes 未安装或公式内容较复杂；脚本会保留可读的纯 HTML 文本。
- 若导入脚本后没有触发，请检查 `Actions & Tags` 中动作是否启用，并确认该动作应用于条目创建或手动运行场景。
