# 使用教程

在开始之前，先记住这几个高频操作：

> 1. 按键盘左右方向键，可以切换上一篇 / 下一篇论文。
>
> 2. 按数字键 `1` `2` `3` `4`，可以快速给论文做颜色标记。
>
> 3. 在小屏设备上，左右滑动页面，也可以切换上一篇 / 下一篇论文。
>
> 4. 页面内置分享按钮，遇到值得收藏的论文时可以快速分享出去。
>
> 5. 喜欢的论文可以一键保存到 Zotero，并自动生成摘要笔记。

## 使用入口

这个项目的大多数入口都集中在左下角的小齿轮里，后台管理、检索配置、工作流触发等功能都在这里。

<p align="center">
  <img src="docs/tutorial/tutorial-entry-panel.png" alt="使用入口面板" width="50%" />
</p>

进入后台管理面板后，点击“新增”可以创建一个新的专题词条。

先在“检索需求”里输入你真正想追踪的方向，再点击“生成候选”，然后从候选结果里勾选需要保留的专题。

<p align="center">
  <img src="docs/tutorial/tutorial-topic-setup.png" alt="专题创建与候选生成" width="88%" />
</p>

建议将关键词控制在 **8 个以内**，自然语言 query 控制在 **5 个以内**，这样更容易保持召回质量和配置可维护性。

保存查询后，记得再保存一次词条。完成后，就可以点击右侧的搜寻论文区域，发起第一次论文检索。

<p align="center">
  <img src="docs/tutorial/tutorial-first-search.png" alt="首次搜寻论文" width="50%" />
</p>

---

### 重置内容按钮

“删除所有”按钮会把当前仓库恢复到“还没有抓取任何论文”的状态，但**不会重置密码**，也不会影响你的解锁方式。

### Zotero 集成

1. 安装 Zotero

2. 安装 [Zotero Connector](https://www.zotero.org/download/connectors)

3. 安装 `Actions & Tags`  
   [Releases · windingwind/zotero-actions-tags](https://github.com/windingwind/zotero-actions-tags/releases/)

4. 打开 Zotero 设置，进入 `Actions & Tags` 完成配置

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-settings.png" alt="Zotero Actions and Tags 设置" width="88%" />
</p>

5. 下载仓库里的脚本，并导入到 Zotero 中  
   脚本链接：
   <a href="others/actions-zotero.yml" data-no-router download="actions-zotero.yml">下载 actions-zotero.yml</a>

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-script-download.png" alt="下载 Zotero 脚本" width="88%" />
</p>

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-script-import.png" alt="导入 Zotero 脚本" width="88%" />
</p>

导入并启用脚本后，打开论文页；如果 Zotero 图标状态已经变化，就可以开始一键保存。

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-save-entry.png" alt="网页端一键保存到 Zotero" width="88%" />
</p>

保存成功后，你可以在 Zotero 中看到自动生成的摘要笔记效果：

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-note-preview.png" alt="Zotero 自动生成摘要笔记预览" width="88%" />
</p>
