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
        citation_journal_title: 'arxiv',
        citation_pdf_url: 'https://daily-paper-reader.invalid/default.pdf',
        citation_publication_date: '2024-01-01',
        citation_date: '2024/01/01',
      };

      const defaultAuthors = ['Daily Paper Reader Team', 'Docsify Renderer'];

      // Zotero 摘要结构标记：方便后续在 Zotero 插件中重新解析
      const START_MARKER = '【🤖 AI Summary】';
      const CHAT_MARKER = '【💬 Chat History】';
      const ORIG_MARKER = '【📄 Original Abstract】';
      const TLDR_MARKER = '【📝 TLDR】';
      const GLANCE_MARKER = '【🧭 速览区】';
      const GLANCE_MARKER_LEGACY = '【🧭 Glance】';
      const DETAIL_MARKER = '【🧩 论文详细总结区】';
      const DETAIL_MARKER_LEGACY = '【🧩 论文详细总结】';
      let latestPaperRawMarkdown = '';

      const extractSectionByTitle = (rawContent, matchFn) => {
        if (!rawContent || typeof rawContent !== 'string') return '';
        const contentWithoutFrontMatter = rawContent
          .replace(/^---[\s\S]*?---\s*/, '')
          .replace(/\r\n/g, '\n');
        const lines = contentWithoutFrontMatter.split('\n');
        let headingIndex = -1;
        for (let i = 0; i < lines.length; i += 1) {
          const m = lines[i].match(/^#{1,6}\s+(.*)$/);
          if (!m) continue;
          if (matchFn(m[1])) {
            headingIndex = i;
            break;
          }
        }
        if (headingIndex < 0) return '';

        const chunk = [];
        for (
          let i = headingIndex + 1;
          i < lines.length && !/^#{1,6}\s+/.test(lines[i]);
          i += 1
        ) {
          chunk.push(lines[i]);
        }
        return chunk.join('\n').trim();
      };

      const escapeRegExp = (value) =>
        String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

      const normalizeTextForMeta = (value) =>
        (value || '').toString().replace(/\r\n/g, '\n').trim();
      const CITATION_ABSTRACT_BR = '__BR__';
      const encodeCitationAbstractForMeta = (value) =>
        normalizeTextForMeta(value)
          .replace(/\r/g, '\n')
          .replace(/\n/g, CITATION_ABSTRACT_BR);

      const trimBeforeMarkers = (value, markers) => {
        const text = normalizeTextForMeta(value);
        if (!text) return '';
        const indices = markers
          .map((marker) => text.indexOf(marker))
          .filter((idx) => idx >= 0)
          .sort((a, b) => a - b);
        if (indices.length === 0) return text;
        return text.slice(0, indices[0]).trim();
      };

      const cleanSectionText = (value) => {
        let text = normalizeTextForMeta(value);
        if (!text) return '';

        text = trimBeforeMarkers(text, [
          CHAT_MARKER,
          ORIG_MARKER,
          START_MARKER,
          TLDR_MARKER,
          GLANCE_MARKER,
          GLANCE_MARKER_LEGACY,
          DETAIL_MARKER,
          DETAIL_MARKER_LEGACY,
        ]);
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(START_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(ORIG_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(CHAT_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(TLDR_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(GLANCE_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(
          new RegExp(`^\\s*${escapeRegExp(GLANCE_MARKER_LEGACY)}\\s*\\n?`, 'i'),
          '',
        );
        text = text.replace(new RegExp(`^\\s*${escapeRegExp(DETAIL_MARKER)}\\s*\\n?`, 'i'), '');
        text = text.replace(
          new RegExp(`^\\s*${escapeRegExp(DETAIL_MARKER_LEGACY)}\\s*\\n?`, 'i'),
          '',
        );
        text = text.replace(/^Tags:\s*.*$/gim, '');
        text = text.replace(/^>?\s*由\s*daily-paper-reader\s*自动生成\s*$/gim, '');
        return text.trim();
      };

      const parseDateFromText = (value) => {
        const text = normalizeTextForMeta(value);
        if (!text) return '';
        const ymdMatch = text.match(/(\d{4})-(\d{2})-(\d{2})/);
        if (ymdMatch) {
          return `${ymdMatch[1]}-${ymdMatch[2]}-${ymdMatch[3]}`;
        }
        const date8Match = text.match(/(\d{4})(\d{2})(\d{2})/);
        if (date8Match && text.indexOf('/') === -1 && text.indexOf('.') === -1) {
          return `${date8Match[1]}-${date8Match[2]}-${date8Match[3]}`;
        }
        return '';
      };

      const splitRawSectionByTitle = (rawContent, shouldMatchTitle) => {
        const source = (rawContent || '').toString();
        const parsed = parseFrontMatter(source);
        const body = (parsed && parsed.body) || source;
        const lines = normalizeTextForMeta(body).split('\n');
        const headingMeta = (lineText) => {
          const normalized = normalizeTextForMeta(lineText).trim();
          const match = normalized.match(/^(#{1,6})\s+(.*)$/);
          if (!match) return null;
          return {
            level: match[1].length,
            title: normalizeTextForMeta(match[2]),
          };
        };
        const isBoundary = (lineText, sectionHeadingLevel) => {
          const t = normalizeTextForMeta(lineText);
          if (!t) return false;
          if (
            t.startsWith(START_MARKER) ||
            t.startsWith(CHAT_MARKER) ||
            t.startsWith(ORIG_MARKER) ||
            t.startsWith(TLDR_MARKER) ||
            t.startsWith(GLANCE_MARKER) ||
            t.startsWith(GLANCE_MARKER_LEGACY) ||
            t.startsWith(DETAIL_MARKER)
            || t.startsWith(DETAIL_MARKER_LEGACY)
          ) {
            return true;
          }
          const heading = headingMeta(lineText);
          if (heading && sectionHeadingLevel) {
            return heading.level <= sectionHeadingLevel;
          }
          return /^#{1,6}\s+/.test(t);
        };

        const extractHeadingTitle = (lineText) => {
          const normalized = normalizeTextForMeta(lineText).trim();
          if (!normalized) return '';
          if (normalized.startsWith(START_MARKER)) return START_MARKER;
          if (normalized.startsWith(CHAT_MARKER)) return CHAT_MARKER;
            if (normalized.startsWith(ORIG_MARKER)) return ORIG_MARKER;
            if (normalized.startsWith(TLDR_MARKER)) return TLDR_MARKER;
            if (normalized.startsWith(GLANCE_MARKER)) return GLANCE_MARKER;
            if (normalized.startsWith(GLANCE_MARKER_LEGACY)) return GLANCE_MARKER_LEGACY;
            if (normalized.startsWith(DETAIL_MARKER)) return DETAIL_MARKER;
            if (normalized.startsWith(DETAIL_MARKER_LEGACY)) return DETAIL_MARKER_LEGACY;
          return normalized.replace(/^#{1,6}\s*/, '');
        };

        let start = -1;
        let sectionHeadingLevel = 1;
        for (let i = 0; i < lines.length; i += 1) {
          const title = extractHeadingTitle(lines[i]);
          if (!title) continue;
          if (shouldMatchTitle(title)) {
            start = i;
            const heading = headingMeta(lines[i]);
            sectionHeadingLevel = heading ? heading.level : 1;
            break;
          }
        }
        if (start < 0) {
          return '';
        }

        let end = lines.length;
        for (let j = start + 1; j < lines.length; j += 1) {
          if (isBoundary(lines[j], sectionHeadingLevel)) {
            end = j;
            break;
          }
        }
        return lines
          .slice(start + 1, end)
          .join('\n')
          .trim();
      };

      const getRawPaperSections = (rawContent) => ({
        aiSummaryText: splitRawSectionByTitle(
          rawContent,
          (title) => {
            const t = normalizeTextForMeta(title).replace(/^\s*#{1,6}\s*/, '').trim().toLowerCase();
            return (
              t.includes('论文详细总结') ||
              t.includes('论文详细总结（自动生成）') ||
              t.includes('ai summary') ||
              t.includes('🤖 ai summary') ||
              t.includes('论文详细总结')
            );
          },
        ),
        originalAbstractText: splitRawSectionByTitle(
          rawContent,
          (title) => {
            const t = normalizeTextForMeta(title)
              .replace(/^\s*#{1,6}\s*/, '')
              .trim()
              .toLowerCase();
            return (
              t === 'abstract' ||
              t.includes('原文摘要') ||
              t.includes('original abstract') ||
              (t.includes('摘要') && t.length <= 8)
            );
          },
        ),
        tldrText: splitRawSectionByTitle(
          rawContent,
          (title) => {
            const t = normalizeTextForMeta(title)
              .replace(/^\s*#{1,6}\s*/, '')
              .trim()
              .toLowerCase();
            return t.includes('tldr') || t.includes('tl;dr') || t.includes('摘要要点');
          },
        ),
      });

      const collectPaperBodySections = (sectionEl) => {
        if (!sectionEl || !sectionEl.children) return [];

        const headingTag = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6'];
        const shouldSkipHeadingBlock = (headingText) => {
          const text = normalizeTextForMeta(headingText || '').toLowerCase();
          if (!text) return false;
          const blocked = [
            'paper-title-row',
            'paper-meta-row',
            'paper-glance-section',
            '互动区',
            '页面导航与交互层',
            '原文摘要',
            'original abstract',
            '论文详细总结',
            'ai summary',
            'chat history',
          ];
          return blocked.some((token) => text.includes(token));
        };

        const shouldSkipNode = (node) =>
          !!(
            node &&
            node.classList &&
            (node.classList.contains('paper-title-row') ||
              node.classList.contains('paper-meta-row') ||
              node.classList.contains('paper-glance-section') ||
              node.classList.contains('paper-title-cn') ||
              node.classList.contains('paper-title-en'))
          );
        const sections = [];
        let currentTitle = '📝 论文正文';
        let currentContent = [];
        let seenHeading = false;
        let skipCurrentSection = false;
        const collectText = (node) => normalizeTextForMeta(node && (node.innerText || node.textContent || ''));

        const flush = () => {
          const text = trimBeforeMarkers(collectText({ innerText: currentContent.join('\n') }), []);
          const cleanText = text.replace(/\n{3,}/g, '\n\n').trim();
          if (cleanText) {
            sections.push({
              title: currentTitle,
              text: cleanText,
            });
          }
          currentContent = [];
        };

        const children = Array.from(sectionEl.children);
        for (const child of children) {
          const tag = child.tagName || '';
          if (shouldSkipNode(child)) {
            flush();
            continue;
          }
          if (
            child.id === 'paper-chat-container' ||
            (child.querySelector && child.querySelector('#paper-chat-container'))
          ) {
            flush();
            continue;
          }

          if (headingTag.includes(tag)) {
            flush();
            const text = normalizeTextForMeta(child.innerText || '').trim();
            skipCurrentSection = shouldSkipHeadingBlock(text);
            if (skipCurrentSection) {
              continue;
            }
            if (text) {
              currentTitle = text;
              seenHeading = true;
            }
            continue;
          }
          if (skipCurrentSection) {
            continue;
          }

          const txt = collectText(child).replace(/\n{2,}/g, '\n').trim();
          if (!txt) {
            continue;
          }
          currentContent.push(txt);
          seenHeading = true;
        }

        if (seenHeading) {
          flush();
        } else {
          const fallback = collectText(sectionEl);
          if (fallback) {
            sections.push({
              title: currentTitle,
              text: fallback,
            });
          }
        }
        return sections;
      };

      // Zotero 元数据更新函数：可被 Docsify 生命周期和聊天模块重复调用
      const updateZoteroMetaFromPage = (
        paperId,
        vmRouteFile,
        rawPaperContent = '',
      ) => {
        try {
          // 优先使用自定义标题条（避免 h1 被隐藏/改造后 innerText 不稳定）
          const dprEn = document.querySelector('.dpr-title-en');
          const dprCn = document.querySelector('.dpr-title-cn');
          let title = '';
          if (dprEn && (dprEn.textContent || '').trim()) {
            title = (dprEn.textContent || '').trim();
          } else if (dprCn && (dprCn.textContent || '').trim()) {
            title = (dprCn.textContent || '').trim();
          } else {
            const titleEl = document.querySelector('.markdown-section h1');
            title = titleEl ? (titleEl.textContent || '').trim() : document.title;
          }
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

          const frontmatterPaperMeta = (() => {
            try {
              const parsed = parseFrontMatter(rawPaperContent || '');
              return parsed && parsed.meta ? parsed.meta : {};
            } catch {
              return {};
            }
          })();

          let date = parseDateFromText(frontmatterPaperMeta.date);
          if (!date) {
            const matchDate = vmRouteFile
              ? vmRouteFile.match(/(\d{4}-\d{2}-\d{2})/)
              : null;
            if (matchDate) {
              date = matchDate[1];
            }
          }
          if (!date) {
            const matchFolderDate = vmRouteFile
              ? vmRouteFile.match(/(?:^|\/)(\d{4})(\d{2})\/(\d{2})(?:\/|$)/)
              : null;
            if (matchFolderDate) {
              date = `${matchFolderDate[1]}-${matchFolderDate[2]}-${matchFolderDate[3]}`;
            }
          }
          if (!date) {
            date = parseDateFromText(frontmatterPaperMeta.published);
          }
          if (!date) {
            date = parseDateFromText(frontmatterPaperMeta.submitted);
          }
          if (!date) {
            date = parseDateFromText(frontmatterPaperMeta.submit_date);
          }
          if (!date && vmRouteFile) {
            const routeMatch = vmRouteFile.match(/(\d{6})\/(\d{2})/);
            if (routeMatch) {
              const yyyymm = routeMatch[1];
              date = `${yyyymm.slice(0, 4)}-${yyyymm.slice(4)}-${routeMatch[2]}`;
            }
          }
          const citationDate = date ? date.replace(/-/g, '/') : '';

          let authors = [];
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
            }
          });

          updateMetaTag('citation_title', title);
          updateMetaTag('citation_journal_title', 'arxiv');
          updateMetaTag('citation_pdf_url', pdfUrl, {
            useFallback: false,
          });
          updateMetaTag('citation_publication_date', date, { useFallback: false });
          updateMetaTag('citation_date', citationDate, { useFallback: false });

          const {
            aiSummaryText: rawSummary,
            originalAbstractText: rawOriginal,
            tldrText: rawTldrText,
          } =
            getRawPaperSections(rawPaperContent || '');

          // 每次路由刷新先清理上一个页面注入的摘要 meta，避免重复残留
          clearSummaryMetaFields();

          // 构造给 Zotero 用的“摘要”元信息：按「AI 总结 / 对话历史 / 原始摘要」分段组织
          let abstractText = '';
          let abstractTextForMetaRaw = '';
          const sectionEl = document.querySelector('.markdown-section');
          if (sectionEl) {
            let aiSummaryText = rawSummary;
            let origAbstractText = rawOriginal;
            aiSummaryText = cleanSectionText(aiSummaryText);
            origAbstractText = cleanSectionText(origAbstractText);

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

            chatSection = cleanSectionText(chatSection);

            const parts = [];
            const seenBlocks = new Set();
            const seenTitles = new Set();
            const cleanText = (value) => cleanSectionText(normalizeTextForMeta(value));
            const rawParts = [];
            const seenRawBlocks = new Set();
            const addMetaSectionBlock = (title, content) => {
              const cleanText = cleanSectionText(content);
              if (!cleanText) return;
              const titleKey = normalizeTextForMeta(title)
                .toLowerCase()
                .replace(/[^a-z0-9\u4e00-\u9fa5]/g, '');
              const contentKey = cleanText
                .toLowerCase()
                .replace(/\s+/g, '')
                .replace(/[#>*_`[\]]/g, '');
              const signature = `${titleKey}|${contentKey}`;
              if (seenTitles.has(titleKey) && seenBlocks.has(signature)) {
                return;
              }
              seenTitles.add(titleKey);
              if (seenBlocks.has(signature)) return;
              seenBlocks.add(signature);
              parts.push(`## ${title}\n${cleanText}`);
            };
            const normalizeMarkerTitle = (label) => {
              const raw = normalizeTextForMeta(label).trim();
              if (!raw) return "";
              if (raw === START_MARKER) return "🤖 AI Summary";
              if (raw === CHAT_MARKER) return "💬 Chat History";
              if (raw === ORIG_MARKER) return "📄 Original Abstract";
              if (raw === TLDR_MARKER) return "📝 TLDR";
              if (raw === GLANCE_MARKER || raw === GLANCE_MARKER_LEGACY) return "🧭 速览区";
              if (raw === DETAIL_MARKER || raw === DETAIL_MARKER_LEGACY) return "🧩 论文详细总结区";
              return raw.replace(/^#{1,6}\s*/, '');
            };
            const addRawMetaBlock = (label, content) => {
              const text = normalizeTextForMeta(content);
              if (!text) return;
              const sectionTitle = normalizeMarkerTitle(label);
              const signature = `${sectionTitle}|${text.replace(/\s+/g, ' ')}`;
              if (seenRawBlocks.has(signature)) return;
              seenRawBlocks.add(signature);
              rawParts.push(`## ${sectionTitle}\n${text}`);
            };
            const addMetaBlock = (label, content) => {
              const cleanText = cleanSectionText(content);
              if (!cleanText) return;
              const signature = cleanText.replace(/\s+/g, ' ');
              if (seenBlocks.has(signature)) return;
              seenBlocks.add(signature);
              const sectionTitle = normalizeMarkerTitle(label);
              parts.push(`## ${sectionTitle}\n${cleanText}`);
            };
            const parseLabelLine = (line) => {
              const raw = normalizeTextForMeta(line || '').trim();
              if (!raw) return null;
              const lineText = raw
                .replace(/^[\-\*]\s*/, '')
                .replace(/^\*\*(.*?)\*\*\s*:?\s*/, '$1:');
              const m = lineText.match(/^(.+?)\s*[:：]\s*(.*)$/);
              if (!m) return null;
              return [normalizeTextForMeta(m[1]).trim(), normalizeTextForMeta(m[2]).trim()];
            };
            const pickFirst = (labelList, fallbackValue) => {
              for (const item of labelList) {
                if (item) return item;
              }
              return fallbackValue || '';
            };
            const normalizeTagValue = (value) =>
              normalizeTextForMeta(value || '')
                .replace(/\s+/g, ' ')
                .trim();

            const collectLabeledPairs = (rows) => {
              const map = new Map();
              rows.forEach((line) => {
                const parsed = parseLabelLine(line);
                if (!parsed) return;
                const [label, value] = parsed;
                if (!label || !value) return;
                const key = label.toLowerCase();
                if (!map.has(key) || normalizeTagValue(map.get(key)).length < value.length) {
                  map.set(key, value);
                }
              });
              return map;
            };
            const buildLabeledText = (map, order) => {
              const lines = [];
              order.forEach((label) => {
                const key = normalizeTextForMeta(label).toLowerCase();
                if (map.has(key)) {
                  lines.push(`- **${label}**: ${map.get(key)}`);
                }
              });
              map.forEach((value, key) => {
                if (!order.includes(key)) {
                  lines.push(`- **${key}**: ${value}`);
                }
              });
              return lines.join('\n');
            };

            const splitBlockText = (text) => {
              const normalized = normalizeTextForMeta(text || '');
              if (!normalized) return [];
              return normalized
                .split('\n')
                .map((item) => item.trim())
                .filter(Boolean);
            };
            const getNodeText = (el) =>
              normalizeTextForMeta(el && (el.innerText || el.textContent || ''));
            const titleZhText = getNodeText(
              document.querySelector('.paper-title-row .paper-title-zh'),
            ) || getNodeText(document.querySelector('.paper-title-zh'));
            const titleEnText = getNodeText(
              document.querySelector('.paper-title-row .paper-title-en'),
            ) || getNodeText(document.querySelector('.dpr-title-en'));
            const metaLeftRows = Array.from(
              document.querySelectorAll('.paper-meta-left p'),
            ).flatMap((el) => splitBlockText(getNodeText(el)));
            const metaRightRows = Array.from(
              document.querySelectorAll('.paper-meta-right p'),
            ).flatMap((el) => splitBlockText(getNodeText(el)));
            const glanceRows = Array.from(
              document.querySelectorAll('.paper-glance-col'),
            ).map((col) => {
              const label = getNodeText(
                col.querySelector('.paper-glance-label'),
              );
              const content = getNodeText(
                col.querySelector('.paper-glance-content'),
              );
              if (!label && !content) return '';
              return `- **${label || '项'}**: ${content || '-'}`;
            });
            const fallbackArray = (value, label = '') =>
              value ? [`- **${label}**: ${Array.isArray(value) ? value.join(' / ') : String(value)}`] : [];

            const titleRowText = [
              `- **中英文标题**: ${titleZhText || frontmatterPaperMeta.title_zh || '-'} / ${titleEnText || frontmatterPaperMeta.title || '-'}`,
            ].filter(Boolean);

            const metaPairs = collectLabeledPairs([...metaLeftRows, ...metaRightRows]);
            const fallbackMetaPairs = collectLabeledPairs([
              ...fallbackArray(frontmatterPaperMeta.evidence, 'Evidence'),
              ...fallbackArray(frontmatterPaperMeta.tldr, 'TLDR'),
              ...fallbackArray(frontmatterPaperMeta.authors, 'Authors'),
              ...fallbackArray(frontmatterPaperMeta.date, 'Date'),
              ...fallbackArray(frontmatterPaperMeta.pdf, 'PDF'),
              ...fallbackArray(frontmatterPaperMeta.tags, 'Tags'),
              ...fallbackArray(frontmatterPaperMeta.score, 'Score'),
            ]);
            ['Evidence', 'TLDR', 'Authors', 'Date', 'PDF', 'Tags', 'Score'].forEach(
              (label) => {
                const key = label.toLowerCase();
                if (!metaPairs.has(key)) {
                  const value = normalizeTagValue(
                    fallbackMetaPairs.get(key) || '',
                  );
                  if (value) metaPairs.set(key, value);
                }
              },
            );
            const glancePairs = collectLabeledPairs(glanceRows);
            const fallbackGlancePairs = collectLabeledPairs([
              ...fallbackArray(frontmatterPaperMeta.motivation, 'Motivation'),
              ...fallbackArray(frontmatterPaperMeta.method, 'Method'),
              ...fallbackArray(frontmatterPaperMeta.result, 'Result'),
              ...fallbackArray(frontmatterPaperMeta.conclusion, 'Conclusion'),
            ]);
            ['Motivation', 'Method', 'Result', 'Conclusion'].forEach((label) => {
              const key = label.toLowerCase();
              if (!glancePairs.has(key)) {
                const value = normalizeTagValue(
                  fallbackGlancePairs.get(key) || '',
                );
                if (value) glancePairs.set(key, value);
              }
            });

            const titleBarEl = document.querySelector('.dpr-title-bar');
            const pageContentEl = document.querySelector('.dpr-page-content');
            const chatContainerEl = document.getElementById('paper-chat-container');
            const chatHistoryEl = document.getElementById('chat-history');
            const uiRows = [
              `- **dpr-title-bar**: ${titleBarEl ? '已挂载' : '未检测到'}`,
              `- **dpr-page-content**: ${pageContentEl ? '已挂载' : '未检测到'}`,
              `- **paper-title-row**: ${document.querySelector('.paper-title-row') ? '已挂载' : '未检测到'}`,
              `- **paper-meta-row**: ${document.querySelector('.paper-meta-row') ? '已挂载' : '未检测到'}`,
              `- **paper-glance-section**: ${document.querySelector('.paper-glance-section') ? '已挂载' : '未检测到'}`,
              `- **#paper-chat-container**: ${chatContainerEl ? '已挂载' : '未检测到'}`,
              `- **#chat-history**: ${chatHistoryEl ? '已挂载' : '未检测到'}`,
            ];

            addMetaSectionBlock(
              'paper-title-row（双语标题区域）',
              titleRowText.join('\n'),
            );
            addMetaSectionBlock(
              'paper-meta-row（中间信息区）',
              cleanText(
                buildLabeledText(
                  metaPairs,
                  ['evidence', 'tldr', 'authors', 'date', 'pdf', 'tags', 'score'],
                ),
              ),
            );
            const tldrText = pickFirst(
              [
                rawTldrText,
                metaPairs.get('tldr'),
                fallbackMetaPairs.get('tldr'),
              ],
              '',
            );
            if (tldrText) {
              addMetaBlock(TLDR_MARKER, normalizeTagValue(tldrText));
              addRawMetaBlock(TLDR_MARKER, normalizeTagValue(tldrText));
            }
            const glanceText = cleanText(
              buildLabeledText(glancePairs, [
                'motivation',
                'method',
                'result',
                'conclusion',
              ]),
            );
            if (glanceText) {
              addMetaBlock(GLANCE_MARKER, glanceText);
              addRawMetaBlock(GLANCE_MARKER, glanceText);
            }
            addMetaSectionBlock(
              '页面导航与交互层',
              cleanText(uiRows.join('\n')),
            );

            // 1) 全文段落：按页面 heading 自动切块，保持顺序写入
            const paperBodySections = collectPaperBodySections(sectionEl);
            paperBodySections.forEach((section) => {
              if (section && section.text) {
                addMetaSectionBlock(section.title, section.text);
              }
            });

            if (aiSummaryText) {
              // AI Summary 区块：仅保留 AI 摘要正文，不再自动拼入 Tags
              let aiBlock = `${START_MARKER}\n`;
              if (aiSummaryText) {
                aiBlock += aiSummaryText;
              }
              addMetaBlock(DETAIL_MARKER, aiBlock);
              addRawMetaBlock(
                DETAIL_MARKER,
                [rawSummary]
                  .filter(Boolean)
                  .join('\n\n'),
              );
            }
            if (chatSection) {
              addMetaBlock(CHAT_MARKER, chatSection);
              addRawMetaBlock(CHAT_MARKER, chatSection);
            }
            if (origAbstractText) {
              addMetaBlock(ORIG_MARKER, origAbstractText);
              addRawMetaBlock(ORIG_MARKER, rawOriginal);
            }

            // 兜底 raw 聚合：确保保留 AI Summary / Original Abstract 原始 Markdown
            // （避免经过 DOM 文本化路径后公式被改写）
            abstractText = parts.join('\n\n\n').trim();
            abstractTextForMetaRaw = rawParts.join('\n\n\n').trim();
          }

          if (abstractText) {
            const abstractTextForMeta =
              abstractTextForMetaRaw || abstractText;
            if (abstractTextForMeta) {
              // 用 Zotero Connector 常识别的字段名：citation_abstract
              // 用占位符编码换行，避免 Connector 导入时丢失段落边界
              const metaText = encodeCitationAbstractForMeta(abstractTextForMeta);
              updateMetaTag('citation_abstract', metaText, {
                useFallback: false,
              });
            }
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
        updateZoteroMetaFromPage(paperId, vmRouteFile, latestPaperRawMarkdown);

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
      // 同时保护 LaTeX 公式块，避免被 marked 误解析。
      const renderMarkdownWithTables = (markdown) => {
        const text = normalizeTables(markdown || '');

        // 保护 LaTeX 公式：先用占位符替换，渲染后再恢复
        const latexBlocks = [];
        let protectedText = text;

        // 保护块级公式 $$...$$
        protectedText = protectedText.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
          const idx = latexBlocks.length;
          latexBlocks.push(match);
          return `%%LATEX_BLOCK_${idx}%%`;
        });

        // 保护行内公式 $...$（不跨行）
        protectedText = protectedText.replace(/\$([^\$\n]+?)\$/g, (match) => {
          const idx = latexBlocks.length;
          latexBlocks.push(match);
          return `%%LATEX_INLINE_${idx}%%`;
        });

        // 预处理：手动将 **...** 和 *...* 转换为 HTML 标签
        // 解决 marked 对中文字符旁的粗体/斜体识别问题
        // 注意：只匹配同一行内、且内容不超过 100 字符的情况，避免误匹配
        protectedText = protectedText.replace(/\*\*([^*\n]{1,100}?)\*\*/g, '<strong>$1</strong>');
        // 斜体：要求前后有空格或中文字符边界，避免误匹配乘号等
        protectedText = protectedText.replace(/(?<=[^\*]|^)\*([^*\n]{1,50}?)\*(?=[^\*]|$)/g, '<em>$1</em>');

        const lines = protectedText.split('\n');
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

        let result = blocks.join('');

        // 恢复 LaTeX 公式
        result = result.replace(/%%LATEX_BLOCK_(\d+)%%/g, (_, idx) => latexBlocks[parseInt(idx, 10)]);
        result = result.replace(/%%LATEX_INLINE_(\d+)%%/g, (_, idx) => latexBlocks[parseInt(idx, 10)]);

        return result;
      };

      const updateMetaTag = (name, content, options = {}) => {
        document
          .querySelectorAll(`meta[name="${name}"]`)
          .forEach((el) => el.remove());
        const useFallback = options.useFallback !== false;
        const value = content || (useFallback ? metaFallbacks[name] : '');
        if (!value) return;
        const meta = document.createElement('meta');
        meta.name = name;
        meta.content = value;
        document.head.appendChild(meta);
      };

      const SUMMARY_META_NAMES = ['citation_abstract'];

      const clearSummaryMetaFields = () => {
        SUMMARY_META_NAMES.forEach((name) => {
          document
            .querySelectorAll(`meta[name="${name}"]`)
            .forEach((el) => el.remove());
        });
      };

      // 导出给外部模块（例如聊天模块）复用
      window.DPRMarkdown = {
        normalizeTables,
        renderMarkdownWithTables,
        renderMathInEl,
      };

      // 3. 小屏下：点击侧边栏条目后自动收起侧边栏（全屏列表 → 正文）
      const setupMobileSidebarAutoCloseOnItemClick = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        if (nav.dataset.mobileAutoCloseBound === '1') return;
        nav.dataset.mobileAutoCloseBound = '1';

        nav.addEventListener('click', (event) => {
          const link = event.target.closest('a');
          if (!link) return;

          const href = link.getAttribute('href') || '';
          // 只处理 Docsify 内部路由（#/ 开头），避免影响外链
          if (!href.includes('#/')) return;

          const width =
            window.innerWidth || document.documentElement.clientWidth || 0;
          // 统一“微宽屏 + 窄屏”为同一套逻辑：<1024 时点击条目后自动收起 sidebar（全屏列表 → 正文）
          if (width >= 1024) return;

          // 让 Docsify 先完成路由跳转，再收起侧边栏
          setTimeout(() => {
            const body = document.body;
            if (!body) return;
            // 适配 Docsify 移动端原生语义：小屏收起侧边栏时不保留 close 类
            body.classList.remove('close');
          }, 0);
        });
      };

      // 4. 侧边栏按“日期”折叠的辅助函数
      const setupCollapsibleSidebarByDay = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const joinUrlPath = (a, b) => {
          const aa = String(a || '');
          const bb = String(b || '');
          if (!aa) return bb.replace(/^\/+/, '');
          if (!bb) return aa;
          const left = aa.endsWith('/') ? aa : `${aa}/`;
          const right = bb.replace(/^\/+/, '');
          return `${left}${right}`;
        };

        const getDocsifyBasePath = () => {
          const bp =
            window.$docsify && typeof window.$docsify.basePath === 'string'
              ? window.$docsify.basePath
              : '';
          return String(bp || '');
        };

        const getDate8FromDayLi = (li, dayKeyOrLabel) => {
          // 优先从 HTML comment marker 读取：<!--dpr-date:YYYYMMDD-->
          try {
            const nodes = Array.from(li.childNodes || []);
            for (const n of nodes) {
              if (n && n.nodeType === Node.COMMENT_NODE) {
                const m = String(n.textContent || '').match(/dpr-date:(\d{8})/);
                if (m) return m[1];
              }
            }
          } catch {
            // ignore
          }

          // 兜底：从 dayKey / label 解析（区间取结束日）
          const s = String(dayKeyOrLabel || '').trim();
          const m = s.match(
            /(\d{4})-(\d{2})-(\d{2})(?:\s*~\s*(\d{4})-(\d{2})-(\d{2}))?$/,
          );
          if (!m) return null;
          if (m[4]) return `${m[4]}${m[5]}${m[6]}`;
          return `${m[1]}${m[2]}${m[3]}`;
        };

        const buildDayIndexJsonUrl = (date8) => {
          const s = String(date8 || '');
          if (!/^\d{8}$/.test(s)) return null;
          const ym = s.slice(0, 6);
          const day = s.slice(6);
          const rel = `${ym}/${day}/papers.meta.json`;
          const baseHref = window.location.href.split('#')[0];
          const fullRel = joinUrlPath(getDocsifyBasePath(), rel);
          try {
            return new URL(fullRel, baseHref).toString();
          } catch {
            return null;
          }
        };

        const downloadJson = (filename, data) => {
          const blob = new Blob([JSON.stringify(data, null, 2)], {
            type: 'application/json;charset=utf-8',
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 500);
        };

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
          const childUl = li.querySelector(':scope > ul');
          const directLink = li.querySelector(':scope > a');
          if (!childUl || directLink) return;

          // 取日期文本：
          // - 初次：li 的第一个文本节点
          // - 已初始化过：wrapper 内的 label
          let rawText = '';
          let firstTextNode = null;
          const first = li.firstChild;
          if (first && first.nodeType === Node.TEXT_NODE) {
            rawText = (first.textContent || '').trim();
            firstTextNode = first;
          } else {
            const label = li.querySelector(
              ':scope > .sidebar-day-toggle .sidebar-day-toggle-label',
            );
            rawText = (label && (label.textContent || '').trim()) || '';
          }

          const rangeMatch = rawText.match(
            /^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$/,
          );
          const isSingleDay = /^\d{4}-\d{2}-\d{2}$/.test(rawText);
          if (!isSingleDay && !rangeMatch) return;

          const dayKey = rangeMatch ? rangeMatch[2] : rawText; // 用区间“结束日”参与最新日判断

          dayItems.push({ li, text: rawText, firstTextNode, dayKey });
          if (!latestDay || dayKey > latestDay) {
            latestDay = dayKey;
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

        const DAY_ANIM_MS = 240;

        const setDayCollapsed = (li, collapsed, options = {}) => {
          const { animate = true } = options || {};
          const ul = li.querySelector(':scope > ul');
          if (!ul) return;
          ul.classList.add('sidebar-day-content');

          const doAnimate = animate && !prefersReducedMotion();
          if (!doAnimate) {
            ul.style.transition = 'none';
            ul.style.maxHeight = collapsed ? '0px' : `${ul.scrollHeight}px`;
            ul.style.opacity = collapsed ? '0' : '1';
            requestAnimationFrame(() => {
              ul.style.transition = '';
            });
            return;
          }

          if (collapsed) {
            ul.style.maxHeight = `${ul.scrollHeight}px`;
            ul.style.opacity = '0';
            requestAnimationFrame(() => {
              ul.style.maxHeight = '0px';
            });
          } else {
            ul.style.opacity = '1';
            ul.style.maxHeight = '0px';
            requestAnimationFrame(() => {
              ul.style.maxHeight = `${ul.scrollHeight}px`;
            });
          }

          setTimeout(() => {
            try {
              if (!li.classList.contains('sidebar-day-collapsed')) {
                ul.style.maxHeight = `${ul.scrollHeight}px`;
              }
            } catch {
              // ignore
            }
          }, DAY_ANIM_MS + 30);
        };

        // 第二遍：真正安装折叠行为
        dayItems.forEach(({ li, text: rawText, firstTextNode, dayKey }) => {
          const childUl = li.querySelector(':scope > ul');
          if (childUl) childUl.classList.add('sidebar-day-content');
          const key = dayKey || rawText;

          // 复用或创建 wrapper（包含日期文字和小箭头）
          let wrapper = li.querySelector(':scope > .sidebar-day-toggle');
          if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'sidebar-day-toggle';

            const labelSpan = document.createElement('span');
            labelSpan.className = 'sidebar-day-toggle-label';
            labelSpan.textContent = rawText;

            const downloadBtn = document.createElement('button');
            downloadBtn.type = 'button';
            downloadBtn.className = 'sidebar-day-download-btn';
            downloadBtn.title = '下载该日期分组下所有论文的元数据（JSON）';
            downloadBtn.setAttribute('aria-label', '下载论文元数据 JSON');
            downloadBtn.textContent = 'JSON';

            const arrowSpan = document.createElement('span');
            arrowSpan.className = 'sidebar-day-toggle-arrow';
            arrowSpan.textContent = '▾';

            const actions = document.createElement('span');
            actions.className = 'sidebar-day-toggle-actions';
            actions.appendChild(downloadBtn);
            actions.appendChild(arrowSpan);

            wrapper.appendChild(labelSpan);
            wrapper.appendChild(actions);

            // 用 wrapper 替换原始文本节点
            if (firstTextNode && firstTextNode.parentNode === li) {
              li.replaceChild(wrapper, firstTextNode);
            }
          }

          const labelSpan = wrapper.querySelector('.sidebar-day-toggle-label');
          if (labelSpan) labelSpan.textContent = rawText;
          const arrowSpan = wrapper.querySelector('.sidebar-day-toggle-arrow');
          const downloadBtn = wrapper.querySelector('.sidebar-day-download-btn');

          if (downloadBtn && !downloadBtn.dataset.dprDownloadBound) {
            downloadBtn.dataset.dprDownloadBound = '1';
            downloadBtn.addEventListener(
              'click',
              async (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                if (downloadBtn.disabled) return;

                const date8 = getDate8FromDayLi(li, dayKey || rawText);
                const indexUrl = buildDayIndexJsonUrl(date8);
                if (!indexUrl) {
                  console.warn('[DPR Export] 无法解析索引 JSON 路径：', {
                    rawText,
                    dayKey,
                    date8,
                  });
                  return;
                }

                downloadBtn.disabled = true;
                const oldText = downloadBtn.textContent;
                downloadBtn.textContent = '...';
                try {
                  const resp = await fetch(indexUrl, { cache: 'no-store' });
                  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                  const payload = await resp.json();
                  window.DPRLastDayExport = payload;

                  const safeLabel = String(rawText || payload.label || 'daily-papers')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .replace(/[^\d\-~_ ]/g, '')
                    .replace(/\s+/g, '_');
                  const filename = `${safeLabel || 'daily-papers'}.json`;
                  downloadJson(filename, payload);

                  downloadBtn.title = `已下载：${payload && payload.count ? payload.count : 0} 篇`;
                } catch (err) {
                  downloadBtn.title = `下载失败（见控制台）：${String(err && err.message ? err.message : err)}`;
                  console.warn('[DPR Export] 下载失败：', err);
                } finally {
                  downloadBtn.disabled = false;
                  downloadBtn.textContent = oldText || 'JSON';
                }
              },
              true,
            );
          }

          // 决定默认展开 / 收起：
          // - 如果本次是“出现了新的一天”：清空历史，只展开最新一天；
          // - 否则若已有用户偏好（state），按偏好来；
          // - 否则（首次使用且没有历史）：仅“最新一天”展开，其余收起。
          let collapsed;
          if (isNewDay) {
            collapsed = key === latestDay ? false : true;
          } else if (hasAnyState) {
            const saved = state[rawText];
            if (saved === 'open') {
              collapsed = false;
            } else if (saved === 'closed') {
              collapsed = true;
            } else {
              // 新出现的日期：默认跟最新一天策略走
              collapsed = key === latestDay ? false : true;
            }
          } else {
            collapsed = key === latestDay ? false : true;
          }

          if (collapsed) {
            li.classList.add('sidebar-day-collapsed');
            if (arrowSpan) arrowSpan.textContent = '▸';
          } else {
            li.classList.remove('sidebar-day-collapsed');
            if (arrowSpan) arrowSpan.textContent = '▾';
          }

          // 初始化一次高度（不做动画，避免首次渲染闪动）
          setDayCollapsed(li, collapsed, { animate: false });

          // 绑定点击：使用 capture 阶段，确保即使旧版本已有 handler 也能覆盖
          if (!wrapper.dataset.dprDayToggleBound) {
            wrapper.dataset.dprDayToggleBound = '1';
            wrapper.addEventListener(
              'click',
              (e) => {
                // 点击“下载 JSON”按钮时，不触发日期折叠（否则 capture 阶段会先被 wrapper 拦截，导致按钮无响应）
                try {
                  const target = e && e.target && e.target.closest
                    ? e.target.closest('.sidebar-day-download-btn')
                    : null;
                  if (target) return;
                } catch {
                  // ignore
                }
                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                const collapsed = li.classList.toggle('sidebar-day-collapsed');
                if (arrowSpan) arrowSpan.textContent = collapsed ? '▸' : '▾';
                setDayCollapsed(li, collapsed, { animate: true });
                state[rawText] = collapsed ? 'closed' : 'open';
                state.__latestDay = latestDay;
                ensureStateSaved();
                // 先做一次即时同步（保证交互反馈），再在动画结束后做一次终态校准，
                // 否则列表在 max-height 过渡中继续位移，会让高亮条“越开越往上偏”。
                requestAnimationFrame(() => {
                  syncSidebarActiveIndicator({ animate: false });
                });
                setTimeout(() => {
                  syncSidebarActiveIndicator({ animate: false });
                }, DAY_ANIM_MS + 34);
              },
              true,
            );
          }

          li.dataset.dayToggleApplied = '2';
        });

        // 每次 doneEach 触发时都刷新一次“已展开分组”的 max-height：
        // 避免 active 项显示评价按钮等导致内容高度变化后被截断，从而出现“只有灰色高亮但看不到文字”的错觉。
        requestAnimationFrame(() => {
          try {
            nav
              .querySelectorAll('li:not(.sidebar-day-collapsed) > ul.sidebar-day-content')
              .forEach((ul) => {
                // 仅做“静默修正”，避免因为 max-height 变化触发过渡，导致侧边栏看起来“滚动/刷新”一下
                const prevTransition = ul.style.transition;
                ul.style.transition = 'none';
                ul.style.maxHeight = `${ul.scrollHeight}px`;
                ul.style.opacity = '1';
                requestAnimationFrame(() => {
                  ul.style.transition = prevTransition || '';
                });
              });
          } catch {
            // ignore
          }
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
            } else if (v === 'good' || v === 'bad' || v === 'blue' || v === 'orange') {
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

      // ---------- Share to GitHub Gist ----------
      const loadGithubTokenForGist = () => {
        try {
          const secret = window.decoded_secret_private || {};
          if (secret.github && secret.github.token) {
            const t = String(secret.github.token || '').trim();
            if (t) return t;
          }
        } catch {
          // ignore
        }
        try {
          if (!window.localStorage) return null;
          const raw = window.localStorage.getItem('github_token_data');
          if (!raw) return null;
          const obj = JSON.parse(raw) || {};
          const t = String(obj.token || '').trim();
          return t || null;
        } catch {
          return null;
        }
      };

      const joinUrlPath = (a, b) => {
        const aa = String(a || '');
        const bb = String(b || '');
        if (!aa) return bb.replace(/^\/+/, '');
        if (!bb) return aa;
        const left = aa.endsWith('/') ? aa : `${aa}/`;
        const right = bb.replace(/^\/+/, '');
        return `${left}${right}`;
      };

      const getDocsifyBasePath = () => {
        const bp =
          window.$docsify && typeof window.$docsify.basePath === 'string'
            ? window.$docsify.basePath
            : 'docs/';
        return String(bp || 'docs/');
      };

      const buildDocsUrl = (rel) => {
        try {
          const baseHref = window.location.href.split('#')[0];
          return new URL(rel, baseHref).toString();
        } catch {
          return rel;
        }
      };

      const fetchPaperMarkdownById = async (paperId) => {
        const rel = joinUrlPath(getDocsifyBasePath(), `${paperId}.md`);
        const url = buildDocsUrl(rel);
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) throw new Error(`无法读取文章 Markdown（HTTP ${res.status}）`);
        return await res.text();
      };

      const loadChatHistoryForPaper = async (paperId) => {
        if (!paperId) return [];
        // IndexedDB 优先：dpr_chat_db_v1 / paper_chats
        if (typeof indexedDB !== 'undefined') {
          try {
            const db = await new Promise((resolve) => {
              const req = indexedDB.open('dpr_chat_db_v1', 1);
              req.onupgradeneeded = (e) => {
                const d = e.target.result;
                if (!d.objectStoreNames.contains('paper_chats')) {
                  d.createObjectStore('paper_chats', { keyPath: 'paperId' });
                }
              };
              req.onsuccess = (e) => resolve(e.target.result);
              req.onerror = () => resolve(null);
            });
            if (db) {
              return await new Promise((resolve) => {
                try {
                  const tx = db.transaction('paper_chats', 'readonly');
                  const store = tx.objectStore('paper_chats');
                  const r = store.get(paperId);
                  r.onsuccess = () => {
                    const rec = r.result;
                    resolve(rec && Array.isArray(rec.messages) ? rec.messages : []);
                  };
                  r.onerror = () => resolve([]);
                } catch {
                  resolve([]);
                }
              });
            }
          } catch {
            // ignore
          }
        }
        // 兜底：旧版 localStorage
        try {
          if (!window.localStorage) return [];
          const raw = window.localStorage.getItem('dpr_chat_history_v1');
          if (!raw) return [];
          const obj = JSON.parse(raw) || {};
          const list = obj[paperId];
          return Array.isArray(list) ? list : [];
        } catch {
          return [];
        }
      };

      const buildShareMarkdown = (paperId, pageMd, chatMessages) => {
        const parts = [];
        parts.push(`<!-- Shared by Daily Paper Reader -->`);
        parts.push(``);
        parts.push(`原始页面：${String(window.location.origin || '')}/#/${paperId}`);
        parts.push(`生成时间：${new Date().toISOString()}`);
        parts.push(``);
        parts.push(`---`);
        parts.push(``);
        parts.push(pageMd || '');
        parts.push(``);
        parts.push(`---`);
        parts.push(``);
        parts.push(`## 💬 Chat History（本机记录）`);
        parts.push(``);
        if (!chatMessages || !chatMessages.length) {
          parts.push(`暂无对话。`);
          return parts.join('\n');
        }
        chatMessages.forEach((m) => {
          const role = m && m.role ? String(m.role) : 'unknown';
          const time = m && m.time ? String(m.time) : '';
          const content = m && m.content ? String(m.content) : '';
          if (role === 'thinking') {
            parts.push(`<details>`);
            parts.push(`<summary>🧠 思考过程 ${time ? `(${time})` : ''}</summary>`);
            parts.push(``);
            parts.push('```');
            parts.push(content);
            parts.push('```');
            parts.push(`</details>`);
            parts.push(``);
            return;
          }
          const label = role === 'ai' ? '🤖 AI' : role === 'user' ? '👤 你' : role;
          parts.push(`### ${label}${time ? ` (${time})` : ''}`);
          parts.push(content);
          parts.push(``);
        });
        return parts.join('\n');
      };

      const ensureShareModal = () => {
        let overlay = document.getElementById('dpr-gist-share-overlay');
        if (overlay) return overlay;
        overlay = document.createElement('div');
        overlay.id = 'dpr-gist-share-overlay';
        overlay.innerHTML = `
          <div class="dpr-gist-share-modal" role="dialog" aria-modal="true">
            <div class="dpr-gist-share-title">分享链接</div>
            <div class="dpr-gist-share-row">
              <input class="dpr-gist-share-input" type="text" readonly />
              <button class="dpr-gist-share-copy" type="button">复制</button>
            </div>
            <div class="dpr-gist-share-hint"></div>
          </div>
        `;
        overlay.addEventListener('pointerdown', (e) => {
          // 点空白处关闭
          if (e && e.target === overlay) {
            overlay.classList.remove('show');
          }
        });
        document.addEventListener('keydown', (e) => {
          if (e && e.key === 'Escape') overlay.classList.remove('show');
        });
        document.body.appendChild(overlay);

        const copyBtn = overlay.querySelector('.dpr-gist-share-copy');
        if (copyBtn) {
          copyBtn.addEventListener('click', async () => {
            const input = overlay.querySelector('.dpr-gist-share-input');
            const v = input ? String(input.value || '') : '';
            if (!v) return;
            try {
              if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(v);
              } else {
                input.focus();
                input.select();
                document.execCommand('copy');
              }
              const hint = overlay.querySelector('.dpr-gist-share-hint');
              if (hint) hint.textContent = '已复制';
            } catch {
              const hint = overlay.querySelector('.dpr-gist-share-hint');
              if (hint) hint.textContent = '复制失败，请手动复制';
            }
          });
        }
        return overlay;
      };

      const showShareModal = (url, hintText) => {
        const overlay = ensureShareModal();
        const input = overlay.querySelector('.dpr-gist-share-input');
        const hint = overlay.querySelector('.dpr-gist-share-hint');
        if (input) input.value = url || '';
        if (hint) hint.textContent = hintText || '';
        overlay.classList.add('show');
      };

      const createGist = async (token, filename, content) => {
        const res = await fetch('https://api.github.com/gists', {
          method: 'POST',
          headers: {
            Authorization: `token ${token}`,
            Accept: 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            description: '论文分享（Daily Paper Reader）',
            public: false,
            files: {
              [filename]: { content },
            },
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = data && data.message ? String(data.message) : '';
          // GitHub 对不支持/无权限的 token（尤其是 fine-grained PAT 不支持 Gist）经常返回 404 Not Found
          if (res.status === 404) {
            throw new Error(
              'Not Found（常见原因：你用的是 Fine-grained PAT，GitHub Gist API 不支持；请改用 Classic PAT 并勾选 gist 权限）',
            );
          }
          if (res.status === 401) {
            throw new Error('未授权（Token 无效或已过期）');
          }
          if (res.status === 403) {
            throw new Error(
              `权限不足（需要 Classic PAT 勾选 gist 权限）。${msg ? `详情：${msg}` : ''}`.trim(),
            );
          }
          throw new Error(msg || `HTTP ${res.status}`);
        }
        return data;
      };

      const sharePaperToGist = async (paperId) => {
        const token = loadGithubTokenForGist();
        if (!token) {
          showShareModal('', '未检测到 GitHub Token，请先在首页配置 GitHub Token。');
          return;
        }
        const pageMd = await fetchPaperMarkdownById(paperId);
        const chat = await loadChatHistoryForPaper(paperId);
        const content = buildShareMarkdown(paperId, pageMd, chat);

        // 文件名：paperId 最后一段 + .md
        const slug = String(paperId || 'paper').split('/').slice(-1)[0] || 'paper';
        const filename = `${slug}.md`;
        const data = await createGist(token, filename, content);
        const url = data && data.html_url ? String(data.html_url) : '';
        const preview = data && data.id ? `https://gist.io/${data.id}` : '';
        showShareModal(url, preview ? `精美预览：${preview}` : '');
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
            'sidebar-paper-blue',
            'sidebar-paper-orange',
          );
          if (status === 'good') {
            li.classList.add('sidebar-paper-good');
          } else if (status === 'bad') {
            li.classList.add('sidebar-paper-bad');
          } else if (status === 'blue') {
            li.classList.add('sidebar-paper-blue');
          } else if (status === 'orange') {
            li.classList.add('sidebar-paper-orange');
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

          // 为侧边栏条目追加"书签标记"按钮（绿/蓝/橙/红）
	          let actionWrapper = li.querySelector('.sidebar-paper-rating-icons');
	          let goodIcon = actionWrapper
	            ? actionWrapper.querySelector('.sidebar-paper-rating-icon.good')
	            : null;
            let blueIcon = actionWrapper
              ? actionWrapper.querySelector('.sidebar-paper-rating-icon.blue')
              : null;
            let orangeIcon = actionWrapper
              ? actionWrapper.querySelector('.sidebar-paper-rating-icon.orange')
              : null;
	          let badIcon = actionWrapper
	            ? actionWrapper.querySelector('.sidebar-paper-rating-icon.bad')
	            : null;

          // 左侧按钮容器（分享 + 收藏）
          let leftActions = li.querySelector('.sidebar-paper-left-actions');
	          if (!actionWrapper) {
	            actionWrapper = document.createElement('span');
	            actionWrapper.className = 'sidebar-paper-rating-icons';

	            goodIcon = document.createElement('button');
	            goodIcon.className = 'sidebar-paper-rating-icon good';
	            goodIcon.title = '标记为「绿色书签」';
	            goodIcon.setAttribute('aria-label', '绿色书签');
	            goodIcon.innerHTML = '';

              blueIcon = document.createElement('button');
              blueIcon.className = 'sidebar-paper-rating-icon blue';
              blueIcon.title = '标记为「蓝色书签」';
              blueIcon.setAttribute('aria-label', '蓝色书签');
              blueIcon.innerHTML = '';

              orangeIcon = document.createElement('button');
              orangeIcon.className = 'sidebar-paper-rating-icon orange';
              orangeIcon.title = '标记为「橙色书签」';
              orangeIcon.setAttribute('aria-label', '橙色书签');
              orangeIcon.innerHTML = '';

	            badIcon = document.createElement('button');
	            badIcon.className = 'sidebar-paper-rating-icon bad';
	            badIcon.title = '标记为「红色书签」';
	            badIcon.setAttribute('aria-label', '红色书签');
	            badIcon.innerHTML = '';

              // 创建左侧按钮容器
              leftActions = document.createElement('span');
              leftActions.className = 'sidebar-paper-left-actions';

              const favoriteIcon = document.createElement('button');
              favoriteIcon.className = 'sidebar-paper-favorite-icon';
              favoriteIcon.title = '收藏';
              favoriteIcon.setAttribute('aria-label', '收藏');
              favoriteIcon.textContent = '☆';
              favoriteIcon.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // 切换收藏状态（功能待实现）
                const isActive = favoriteIcon.classList.toggle('active');
                favoriteIcon.textContent = isActive ? '★' : '☆';
              });

              const shareIcon = document.createElement('button');
              shareIcon.className = 'sidebar-paper-share-icon';
              shareIcon.title = '分享（生成 GitHub Gist 链接）';
              shareIcon.setAttribute('aria-label', '分享');
              shareIcon.textContent = '⤴';

              const setStateAndRefresh = (value) => {
                const latestState = loadReadState();
                const current = latestState[paperIdFromHref];
                if (current === value) {
                  latestState[paperIdFromHref] = 'read';
                } else {
                  latestState[paperIdFromHref] = value;
                }
                saveReadState(latestState);
                markSidebarReadState(null);
                requestAnimationFrame(() => {
                  syncSidebarActiveIndicator({ animate: false });
                });
              };

	            goodIcon.addEventListener('click', (e) => {
	              e.preventDefault();
	              e.stopPropagation();
	              setStateAndRefresh('good');
	            });

              blueIcon.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                setStateAndRefresh('blue');
              });

              orangeIcon.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                setStateAndRefresh('orange');
              });

              shareIcon.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (shareIcon.disabled) return;
                const old = shareIcon.textContent;
                shareIcon.disabled = true;
                shareIcon.textContent = '...';
                try {
                  await sharePaperToGist(paperIdFromHref);
                } catch (err) {
                  const msg = String(err && err.message ? err.message : err);
                  showShareModal('', `上传失败：${msg}`);
                } finally {
                  shareIcon.disabled = false;
                  shareIcon.textContent = old || '⤴';
                }
              });

	            badIcon.addEventListener('click', (e) => {
	              e.preventDefault();
	              e.stopPropagation();
	              setStateAndRefresh('bad');
	            });

              // 左侧容器添加收藏和分享按钮
              leftActions.appendChild(favoriteIcon);
              leftActions.appendChild(shareIcon);
              a.parentNode.insertBefore(leftActions, a);

              // 右侧容器添加书签按钮
	            actionWrapper.appendChild(goodIcon);
              actionWrapper.appendChild(blueIcon);
              actionWrapper.appendChild(orangeIcon);
	            actionWrapper.appendChild(badIcon);
	            a.parentNode.insertBefore(actionWrapper, a.nextSibling);
	          }

	          // 无论按钮是否刚创建，都要基于“最新 state”刷新激活态（支持空格键切换）
	          try {
	            const s = state[paperIdFromHref];
	            if (goodIcon) goodIcon.classList.toggle('active', s === 'good');
              if (blueIcon) blueIcon.classList.toggle('active', s === 'blue');
              if (orangeIcon) orangeIcon.classList.toggle('active', s === 'orange');
	            if (badIcon) badIcon.classList.toggle('active', s === 'bad');
	          } catch {
	            // ignore
	          }

	          applyLiState(li, paperIdFromHref);
	        });
	      };

      // 侧边栏/正文的论文页标题条：英文右侧，中文左侧，中间竖线
      const isPaperRouteFile = (file) => {
        const f = String(file || '');
        return /^(?:\d{6}\/\d{2}|\d{8}-\d{8})\/(?!README\.md$).+\.md$/i.test(f);
      };

      const isReportRouteFile = (file) => {
        const f = String(file || '');
        return /^(?:\d{6}\/\d{2}|\d{8}-\d{8})\/README\.md$/i.test(f);
      };

      const fitTextToBox = (el, minPx, maxPx) => {
        if (!el) return;
        let size = maxPx;
        el.style.fontSize = `${size}px`;
        // 逐步缩小直到不溢出或达到最小值
        // 注意：scrollHeight > clientHeight 表示溢出（包含被 line-clamp 截断的情况）
        while (size > minPx && el.scrollHeight > el.clientHeight + 1) {
          size -= 1;
          el.style.fontSize = `${size}px`;
        }
      };

      // 为切页动效准备一个“正文包装层”，避免把聊天浮层/白色遮罩一起做淡入淡出（否则会闪烁）
      const DPR_PAGE_CONTENT_CLASS = 'dpr-page-content';

      const ensurePageContentRoot = () => {
        const section = document.querySelector('.markdown-section');
        if (!section) return null;
        const existing = section.querySelector(
          `:scope > .${DPR_PAGE_CONTENT_CLASS}`,
        );
        if (existing) return existing;

        const root = document.createElement('div');
        root.className = DPR_PAGE_CONTENT_CLASS;
        // 将当前渲染出来的正文内容整体移入 root（此时 chat 模块尚未插入，避免把输入框一起移入）
        while (section.firstChild) {
          root.appendChild(section.firstChild);
        }
        section.appendChild(root);
        return root;
      };

      const getPageAnimEl = () => {
        const section = document.querySelector('.markdown-section');
        if (!section) return null;
        return (
          section.querySelector(`:scope > .${DPR_PAGE_CONTENT_CLASS}`) || section
        );
      };

      const applyPaperTitleBar = () => {
        const file = vm && vm.route ? vm.route.file : '';
        if (!isPaperRouteFile(file)) {
          document.body.classList.remove('dpr-paper-page');
          return;
        }
        document.body.classList.add('dpr-paper-page');

        const section = document.querySelector('.markdown-section');
        if (!section) return;
        const root =
          section.querySelector(`:scope > .${DPR_PAGE_CONTENT_CLASS}`) || section;

        // 防止重复插入
        const existing = root.querySelector('.dpr-title-bar');
        if (existing) existing.remove();
        const h1s = Array.from(root.querySelectorAll('h1'));
        if (!h1s.length) return;

        // 优先从带有 paper-title-zh / paper-title-en 类名的 h1 中获取标题（frontmatter 渲染）
        const paperTitleZh = root.querySelector('h1.paper-title-zh');
        const paperTitleEn = root.querySelector('h1.paper-title-en');

        let cnTitle = '';
        let enTitle = '';

        if (paperTitleZh || paperTitleEn) {
          // 新格式：从 frontmatter 渲染的带类名 h1 中获取
          cnTitle = paperTitleZh ? (paperTitleZh.textContent || '').trim() : '';
          enTitle = paperTitleEn ? (paperTitleEn.textContent || '').trim() : '';
        } else {
          // 旧格式兼容：如果有两个 h1，则第一个为英文、第二个为中文；
          // 如果只有一个 h1，则认为是"单标题"，放在左侧（cn 区）
          enTitle = (h1s[0].textContent || '').trim();
          cnTitle = (h1s[1] ? (h1s[1].textContent || '').trim() : '').trim();
          if (h1s.length === 1) {
            cnTitle = enTitle;
            enTitle = '';
          }
        }

        // 兜底：若只有英文标题（缺少 title_zh），将英文挪到左侧显示，
        // 避免 dpr-title-single 样式把右侧英文区域隐藏后出现“无标题”。
        if (!cnTitle && enTitle) {
          cnTitle = enTitle;
          enTitle = '';
        }

        // 隐藏原始 h1，但保留在 DOM 里供复制/SEO/元信息提取兜底
        h1s.forEach((h) => h.classList.add('dpr-title-hidden'));

        const bar = document.createElement('div');
        bar.className = 'dpr-title-bar';
        bar.innerHTML = `
          <div class="dpr-title-cn">${escapeHtml(cnTitle || '')}</div>
          <div class="dpr-title-sep" aria-hidden="true"></div>
          <div class="dpr-title-en">${escapeHtml(enTitle || '')}</div>
        `;
        if (!cnTitle) {
          bar.classList.add('dpr-title-single');
        }

        root.insertBefore(bar, root.firstChild);

        // 字体自适应：让标题条高度稳定，长标题自动缩小
        requestAnimationFrame(() => {
          const cnEl = bar.querySelector('.dpr-title-cn');
          const enEl = bar.querySelector('.dpr-title-en');
          if (cnEl && cnTitle) fitTextToBox(cnEl, 14, 22);
          if (enEl && enTitle) fitTextToBox(enEl, 13, 20);
        });
      };

      // 论文页导航：左右滑动 / 键盘方向键切换论文
      const DPR_NAV_STATE = {
        paperHrefs: [],
        reportHrefs: [],
        currentHref: '',
        currentReportHref: '',
        lastNavTs: 0,
        lastNavSource: '', // 'click' | 'key' | 'wheel' | 'swipe' | ''
      };

      const DPR_SIDEBAR_CENTER_STATE = {
        lastHref: '',
        lastTs: 0,
      };

      const DPR_SIDEBAR_ACTIVE_INDICATOR = {
        el: null,
        parent: null,
        justMoved: false,
      };

      const getSidebarScrollEl = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return null;
        const candidates = [
          nav,
          nav.closest('.sidebar'),
          nav.parentElement,
          document.querySelector('.sidebar'),
        ].filter(Boolean);
        for (const el of candidates) {
          try {
            if (el.scrollHeight > el.clientHeight + 4) return el;
          } catch {
            // ignore
          }
        }
        return nav;
      };

      const ensureSidebarActiveIndicator = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return null;

        if (
          DPR_SIDEBAR_ACTIVE_INDICATOR.el &&
          DPR_SIDEBAR_ACTIVE_INDICATOR.parent === nav &&
          nav.contains(DPR_SIDEBAR_ACTIVE_INDICATOR.el)
        ) {
          return { el: DPR_SIDEBAR_ACTIVE_INDICATOR.el, newlyCreated: false };
        }

        // 清理旧的（例如热更新/重复初始化场景）
        try {
          if (DPR_SIDEBAR_ACTIVE_INDICATOR.el && DPR_SIDEBAR_ACTIVE_INDICATOR.el.remove) {
            DPR_SIDEBAR_ACTIVE_INDICATOR.el.remove();
          }
        } catch {
          // ignore
        }

        const indicator = document.createElement('div');
        indicator.className = 'dpr-sidebar-active-indicator';
        indicator.setAttribute('aria-hidden', 'true');
        // 刚创建时先禁用 transition，避免出现“从 sidebar 顶部滑下来”的二次动效
        indicator.style.transition = 'none';
        // 放在最前面，确保在所有 li 下面
        nav.insertBefore(indicator, nav.firstChild);
        DPR_SIDEBAR_ACTIVE_INDICATOR.el = indicator;
        DPR_SIDEBAR_ACTIVE_INDICATOR.parent = nav;
        return { el: indicator, newlyCreated: true };
      };

      const hideSidebarActiveIndicator = () => {
        const ensured = ensureSidebarActiveIndicator();
        if (!ensured || !ensured.el) return;
        const indicator = ensured.el;
        // 避免后续复用时残留 good/bad 配色
        indicator.classList.remove('is-good', 'is-bad', 'is-blue', 'is-orange');
        indicator.style.opacity = '0';
        indicator.style.width = '0';
        indicator.style.height = '0';
      };

      const showSidebarActiveIndicator = () => {
        const ensured = ensureSidebarActiveIndicator();
        if (!ensured || !ensured.el) return;
        ensured.el.style.opacity = '1';
      };

      const isSidebarItemVisible = (el) => {
        try {
          if (!el) return false;
          // display:none / 被折叠时 offsetParent 会是 null
          if (el.offsetParent === null) return false;
          const rect = el.getBoundingClientRect();
          return rect && rect.width > 0 && rect.height > 0;
        } catch {
          return false;
        }
      };

      const moveSidebarActiveIndicatorToEl = (li, options = {}) => {
        if (!li) return;
        const { animate = true } = options || {};
        const ensured = ensureSidebarActiveIndicator();
        if (!ensured || !ensured.el) return;
        const indicator = ensured.el;
        const newlyCreated = ensured.newlyCreated;

        // 先清空上一条目的配色状态，避免出现“取消勾选/叉选后仍残留底色”
        try {
          indicator.classList.remove('is-good', 'is-bad', 'is-blue', 'is-orange');
        } catch {
          // ignore
        }

        // 只对论文条目启用（避免日期分组标题等）
        if (!li.classList || !li.classList.contains('sidebar-paper-item')) return;
        // 若该条目在“折叠的日期”之下：隐藏高亮层，避免折叠后仍残留选中背景
        try {
          if (li.closest && li.closest('li.sidebar-day-collapsed')) {
            hideSidebarActiveIndicator();
            return;
          }
        } catch {
          // ignore
        }
        if (!isSidebarItemVisible(li)) {
          hideSidebarActiveIndicator();
          return;
        }

        showSidebarActiveIndicator();

        // 选中高亮层配色：根据 good/bad 状态切换（用于“已打勾/打叉”的选中底色）
        try {
          const isGood =
            li.classList && li.classList.contains('sidebar-paper-good');
          const isBad = li.classList && li.classList.contains('sidebar-paper-bad');
          const isBlue =
            li.classList && li.classList.contains('sidebar-paper-blue');
          const isOrange =
            li.classList && li.classList.contains('sidebar-paper-orange');

          // 单选：如果同时存在（理论上不应发生），按优先级取第一个
          const any = isGood || isBad || isBlue || isOrange;
          indicator.classList.toggle('is-good', !!isGood && any && !isBad && !isBlue && !isOrange);
          indicator.classList.toggle('is-bad', !!isBad && any && !isGood && !isBlue && !isOrange);
          indicator.classList.toggle('is-blue', !!isBlue && any && !isGood && !isBad && !isOrange);
          indicator.classList.toggle('is-orange', !!isOrange && any && !isGood && !isBad && !isBlue);
        } catch {
          // ignore
        }

        // 不能用 offsetTop/offsetLeft：
        // 侧边栏是多层嵌套 li/ul，offset* 参照系会落在中间层，导致越往下选中偏移越明显。
        // 统一使用相对 .sidebar-nav 的几何坐标，保证展开多天后仍准确对齐。
        const nav = ensured.parent || (li.closest && li.closest('.sidebar-nav'));
        const navRect = nav ? nav.getBoundingClientRect() : null;
        const liRect = li.getBoundingClientRect();
        const x = navRect ? liRect.left - navRect.left + (nav.scrollLeft || 0) : li.offsetLeft;
        const y = navRect ? liRect.top - navRect.top + (nav.scrollTop || 0) : li.offsetTop;
        const w = liRect.width || li.offsetWidth;
        const h = liRect.height || li.offsetHeight;

        // 新建/或要求不动画时：先关 transition，直接定位到最终位置，再恢复 transition
        if (newlyCreated || !animate) {
          indicator.style.transition = 'none';
        }

        indicator.style.width = `${w}px`;
        indicator.style.height = `${h}px`;
        indicator.style.transform = `translate3d(${x}px, ${y}px, 0)`;

        if (newlyCreated || !animate) {
          requestAnimationFrame(() => {
            indicator.style.transition = '';
          });
        }
      };

      const moveSidebarActiveIndicatorToHref = (href, options = {}) => {
        const targetHref = normalizeHref(href);
        if (!targetHref) return;
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        const link = nav.querySelector(`a[href="${targetHref}"]`);
        if (!link) return;
        const li = link.closest('li');
        moveSidebarActiveIndicatorToEl(li, options);
      };

      const syncSidebarActiveIndicator = (options = {}) => {
        const { animate = false } = options || {};
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        // 1) 优先按“当前路由 href”精确匹配，避免 Docsify 多个 active 时命中错误项
        const routeHref = DPR_NAV_STATE.currentHref || '';
        if (routeHref) {
          const links = Array.from(nav.querySelectorAll('a[href]'));
          for (let i = 0; i < links.length; i += 1) {
            const a = links[i];
            const href = normalizeHref(a.getAttribute('href') || '');
            if (href !== routeHref) continue;
            const li = a.closest('li');
            if (li && li.classList && li.classList.contains('sidebar-paper-item')) {
              moveSidebarActiveIndicatorToEl(li, { animate });
              return;
            }
          }
        }

        // 2) 兜底：如果存在多个 active，取最后一个（通常是更深层、当前真正选中项）
        const activeLis = Array.from(
          nav.querySelectorAll('li.active.sidebar-paper-item'),
        );
        if (activeLis.length > 0) {
          moveSidebarActiveIndicatorToEl(activeLis[activeLis.length - 1], {
            animate,
          });
          return;
        }

        hideSidebarActiveIndicator();
      };

      // 暴露到全局，供 sidebar resize 时调用
      window.syncSidebarActiveIndicator = syncSidebarActiveIndicator;

      const DPR_TRANSITION = {
        // 'enter-from-left' | 'enter-from-right' | ''
        pendingEnter: '',
      };

      const decodeLegacyIdHash = (rawHash) => {
        const raw = String(rawHash || '').trim();
        if (!raw) return '';
        // 兼容 Docsify 旧式 hash：#/?id=%2f202602%2f06%2fxxx 或 #?id=/202602/06/xxx
        const m = raw.match(/^#\/?\?id=([^&]+)(?:&.*)?$/i);
        if (!m) return '';
        let decoded = '';
        try {
          decoded = decodeURIComponent(m[1] || '');
        } catch {
          decoded = m[1] || '';
        }
        decoded = String(decoded || '').trim();
        if (!decoded) return '';
        // 统一为无 .md 的路由形式
        decoded = decoded.replace(/\.md$/i, '');
        if (!decoded.startsWith('/')) decoded = '/' + decoded;
        return '#'+ decoded;
      };

      const normalizeHref = (href) => {
        const raw = String(href || '').trim();
        if (!raw) return '';
        const legacy = decodeLegacyIdHash(raw);
        if (legacy) return legacy;
        // 统一成 "#/xxxx" 形式
        if (raw.startsWith('#/')) return raw;
        if (raw.startsWith('#')) return '#/' + raw.slice(1).replace(/^\//, '');
        return '#/' + raw.replace(/^\//, '');
      };

      const isPaperHref = (href) => {
        const h = normalizeHref(href);
        // 只匹配论文页：#/YYYYMM/DD/slug
        return /^#\/\d{6}\/\d{2}\/(?!README$).+/i.test(h);
      };

      const isReportHref = (href) => {
        const h = normalizeHref(href);
        return /^#\/\d{6}\/\d{2}\/README$/i.test(h);
      };

      const collectPaperHrefsFromSidebar = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return [];
        const links = Array.from(nav.querySelectorAll('a[href]'));
        const out = [];
        const seen = new Set();
        links.forEach((a) => {
          const href = a.getAttribute('href') || '';
          if (!isPaperHref(href)) return;
          const norm = normalizeHref(href);
          if (seen.has(norm)) return;
          seen.add(norm);
          out.push(norm);
        });
        return out;
      };

      const collectReportHrefsFromSidebar = () => {
        const links = [];
        const nav = document.querySelector('.sidebar-nav');
        if (nav) {
          links.push(...Array.from(nav.querySelectorAll('a[href]')));
        }
        const main = document.querySelector('.markdown-section');
        if (main) {
          links.push(...Array.from(main.querySelectorAll('a[href]')));
        }
        const out = [];
        const seen = new Set();
        links.forEach((a) => {
          const href = a.getAttribute('href') || '';
          if (!isReportHref(href)) return;
          const norm = normalizeHref(href);
          if (seen.has(norm)) return;
          seen.add(norm);
          out.push(norm);
        });
        return out;
      };

      const updateNavState = () => {
        DPR_NAV_STATE.paperHrefs = collectPaperHrefsFromSidebar();
        DPR_NAV_STATE.reportHrefs = collectReportHrefsFromSidebar();
        const file = vm && vm.route ? vm.route.file : '';
        if (file && isPaperRouteFile(file)) {
          DPR_NAV_STATE.currentHref = normalizeHref('#/' + String(file).replace(/\.md$/i, ''));
        } else {
          DPR_NAV_STATE.currentHref = '';
        }
        if (file && isReportRouteFile(file)) {
          DPR_NAV_STATE.currentReportHref = normalizeHref('#/' + String(file).replace(/\.md$/i, ''));
        } else {
          DPR_NAV_STATE.currentReportHref = '';
        }
      };

      const centerSidebarOnHref = (href) => {
        const targetHref = normalizeHref(href);
        if (!targetHref) return;
        if (targetHref === DPR_SIDEBAR_CENTER_STATE.lastHref) return;
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const link =
          nav.querySelector(`a[href="${targetHref}"]`) ||
          nav.querySelector(`a[href="${targetHref.replace(/^#\//, '#/')}"]`);
        if (!link) return;

        const item = link.closest('li') || link;
        const scrollEl = getSidebarScrollEl();
        if (!scrollEl || scrollEl.scrollHeight <= scrollEl.clientHeight + 4) {
          DPR_SIDEBAR_CENTER_STATE.lastHref = targetHref;
          return;
        }

        const scrollRect = scrollEl.getBoundingClientRect();
        const itemRect = item.getBoundingClientRect();

        const currentTop = scrollEl.scrollTop;
        const deltaTop = itemRect.top - scrollRect.top;
        const targetTop =
          currentTop + deltaTop - (scrollRect.height / 2 - itemRect.height / 2);

        const clamped = Math.max(
          0,
          Math.min(targetTop, scrollEl.scrollHeight - scrollEl.clientHeight),
        );

        DPR_SIDEBAR_CENTER_STATE.lastTs = Date.now();
        DPR_SIDEBAR_CENTER_STATE.lastHref = targetHref;

        // 居中时只需要“滚动”动画，不做额外高亮动画
        const duration = prefersReducedMotion() ? 0 : DPR_TRANSITION_MS;
        animateScrollTop(scrollEl, clamped, duration);
      };

      const centerSidebarOnCurrent = () => {
        // 优先跟随 Docsify 的“active”状态（这才是你看到的选中项）
        const nav = document.querySelector('.sidebar-nav');
        if (nav) {
          const activeLi = nav.querySelector('li.active');
          const activeLink = nav.querySelector('a.active');
          const el = activeLi || activeLink;
          if (el) {
            const href = (activeLink && activeLink.getAttribute('href')) || '';
            // 如果拿得到 href，就走 href 去重；否则用一个稳定的占位 key
            const key = href ? normalizeHref(href) : '__active__';
            if (key && key === DPR_SIDEBAR_CENTER_STATE.lastHref) return;

            const scrollEl = getSidebarScrollEl();
            if (!scrollEl) return;

            const scrollRect = scrollEl.getBoundingClientRect();
            const itemRect = el.getBoundingClientRect();

            const currentTop = scrollEl.scrollTop;
            const deltaTop = itemRect.top - scrollRect.top;
            const targetTop =
              currentTop +
              deltaTop -
              (scrollRect.height / 2 - itemRect.height / 2);

            const clamped = Math.max(
              0,
              Math.min(targetTop, scrollEl.scrollHeight - scrollEl.clientHeight),
            );

            DPR_SIDEBAR_CENTER_STATE.lastTs = Date.now();
            DPR_SIDEBAR_CENTER_STATE.lastHref = key;

            const duration = prefersReducedMotion() ? 0 : DPR_TRANSITION_MS;
            animateScrollTop(scrollEl, clamped, duration);
            return;
          }
        }

        // 兜底：按当前路由 href 匹配
        const href = DPR_NAV_STATE.currentHref || '';
        if (!href) return;
        centerSidebarOnHref(href);
      };

      const shouldIgnoreKeyNav = (event) => {
        if (!event) return true;
        if (event.defaultPrevented) return true;
        if (event.metaKey || event.ctrlKey || event.altKey) return true;
        const target = event.target;
        if (!target) return false;
        const tag = (target.tagName || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (target.isContentEditable) return true;
        return false;
      };

      const navigateByDelta = (delta) => {
        const paperList = DPR_NAV_STATE.paperHrefs || [];
        const reportList = DPR_NAV_STATE.reportHrefs || [];
        const now = Date.now();
        if (now - (DPR_NAV_STATE.lastNavTs || 0) < 450) return;
        DPR_NAV_STATE.lastNavTs = now;

        const current = DPR_NAV_STATE.currentHref;
        const currentReport = DPR_NAV_STATE.currentReportHref;
        const isHome = !current && !currentReport;
        const reportMode = isHome || !!currentReport;
        const list = reportMode ? reportList : paperList;
        if (!list.length) return;

        // 首页：右键/左滑（delta=+1）跳到最新一天第一篇
        if (isHome) {
          if (delta > 0) {
            triggerPageNav(list[0], 'forward');
          }
          return;
        }

        const anchor = reportMode ? currentReport : current;
        const idx = list.indexOf(anchor);
        if (idx === -1) return;
        const nextIdx = idx + delta;
        if (nextIdx < 0 || nextIdx >= list.length) return;
        triggerPageNav(list[nextIdx], delta > 0 ? 'forward' : 'backward');
      };

      const prefersReducedMotion = () => {
        try {
          return (
            window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches
          );
        } catch {
          return false;
        }
      };

      // 统一“sidebar 居中滚动”和“页面切换”的动画时长，确保观感一致
      const DPR_TRANSITION_MS = 320;
      try {
        document.documentElement.style.setProperty(
          '--dpr-transition-ms',
          `${DPR_TRANSITION_MS}ms`,
        );
      } catch {
        // ignore
      }

      const DPR_SIDEBAR_SCROLL_ANIM = {
        rafId: 0,
      };

      const easeInOutCubic = (t) => {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      };

      const animateScrollTop = (el, targetTop, durationMs) => {
        if (!el) return;

        try {
          if (DPR_SIDEBAR_SCROLL_ANIM.rafId) {
            cancelAnimationFrame(DPR_SIDEBAR_SCROLL_ANIM.rafId);
            DPR_SIDEBAR_SCROLL_ANIM.rafId = 0;
          }
        } catch {
          // ignore
        }

        const to = Math.max(
          0,
          Math.min(targetTop, el.scrollHeight - el.clientHeight),
        );
        const from = el.scrollTop;
        const delta = to - from;
        if (Math.abs(delta) < 1 || !durationMs) {
          el.scrollTop = to;
          return;
        }

        const start =
          (window.performance && performance.now && performance.now()) ||
          Date.now();
        const step = (now) => {
          const t = Math.min(1, (now - start) / durationMs);
          const p = easeInOutCubic(t);
          el.scrollTop = from + delta * p;
          if (t < 1) {
            DPR_SIDEBAR_SCROLL_ANIM.rafId = requestAnimationFrame(step);
          } else {
            DPR_SIDEBAR_SCROLL_ANIM.rafId = 0;
          }
        };
        DPR_SIDEBAR_SCROLL_ANIM.rafId = requestAnimationFrame(step);
      };

      const triggerPageNav = (href, direction) => {
        const target = normalizeHref(href);
        if (!target) return;

        // 先把 sidebar 的“选中高亮层”滑动到目标条目，和页面切换同步
        moveSidebarActiveIndicatorToHref(target, { animate: true });
        DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = true;

        // 通过左右键/滑动切换时：提前把 sidebar 滚到目标项附近，提升“跟手”观感
        if (DPR_NAV_STATE.lastNavSource !== 'click') {
          centerSidebarOnHref(target);
        }

        // 决定入场方向：forward => 新页从右进；backward => 新页从左进
        DPR_TRANSITION.pendingEnter =
          direction === 'backward' ? 'enter-from-left' : 'enter-from-right';

        if (prefersReducedMotion()) {
          window.location.hash = target;
          return;
        }

        const animEl = getPageAnimEl();
        if (!animEl) {
          window.location.hash = target;
          return;
        }

        const exitClass =
          direction === 'backward' ? 'dpr-page-exit-right' : 'dpr-page-exit-left';

        animEl.classList.add('dpr-page-exit', exitClass);
        // 等退场动画结束后再切换路由
        setTimeout(() => {
          window.location.hash = target;
        }, DPR_TRANSITION_MS);
      };

      const PREFETCH_STATE = {
        cache: new Map(),
      };

      const hrefToMdUrl = (href) => {
        const h = normalizeHref(href);
        const m = h.match(/^#\/(.+)$/);
        if (!m) return '';
        const file = m[1].replace(/\/$/, '') + '.md';
        return 'docs/' + file;
      };

      const prefetchHref = async (href) => {
        const url = hrefToMdUrl(href);
        if (!url) return;
        const key = url;
        const now = Date.now();
        const prev = PREFETCH_STATE.cache.get(key);
        if (prev && now - prev.ts < 5 * 60 * 1000) return; // 5 分钟内不重复拉取
        try {
          const res = await fetch(url, { cache: 'force-cache' });
          if (!res.ok) return;
          // 读一下 body，确保写入浏览器缓存（同时做内存缓存兜底）
          const text = await res.text();
          PREFETCH_STATE.cache.set(key, { ts: now, len: text.length });
        } catch {
          // ignore
        }
      };

      const prefetchAdjacent = () => {
        const list = DPR_NAV_STATE.paperHrefs || [];
        if (!list.length) return;
        const current = DPR_NAV_STATE.currentHref;
        if (!current) {
          // 首页：预取最新一天第一篇
          prefetchHref(list[0]);
          return;
        }
        const idx = list.indexOf(current);
        if (idx === -1) return;
        const prev = idx > 0 ? list[idx - 1] : '';
        const next = idx + 1 < list.length ? list[idx + 1] : '';
        if (prev) prefetchHref(prev);
        if (next) prefetchHref(next);
      };

      const ensureNavHandlers = () => {
        if (window.__dprNavBound) return;
        window.__dprNavBound = true;

        // 禁用 Docsify 原生的标题锚点点击功能
        document.addEventListener('click', (e) => {
          try {
            if (!e || e.defaultPrevented) return;
            const target = e.target;
            // 检测是否点击了标题或标题内的锚点
            if (target && target.closest) {
              const heading = target.closest('h1, h2, h3, h4, h5, h6');
              if (heading && heading.closest('.markdown-section')) {
                const link = target.closest('a');
                if (link && link.hash && link.hash.startsWith('#') && !link.hash.startsWith('#/')) {
                  // 阻止标题锚点的默认跳转行为
                  e.preventDefault();
                  e.stopPropagation();
                  return false;
                }
              }
            }
          } catch {
            // ignore
          }
        }, true); // 使用捕获阶段，确保在 Docsify 之前拦截

        const toggleGoodForCurrent = () => {
          const current = DPR_NAV_STATE.currentHref || '';
          if (!current) return;
          const m = current.match(/^#\/(.+)$/);
          if (!m) return;
          const paperId = m[1];

          const state = loadReadState();
          const cur = state[paperId];
          // 空格：在 good 与 read 之间切换
          if (cur === 'good') {
            state[paperId] = 'read';
          } else {
            state[paperId] = 'good';
          }
	          saveReadState(state);
	          markSidebarReadState(null);
	          // 同步选中高亮层颜色（good <-> read 切换时避免残留绿色底）
	          requestAnimationFrame(() => {
	            syncSidebarActiveIndicator({ animate: false });
	          });
	        };

        // 通用书签切换函数：数字键 1234 对应 绿蓝紫红
        const toggleBookmarkForCurrent = (bookmarkType) => {
          const current = DPR_NAV_STATE.currentHref || '';
          if (!current) return;
          const m = current.match(/^#\/(.+)$/);
          if (!m) return;
          const paperId = m[1];

          const state = loadReadState();
          const cur = state[paperId];
          // 切换：如果当前已是该状态则取消（变为 read），否则设置为该状态
          if (cur === bookmarkType) {
            state[paperId] = 'read';
          } else {
            state[paperId] = bookmarkType;
          }
          saveReadState(state);
          markSidebarReadState(null);
          requestAnimationFrame(() => {
            syncSidebarActiveIndicator({ animate: false });
          });
          // 移除所有按钮焦点，避免数字键触发按钮
          if (document.activeElement && document.activeElement.blur) {
            document.activeElement.blur();
          }
        };

        // 键盘：左右方向键 + 数字键 1234
        window.addEventListener('keydown', (e) => {
          const key = e.key || '';
          if (shouldIgnoreKeyNav(e)) return;

          // 数字键 1234：绿蓝紫红书签
          if (key === '1') {
            e.preventDefault();
            toggleBookmarkForCurrent('good');   // 绿色
            return;
          }
          if (key === '2') {
            e.preventDefault();
            toggleBookmarkForCurrent('blue');   // 蓝色
            return;
          }
          if (key === '3') {
            e.preventDefault();
            toggleBookmarkForCurrent('orange'); // 紫色（橙色）
            return;
          }
          if (key === '4') {
            e.preventDefault();
            toggleBookmarkForCurrent('bad');    // 红色
            return;
          }

          if (key === ' ') {
            // 空格键：切换"不错（绿色勾）"
            e.preventDefault();
            toggleGoodForCurrent();
            return;
          }
          if (key !== 'ArrowLeft' && key !== 'ArrowRight') return;
          // 只在当前页面聚焦时工作：浏览器已聚焦窗口即可
          e.preventDefault();
          DPR_NAV_STATE.lastNavSource = 'key';
          navigateByDelta(key === 'ArrowRight' ? +1 : -1);
        });

        // 点击论文链接也走同一套“整页切换”动效（避免只有滑动/方向键有动画）
        document.addEventListener('click', (e) => {
          try {
            if (!e || e.defaultPrevented) return;
            // 仅拦截普通左键点击，避免影响新标签页/复制链接等行为
            if (typeof e.button === 'number' && e.button !== 0) return;
            if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;

            const link = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (!link) return;
            const href = link.getAttribute('href') || '';
            if (!isPaperHref(href)) return;

            const target = normalizeHref(href);
            if (!target) return;
            if (target === (DPR_NAV_STATE.currentHref || '')) return;

            // 鼠标点击 sidebar：不触发“居中”逻辑
            DPR_NAV_STATE.lastNavSource = 'click';

            // 推断方向：按侧边栏顺序判断“前进/后退”
            let direction = 'forward';
            const list = DPR_NAV_STATE.paperHrefs || [];
            const cur = DPR_NAV_STATE.currentHref || '';
            if (list.length && cur) {
              const curIdx = list.indexOf(cur);
              const tgtIdx = list.indexOf(target);
              if (curIdx !== -1 && tgtIdx !== -1) {
                direction = tgtIdx < curIdx ? 'backward' : 'forward';
              }
            }

            // 只在论文页启用动效拦截，避免首页点击出现“无动画但有延迟”的体验
            if (document.body && document.body.classList.contains('dpr-paper-page') && !prefersReducedMotion()) {
              e.preventDefault();
              triggerPageNav(target, direction);
            }
          } catch {
            // ignore
          }
        });

        // 鼠标/触控板横向滚动：切换论文，并阻止浏览器的“整页滑动/回退动效”
        document.addEventListener(
          'wheel',
          (e) => {
            if (shouldIgnoreKeyNav(e)) return;
            const dx = e.deltaX || 0;
            const dy = e.deltaY || 0;
            if (Math.abs(dx) < 28) return;
            if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
            e.preventDefault();
            // dx < 0：向左滑 => 下一篇
            // dx > 0：向右滑 => 上一篇
            DPR_NAV_STATE.lastNavSource = 'wheel';
            navigateByDelta(dx < 0 ? +1 : -1);
          },
          { passive: false },
        );

        // 触摸滑动：左右切换
        let startX = 0;
        let startY = 0;
        let startAt = 0;
        let lockHorizontal = false;
        const threshold = 60;

        const onTouchStart = (e) => {
          const t = e.touches && e.touches[0];
          if (!t) return;
          startX = t.clientX;
          startY = t.clientY;
          startAt = Date.now();
          lockHorizontal = false;
        };

        const onTouchMove = (e) => {
          const t = e.touches && e.touches[0];
          if (!t) return;
          const dx = t.clientX - startX;
          const dy = t.clientY - startY;
          if (Math.abs(dx) < 18) return;
          if (Math.abs(dx) > Math.abs(dy) * 1.2) {
            lockHorizontal = true;
          }
          if (lockHorizontal) {
            // 阻止浏览器的横向滑动/回退动效，让切换更“丝滑”
            if (e.cancelable) {
              e.preventDefault();
            }
          }
        };

        const onTouchEnd = (e) => {
          const t = e.changedTouches && e.changedTouches[0];
          if (!t) return;
          const dx = t.clientX - startX;
          const dy = t.clientY - startY;
          const dt = Date.now() - startAt;
          // 排除长按、轻微滑动、明显上下滚动
          if (dt > 900) return;
          if (Math.abs(dx) < threshold) return;
          if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
          // dx < 0：向左滑 => 下一篇（相当于 ArrowRight）
          // dx > 0：向右滑 => 上一篇（相当于 ArrowLeft）
          DPR_NAV_STATE.lastNavSource = 'swipe';
          navigateByDelta(dx < 0 ? +1 : -1);
        };

        document.addEventListener('touchstart', onTouchStart, { passive: true });
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd, { passive: true });
      };

      // --- 解析 YAML front matter 并转换为 HTML ---
      const parseFrontMatter = (content) => {
        if (!content || !content.startsWith('---')) {
          return { meta: null, body: content };
        }
        const endIdx = content.indexOf('\n---', 3);
        if (endIdx === -1) {
          return { meta: null, body: content };
        }
        const yamlStr = content.slice(4, endIdx).trim();
        const body = content.slice(endIdx + 4).trim();

        // 简单解析 YAML（不依赖外部库）
        const meta = {};
        const lines = yamlStr.split('\n');
        for (const line of lines) {
          const colonIdx = line.indexOf(':');
          if (colonIdx === -1) continue;
          const key = line.slice(0, colonIdx).trim();
          let value = line.slice(colonIdx + 1).trim();

          // 处理数组格式 [a, b, c]
          if (value.startsWith('[') && value.endsWith(']')) {
            const inner = value.slice(1, -1);
            // 简单分割，处理引号内的逗号
            const items = [];
            let current = '';
            let inQuote = false;
            let quoteChar = '';
            for (let i = 0; i < inner.length; i++) {
              const c = inner[i];
              if (!inQuote && (c === '"' || c === "'")) {
                inQuote = true;
                quoteChar = c;
              } else if (inQuote && c === quoteChar) {
                inQuote = false;
              } else if (!inQuote && c === ',') {
                items.push(current.trim());
                current = '';
                continue;
              }
              current += c;
            }
            if (current.trim()) items.push(current.trim());
            // 去除引号
            meta[key] = items.map(s => s.replace(/^["']|["']$/g, ''));
          } else {
            // 去除引号
            meta[key] = value.replace(/^["']|["']$/g, '').replace(/\\n/g, '\n').replace(/\\"/g, '"');
          }
        }
        return { meta, body };
      };

      // 根据 front matter 生成论文页面 HTML
      const renderPaperFromMeta = (meta) => {
        if (!meta) return '';

        const escapeHtml = (s) => {
          if (!s) return '';
          return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        };

        // 解析标签，生成带颜色的 HTML
        const renderTags = (tags) => {
          if (!tags || !tags.length) return '';
          return tags.map(tag => {
            const [kind, label] = tag.includes(':') ? tag.split(':', 2) : ['other', tag];
            const css = { keyword: 'tag-green', query: 'tag-blue', paper: 'tag-pink' }[kind] || 'tag-pink';
            return `<span class="tag-label ${css}">${escapeHtml(label)}</span>`;
          }).join(' ');
        };

        const lines = [];

        // 标题区域
        lines.push('<div class="paper-title-row">');
        if (meta.title_zh) {
          lines.push(`<h1 class="paper-title-zh">${escapeHtml(meta.title_zh)}</h1>`);
        }
        if (meta.title) {
          lines.push(`<h1 class="paper-title-en">${escapeHtml(meta.title)}</h1>`);
        }
        lines.push('</div>');
        lines.push('');

        // 中间区域
        lines.push('<div class="paper-meta-row">');

        // 左侧：Evidence 和 TLDR
        lines.push('<div class="paper-meta-left">');
        if (meta.evidence) {
          lines.push(`<p><strong>Evidence</strong>: ${escapeHtml(meta.evidence)}</p>`);
        }
        if (meta.tldr) {
          lines.push(`<p><strong>TLDR</strong>: ${escapeHtml(meta.tldr)}</p>`);
        }
        lines.push('</div>');

        // 右侧：基本信息
        lines.push('<div class="paper-meta-right">');
        lines.push(`<p><strong>Authors</strong>: ${escapeHtml(meta.authors || 'Unknown')}</p>`);
        lines.push(`<p><strong>Date</strong>: ${escapeHtml(meta.date || 'Unknown')}</p>`);
        if (meta.pdf) {
          lines.push(`<p><strong>PDF</strong>: <a href="${escapeHtml(meta.pdf)}" target="_blank">${escapeHtml(meta.pdf)}</a></p>`);
        }
        if (meta.tags && meta.tags.length) {
          lines.push(`<p><strong>Tags</strong>: ${renderTags(meta.tags)}</p>`);
        }
        if (meta.score !== undefined && meta.score !== null) {
          lines.push(`<p><strong>Score</strong>: ${escapeHtml(String(meta.score))}</p>`);
        }
        lines.push('</div>');

        lines.push('</div>');
        lines.push('');

        // 速览区域
        if (meta.motivation || meta.method || meta.result || meta.conclusion) {
          lines.push('<div class="paper-glance-section">');
          lines.push('<h2 class="paper-glance-title">速览</h2>');
          lines.push('<div class="paper-glance-row">');

          lines.push('<div class="paper-glance-col">');
          lines.push('<div class="paper-glance-label">Motivation</div>');
          lines.push(`<div class="paper-glance-content">${escapeHtml(meta.motivation || '-')}</div>`);
          lines.push('</div>');

          lines.push('<div class="paper-glance-col">');
          lines.push('<div class="paper-glance-label">Method</div>');
          lines.push(`<div class="paper-glance-content">${escapeHtml(meta.method || '-')}</div>`);
          lines.push('</div>');

          lines.push('<div class="paper-glance-col">');
          lines.push('<div class="paper-glance-label">Result</div>');
          lines.push(`<div class="paper-glance-content">${escapeHtml(meta.result || '-')}</div>`);
          lines.push('</div>');

          lines.push('<div class="paper-glance-col">');
          lines.push('<div class="paper-glance-label">Conclusion</div>');
          lines.push(`<div class="paper-glance-content">${escapeHtml(meta.conclusion || '-')}</div>`);
          lines.push('</div>');

          lines.push('</div>');
          lines.push('</div>');
          lines.push('');
        }

        // 注意：在 Markdown 中插入 HTML block（如 <hr>）后，需要一个“空行”才能让后续的 `##` 等 Markdown 正常解析。
        // 这里通过追加两个空行，确保最终输出以 `<hr>\n\n` 结尾。
        lines.push('<hr>');
        lines.push('');
        lines.push('');

        return lines.join('\n');
      };

      // --- Docsify beforeEach 钩子：解析 front matter ---
      hook.beforeEach(function (content) {
        const file = vm && vm.route ? vm.route.file : '';
        // 只对论文页面处理
        if (!isPaperRouteFile(file)) {
          latestPaperRawMarkdown = '';
          return content;
        }
        latestPaperRawMarkdown = content || '';

        const { meta, body } = parseFrontMatter(content);
        if (!meta) {
          return content;
        }

        // 生成论文页面 HTML + 正文
        const paperHtml = renderPaperFromMeta(meta);
        return paperHtml + body;
      });

      // --- Docsify 生命周期钩子 ---
      hook.doneEach(function () {
        // 路由统一：将 #/?id=%2f... 自动规整为 #/...
        try {
          const canonical = decodeLegacyIdHash(window.location.hash || '');
          if (canonical && canonical !== window.location.hash) {
            window.location.replace(canonical);
            return;
          }
        } catch {
          // ignore
        }

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
        const file = vm && vm.route ? vm.route.file : '';
        const isReportPage = isReportRouteFile(file);
        const isPaperPage = isPaperRouteFile(file);
        const isLandingLikePage = isHomePage || isReportPage;

        // A. 对正文区域进行一次全局公式渲染（支持 $...$ / $$...$$）
        const mainContent = document.querySelector('.markdown-section');
        if (mainContent) {
          // 先创建正文包装层，避免后续切页动画影响聊天浮层
          const root = isPaperPage ? ensurePageContentRoot() : null;
          renderMathInEl(root || mainContent);
        }

        // 论文页标题条排版（只对 docs/YYYYMM/DD/*.md 生效）
        applyPaperTitleBar();

        // 论文页左右切换：更新导航列表并绑定事件（只绑定一次）
        updateNavState();
        ensureNavHandlers();
        // 预取相邻论文的 Markdown（利用浏览器 cache，让切换更丝滑）
        prefetchAdjacent();

        // 页面入场动画：根据上一跳的方向做滑入
        const animEl = getPageAnimEl();
        if (animEl) {
          // 清理上一次退场残留（防止极端情况下没清掉）
          animEl.classList.remove(
            'dpr-page-exit',
            'dpr-page-exit-left',
            'dpr-page-exit-right',
          );
          const enter = DPR_TRANSITION.pendingEnter;
          DPR_TRANSITION.pendingEnter = '';
          if (enter && !prefersReducedMotion()) {
            animEl.classList.add('dpr-page-enter', enter);
            requestAnimationFrame(() => {
              // 触发 transition 到“静止态”
              animEl.classList.add('dpr-page-enter-active');
              setTimeout(() => {
                animEl.classList.remove(
                  'dpr-page-enter',
                  'dpr-page-enter-active',
                  'enter-from-left',
                  'enter-from-right',
                );
              }, DPR_TRANSITION_MS + 40);
            });
          }
        }

        if (!isLandingLikePage && window.PrivateDiscussionChat) {
          window.PrivateDiscussionChat.initForPage(paperId);
        }

        // ----------------------------------------------------
        // E. 小屏点击侧边栏条目后自动收起
        // ----------------------------------------------------
        setupMobileSidebarAutoCloseOnItemClick();

        // ----------------------------------------------------
        // F. 侧边栏按日期折叠
        // ----------------------------------------------------
        setupCollapsibleSidebarByDay();

        // ----------------------------------------------------
        // G. 侧边栏已阅读论文状态高亮
        // ----------------------------------------------------
        if (!isLandingLikePage && paperId) {
          markSidebarReadState(paperId);
        } else {
          // 首页也需要应用已有的“已读高亮”，但不新增记录
          markSidebarReadState(null);
        }

        // 让滑动高亮层跟随当前 active 项（点击、路由变化后会更新 active 类）
        try {
          const movedByNavAnim = !!DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved;
          if (!movedByNavAnim) {
            // 非“点击触发的预先滑动”场景：先立即贴齐一次
            syncSidebarActiveIndicator({ animate: false });
          }
          // 统一做一次延迟终态校准：
          // - 点击切页时避免“先对齐 -> 上跳 -> 再回位”的双重抖动
          // - 分组展开/收起有 max-height 过渡，布局稳定后再校准一次
          setTimeout(() => {
            try {
              syncSidebarActiveIndicator({ animate: false });
            } finally {
              DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = false;
            }
          }, movedByNavAnim ? 220 : 280);
        } catch {
          // ignore
          DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = false;
        }

        // 自动把当前论文在 sidebar 中滚动到居中位置，便于连续阅读
        if (DPR_NAV_STATE.lastNavSource !== 'click') {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              centerSidebarOnCurrent();
            });
          });
        }

        // 本次 doneEach 的来源只用于控制“是否居中”，用完即清理
        DPR_NAV_STATE.lastNavSource = '';

        // ----------------------------------------------------
        // H. Zotero 元数据注入逻辑 (带延时和唤醒)
        // ----------------------------------------------------
        setTimeout(() => {
          updateZoteroMetaFromPage(
            paperId,
            vm.route.file,
            latestPaperRawMarkdown,
          );
        }, 1); // 延迟执行，等待 DOM 渲染完毕
      });
      // ----------------------------------------------------
      // I. 响应式侧边栏：窄屏首次加载时确保收起（仅移除 close 类）
      // ----------------------------------------------------
      const SIDEBAR_AUTO_COLLAPSE_WIDTH = 1024;

      const ensureCollapsedOnNarrowScreen = () => {
        const windowWidth =
          window.innerWidth || document.documentElement.clientWidth || 0;
        if (windowWidth >= SIDEBAR_AUTO_COLLAPSE_WIDTH) return;

        const body = document.body;
        if (!body.classList) return;
        // 进入窄屏时使用 "默认不带 close" 的收起态，兼容 Docsify 的移动端语义
        body.classList.remove('close');
      };

      // 初始化时执行一次
      ensureCollapsedOnNarrowScreen();
    },
  ],
};
