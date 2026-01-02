// Docsify 配置与公共插件（评论区 + Zotero 元数据）
window.$docsify = {
  name: 'Daily Paper Reader',
  repo: '',
  // 文档内容与侧边栏都存放在 docs/ 下
  basePath: 'docs/', // 所有 Markdown 路由以 docs/ 为前缀
  loadSidebar: '_sidebar.md', // 在 basePath 下加载 _sidebar.md
  // 始终使用根目录的 _sidebar.md，避免每个子目录都要放一份
  alias: {
    '/.*/_sidebar.md': '/_sidebar.md',
  },
  // 只在侧边栏展示论文列表标题，不展示文内小节（例如 Abstract）
  subMaxLevel: 0,

  // --- 核心：注册自定义插件 ---
  plugins: [
    function (hook, vm) {
      // 确保 marked 开启 GFM 表格支持，并允许内联 HTML（用于聊天区 Markdown 渲染）
      if (window.marked && window.marked.setOptions) {
        const baseOptions =
          (window.marked.getDefaults && window.marked.getDefaults()) || {};
        window.marked.setOptions(
          Object.assign({}, baseOptions, {
            gfm: true,
            breaks: false,
            tables: true,
            // 允许 <sup> 等内联 HTML 直接渲染，而不是被转义
            sanitize: false,
            mangle: false,
            headerIds: false,
          }),
        );
      }

      // 1. 解析当前文章 ID (简单用文件名作为 ID)
      const getPaperId = () => {
        return vm.route.file.replace('.md', '');
      };

      const metaFallbacks = {
        citation_title: 'Daily Paper Reader Default Entry',
        citation_journal_title: 'Daily Paper Reader (ArXiv)',
        citation_pdf_url: 'https://daily-paper-reader.invalid/default.pdf',
        citation_publication_date: '2024-01-01',
        citation_date: '2024/01/01',
      };

      const defaultAuthors = ['Daily Paper Reader Team', 'Docsify Renderer'];

      // Zotero 摘要结构标记：方便后续在 Zotero 插件中重新解析
      const START_MARKER = '【🤖 AI Summary】';
      const CHAT_MARKER = '【💬 Chat History】';
      const ORIG_MARKER = '【📄 Original Abstract】';

      // Zotero 元数据更新函数：可被 Docsify 生命周期和聊天模块重复调用
      const updateZoteroMetaFromPage = (paperId, vmRouteFile) => {
        try {
          const titleEl = document.querySelector('.markdown-section h1');
          let title = titleEl ? titleEl.innerText : document.title;
          if (title) {
            // 清理标题中的多余空白与插件注入内容
            title = title.replace(/\s+/g, ' ').trim();
          }

          let pdfLinkEl = document.querySelector('a[href*="arxiv.org/pdf"]');
          if (!pdfLinkEl) {
            pdfLinkEl = document.querySelector('a[href$=".pdf"]');
          }

          let pdfUrl = '';
          if (pdfLinkEl) {
            pdfUrl = new URL(pdfLinkEl.href, window.location.href).href;
          }

          let date = '';
          const matchDate = vmRouteFile
            ? vmRouteFile.match(/(\d{4}-\d{2}-\d{2})/)
            : null;
          if (matchDate) {
            date = matchDate[1];
          }
          const citationDate = date ? date.replace(/-/g, '/') : '';

          let authors = [];
          let tagsLine = '';
          document.querySelectorAll('.markdown-section p').forEach((p) => {
            if (p.innerText.includes('Authors:')) {
              let text = p.innerText.replace('Authors:', '').trim();
              // 清理可能被其它扩展注入的换行和尾部信息，以及尾部日期
              text = text.replace(/\s+/g, ' ').trim();
              text = text
                .replace(/Date\s*:\s*\d{4}-\d{2}-\d{2}.*/i, '')
                .trim();
              authors = text
                .split(/,|，/)
                .map((a) => a.trim())
                .filter(Boolean);
            } else if (p.innerText.includes('Tags:')) {
              // 提取 Tags 行，用于 AI Summary 区块展示
              tagsLine = (p.innerText || '').trim();
            }
          });

          updateMetaTag('citation_title', title);
          updateMetaTag('citation_journal_title', 'Daily Paper Reader (ArXiv)');
          updateMetaTag('citation_pdf_url', pdfUrl, {
            useFallback: false,
          });
          updateMetaTag('citation_publication_date', date);
          updateMetaTag('citation_date', citationDate);

          // 构造给 Zotero 用的“摘要”元信息：按「AI 总结 / 对话历史 / 原始摘要」分段组织
          let abstractText = '';
          const sectionEl = document.querySelector('.markdown-section');
          if (sectionEl) {
            let aiSummaryText = '';
            let origAbstractText = '';

            // 1) 从 Markdown 中提取“论文详细总结（自动生成）”这一节，作为 AI 总结
            const h2List = Array.from(sectionEl.querySelectorAll('h2'));
            const summaryHeader = h2List.find((h) =>
              h.innerText.includes('论文详细总结'),
            );
            if (summaryHeader) {
              let cursor = summaryHeader.nextElementSibling;
              const parts = [];
              while (
                cursor &&
                cursor.tagName !== 'H1' &&
                cursor.tagName !== 'H2'
              ) {
                parts.push(cursor.innerText || '');
                cursor = cursor.nextElementSibling;
              }
              aiSummaryText = parts.join('\n\n').trim();
            }

            // 2) 提取「原始摘要」区域（例如 "## Abstract" 或包含“摘要”的二级标题）
            const abstractHeader = h2List.find((h) =>
              /abstract|摘要/i.test(h.innerText || ''),
            );
            if (abstractHeader) {
              let cursor = abstractHeader.nextElementSibling;
              const parts = [];
              while (
                cursor &&
                cursor.tagName !== 'H1' &&
                cursor.tagName !== 'H2'
              ) {
                // 一旦遇到聊天容器（或其父容器），立即停止，避免把“私人研讨区”等内容当作摘要
                if (
                  cursor.id === 'paper-chat-container' ||
                  (cursor.querySelector &&
                    cursor.querySelector('#paper-chat-container'))
                ) {
                  break;
                }
                parts.push(cursor.innerText || '');
                cursor = cursor.nextElementSibling;
              }
              origAbstractText = parts.join('\n\n').trim();
            }

            // 如果没有找到 AI 总结，就退回到正文前几段作为粗略总结
            if (!aiSummaryText) {
              const paras = [];
              sectionEl.querySelectorAll('p').forEach((p) => {
                if (paras.length >= 6) return;
                // 跳过聊天区域中的段落，避免把私人研讨区内容当作总结
                if (p.closest && p.closest('#paper-chat-container')) return;
                paras.push(p);
              });
              aiSummaryText = paras
                .map((p) => p.innerText || '')
                .join('\n\n')
                .trim();
            }

            // 3) 解析聊天历史，按「User / AI」打标签
            let chatSection = '';
            const chatRoot = document.getElementById('chat-history');
            if (chatRoot) {
              const items = chatRoot.querySelectorAll('.msg-item');
              const lines = [];
              items.forEach((item) => {
                const roleEl = item.querySelector('.msg-role');
                const contentEl = item.querySelector('.msg-content');
                if (!roleEl || !contentEl) return;
                const roleText = roleEl.textContent || '';
                // 显式排除“思考过程”类消息（thinking）
                if (roleText.includes('思考过程')) return;
                let speaker = '';
                if (roleText.includes('你')) {
                  speaker = 'User';
                } else if (roleText.includes('助手')) {
                  speaker = 'AI';
                } else {
                  // 略过其它未知角色
                  return;
                }
                const contentText = (contentEl.innerText || '').trim();
                if (!contentText) return;
                const icon = speaker === 'User' ? '👤' : '🤖';
                lines.push(`${icon} ${speaker}: ${contentText}`);
              });
              if (lines.length) {
                // 不再截断，对话区所有内容全部写入摘要
                chatSection = lines.join('\n\n');
              }
            }

            const parts = [];
            if (aiSummaryText || tagsLine) {
              // AI Summary 区块：保留 Tags 行，但不再包含 Authors 信息
              let aiBlock = `${START_MARKER}\n`;
              if (tagsLine) {
                aiBlock += `${tagsLine}\n\n`;
              }
              if (aiSummaryText) {
                aiBlock += aiSummaryText;
              }
              parts.push(aiBlock.trim());
            }
            if (chatSection) {
              parts.push(`${CHAT_MARKER}\n${chatSection}`);
            }
            if (origAbstractText) {
              parts.push(`${ORIG_MARKER}\n${origAbstractText}`);
            }
            abstractText = parts.join('\n\n\n').trim();
          }

          if (abstractText) {
            // 为兼容 Zotero 的摘要存储行为，将换行统一替换为占位符 __BR__
            const abstractForMeta = abstractText.replace(/\n/g, '__BR__');

            // 写入多种摘要字段，提升 Zotero 等工具的识别率
            updateMetaTag('citation_abstract', abstractForMeta, {
              useFallback: false,
            });
            updateMetaTag('description', abstractForMeta, {
              useFallback: false,
            });
            updateMetaTag('dc.description', abstractForMeta, {
              useFallback: false,
            });
            updateMetaTag('abstract', abstractForMeta, {
              useFallback: false,
            });
            updateMetaTag('DC.description', abstractForMeta, {
              useFallback: false,
            });
          }

          document
            .querySelectorAll('meta[name="citation_author"]')
            .forEach((el) => el.remove());
          const authorList = authors.length ? authors : defaultAuthors;
          authorList.forEach((author) => {
            const meta = document.createElement('meta');
            meta.name = 'citation_author';
            meta.content = author;
            document.head.appendChild(meta);
          });

          document.dispatchEvent(
            new Event('ZoteroItemUpdated', {
              bubbles: true,
              cancelable: true,
            }),
          );
        } catch (e) {
          console.error('Zotero meta update failed:', e);
        }
      };

      // 导出给其它前端模块（例如聊天模块）主动刷新 Zotero 元数据
      window.DPRZoteroMeta = window.DPRZoteroMeta || {};
      window.DPRZoteroMeta.updateFromPage = (paperId, vmRouteFile) =>
        updateZoteroMetaFromPage(paperId, vmRouteFile);

      // 公共工具：在指定元素上渲染公式
      const renderMathInEl = (el) => {
        if (!window.renderMathInElement || !el) return;
        window.renderMathInElement(el, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
          ],
          throwOnError: false,
        });
      };

      // 公共工具：简单表格 + 标记修正：
      // 1）移除协议标记 [ANS]/[THINK]
      // 2）移除表格行之间多余空行，避免把同一张表拆成两块
      const normalizeTables = (markdown) => {
        if (!markdown) return '';
        // 清理历史遗留的协议标记
        let text = markdown
          .replace(/\[ANS\]/g, '')
          .replace(/\[THINK\]/g, '');

        const lines = text.split('\n');
        const isTableLine = (line) => /^\s*\|.*\|\s*$/.test(line);
        const result = [];
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          const prev = result.length ? result[result.length - 1] : '';
          const next = i + 1 < lines.length ? lines[i + 1] : '';
          if (
            line.trim() === '' &&
            isTableLine(prev || '') &&
            isTableLine(next || '')
          ) {
            // 跳过表格行之间的空行
            continue;
          }
          result.push(line);
        }
        return result.join('\n');
      };

      const escapeHtml = (str) => {
        return str
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      };

      // 自定义表格渲染：检测 Markdown 表格块并手写生成 <table>，
      // 其他内容仍交给 marked 渲染。
      const renderMarkdownWithTables = (markdown) => {
        const text = normalizeTables(markdown || '');
        const lines = text.split('\n');
        const isTableLine = (line) => /^\s*\|.*\|\s*$/.test(line);
        const isAlignLine = (line) =>
          /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line);

        const parseRow = (line) => {
          const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
          return trimmed.split('|').map((cell) => cell.trim());
        };

        const inlineRender = (cellText) => {
          if (!cellText) return '';
          if (window.marked && window.marked.parseInline) {
            return window.marked.parseInline(cellText);
          }
          return escapeHtml(cellText);
        };

        const blocks = [];
        let i = 0;

        const flushParagraph = (paraLines) => {
          const paraText = paraLines.join('\n').trim();
          if (!paraText) return;
          if (window.marked) {
            blocks.push(window.marked.parse(`\n${paraText}\n`));
          } else {
            blocks.push(`<p>${escapeHtml(paraText)}</p>`);
          }
        };

        while (i < lines.length) {
          const line = lines[i];

          // 检测表格块：当前行是表格行，下一行是对齐行
          if (
            isTableLine(line) &&
            i + 1 < lines.length &&
            isAlignLine(lines[i + 1])
          ) {
            const headerLine = lines[i];
            i += 2; // 跳过对齐行

            const bodyLines = [];
            while (i < lines.length && isTableLine(lines[i])) {
              bodyLines.push(lines[i]);
              i++;
            }

            const headers = parseRow(headerLine);
            const rows = bodyLines.map(parseRow);

            let html = '<table class="chat-table"><thead><tr>';
            headers.forEach((h) => {
              html += `<th>${inlineRender(h)}</th>`;
            });
            html += '</tr></thead><tbody>';
            rows.forEach((row) => {
              html += '<tr>';
              row.forEach((cell) => {
                html += `<td>${inlineRender(cell)}</td>`;
              });
              html += '</tr>';
            });
            html += '</tbody></table>';

            blocks.push(html);
          } else {
            // 非表格块：收集到下一个表格或结尾
            const paraLines = [];
            while (
              i < lines.length &&
              !(
                isTableLine(lines[i]) &&
                i + 1 < lines.length &&
                isAlignLine(lines[i + 1])
              )
            ) {
              paraLines.push(lines[i]);
              i++;
            }
            flushParagraph(paraLines);
          }
        }

        return blocks.join('');
      };

      const updateMetaTag = (name, content, options = {}) => {
        const old = document.querySelector(`meta[name="${name}"]`);
        if (old) old.remove();
        const useFallback = options.useFallback !== false;
        const value = content || (useFallback ? metaFallbacks[name] : '');
        if (!value) return;
        const meta = document.createElement('meta');
        meta.name = name;
        meta.content = value;
        document.head.appendChild(meta);
      };

      // 导出给外部模块（例如聊天模块）复用
      window.DPRMarkdown = {
        normalizeTables,
        renderMarkdownWithTables,
        renderMathInEl,
      };

      // 3. 侧边栏按“日期”折叠的辅助函数
      const setupCollapsibleSidebarByDay = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const STORAGE_KEY = 'dpr_sidebar_day_state_v1';
        let state = {};
        try {
          const raw = window.localStorage
            ? window.localStorage.getItem(STORAGE_KEY)
            : null;
          if (raw) {
            state = JSON.parse(raw) || {};
          }
        } catch {
          state = {};
        }
        // 先扫描一遍，找出所有日期和最新一天
        const items = nav.querySelectorAll('li');
        const dayItems = [];
        let latestDay = '';

        items.forEach((li) => {
          if (li.dataset.dayToggleApplied === '1') return;

          const childUl = li.querySelector(':scope > ul');
          const directLink = li.querySelector(':scope > a');
          if (!childUl || directLink) return;

          // 取第一个文本节点作为标签文本
          const first = li.firstChild;
          if (!first || first.nodeType !== Node.TEXT_NODE) return;
          const rawText = (first.textContent || '').trim();
          if (!/^\d{4}-\d{2}-\d{2}$/.test(rawText)) return;

          dayItems.push({ li, text: rawText, first });
          if (!latestDay || rawText > latestDay) {
            latestDay = rawText;
          }
        });

        if (!dayItems.length) return;

        // 判断是否出现了“更新后的新一天”
        const prevLatest =
          typeof state.__latestDay === 'string' ? state.__latestDay : null;
        const isNewDay =
          latestDay &&
          (!prevLatest || (typeof prevLatest === 'string' && latestDay > prevLatest));

        // 如果出现了新的一天：清空历史状态，只保留最新一天的信息
        if (isNewDay) {
          state = { __latestDay: latestDay };
        } else if (!prevLatest && latestDay) {
          // 第一次使用，没有历史记录但也不算“新一天触发重置”的场景：记录当前最新日期
          state.__latestDay = latestDay;
        }

        const hasAnyState =
          !isNewDay && Object.keys(state).some((k) => k !== '__latestDay');

        const ensureStateSaved = () => {
          try {
            if (window.localStorage) {
              window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            }
          } catch {
            // ignore
          }
        };

        // 第二遍：真正安装折叠行为
        dayItems.forEach(({ li, text: rawText, first }) => {
          if (li.dataset.dayToggleApplied === '1') return;

          // 创建可点击的容器（包含日期文字和小箭头）
          const wrapper = document.createElement('div');
          wrapper.className = 'sidebar-day-toggle';

          const labelSpan = document.createElement('span');
          labelSpan.className = 'sidebar-day-toggle-label';
          labelSpan.textContent = rawText;

          const arrowSpan = document.createElement('span');
          arrowSpan.className = 'sidebar-day-toggle-arrow';
          arrowSpan.textContent = '▾';

          wrapper.appendChild(labelSpan);
          wrapper.appendChild(arrowSpan);

          // 用 wrapper 替换原始文本节点
          li.replaceChild(wrapper, first);

          // 决定默认展开 / 收起：
          // - 如果本次是“出现了新的一天”：清空历史，只展开最新一天；
          // - 否则若已有用户偏好（state），按偏好来；
          // - 否则（首次使用且没有历史）：仅“最新一天”展开，其余收起。
          let collapsed;
          if (isNewDay) {
            collapsed = rawText === latestDay ? false : true;
          } else if (hasAnyState) {
            const saved = state[rawText];
            if (saved === 'open') {
              collapsed = false;
            } else if (saved === 'closed') {
              collapsed = true;
            } else {
              // 新出现的日期：默认跟最新一天策略走
              collapsed = rawText === latestDay ? false : true;
            }
          } else {
            collapsed = rawText === latestDay ? false : true;
          }

          if (collapsed) {
            li.classList.add('sidebar-day-collapsed');
            arrowSpan.textContent = '▸';
          } else {
            li.classList.remove('sidebar-day-collapsed');
            arrowSpan.textContent = '▾';
          }

          wrapper.addEventListener('click', () => {
            const collapsed = li.classList.toggle('sidebar-day-collapsed');
            arrowSpan.textContent = collapsed ? '▸' : '▾';
            state[rawText] = collapsed ? 'closed' : 'open';
            state.__latestDay = latestDay;
            ensureStateSaved();
          });

          li.dataset.dayToggleApplied = '1';
        });
      };

      // 4. 论文“已阅读”状态管理（存储在 localStorage）
      const READ_STORAGE_KEY = 'dpr_read_papers_v1';

      const loadReadState = () => {
        try {
          if (!window.localStorage) return {};
          const raw = window.localStorage.getItem(READ_STORAGE_KEY);
          if (!raw) return {};
          const obj = JSON.parse(raw);
          if (!obj || typeof obj !== 'object') return {};

          // 兼容旧版本（值为 true 的情况）
          const normalized = {};
          Object.keys(obj).forEach((k) => {
            const v = obj[k];
            if (v === true || v === 'read') {
              normalized[k] = 'read';
            } else if (v === 'good' || v === 'bad') {
              normalized[k] = v;
            }
          });
          return normalized;
        } catch {
          return {};
        }
      };

      const saveReadState = (state) => {
        try {
          if (!window.localStorage) return;
          window.localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(state));
        } catch {
          // ignore
        }
      };

      const markSidebarReadState = (currentPaperId) => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const state = loadReadState();
        if (currentPaperId) {
          if (!state[currentPaperId]) {
            state[currentPaperId] = 'read';
          }
          saveReadState(state);
        }

        const applyLiState = (li, paperIdFromHref) => {
          const status = state[paperIdFromHref];
          li.classList.remove(
            'sidebar-paper-read',
            'sidebar-paper-good',
            'sidebar-paper-bad',
          );
          if (status === 'good') {
            li.classList.add('sidebar-paper-good');
          } else if (status === 'bad') {
            li.classList.add('sidebar-paper-bad');
          } else if (status) {
            li.classList.add('sidebar-paper-read');
          }
        };

        const links = nav.querySelectorAll('a[href*="#/"]');
        links.forEach((a) => {
          const href = a.getAttribute('href') || '';
          const m = href.match(/#\/(.+)$/);
          if (!m) return;
          const paperIdFromHref = m[1].replace(/\/$/, '');
          const li = a.closest('li');
          if (!li) return;
          // 标记这是一个具体论文条目，方便样式细化（避免整天标题一起高亮）
          li.classList.add('sidebar-paper-item');

          // 为侧边栏条目追加“不错 / 一般”圆圈图标按钮
          let actionWrapper = li.querySelector('.sidebar-paper-rating-icons');
          if (!actionWrapper) {
            actionWrapper = document.createElement('span');
            actionWrapper.className = 'sidebar-paper-rating-icons';

            const goodIcon = document.createElement('button');
            goodIcon.className = 'sidebar-paper-rating-icon good';
            goodIcon.title = '标记为「不错」';
            goodIcon.innerHTML = '✓';

            const badIcon = document.createElement('button');
            badIcon.className = 'sidebar-paper-rating-icon bad';
            badIcon.title = '标记为「一般」';
            badIcon.innerHTML = '✕';

            const state = loadReadState();
            const syncIconState = () => {
              const s = state[paperIdFromHref];
              goodIcon.classList.toggle('active', s === 'good');
              badIcon.classList.toggle('active', s === 'bad');
            };

            goodIcon.addEventListener('click', (e) => {
              e.preventDefault();
              e.stopPropagation();
              const current = state[paperIdFromHref];
              if (current === 'good') {
                state[paperIdFromHref] = 'read';
              } else {
                state[paperIdFromHref] = 'good';
              }
              saveReadState(state);
              syncIconState();
              applyLiState(li, paperIdFromHref);
              // 重新应用整棵侧边栏的已读/评价样式，确保当前选中项立即刷新
              markSidebarReadState(null);
            });

            badIcon.addEventListener('click', (e) => {
              e.preventDefault();
              e.stopPropagation();
              const current = state[paperIdFromHref];
              if (current === 'bad') {
                state[paperIdFromHref] = 'read';
              } else {
                state[paperIdFromHref] = 'bad';
              }
              saveReadState(state);
              syncIconState();
              applyLiState(li, paperIdFromHref);
              markSidebarReadState(null);
            });

            actionWrapper.appendChild(goodIcon);
            actionWrapper.appendChild(badIcon);
            a.parentNode.insertBefore(actionWrapper, a.nextSibling);
            syncIconState();
          }

          applyLiState(li, paperIdFromHref);
        });
      };

      // --- Docsify 生命周期钩子 ---
      hook.doneEach(function () {
        // 当前路由对应的“论文 ID”（简单用文件名去掉 .md）
        const paperId = getPaperId();
        const routePath = vm.route && vm.route.path ? vm.route.path : '';
        const lowerId = (paperId || '').toLowerCase();

        // 首页（如 README.md 或根路径）不展示研讨区，只做数学渲染和 Zotero 元数据更新
        const isHomePage =
          !paperId ||
          lowerId === 'readme' ||
          routePath === '/' ||
          routePath === '';

        // A. 对正文区域进行一次全局公式渲染（支持 $...$ / $$...$$）
        const mainContent = document.querySelector('.markdown-section');
        if (mainContent) {
          renderMathInEl(mainContent);
        }

        if (!isHomePage && window.PrivateDiscussionChat) {
          window.PrivateDiscussionChat.initForPage(paperId);
        }

        // ----------------------------------------------------
        // E. 侧边栏按日期折叠
        // ----------------------------------------------------
        setupCollapsibleSidebarByDay();

        // ----------------------------------------------------
        // F. 侧边栏已阅读论文状态高亮
        // ----------------------------------------------------
        if (!isHomePage && paperId) {
          markSidebarReadState(paperId);
        } else {
          // 首页也需要应用已有的“已读高亮”，但不新增记录
          markSidebarReadState(null);
        }

        // ----------------------------------------------------
        // G. Zotero 元数据注入逻辑 (带延时和唤醒)
        // ----------------------------------------------------
        setTimeout(() => {
          updateZoteroMetaFromPage(paperId, vm.route.file);
        }, 1); // 延迟执行，等待 DOM 渲染完毕
      });
      // ----------------------------------------------------
      // H. 响应式侧边栏：窗口宽度小于指定阈值时自动收起
      // ----------------------------------------------------
      const SIDEBAR_AUTO_COLLAPSE_WIDTH = 1024; // 窗口宽度小于1024px时自动收起侧边栏
      let isManualToggle = false; // 标记是否为用户手动切换

      const handleSidebarAutoCollapse = () => {
        if (isManualToggle) return; // 如果用户手动切换过，不自动调整
        
        const windowWidth = window.innerWidth;
        const body = document.body;
        
        if (windowWidth < SIDEBAR_AUTO_COLLAPSE_WIDTH) {
          // 窗口较小，自动收起侧边栏
          if (!body.classList.contains('close')) {
            body.classList.add('close');
          }
        } else {
          // 窗口较大，自动展开侧边栏
          if (body.classList.contains('close')) {
            body.classList.remove('close');
          }
        }
      };

      // 监听窗口大小变化
      window.addEventListener('resize', handleSidebarAutoCollapse);

      // 初始化时检查一次
      handleSidebarAutoCollapse();

      // 监听侧边栏切换按钮的点击（用户手动切换时标记，避免自动调整干扰）
      document.addEventListener('click', (e) => {
        const toggleBtn = e.target.closest('.sidebar-toggle');
        if (toggleBtn) {
          isManualToggle = true;
          // 3秒后重置标记，允许自动调整恢复
          setTimeout(() => {
            isManualToggle = false;
            handleSidebarAutoCollapse();
          }, 3000);
        }
      });    },
  ],
};
