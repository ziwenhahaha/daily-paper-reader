// Docsify configuration and shared plugins (discussion area + Zotero metadata)
window.$docsify = {
  name: 'Daily Paper Reader',
  repo: '',
  // Document content and the sidebar both live under docs/
  basePath: 'docs/', // All Markdown routes are prefixed with docs/
  loadSidebar: '_sidebar.md', // Load _sidebar.md under basePath
  // Always use the root _sidebar.md so each subdirectory does not need its own copy
  alias: {
    '/.*/_sidebar.md': '/_sidebar.md',
  },
  // Only show paper list titles in the sidebar, not in-page sections (e.g. Abstract)
  subMaxLevel: 0,

  // --- Core: register custom plugins ---
  plugins: [
    function (hook, vm) {
      // Ensure marked enables GFM table support and allows inline HTML (used for chat-area Markdown rendering)
      if (window.marked && window.marked.setOptions) {
        const baseOptions =
          (window.marked.getDefaults && window.marked.getDefaults()) || {};
        window.marked.setOptions(
          Object.assign({}, baseOptions, {
            gfm: true,
            breaks: false,
            tables: true,
            // Allow inline HTML such as <sup> to render directly instead of being escaped
            sanitize: false,
            mangle: false,
            headerIds: false,
          }),
        );
      }

      // 1. Resolve the current article ID (simply use the filename as the ID)
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

      // Zotero abstract structure markers: make later re-parsing easy inside the Zotero plugin
      const START_MARKER = '【🤖 AI Summary】';
      const CHAT_MARKER = '【💬 Chat History】';
      const ORIG_MARKER = '【📄 Original Abstract】';
      const TLDR_MARKER = '【📝 TLDR】';
      const GLANCE_MARKER = '【🧭 Glance】';
      const GLANCE_MARKER_LEGACY = '【🧭 速览区】';
      const DETAIL_MARKER = '【🧩 Detailed Summary】';
      const DETAIL_MARKER_LEGACY = '【🧩 论文详细总结区】';
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
        text = text.replace(/^>?\s*(?:由\s*)?daily-paper-reader\s*(?:自动生成|auto-generated)\s*$/gim, '');
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

      const getRawPaperSections = (rawContent) => {
        const helper =
          window.DPRZoteroMetaUtils &&
          typeof window.DPRZoteroMetaUtils.getRawPaperSections === 'function'
            ? window.DPRZoteroMetaUtils.getRawPaperSections
            : null;
        if (helper) {
          return helper(rawContent);
        }
        return {
          aiSummaryText: splitRawSectionByTitle(
            rawContent,
            (title) => {
              const t = normalizeTextForMeta(title).replace(/^\s*#{1,6}\s*/, '').trim().toLowerCase();
              return (
                t.includes('detailed summary') ||
                t.includes('论文详细总结') ||
                t.includes('论文详细总结（自动生成）') ||
                t.includes('ai summary') ||
                t.includes('🤖 ai summary')
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
                t.includes('original abstract')
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
        };
      };

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
            'interaction area',
            'page navigation and interaction layer',
            'original abstract',
            '原文摘要',
            'detailed summary',
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
        let currentTitle = '📝 Paper Body';
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

      // Zotero metadata update function: can be called repeatedly by the Docsify lifecycle and the chat module
      const updateZoteroMetaFromPage = async (
        paperId,
        vmRouteFile,
        rawPaperContent = '',
      ) => {
        try {
          // Prefer the custom title bar (avoids unstable innerText after the h1 is hidden/modified)
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
            // Clean up extra whitespace and plugin-injected content in the title
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
              // Clean up line breaks and trailing info that other extensions may inject, plus the trailing date
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

          // On each route refresh, first clear the previous page's injected abstract meta to avoid duplicates
          clearSummaryMetaFields();

          // Build the Zotero "abstract" metadata: organized into AI summary / chat history / original abstract sections
          let abstractText = '';
          let abstractTextForMetaRaw = '';
          const sectionEl = document.querySelector('.markdown-section');
          if (sectionEl) {
            let aiSummaryText = rawSummary;
            let origAbstractText = rawOriginal;
            aiSummaryText = cleanSectionText(aiSummaryText);
            origAbstractText = cleanSectionText(origAbstractText);

            // 3) Parse chat history, preferring the local raw chat records to avoid formulas being broken when read from DOM innerText
            let chatSection = '';
            const buildChatLinesFromMessages =
              window.DPRZoteroChatUtils &&
              typeof window.DPRZoteroChatUtils.buildChatLinesFromMessages === 'function'
                ? window.DPRZoteroChatUtils.buildChatLinesFromMessages
                : null;
            const storedChat = await loadChatHistoryForPaper(paperId);
            const storedLines = buildChatLinesFromMessages
              ? buildChatLinesFromMessages(storedChat)
              : [];
            if (storedLines.length) {
              chatSection = storedLines.join('\n\n');
            } else {
              const chatRoot = document.getElementById('chat-history');
              if (chatRoot) {
                const items = chatRoot.querySelectorAll('.msg-item');
                const lines = [];
                const inferSpeaker =
                  window.DPRZoteroChatUtils &&
                  typeof window.DPRZoteroChatUtils.inferSpeaker === 'function'
                    ? window.DPRZoteroChatUtils.inferSpeaker
                    : ({ roleText = '', className = '' } = {}) => {
                        const role = String(roleText || '').trim().toLowerCase();
                        const cls = String(className || '').trim();
                        if (role.includes('thinking')) return '';
                        if (role.includes('user') || role.includes('you')) return 'User';
                        if (role.includes('assistant') || role.includes('ai')) return 'AI';
                        if (/\bmsg-content-user\b/.test(cls)) return 'User';
                        if (/\bmsg-content-ai\b/.test(cls)) return 'AI';
                        return '';
                      };
                items.forEach((item) => {
                  const roleEl = item.querySelector('.msg-role');
                  const contentEl = item.querySelector('.msg-content');
                  if (!contentEl) return;
                  const roleText = roleEl ? (roleEl.textContent || '') : '';
                  const speaker = inferSpeaker({
                    roleText,
                    className: contentEl.className || '',
                  });
                  if (!speaker) return;
                  const contentText = (contentEl.innerText || '').trim();
                  if (!contentText) return;
                  const icon = speaker === 'User' ? '👤' : '🤖';
                  lines.push(`${icon} ${speaker}: ${contentText}`);
                });
                if (lines.length) {
                  chatSection = lines.join('\n\n');
                }
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
              if (raw === GLANCE_MARKER || raw === GLANCE_MARKER_LEGACY) return "🧭 Glance";
              if (raw === DETAIL_MARKER || raw === DETAIL_MARKER_LEGACY) return "🧩 Detailed Summary";
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
              return `- **${label || 'item'}**: ${content || '-'}`;
            });
            const fallbackArray = (value, label = '') =>
              value ? [`- **${label}**: ${Array.isArray(value) ? value.join(' / ') : String(value)}`] : [];

            const titleRowText = [
              `- **Title (ZH/EN)**: ${titleZhText || frontmatterPaperMeta.title_zh || '-'} / ${titleEnText || frontmatterPaperMeta.title || '-'}`,
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
              `- **dpr-title-bar**: ${titleBarEl ? 'mounted' : 'not found'}`,
              `- **dpr-page-content**: ${pageContentEl ? 'mounted' : 'not found'}`,
              `- **paper-title-row**: ${document.querySelector('.paper-title-row') ? 'mounted' : 'not found'}`,
              `- **paper-meta-row**: ${document.querySelector('.paper-meta-row') ? 'mounted' : 'not found'}`,
              `- **paper-glance-section**: ${document.querySelector('.paper-glance-section') ? 'mounted' : 'not found'}`,
              `- **#paper-chat-container**: ${chatContainerEl ? 'mounted' : 'not found'}`,
              `- **#chat-history**: ${chatHistoryEl ? 'mounted' : 'not found'}`,
            ];

            addMetaSectionBlock(
              'paper-title-row (bilingual title area)',
              titleRowText.join('\n'),
            );
            addMetaSectionBlock(
              'paper-meta-row (middle info area)',
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
              'Page navigation and interaction layer',
              cleanText(uiRows.join('\n')),
            );

            // 1) Full-text paragraphs: auto-split by page heading, written in order
            const paperBodySections = collectPaperBodySections(sectionEl);
            paperBodySections.forEach((section) => {
              if (section && section.text) {
                addMetaSectionBlock(section.title, section.text);
              }
            });

            if (aiSummaryText) {
              // AI Summary block: keep only the AI summary body, no longer auto-appending Tags
              let aiBlock = `${START_MARKER}\n`;
              if (aiSummaryText) {
                aiBlock += aiSummaryText;
              }
              addMetaBlock(START_MARKER, aiBlock);
              addRawMetaBlock(
                START_MARKER,
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

            // Fallback raw aggregation: ensure the AI Summary / Original Abstract raw Markdown is preserved
            // (avoids formulas being rewritten after going through the DOM text path)
            abstractText = parts.join('\n\n\n').trim();
            abstractTextForMetaRaw = rawParts.join('\n\n\n').trim();
          }

          if (abstractText) {
            const abstractTextForMeta =
              abstractTextForMetaRaw || abstractText;
            if (abstractTextForMeta) {
              // Use the field name Zotero Connector commonly recognizes: citation_abstract
              // Encode line breaks with a placeholder so the Connector does not lose paragraph boundaries on import
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

      // Exported so other frontend modules (e.g. the chat module) can actively refresh Zotero metadata
      window.DPRZoteroMeta = window.DPRZoteroMeta || {};
      window.DPRZoteroMeta.updateFromPage = (paperId, vmRouteFile) =>
        Promise.resolve(
          updateZoteroMetaFromPage(paperId, vmRouteFile, latestPaperRawMarkdown),
        ).catch((e) => {
          console.error('Zotero meta update failed:', e);
        });

      // Shared utility: protect LaTeX formulas from being broken by marked
      // Called in the beforeEach phase to wrap formulas in HTML tags (marked does not parse HTML)
      const protectLatex = (text) => {
        if (!text) return text;
        // 1) Convert \[...\] to $$...$$ and \(...\) to $...$
        //    Note: \[ may appear at line start or inline
        text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => `$$${inner}$$`);
        text = text.replace(/\\\((.*?)\\\)/g, (_, inner) => `$${inner}$`);
        // 2) Protect block formulas $$...$$ → <div class="dpr-math" data-display="true">
        text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, inner) => {
          const escaped = inner.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          return `<div class="dpr-math" data-display="true">${escaped}</div>`;
        });
        // 3) Protect inline formulas $...$ → <span class="dpr-math" data-display="false">
        //    No line spanning; exclude cases where a space follows or precedes $ (reduces false matches)
        text = text.replace(/\$([^\$\n]+?)\$/g, (match, inner) => {
          // Exclude obvious non-formula cases (e.g. prices like $10)
          if (/^\d+$/.test(inner.trim())) return match;
          const escaped = inner.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          return `<span class="dpr-math" data-display="false">${escaped}</span>`;
        });
        return text;
      };

      // Shared utility: render formulas on a given element
      const renderMathInEl = (el) => {
        if (!el) return;
        // Prefer rendering the .dpr-math tags produced by protectLatex
        if (window.katex) {
          el.querySelectorAll('.dpr-math').forEach((node) => {
            const latex = node.textContent;
            const displayMode = node.getAttribute('data-display') === 'true';
            try {
              window.katex.render(latex, node, {
                displayMode,
                throwOnError: false,
              });
            } catch (e) {
              // Keep the original text if rendering fails
            }
          });
        }
        // Fallback: handle leftover $...$ / $$...$$ in plain text with auto-render
        if (window.renderMathInElement) {
          window.renderMathInElement(el, {
            delimiters: [
              { left: '$$', right: '$$', display: true },
              { left: '$', right: '$', display: false },
              { left: '\\[', right: '\\]', display: true },
              { left: '\\(', right: '\\)', display: false },
            ],
            throwOnError: false,
          });
        }
      };

      // Shared utility: simple table + marker fixes:
      // 1) Remove protocol markers [ANS]/[THINK]
      // 2) Remove extra blank lines between table rows so one table is not split in two
      const normalizeTables = (markdown) => {
        if (!markdown) return '';
        // Clean up legacy protocol markers
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
            // Skip blank lines between table rows
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

      // Custom table rendering: detect Markdown table blocks and emit <table> by hand,
      // other content is still rendered by marked.
      // Also protect LaTeX formula blocks from being misparsed by marked.
      const renderMarkdownWithTables = (markdown) => {
        const text = normalizeTables(markdown || '');

        // Protect LaTeX formulas: replace with placeholders first, restore after rendering
        const latexBlocks = [];
        let protectedText = text;

        // First convert \[...\] → $$...$$ and \(...\) → $...$
        protectedText = protectedText.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => `$$${inner}$$`);
        protectedText = protectedText.replace(/\\\((.*?)\\\)/g, (_, inner) => `$${inner}$`);

        // Protect block formulas $$...$$
        protectedText = protectedText.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
          const idx = latexBlocks.length;
          latexBlocks.push(match);
          return `%%LATEX_BLOCK_${idx}%%`;
        });

        // Protect inline formulas $...$ (no line spanning)
        protectedText = protectedText.replace(/\$([^\$\n]+?)\$/g, (match) => {
          const idx = latexBlocks.length;
          latexBlocks.push(match);
          return `%%LATEX_INLINE_${idx}%%`;
        });

        // Preprocess: manually convert **...** and *...* into HTML tags
        // Works around marked failing to detect bold/italic next to CJK characters
        // Note: only match within a single line and under 100 characters, to avoid false matches
        protectedText = protectedText.replace(/\*\*([^*\n]{1,100}?)\*\*/g, '<strong>$1</strong>');
        // Italic: require surrounding spaces or CJK boundaries to avoid matching multiplication signs, etc.
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

          // Detect a table block: current line is a table row, next line is the alignment row
          if (
            isTableLine(line) &&
            i + 1 < lines.length &&
            isAlignLine(lines[i + 1])
          ) {
            const headerLine = lines[i];
            i += 2; // Skip the alignment row

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
            // Non-table block: collect until the next table or the end
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

        // Restore LaTeX formulas
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

      // Exported for reuse by external modules (e.g. the chat module)
      window.DPRMarkdown = {
        normalizeTables,
        renderMarkdownWithTables,
        renderMathInEl,
      };

      // 3. On small screens: auto-collapse the sidebar after clicking an entry (full-screen list → body)
      const setupMobileSidebarAutoCloseOnItemClick = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        if (nav.dataset.mobileAutoCloseBound === '1') return;
        nav.dataset.mobileAutoCloseBound = '1';

        nav.addEventListener('click', (event) => {
          const link = event.target.closest('a');
          if (!link) return;

          const href = link.getAttribute('href') || '';
          // Only handle internal Docsify routes (starting with #/), to avoid affecting external links
          if (!href.includes('#/')) return;

          const width =
            window.innerWidth || document.documentElement.clientWidth || 0;
          // Treat "narrowish + narrow" screens uniformly: at <1024, auto-collapse the sidebar after clicking an entry (full-screen list → body)
          if (width >= 1024) return;

          // Let Docsify finish the route change first, then collapse the sidebar
          setTimeout(() => {
            const body = document.body;
            if (!body) return;
            // Match Docsify mobile semantics: do not keep the close class when collapsing the sidebar on small screens
            body.classList.remove('close');
          }, 0);
        });
      };

      // 4. Helper functions for collapsing the sidebar by date
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

        const normalizeHashHref = (href) => {
          const raw = String(href || '').trim();
          if (!raw) return '';
          if (raw.startsWith('#/')) return raw;
          if (raw.startsWith('#')) return `#/${raw.slice(1).replace(/^\//, '')}`;
          return `#/${raw.replace(/^\//, '')}`;
        };

        const isPaperRouteHash = (hash) => {
          const route = String(hash || '')
            .replace(/^#\/?/, '')
            .replace(/\.md$/i, '')
            .replace(/\/$/, '');
          return (
            /^(\d{6}\/\d{2}|\d{8}(?:-\d{8}))\/(?!README$).+/i.test(route) &&
            /^(\d{6}\/\d{2}|\d{8}(?:-\d{8}))\/[^/]+$/i.test(route)
          );
        };

        const getDirectText = (li) => {
          if (!li) return '';
          if (typeof Node !== 'undefined') {
            const directTextNode = Array.from(li.childNodes || []).find((n) => {
              if (!n || n.nodeType !== Node.TEXT_NODE) return false;
              return String(n.textContent || '').trim();
            });
            if (directTextNode) {
              return String(directTextNode.textContent || '').trim();
            }
          }
          const title = li.querySelector(
            ':scope > .sidebar-day-toggle .sidebar-day-toggle-label',
          );
          return String((title && title.textContent) || '').trim();
        };

        const getPaperSectionFromAnchor = (anchor, rowLi) => {
          if (!anchor || !rowLi) return '';
          let currentLi = anchor.closest('li');
          while (currentLi) {
            const parentUl = currentLi.parentElement;
            const parentLi = parentUl ? parentUl.closest('li') : null;
            if (!parentLi || parentLi === rowLi) break;
            const text = getDirectText(parentLi);
            if (
              text &&
              !/^(\d{4}-\d{2}-\d{2})(\s*~\s*\d{4}-\d{2}-\d{2})?$/.test(
                text,
              )
            ) {
              return text;
            }
            currentLi = parentLi;
          }
          return '';
        };

        const collectDayPaperItems = (rowLi) => {
          if (!rowLi) return [];
          const anchors = Array.from(rowLi.querySelectorAll('a[href*=\"#/\"]'));
          const out = [];
          const seen = new Set();

          anchors.forEach((anchor) => {
            const href = normalizeHashHref(anchor.getAttribute('href'));
            if (!href || !isPaperRouteHash(href)) return;
            const paperId = href.replace(/^#\//, '');
            if (!paperId || paperId.endsWith('/README')) return;
            if (seen.has(paperId)) return;
            seen.add(paperId);
            out.push({
              anchor,
              href,
              paperId,
              section: getPaperSectionFromAnchor(anchor, rowLi),
            });
          });
          return out;
        };

        const normalizeSection = (section) => {
          const v = String(section || '').trim();
          if (!v) return '';
          if (/深度|精读|deep/i.test(v)) return 'deep';
          if (/速读|速览|quick/i.test(v)) return 'quick';
          return v.toLowerCase();
        };

        const normalizeAuthorsForExport = (authors) => {
          if (Array.isArray(authors)) {
            return authors
              .map((item) => String(item || '').trim())
              .filter(Boolean)
              .join(', ');
          }
          return String(authors || '').trim();
        };

        const normalizeTagsForExport = (tags) => {
          if (!tags) return '';
          if (Array.isArray(tags)) {
            return tags
              .map((tag) => {
                if (typeof tag === 'string') return tag.trim();
                if (!tag || typeof tag !== 'object') return '';
                const kind = String(tag.kind || '').trim();
                const label = String(tag.label || '').trim();
                return kind ? `${kind}:${label}` : label;
              })
              .filter(Boolean)
              .join(', ');
          }
          return String(tags || '').trim();
        };

        const normalizeDateField = (value) => {
          const text = String(value || '').trim();
          if (!text) return '';
          const m = text.match(/(\d{4})(\d{2})(\d{2})/);
          if (!m) return text;
          return `${m[1]}-${m[2]}-${m[3]}`;
        };

        const buildPaperMetaFromMarkdown = (paperId, section, markdownText) => {
          const parsed = parseFrontMatter(markdownText || '');
          const meta = parsed && parsed.meta ? parsed.meta : {};
          const body = parsed && parsed.body ? parsed.body : '';

          const title_en = String(meta.title_en || meta.title || '').trim();
          const abstractFromFrontMatter = String(
            meta.abstract_en || meta.abstract || '',
          ).trim();
          const authors = normalizeAuthorsForExport(meta.authors || meta.author);
          const score = String(meta.score || '').trim();
          const evidence = String(meta.evidence || '').trim();
          const tldr = String(meta.tldr || meta.summary || '').trim();

          const abstractFromBody = trimBeforeMarkers(
            extractSectionByTitle(body, (title) => {
              const normalized = String(title || '').trim().toLowerCase();
              return normalized === 'abstract' || normalized === '摘要';
            }),
            [],
          ).trim();

          return {
            paper_id: paperId,
            section: normalizeSection(section) || 'quick',
            title_en,
            source: String(meta.source || meta.Source || '').trim(),
            selection_source: String(meta.selection_source || '').trim(),
            authors,
            date: normalizeDateField(meta.date || ''),
            pdf: String(meta.pdf || meta.PDF || '').trim(),
            score,
            evidence,
            tldr,
            tags: normalizeTagsForExport(meta.tags || []),
            abstract_en: abstractFromFrontMatter || abstractFromBody,
          };
        };

        const markDayPapersUnrecommended = (paperItems) => {
          if (!Array.isArray(paperItems) || !paperItems.length) return;
          let readState = loadReadState();
          if (!readState || typeof readState !== 'object') readState = {};
          const toClear = new Set(['good', 'blue', 'orange', 'bad']);
          let changed = false;
          paperItems.forEach((item) => {
            const paperId = item && typeof item.paperId === 'string' ? item.paperId : '';
            if (!paperId) return;
            if (toClear.has(String(readState[paperId] || '').trim().toLowerCase())) {
              delete readState[paperId];
              changed = true;
            }
          });
          if (changed) saveReadState(readState);
        };

        const closeAllDayMenus = () => {
          const openedMenus = nav.querySelectorAll('.sidebar-day-menu.is-open');
          openedMenus.forEach((m) => {
            m.classList.remove('is-open');
          });
        };

        if (!nav.dataset.dprDayMenuBound) {
          nav.dataset.dprDayMenuBound = '1';
          document.addEventListener('click', (e) => {
            const target = e && e.target ? e.target : null;
            if (!target || !target.closest) return;
            if (!target.closest('.sidebar-day-toggle-actions')) {
              closeAllDayMenus();
            }
          });
        }

        const downloadJson = (filename, data) => {
          const blob = new Blob([JSON.stringify(data, null, 2)], {
            type: 'application/json;charset=utf-8',
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          a.className = 'dpr-sidebar-export-link';
          a.target = '_self';
          a.style.display = 'none';
          const stopLinkNav = (event) => {
            event.stopPropagation();
            if (event.stopImmediatePropagation) event.stopImmediatePropagation();
          };
          a.addEventListener('click', stopLinkNav, true);
          document.body.appendChild(a);
          requestAnimationFrame(() => {
            a.click();
            setTimeout(() => {
              a.remove();
            }, 0);
          });
          setTimeout(() => URL.revokeObjectURL(url), 500);
        };

        const STORAGE_KEY = 'dpr_sidebar_day_state_v1';
        const HIDDEN_DAYS_KEY = '__hiddenDays';
        let state = {};
        let hiddenDays = new Set();
        try {
          const raw = window.localStorage
            ? window.localStorage.getItem(STORAGE_KEY)
            : null;
          if (raw) {
            state = JSON.parse(raw) || {};
            const savedHidden = state[HIDDEN_DAYS_KEY];
            if (Array.isArray(savedHidden)) {
              hiddenDays = new Set(
                savedHidden
                  .map((x) => (typeof x === 'string' ? x : ''))
                  .filter(Boolean),
              );
            }
          }
        } catch {
          state = {};
          hiddenDays = new Set();
        }
        // First scan to find all dates and the latest day
        const items = nav.querySelectorAll('li');
        const dayItems = [];
        let latestDay = '';

        items.forEach((li) => {
          const childUl = li.querySelector(':scope > ul');
          const directLink = li.querySelector(':scope > a');
          if (!childUl || directLink) return;

          // Get the date text:
          // - First time: the li's first text node
          // - Already initialized: the label inside the wrapper
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

          const dayKey = rangeMatch ? rangeMatch[2] : rawText; // Use the range end-day to determine the latest day
          if (hiddenDays.has(dayKey)) return;

          dayItems.push({ li, text: rawText, firstTextNode, dayKey });
          if (!latestDay || dayKey > latestDay) {
            latestDay = dayKey;
          }
        });

        if (!dayItems.length) return;

        // Determine whether an updated new day has appeared
        const prevLatest =
          typeof state.__latestDay === 'string' ? state.__latestDay : null;
        const isNewDay =
          latestDay &&
          (!prevLatest || (typeof prevLatest === 'string' && latestDay > prevLatest));

        // If a new day appears: clear historical state and keep only the latest day's info
        if (isNewDay) {
          const prevHidden = hiddenDays;
          state = { __latestDay: latestDay };
          if (prevHidden.size) {
            state[HIDDEN_DAYS_KEY] = Array.from(prevHidden);
          }
        } else if (!prevLatest && latestDay) {
          // First use, with no history and not a new-day-reset case: record the current latest date
          state.__latestDay = latestDay;
        }

        const hasAnyState =
          !isNewDay &&
          Object.keys(state).some((k) => k && !k.startsWith('__'));

        const ensureStateSaved = () => {
          try {
            if (window.localStorage) {
              state[HIDDEN_DAYS_KEY] = Array.from(hiddenDays);
              window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            }
          } catch {
            // ignore
          }
        };

        const downloadDayMeta = async (opts) => {
          const { li: rowLi, rawText: rowText } = opts || {};
          const dayPaperItems = collectDayPaperItems(rowLi);
          const payload = {
            label: String(rowText || 'daily-papers').trim(),
            date: String(rowText || '').trim(),
            generated_at: new Date().toISOString(),
            count: 0,
            papers: [],
            errors: [],
          };

          const menuDownload = rowLi
            ? rowLi.querySelector('.sidebar-day-menu-item-download')
            : null;
          const oldText = menuDownload ? menuDownload.textContent : null;
          if (menuDownload) {
            menuDownload.disabled = true;
            menuDownload.textContent = 'Downloading...';
          }
          try {
            if (!dayPaperItems.length) {
              payload.errors.push({
                paper_id: '',
                error: 'No exportable papers found under this day group',
              });
            } else {
              const baseHref = window.location.href.split('#')[0];
              await Promise.all(
                dayPaperItems.map(async (item) => {
                  let rawMarkdown = '';
                  try {
                    const rel = joinUrlPath(
                      getDocsifyBasePath(),
                      `${item.paperId}.md`,
                    );
                    const mdUrl = new URL(rel, baseHref).toString();
                    const resp = await fetch(mdUrl, { cache: 'no-store' });
                    if (!resp.ok) {
                      throw new Error(`HTTP ${resp.status}`);
                    }
                    rawMarkdown = await resp.text();
                  } catch (err) {
                    payload.errors.push({
                      paper_id: item.paperId,
                      error: String(err && err.message ? err.message : err),
                    });
                    return;
                  }

                  try {
                    payload.papers.push(
                      buildPaperMetaFromMarkdown(item.paperId, item.section, rawMarkdown),
                    );
                  } catch (err) {
                    payload.errors.push({
                      paper_id: item.paperId,
                      error: String(err && err.message ? err.message : err),
                    });
                  }
                }),
              );
            }

            payload.count = payload.papers.length;
            window.DPRLastDayExport = payload;

            const safeLabel = String(payload.label || 'daily-papers')
              .replace(/\s+/g, ' ')
              .trim()
              .replace(/[^\d\-~_ ]/g, '')
              .replace(/\s+/g, '_');
            const filename = `${safeLabel || 'daily-papers'}.json`;
            downloadJson(filename, payload);

            if (rowLi) {
              const trigger = rowLi.querySelector('.sidebar-day-menu-trigger');
              if (trigger) {
                trigger.title = `Downloaded: ${payload.count || 0}`;
              }
            }
          } catch (err) {
            if (rowLi) {
              const trigger = rowLi.querySelector('.sidebar-day-menu-trigger');
              if (trigger) {
                trigger.title = `Download failed (see console): ${String(
                  err && err.message ? err.message : err,
                )}`;
              }
            }
            console.warn('[DPR Export] Download failed:', err);
            throw err;
          } finally {
            if (menuDownload) {
              menuDownload.disabled = false;
              menuDownload.textContent = oldText || 'Download JSON';
            }
          }
        };

        const deleteDaySection = ({ rowLi, rowText, dayKey }) => {
          if (!rowLi) return;
          if (dayKey) hiddenDays.add(dayKey);
          if (dayKey) delete state[dayKey];
          if (rowText) delete state[rowText];
          markDayPapersUnrecommended(collectDayPaperItems(rowLi));
          closeAllDayMenus();
          ensureStateSaved();
          rowLi.remove();
          syncSidebarActiveIndicator({ animate: false });
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

        // Second pass: actually install the collapse behavior
        dayItems.forEach(({ li, text: rawText, firstTextNode, dayKey }) => {
          const childUl = li.querySelector(':scope > ul');
          if (childUl) childUl.classList.add('sidebar-day-content');
          const key = dayKey || rawText;

          // Reuse or create the wrapper (containing the date text and a small arrow)
          let wrapper = li.querySelector(':scope > .sidebar-day-toggle');
          if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'sidebar-day-toggle';

            const labelSpan = document.createElement('span');
            labelSpan.className = 'sidebar-day-toggle-label';
            labelSpan.textContent = rawText;

            const menuTrigger = document.createElement('button');
            menuTrigger.type = 'button';
            menuTrigger.className = 'sidebar-day-menu-trigger';
            menuTrigger.title = 'More actions';
            menuTrigger.setAttribute('aria-label', 'More actions');
            menuTrigger.textContent = '⋮';

            const menu = document.createElement('span');
            menu.className = 'sidebar-day-menu';

            const downloadBtn = document.createElement('button');
            downloadBtn.type = 'button';
            downloadBtn.className = 'sidebar-day-menu-item sidebar-day-menu-item-download';
            downloadBtn.textContent = 'Download JSON';
            downloadBtn.setAttribute('aria-label', 'Download paper metadata JSON');

            const arrowSpan = document.createElement('span');
            arrowSpan.className = 'sidebar-day-toggle-arrow';
            arrowSpan.textContent = '▾';

            const actions = document.createElement('span');
            actions.className = 'sidebar-day-toggle-actions';
            actions.appendChild(menuTrigger);
            menu.appendChild(downloadBtn);
            actions.appendChild(menu);
            actions.appendChild(arrowSpan);

            wrapper.appendChild(labelSpan);
            wrapper.appendChild(actions);

            // Replace the original text node with the wrapper
            if (firstTextNode && firstTextNode.parentNode === li) {
              li.replaceChild(wrapper, firstTextNode);
            }
          }

          const labelSpan = wrapper.querySelector('.sidebar-day-toggle-label');
          if (labelSpan) labelSpan.textContent = rawText;
          const arrowSpan = wrapper.querySelector('.sidebar-day-toggle-arrow');
          const menuTrigger = wrapper.querySelector('.sidebar-day-menu-trigger');
          const menu = wrapper.querySelector('.sidebar-day-menu');
          const downloadBtn = wrapper.querySelector('.sidebar-day-menu-item-download');

          if (menuTrigger && !menuTrigger.dataset.dprDayMenuTriggerBound) {
            menuTrigger.dataset.dprDayMenuTriggerBound = '1';
            menuTrigger.addEventListener('click', (e) => {
              e.preventDefault();
              e.stopPropagation();
              if (e.stopImmediatePropagation) e.stopImmediatePropagation();
              if (!menu) return;
              const nowOpen = !menu.classList.contains('is-open');
              if (nowOpen) {
                closeAllDayMenus();
                menu.classList.add('is-open');
              } else {
                menu.classList.remove('is-open');
              }
            });
          }

          if (downloadBtn && !downloadBtn.dataset.dprDownloadBound) {
            downloadBtn.dataset.dprDownloadBound = '1';
            downloadBtn.addEventListener('click', async (e) => {
              e.preventDefault();
              e.stopPropagation();
              if (e.stopImmediatePropagation) e.stopImmediatePropagation();
              if (downloadBtn.disabled) return;
              try {
                await downloadDayMeta({
                  li,
                  rawText,
                  dateKey: dayKey || rawText,
                });
              } catch {
                // ignore
              }
              if (menu) {
                menu.classList.remove('is-open');
              }
            });
          }

          // Decide the default expanded / collapsed state:
          // - If this is a "new day appeared" case: clear history and expand only the latest day;
          // - Otherwise, if a user preference (state) exists, follow it;
          // - Otherwise (first use with no history): expand only the latest day, collapse the rest.
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
              // Newly appeared date: follow the latest-day strategy by default
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

          // Initialize the height once (no animation, to avoid first-render flicker)
          setDayCollapsed(li, collapsed, { animate: false });

          // Bind click in the capture phase so it overrides any handler from older versions
          if (!wrapper.dataset.dprDayToggleBound) {
            wrapper.dataset.dprDayToggleBound = '1';

            // --- Drag detection: record the pointerdown start position, decide on click whether it was a drag ---
            let _dayTogglePtrStart = null;
            wrapper.addEventListener('pointerdown', (pe) => {
              _dayTogglePtrStart = { x: pe.clientX, y: pe.clientY };
            }, true);

            wrapper.addEventListener(
              'click',
              (e) => {
                // badge is being dragged; swallow the click
                if (wrapper._dprBadgeDragging) return;
                // When the drag distance exceeds the threshold, treat it as a drag and do not toggle collapse
                if (_dayTogglePtrStart) {
                  const dx = e.clientX - _dayTogglePtrStart.x;
                  const dy = e.clientY - _dayTogglePtrStart.y;
                  _dayTogglePtrStart = null;
                  if (Math.abs(dx) > 5 || Math.abs(dy) > 5) return;
                }
                // Do not trigger date collapse when clicking menu controls or the unread badge
                try {
                  const target = e && e.target && e.target.closest
                    ? e.target.closest(
                        '.sidebar-day-menu-trigger,.sidebar-day-menu,.sidebar-day-menu-item,.dpr-unread-badge',
                      )
                    : null;
                  if (target) return;
                } catch {
                  // ignore
                }
                closeAllDayMenus();
                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                const collapsed = li.classList.toggle('sidebar-day-collapsed');
                if (arrowSpan) arrowSpan.textContent = collapsed ? '▸' : '▾';
                setDayCollapsed(li, collapsed, { animate: true });
                state[rawText] = collapsed ? 'closed' : 'open';
                state.__latestDay = latestDay;
                ensureStateSaved();
                // Do an immediate sync first (for interaction feedback), then a final calibration after the animation,
                // otherwise the list keeps shifting during the max-height transition, making the highlight bar drift upward.
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

        // On each doneEach, refresh the max-height of the expanded group:
        // Avoids the active item being clipped after its height changes (e.g. rating buttons), which looks like "highlight but no text".
        requestAnimationFrame(() => {
          try {
            nav
              .querySelectorAll('li:not(.sidebar-day-collapsed) > ul.sidebar-day-content')
              .forEach((ul) => {
                // Only a silent correction, to avoid the max-height change triggering a transition that makes the sidebar appear to scroll/refresh
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

      const setupCollapsibleConferenceSidebar = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const STORAGE_KEY = 'dpr_sidebar_conference_state_v1';
        const ANIM_MS = 240;

        const readState = () => {
          try {
            const raw = window.localStorage
              ? window.localStorage.getItem(STORAGE_KEY)
              : null;
            return raw ? JSON.parse(raw) || {} : {};
          } catch {
            return {};
          }
        };

        const state = readState();
        const saveState = () => {
          try {
            if (window.localStorage) {
              window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            }
          } catch {
            // ignore
          }
        };

        const getDirectTextNode = (li) => {
          if (!li || typeof Node === 'undefined') return null;
          return (
            Array.from(li.childNodes || []).find((node) => {
              return node && node.nodeType === Node.TEXT_NODE && String(node.textContent || '').trim();
            }) || null
          );
        };

        const getDirectLabelNode = (li) => {
          if (!li) return null;
          const textNode = getDirectTextNode(li);
          if (textNode) return textNode;
          return (
            Array.from(li.children || []).find((node) => {
              if (!node || node.tagName === 'UL') return false;
              if (node.classList && node.classList.contains('sidebar-conference-content')) return false;
              if (node.classList && node.classList.contains('sidebar-conference-toggle')) return true;
              return !!String(node.textContent || '').trim();
            }) || null
          );
        };

        const getToggleLabel = (li) => {
          if (!li) return '';
          const label = li.querySelector(
            ':scope > .sidebar-conference-toggle .sidebar-conference-toggle-label',
          );
          if (label) return String(label.textContent || '').trim();
          const labelNode = getDirectLabelNode(li);
          return String((labelNode && labelNode.textContent) || '').trim();
        };

        const normalizeKeyPart = (value) => {
          return String(value || '').trim().toLowerCase().replace(/\s+/g, '-');
        };

        const getElementDepth = (el) => {
          let depth = 0;
          let current = el;
          while (current && current.parentElement) {
            depth += 1;
            current = current.parentElement;
          }
          return depth;
        };

        const syncOpenDescendantHeights = (li) => {
          if (!li) return;
          Array.from(
            li.querySelectorAll(
              'li.sidebar-conference-node:not(.sidebar-conference-collapsed) > ul.sidebar-conference-content',
            ),
          )
            .sort((a, b) => getElementDepth(b) - getElementDepth(a))
            .forEach((ul) => {
              ul.style.maxHeight = `${ul.scrollHeight}px`;
              ul.style.opacity = '1';
            });
        };

        const getConferenceContentHeight = (li) => {
          if (!li) return 0;
          syncOpenDescendantHeights(li);
          const ul = li.querySelector(':scope > ul.sidebar-conference-content, :scope > ul');
          return ul ? ul.scrollHeight : 0;
        };

        const updateOpenAncestorHeights = (li) => {
          let parent = li ? li.parentElement : null;
          while (parent) {
            const parentLi = parent.closest('li.sidebar-conference-node');
            if (!parentLi) break;
            if (!parentLi.classList.contains('sidebar-conference-collapsed')) {
              const ul = parentLi.querySelector(':scope > ul.sidebar-conference-content');
              if (ul) ul.style.maxHeight = `${getConferenceContentHeight(parentLi)}px`;
            }
            parent = parentLi.parentElement;
          }
        };

        const setConferenceCollapsed = (li, collapsed, options = {}) => {
          const { animate = true } = options || {};
          const ul = li.querySelector(':scope > ul');
          if (!ul) return;
          ul.classList.add('sidebar-conference-content');
          const doAnimate = animate && !prefersReducedMotion();

          if (!doAnimate) {
            ul.style.transition = 'none';
            ul.style.maxHeight = collapsed ? '0px' : `${getConferenceContentHeight(li)}px`;
            ul.style.opacity = collapsed ? '0' : '1';
            requestAnimationFrame(() => {
              ul.style.transition = '';
              updateOpenAncestorHeights(li);
            });
            return;
          }

          if (collapsed) {
            ul.style.maxHeight = `${getConferenceContentHeight(li)}px`;
            ul.style.opacity = '0';
            requestAnimationFrame(() => {
              ul.style.maxHeight = '0px';
              updateOpenAncestorHeights(li);
            });
          } else {
            ul.style.opacity = '1';
            ul.style.maxHeight = '0px';
            requestAnimationFrame(() => {
              ul.style.maxHeight = `${getConferenceContentHeight(li)}px`;
              updateOpenAncestorHeights(li);
              requestAnimationFrame(() => {
                updateOpenAncestorHeights(li);
              });
            });
          }

          setTimeout(() => {
            try {
              if (!li.classList.contains('sidebar-conference-collapsed')) {
                ul.style.maxHeight = `${getConferenceContentHeight(li)}px`;
              }
              updateOpenAncestorHeights(li);
              syncSidebarActiveIndicator({ animate: false });
            } catch {
              // ignore
            }
          }, ANIM_MS + 30);
        };

        const ensureToggle = (li, label, storageKey) => {
          if (!li || !label || !storageKey) return;
          const childUl = li.querySelector(':scope > ul');
          if (!childUl) return;

          li.classList.add('sidebar-conference-node');
          childUl.classList.add('sidebar-conference-content');

          let wrapper = li.querySelector(':scope > .sidebar-conference-toggle');
          if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'sidebar-conference-toggle';

            const labelSpan = document.createElement('span');
            labelSpan.className = 'sidebar-conference-toggle-label';

            const arrowSpan = document.createElement('span');
            arrowSpan.className = 'sidebar-conference-toggle-arrow';
            arrowSpan.setAttribute('aria-hidden', 'true');

            wrapper.appendChild(labelSpan);
            wrapper.appendChild(arrowSpan);

            const labelNode = getDirectLabelNode(li);
            if (labelNode && labelNode.parentNode === li) {
              li.replaceChild(wrapper, labelNode);
            } else {
              li.insertBefore(wrapper, li.firstChild);
            }
          }

          const labelSpan = wrapper.querySelector('.sidebar-conference-toggle-label');
          const arrowSpan = wrapper.querySelector('.sidebar-conference-toggle-arrow');
          if (labelSpan) labelSpan.textContent = label;

          const collapsed = state[storageKey] === 'closed';
          li.dataset.sidebarConferenceKey = storageKey;
          li.classList.toggle('sidebar-conference-collapsed', collapsed);
          if (arrowSpan) arrowSpan.textContent = collapsed ? '▸' : '▾';
          wrapper.setAttribute('role', 'button');
          wrapper.setAttribute('tabindex', '0');
          wrapper.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
          setConferenceCollapsed(li, collapsed, { animate: false });

          if (!wrapper.dataset.dprConferenceToggleBound) {
            wrapper.dataset.dprConferenceToggleBound = '1';

            // --- Drag detection: record the pointerdown start position, decide on click whether it was a drag ---
            let _confTogglePtrStart = null;
            wrapper.addEventListener('pointerdown', (pe) => {
              _confTogglePtrStart = { x: pe.clientX, y: pe.clientY };
            }, true);

            const toggle = (event) => {
              // badge is being dragged; swallow the click
              if (wrapper._dprBadgeDragging) return;
              // When the drag distance exceeds the threshold, treat it as a drag and do not toggle collapse
              if (event && event.type === 'click' && _confTogglePtrStart) {
                const dx = event.clientX - _confTogglePtrStart.x;
                const dy = event.clientY - _confTogglePtrStart.y;
                _confTogglePtrStart = null;
                if (Math.abs(dx) > 5 || Math.abs(dy) > 5) return;
              }
              if (event) {
                event.preventDefault();
                event.stopPropagation();
                if (event.stopImmediatePropagation) event.stopImmediatePropagation();
              }
              const nowCollapsed = li.classList.toggle('sidebar-conference-collapsed');
              const currentArrow = wrapper.querySelector('.sidebar-conference-toggle-arrow');
              if (currentArrow) currentArrow.textContent = nowCollapsed ? '▸' : '▾';
              wrapper.setAttribute('aria-expanded', nowCollapsed ? 'false' : 'true');
              state[storageKey] = nowCollapsed ? 'closed' : 'open';
              saveState();
              setConferenceCollapsed(li, nowCollapsed, { animate: true });
              requestAnimationFrame(() => {
                syncSidebarActiveIndicator({ animate: false });
              });
            };
            wrapper.addEventListener('click', toggle, true);
            wrapper.addEventListener('keydown', (event) => {
              const keyName = event && event.key ? event.key : '';
              if (keyName !== 'Enter' && keyName !== ' ') return;
              toggle(event);
            });
          }
        };

        const buildNodeKey = (rootLi, li, label) => {
          if (li === rootLi) return 'root:conference-papers';
          const labels = [];
          let current = li;
          while (current && current !== rootLi) {
            const currentLabel = getToggleLabel(current);
            if (currentLabel) labels.unshift(normalizeKeyPart(currentLabel));
            const parentUl = current.parentElement;
            current = parentUl ? parentUl.closest('li.sidebar-conference-node, li') : null;
          }
          const path = labels.filter(Boolean).join('/');
          return `conference:${path || normalizeKeyPart(label)}`;
        };

        const setupConferenceTree = (rootLi, li) => {
          if (!li || !li.querySelector(':scope > ul')) return;
          const label = li === rootLi ? 'Conference Papers' : getToggleLabel(li);
          if (!label) return;
          ensureToggle(li, label, buildNodeKey(rootLi, li, label));
          Array.from(li.querySelectorAll(':scope > ul > li')).forEach((childLi) => {
            setupConferenceTree(rootLi, childLi);
          });
        };

        const rootItems = Array.from(nav.querySelectorAll('li')).filter((li) => {
          if (!li.querySelector(':scope > ul')) return false;
          return getToggleLabel(li) === 'Conference Papers';
        });

        rootItems.forEach((rootLi) => {
          setupConferenceTree(rootLi, rootLi);
        });

        requestAnimationFrame(() => {
          try {
            Array.from(
              nav.querySelectorAll(
                'li.sidebar-conference-node:not(.sidebar-conference-collapsed) > ul.sidebar-conference-content',
              ),
            )
              .sort((a, b) => getElementDepth(b) - getElementDepth(a))
              .forEach((ul) => {
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

      // 4. Paper "read" state management (stored in localStorage)
      const READ_STORAGE_KEY = 'dpr_read_papers_v1';

      const loadReadState = () => {
        // Authenticated users read from the Supabase cache first
        if (window.DPRReadStateSync && window.DPRReadStateSync.isActive()) {
          return window.DPRReadStateSync.getAll();
        }
        try {
          if (!window.localStorage) return {};
          const raw = window.localStorage.getItem(READ_STORAGE_KEY);
          if (!raw) return {};
          const obj = JSON.parse(raw);
          if (!obj || typeof obj !== 'object') return {};

          // Backward compatibility (when the value is true)
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
        // Always persist to localStorage (offline fallback)
        try {
          if (window.localStorage) {
            window.localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(state));
          }
        } catch {
          // ignore
        }
      };

      const markPaperRead = (paperId, status) => {
        if (!paperId) return;
        const st = status || 'read';
        // Write localStorage
        const state = loadReadState();
        state[paperId] = st;
        saveReadState(state);
        // Sync to Supabase
        if (window.DPRReadStateSync && window.DPRReadStateSync.isActive()) {
          window.DPRReadStateSync.markRead(paperId, st);
        }
      };

      const clearPaperRead = (paperId) => {
        if (!paperId) return;
        const state = loadReadState();
        delete state[paperId];
        saveReadState(state);
        if (window.DPRReadStateSync && window.DPRReadStateSync.isActive()) {
          window.DPRReadStateSync.clearRead(paperId);
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
        if (!res.ok) throw new Error(`Could not read the article Markdown (HTTP ${res.status})`);
        return await res.text();
      };

      const loadChatHistoryForPaper = async (paperId) => {
        if (!paperId) return [];
        // IndexedDB first: dpr_chat_db_v1 / paper_chats
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
        // Fallback: legacy localStorage
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
        const builder =
          window.DPRGistShareUtils &&
          typeof window.DPRGistShareUtils.buildShareMarkdown === 'function'
            ? window.DPRGistShareUtils.buildShareMarkdown
            : null;
        if (builder) {
          return builder({
            paperId,
            pageMd,
            chatMessages,
            origin: String(window.location.origin || ''),
            generatedAt: new Date().toISOString(),
          });
        }

        const parsed = parseFrontMatter(String(pageMd || ''));
        const safeMeta = parsed && parsed.meta && typeof parsed.meta === 'object' ? parsed.meta : {};
        const body = parsed && typeof parsed.body === 'string'
          ? parsed.body
          : String(pageMd || '').replace(/^---\n[\s\S]*?\n---\n?/, '').trim();
        const heading = String(safeMeta.title_zh || safeMeta.title || paperId || 'Paper Share').trim();
        const subtitle = safeMeta.title_zh && safeMeta.title ? String(safeMeta.title).trim() : '';
        const tags = Array.isArray(safeMeta.tags) ? safeMeta.tags : [];
        const pageUrl = `${String(window.location.origin || '').replace(/\/+$/, '')}/#/${paperId}`;
        const parts = [];

        parts.push('<!-- Shared by Daily Paper Reader -->');
        parts.push('');
        parts.push(`# ${heading}`);
        if (subtitle) {
          parts.push('');
          parts.push(`_${subtitle}_`);
        }
        parts.push('');
        if (safeMeta.authors) parts.push(`- **Authors**: ${String(safeMeta.authors).trim()}`);
        if (safeMeta.source) parts.push(`- **Source**: ${String(safeMeta.source).trim()}`);
        if (safeMeta.date) parts.push(`- **Date**: ${String(safeMeta.date).trim()}`);
        if (safeMeta.pdf) parts.push(`- **PDF**: ${String(safeMeta.pdf).trim()}`);
        if (tags.length) parts.push(`- **Tags**: ${tags.join(', ')}`);
        if (safeMeta.evidence) parts.push(`- **Evidence**: ${String(safeMeta.evidence).trim()}`);
        if (safeMeta.tldr) parts.push(`- **TLDR**: ${String(safeMeta.tldr).trim()}`);
        parts.push(`- **Source page**: ${pageUrl}`);
        parts.push(`- **Generated at**: ${new Date().toISOString()}`);
        parts.push('');
        parts.push('---');
        parts.push('');
        parts.push(body || String(pageMd || '').trim());
        parts.push('');
        parts.push('---');
        parts.push('');
        parts.push('## 💬 Chat History (local records)');
        parts.push('');
        if (!chatMessages || !chatMessages.length) {
          parts.push('No conversation yet.');
          return parts.join('\n');
        }
        chatMessages.forEach((m) => {
          const role = m && m.role ? String(m.role) : 'unknown';
          const time = m && m.time ? String(m.time) : '';
          const content = m && m.content ? String(m.content) : '';
          if (role === 'thinking') {
            parts.push('<details>');
            parts.push(`<summary>🧠 Thinking ${time ? `(${time})` : ''}</summary>`);
            parts.push('');
            parts.push('```');
            parts.push(content);
            parts.push('```');
            parts.push('</details>');
            parts.push('');
            return;
          }
          const label = role === 'ai' ? '🤖 AI' : role === 'user' ? '👤 You' : role;
          parts.push(`### ${label}${time ? ` (${time})` : ''}`);
          parts.push(content);
          parts.push('');
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
            <div class="dpr-gist-share-title">Share link</div>
            <div class="dpr-gist-share-row">
              <input class="dpr-gist-share-input" type="text" readonly />
              <button class="dpr-gist-share-copy" type="button">Copy</button>
            </div>
            <div class="dpr-gist-share-hint"></div>
          </div>
        `;
        overlay.addEventListener('pointerdown', (e) => {
          // Click outside to close
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
              if (hint) hint.textContent = 'Copied';
            } catch {
              const hint = overlay.querySelector('.dpr-gist-share-hint');
              if (hint) hint.textContent = 'Copy failed, please copy manually';
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
            description: 'Paper share (Daily Paper Reader)',
            public: false,
            files: {
              [filename]: { content },
            },
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = data && data.message ? String(data.message) : '';
          // GitHub often returns 404 Not Found for unsupported/unauthorized tokens (especially fine-grained PATs, which do not support Gist)
          if (res.status === 404) {
            throw new Error(
              'Not Found (common cause: you are using a Fine-grained PAT, which the GitHub Gist API does not support; please use a Classic PAT with the gist scope enabled)',
            );
          }
          if (res.status === 401) {
            throw new Error('Unauthorized (token is invalid or expired)');
          }
          if (res.status === 403) {
            throw new Error(
              `Insufficient permissions (a Classic PAT with the gist scope is required).${msg ? ` Details: ${msg}` : ''}`.trim(),
            );
          }
          throw new Error(msg || `HTTP ${res.status}`);
        }
        return data;
      };

      const sharePaperToGist = async (paperId) => {
        const token = loadGithubTokenForGist();
        if (!token) {
          showShareModal('', 'No GitHub Token detected. Please configure a GitHub Token on the home page first.');
          return;
        }
        const pageMd = await fetchPaperMarkdownById(paperId);
        const chat = await loadChatHistoryForPaper(paperId);
        const content = buildShareMarkdown(paperId, pageMd, chat);

        // Filename: last segment of paperId + .md
        const slug = String(paperId || 'paper').split('/').slice(-1)[0] || 'paper';
        const filename = `${slug}.md`;
        const data = await createGist(token, filename, content);
        const url = data && data.html_url ? String(data.html_url) : '';
        const preview = data && data.id ? `https://gist.io/${data.id}` : '';
        showShareModal(url, preview ? `Rich preview: ${preview}` : '');
      };

      // --- Sidebar unread badge update ---
      const updateSidebarUnreadBadges = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        const state = loadReadState();

        let badgeCount = 0;

        // Find all first- and second-level groups (dates or conference names under Conference/Daily)
        nav.querySelectorAll('li').forEach((li) => {
          // Skip leaf nodes (the paper entries themselves)
          const childUl = li.querySelector('ul');
          if (!childUl) return;

          // Collect all paper links under this li (recursively across all descendants)
          const paperLinks = li.querySelectorAll('a.dpr-sidebar-item-link[href*="#/"]');
          if (!paperLinks.length) return;

          let total = 0;
          let readCount = 0;
          paperLinks.forEach((a) => {
            const href = a.getAttribute('href') || '';
            const m = href.match(/#\/(.+)$/);
            if (!m) return;
            const paperId = m[1].replace(/\/$/, '');
            total++;
            if (state[paperId]) readCount++;
          });

          const unread = total - readCount;

          // Find this li's heading element: try several selectors
          let titleEl = li.querySelector(':scope > p')
            || li.querySelector(':scope > a')
            || li.querySelector(':scope > div')
            || li.querySelector(':scope > strong')
            || li.querySelector(':scope > span');

          // docsify may render a group header as a bare text node with no wrapping tag
          // In that case we need to create a wrapping span
          if (!titleEl) {
            // Check whether the li's first child node is text
            const firstNode = li.childNodes[0];
            if (firstNode && firstNode.nodeType === 3 && firstNode.textContent.trim()) {
              const wrapper = document.createElement('span');
              wrapper.className = 'dpr-sidebar-group-title';
              wrapper.textContent = firstNode.textContent;
              li.replaceChild(wrapper, firstNode);
              titleEl = wrapper;
            }
          }

          if (!titleEl) return;

          // Find or create the badge — placed to the left of the actions button group
          let badge = li.querySelector(':scope > .sidebar-day-toggle > .dpr-unread-badge')
            || titleEl.querySelector('.dpr-unread-badge');
          if (!badge) {
            badge = document.createElement('span');
            badge.className = 'dpr-unread-badge';
            // If sidebar-day-toggle-actions exists, insert before it
            const actions = titleEl.querySelector('.sidebar-day-toggle-actions');
            if (actions) {
              titleEl.insertBefore(badge, actions);
            } else {
              titleEl.appendChild(badge);
            }
          }
          badge.textContent = unread > 0 ? String(unread) : '';
          badge.setAttribute('data-count', String(unread));
          if (unread > 0) {
            badgeCount++;
            if (!badge._dprDragBound) {
              badge._dprDragBound = true;
              badge.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return; // Only handle left click
                e.preventDefault();
                e.stopPropagation();
                console.log('[DPR-badge] mousedown fired on badge', badge.textContent);

                // Mark the badge as dragging — the wrapper's click handler checks this flag
                const parentToggle = badge.closest('.sidebar-day-toggle,.sidebar-conference-toggle');
                if (parentToggle) parentToggle._dprBadgeDragging = true;

                const rect = badge.getBoundingClientRect();
                const startX = e.clientX, startY = e.clientY;
                const origLeft = rect.left + rect.width / 2;
                const origTop = rect.top + rect.height / 2;

                const ghost = document.createElement('span');
                ghost.className = 'dpr-unread-badge-ghost';
                ghost.textContent = badge.textContent;
                ghost.style.left = (e.clientX - rect.width / 2) + 'px';
                ghost.style.top = (e.clientY - rect.height / 2) + 'px';
                document.body.appendChild(ghost);
                console.log('[DPR-badge] ghost created and appended');

                badge.style.opacity = '0';

                const clearDragFlag = () => {
                  setTimeout(() => {
                    if (parentToggle) parentToggle._dprBadgeDragging = false;
                  }, 80);
                };

                // --- Use document-level mousemove/mouseup, the most reliable drag pattern ---
                const onMouseMove = (ev) => {
                  ghost.style.left = (ev.clientX - rect.width / 2) + 'px';
                  ghost.style.top = (ev.clientY - rect.height / 2) + 'px';
                };

                const onMouseUp = (ev) => {
                  document.removeEventListener('mousemove', onMouseMove, true);
                  document.removeEventListener('mouseup', onMouseUp, true);

                  const dx = ev.clientX - startX, dy = ev.clientY - startY;
                  const dist = Math.sqrt(dx * dx + dy * dy);
                  console.log('[DPR-badge] mouseup: dist=' + dist.toFixed(1) + ' (threshold=60)');

                  if (dist > 60) {
                    // ── Drag far: mark as read and disappear ──
                    console.log('[DPR-badge] distance > 60, marking as read...');
                    const groupLi = badge.closest('li');
                    const links = groupLi ? groupLi.querySelectorAll('a.dpr-sidebar-item-link[href*="#/"]') : [];
                    console.log('[DPR-badge] found ' + links.length + ' paper links to mark read');
                    links.forEach((a) => {
                      const href = a.getAttribute('href') || '';
                      const m = href.match(/#\/(.+)$/);
                      if (m) {
                        const paperId = m[1].replace(/\/$/, '');
                        console.log('[DPR-badge] marking read:', paperId);
                        markPaperRead(paperId, 'read');
                      }
                    });
                    badge.style.opacity = '';
                    updateSidebarUnreadBadges();
                    clearDragFlag();
                    if (ghost.parentNode) ghost.remove();
                  } else {
                    // ── Drag near: snap back into place ──
                    console.log('[DPR-badge] distance < 60, returning to origin');
                    badge.style.opacity = '';
                    clearDragFlag();
                    if (ghost.parentNode) ghost.remove();
                  }
                };

                document.addEventListener('mousemove', onMouseMove, true);
                document.addEventListener('mouseup', onMouseUp, true);
                console.log('[DPR-badge] document listeners attached');
              });
            }
          }
        });

        if (badgeCount === 0) {
          console.debug('[DPR] updateSidebarUnreadBadges: no badges added (0 groups with unread)');
        }
      };

	      const markSidebarReadState = (currentPaperId) => {
	        const nav = document.querySelector('.sidebar-nav');
	        if (!nav) return;

	        const state = loadReadState();
        if (currentPaperId) {
          if (!state[currentPaperId]) {
            markPaperRead(currentPaperId, 'read');
            state[currentPaperId] = 'read';
          }
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
	          // Mark this as a specific paper entry to allow style refinement (avoids highlighting the whole day's title together)
	          li.classList.add('sidebar-paper-item');

          // Append "bookmark" buttons to the sidebar entry (green/blue/orange/red)
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

          // Left button container (share + favorite)
          let leftActions = li.querySelector('.sidebar-paper-left-actions');
	          if (!actionWrapper) {
	            actionWrapper = document.createElement('span');
	            actionWrapper.className = 'sidebar-paper-rating-icons';

	            goodIcon = document.createElement('button');
	            goodIcon.className = 'sidebar-paper-rating-icon good';
	            goodIcon.title = 'Mark as green bookmark';
	            goodIcon.setAttribute('aria-label', 'Green bookmark');
	            goodIcon.innerHTML = '';

              blueIcon = document.createElement('button');
              blueIcon.className = 'sidebar-paper-rating-icon blue';
              blueIcon.title = 'Mark as blue bookmark';
              blueIcon.setAttribute('aria-label', 'Blue bookmark');
              blueIcon.innerHTML = '';

              orangeIcon = document.createElement('button');
              orangeIcon.className = 'sidebar-paper-rating-icon orange';
              orangeIcon.title = 'Mark as orange bookmark';
              orangeIcon.setAttribute('aria-label', 'Orange bookmark');
              orangeIcon.innerHTML = '';

	            badIcon = document.createElement('button');
	            badIcon.className = 'sidebar-paper-rating-icon bad';
	            badIcon.title = 'Mark as red bookmark';
	            badIcon.setAttribute('aria-label', 'Red bookmark');
	            badIcon.innerHTML = '';

              // Create the left button container
              leftActions = document.createElement('span');
              leftActions.className = 'sidebar-paper-left-actions';

              const favoriteIcon = document.createElement('button');
              favoriteIcon.className = 'sidebar-paper-favorite-icon';
              favoriteIcon.title = 'Favorite';
              favoriteIcon.setAttribute('aria-label', 'Favorite');
              favoriteIcon.textContent = '☆';
              favoriteIcon.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // Toggle favorite state (feature to be implemented)
                const isActive = favoriteIcon.classList.toggle('active');
                favoriteIcon.textContent = isActive ? '★' : '☆';
              });

              const shareIcon = document.createElement('button');
              shareIcon.className = 'sidebar-paper-share-icon';
              shareIcon.title = 'Share (generate a GitHub Gist link)';
              shareIcon.setAttribute('aria-label', 'Share');
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
                  showShareModal('', `Upload failed: ${msg}`);
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

              // Add favorite and share buttons to the left container
              leftActions.appendChild(favoriteIcon);
              leftActions.appendChild(shareIcon);
              a.parentNode.insertBefore(leftActions, a);

              // Add bookmark buttons to the right container
	            actionWrapper.appendChild(goodIcon);
              actionWrapper.appendChild(blueIcon);
              actionWrapper.appendChild(orangeIcon);
	            actionWrapper.appendChild(badIcon);
	            a.parentNode.insertBefore(actionWrapper, a.nextSibling);
	          }

	          // Whether or not the button was just created, refresh the active state from the latest state (supports space-key toggle)
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

          // Update the group's unread badge
          updateSidebarUnreadBadges();
	      };

      const scoreToStarRating = (scoreValue) => {
        const score = Number(scoreValue);
        if (!Number.isFinite(score)) return 0;
        const clamped = Math.max(0, Math.min(10, score));
        return Math.floor(clamped + 0.5) / 2;
      };

      const buildSidebarStarsHtml = (scoreValue) => {
        const rating = scoreToStarRating(scoreValue);
        const scoreNum = Number(scoreValue);
        const scoreText = Number.isFinite(scoreNum) ? scoreNum.toFixed(1) : '';
        const title = scoreText
          ? `Score: ${scoreText}/10 (${rating.toFixed(1)}/5)`
          : 'Score: N/A';
        const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
        return (
          `<span class="dpr-stars" title="${escapeHtml(title)}" aria-label="${rating.toFixed(1)} out of 5">` +
          '<span class="dpr-stars-bg">☆☆☆☆☆</span>' +
          `<span class="dpr-stars-fill" style="width:${pct.toFixed(0)}%">★★★★★</span>` +
          '</span>'
        );
      };

      const hydrateStructuredSidebarItems = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        const links = nav.querySelectorAll('a.dpr-sidebar-item-link.dpr-sidebar-item-structured');
        links.forEach((a) => {
          if (a.dataset.sidebarStructuredHydrated === '1') return;
          const li = a.closest('li');
          if (li && li.classList) {
            li.classList.add('sidebar-paper-item');
          }
          const href = String(a.getAttribute('href') || '').trim();
          const routeMatch = href.match(/#\/(.+)$/);
          const routeId = routeMatch ? decodeURIComponent(routeMatch[1]).replace(/\/$/, '') : '';
          const arxivId = routeId ? routeId.split('/').slice(-1)[0] : '';
          const fallbackLink = arxivId ? `https://arxiv.org/abs/${arxivId}` : '';

          let payload = null;
          const raw = a.getAttribute('data-sidebar-item') || '';
          if (raw) {
            try {
              payload = JSON.parse(raw);
            } catch {
              payload = null;
            }
          }

          // Backward compatibility for legacy sidebars: backfill structured data from the old DOM (title/tags/score)
          if (!payload || typeof payload !== 'object') {
            const legacyTitle = String(
              (a.querySelector('.dpr-sidebar-title') && a.querySelector('.dpr-sidebar-title').textContent) ||
                a.textContent ||
                '',
            ).trim();
            const legacyScoreNode = a.querySelector('.dpr-sidebar-tag-score .dpr-stars');
            const legacyScoreTitle = String(
              (legacyScoreNode && legacyScoreNode.getAttribute('title')) || '',
            );
            const scoreMatch = legacyScoreTitle.match(/(?:评分：|Score:)\s*([0-9]+(?:\.[0-9]+)?)\s*\/10/);
            const legacyScore = scoreMatch ? scoreMatch[1] : '-';
            const legacyTags = [];
            const tagNodes = a.querySelectorAll('.dpr-sidebar-tag');
            tagNodes.forEach((node) => {
              if (node.classList.contains('dpr-sidebar-tag-score')) return;
              const label = String(node.textContent || '').trim();
              if (!label) return;
              let kind = 'other';
              if (node.classList.contains('dpr-sidebar-tag-keyword')) kind = 'keyword';
              if (node.classList.contains('dpr-sidebar-tag-query')) kind = 'query';
              if (node.classList.contains('dpr-sidebar-tag-paper')) kind = 'paper';
              legacyTags.push({ kind, label });
            });
            payload = {
              title: legacyTitle || routeId,
              link: fallbackLink || href,
              score: legacyScore,
              tags: legacyTags,
            };
          }

          if (!payload || typeof payload !== 'object') return;

          const title = String(payload.title || a.textContent || '').trim();
          const link = String(payload.link || fallbackLink || href || '').trim();
          const score = String(payload.score || '').trim();
          const evidence = String((payload && payload.evidence) || '').trim();
          const tags = Array.isArray(payload.tags) ? payload.tags : [];

          const scoreHtml =
            score && score !== '-'
              ? `<span class="dpr-sidebar-tag dpr-sidebar-tag-score">${buildSidebarStarsHtml(score)}</span>`
              : '<span class="dpr-sidebar-score-empty">-</span>';

          const tagsHtml = tags
            .map((item) => {
              const rawKind = String((item && item.kind) || 'other').trim().toLowerCase();
              const kind = /^(keyword|query|paper|other)$/.test(rawKind) ? rawKind : 'other';
              const label = String((item && item.label) || '').trim();
              if (!label) return '';
              return `<span class="dpr-sidebar-tag dpr-sidebar-tag-${kind}">${escapeHtml(label)}</span>`;
            })
            .filter(Boolean)
            .join(' ');

          a.innerHTML =
            `<div class="dpr-sidebar-title">${escapeHtml(title)}</div>` +
            `<div class="dpr-sidebar-link-line">${escapeHtml(evidence || '-')}</div>` +
            `<div class="dpr-sidebar-meta-line">` +
            `${scoreHtml}` +
            `<span class="dpr-sidebar-meta-tags">${tagsHtml || '<span class="dpr-sidebar-tag dpr-sidebar-tag-other">-</span>'}</span>` +
            `</div>`;
          a.dataset.sidebarStructuredHydrated = '1';
        });
      };

      const neutralizeSidebarNoactiveLinks = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        const links = nav.querySelectorAll('a.dpr-sidebar-noactive-link');
        links.forEach((a) => {
          try {
            a.classList.remove('active', 'router-link-active');
          } catch {
            // ignore
          }
          try {
            const li = a.closest('li');
            if (li) {
              li.classList.remove('active');
            }
          } catch {
            // ignore
          }
        });
      };

      const bindSidebarVirtualHashLinks = () => {
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;
        const links = nav.querySelectorAll('a[data-dpr-hash]');
        links.forEach((a) => {
          if (a.dataset.dprHashBound === '1') return;
          a.dataset.dprHashBound = '1';
          a.addEventListener('click', (e) => {
            const target = normalizeHref(a.getAttribute('data-dpr-hash') || '');
            if (!target) return;
            e.preventDefault();
            DPR_NAV_STATE.lastNavSource = 'click';
            window.location.hash = target;
          });
        });
      };

      // Paper-page title bar in sidebar/body: English on the right, Chinese on the left, vertical bar in between
      const isPaperRouteFile = (file) => {
        const f = String(file || '');
        return (
          /^(?:\d{6}\/\d{2}|\d{8}-\d{8})\/(?!README\.md$).+\.md$/i.test(f) ||
          /^conference\/[^/]+\/(?!README\.md$).+\.md$/i.test(f)
        );
      };

      const isReportRouteFile = (file) => {
        const f = String(file || '');
        return /^(?:\d{6}\/\d{2}|\d{8}-\d{8})\/README\.md$/i.test(f);
      };

      const fitTextToBox = (el, minPx, maxPx) => {
        if (!el) return;
        let size = maxPx;
        el.style.fontSize = `${size}px`;
        // Shrink step by step until it no longer overflows or reaches the minimum
        // Note: scrollHeight > clientHeight indicates overflow (including line-clamp truncation)
        while (size > minPx && el.scrollHeight > el.clientHeight + 1) {
          size -= 1;
          el.style.fontSize = `${size}px`;
        }
      };

      // Prepare a "body wrapper" for the page-transition animation, to avoid fading the chat overlay/white mask along with it (which would flicker)
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
        // Move the currently rendered body content into root as a whole (the chat module is not inserted yet, so the input box is not moved in)
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

      const syncPageTypeClasses = ({
        isHomePage = false,
        isReportPage = false,
        isPaperPage = false,
      } = {}) => {
        const body = document.body;
        if (!body || !body.classList) return;
        body.classList.toggle('dpr-home-page', !!isHomePage);
        body.classList.toggle('dpr-report-page', !!isReportPage);
        body.classList.toggle('dpr-landing-page', !!(isHomePage || isReportPage));
        body.classList.toggle('dpr-paper-page', !!isPaperPage);
      };

      const applyPaperTitleBar = () => {
        const file = vm && vm.route ? vm.route.file : '';
        if (!isPaperRouteFile(file)) {
          return;
        }

        const section = document.querySelector('.markdown-section');
        if (!section) return;
        const root =
          section.querySelector(`:scope > .${DPR_PAGE_CONTENT_CLASS}`) || section;

        // Prevent duplicate insertion
        const existing = root.querySelector('.dpr-title-bar');
        if (existing) existing.remove();
        const h1s = Array.from(root.querySelectorAll('h1'));
        if (!h1s.length) return;

        // Prefer reading the title from the h1 with the paper-title-zh / paper-title-en class (frontmatter rendering)
        const paperTitleZh = root.querySelector('h1.paper-title-zh');
        const paperTitleEn = root.querySelector('h1.paper-title-en');

        let cnTitle = '';
        let enTitle = '';

        if (paperTitleZh || paperTitleEn) {
          // New format: read from the class-named h1 rendered by frontmatter
          cnTitle = paperTitleZh ? (paperTitleZh.textContent || '').trim() : '';
          enTitle = paperTitleEn ? (paperTitleEn.textContent || '').trim() : '';
        } else {
          // Legacy format: if there are two h1s, the first is English and the second is Chinese;
          // if there is only one h1, treat it as a single title placed on the left (cn area)
          enTitle = (h1s[0].textContent || '').trim();
          cnTitle = (h1s[1] ? (h1s[1].textContent || '').trim() : '').trim();
          if (h1s.length === 1) {
            cnTitle = enTitle;
            enTitle = '';
          }
        }

        // Fallback: if only an English title exists (no title_zh), move the English to the left,
        // to avoid a "no title" state after the dpr-title-single style hides the right-side English area.
        if (!cnTitle && enTitle) {
          cnTitle = enTitle;
          enTitle = '';
        }

        // Hide the original h1 but keep it in the DOM for copy/SEO/metadata-extraction fallback
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

        // Adaptive font sizing: keep the title bar height stable; long titles shrink automatically
        requestAnimationFrame(() => {
          const cnEl = bar.querySelector('.dpr-title-cn');
          const enEl = bar.querySelector('.dpr-title-en');
          if (cnEl && cnTitle) fitTextToBox(cnEl, 14, 22);
          if (enEl && enTitle) fitTextToBox(enEl, 13, 20);
        });
      };

      // Paper-page navigation: swipe left/right or use arrow keys to switch papers
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

        // Clean up the old one (e.g. hot-reload/duplicate-init scenarios)
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
        // Disable transition on creation to avoid a secondary "slide down from the sidebar top" animation
        indicator.style.transition = 'none';
        // Put it first so it sits beneath all li elements
        nav.insertBefore(indicator, nav.firstChild);
        DPR_SIDEBAR_ACTIVE_INDICATOR.el = indicator;
        DPR_SIDEBAR_ACTIVE_INDICATOR.parent = nav;
        return { el: indicator, newlyCreated: true };
      };

      const hideSidebarActiveIndicator = () => {
        const ensured = ensureSidebarActiveIndicator();
        if (!ensured || !ensured.el) return;
        const indicator = ensured.el;
        // Avoid leftover good/bad colors on later reuse
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
          // offsetParent is null when display:none / collapsed
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

        // Clear the previous entry color state first to avoid a leftover background after unchecking/uncrossing
        try {
          indicator.classList.remove('is-good', 'is-bad', 'is-blue', 'is-orange');
        } catch {
          // ignore
        }

        // Enable only for paper entries (not date-group headers, etc.)
        if (!li.classList || !li.classList.contains('sidebar-paper-item')) return;
        // If this entry is under a collapsed group: hide the highlight layer to avoid a leftover selection background
        try {
          if (
            li.closest &&
            (li.closest('li.sidebar-day-collapsed') ||
              li.closest('li.sidebar-conference-collapsed'))
          ) {
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

        // Highlight-layer color: switches by good/bad state (the selection background for checked/crossed)
        try {
          const isGood =
            li.classList && li.classList.contains('sidebar-paper-good');
          const isBad = li.classList && li.classList.contains('sidebar-paper-bad');
          const isBlue =
            li.classList && li.classList.contains('sidebar-paper-blue');
          const isOrange =
            li.classList && li.classList.contains('sidebar-paper-orange');

          // Single select: if both exist (should not happen in theory), take the first by priority
          const any = isGood || isBad || isBlue || isOrange;
          indicator.classList.toggle('is-good', !!isGood && any && !isBad && !isBlue && !isOrange);
          indicator.classList.toggle('is-bad', !!isBad && any && !isGood && !isBlue && !isOrange);
          indicator.classList.toggle('is-blue', !!isBlue && any && !isGood && !isBad && !isOrange);
          indicator.classList.toggle('is-orange', !!isOrange && any && !isGood && !isBad && !isBlue);
        } catch {
          // ignore
        }

        // Cannot use offsetTop/offsetLeft:
        // The sidebar is deeply nested li/ul, so offset* references land on a middle layer, making the selection drift worse further down.
        // Use geometry relative to .sidebar-nav consistently so alignment stays accurate after expanding many days.
        const nav = ensured.parent || (li.closest && li.closest('.sidebar-nav'));
        const navRect = nav ? nav.getBoundingClientRect() : null;
        const liRect = li.getBoundingClientRect();
        const x = navRect ? liRect.left - navRect.left + (nav.scrollLeft || 0) : li.offsetLeft;
        const y = navRect ? liRect.top - navRect.top + (nav.scrollTop || 0) : li.offsetTop;
        const w = liRect.width || li.offsetWidth;
        const h = liRect.height || li.offsetHeight;

        // On creation / when animation is not wanted: turn off transition, jump to the final position, then restore transition
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

        // 1) Match precisely by the current route href first, to avoid hitting the wrong item when Docsify has multiple actives
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

        // 2) Fallback: if multiple actives exist, take the last one (usually the deeper, truly selected item)
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

      // Expose globally so it can be called on sidebar resize
      window.syncSidebarActiveIndicator = syncSidebarActiveIndicator;

      const DPR_TRANSITION = {
        // 'enter-from-left' | 'enter-from-right' | ''
        pendingEnter: '',
      };

      const decodeLegacyIdHash = (rawHash) => {
        const raw = String(rawHash || '').trim();
        if (!raw) return '';
        // Backward compatibility for Docsify legacy hashes: #/?id=%2f202602%2f06%2fxxx or #?id=/202602/06/xxx
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
        // Normalize to the route form without .md
        decoded = decoded.replace(/\.md$/i, '');
        if (!decoded.startsWith('/')) decoded = '/' + decoded;
        return '#'+ decoded;
      };

      const normalizeHref = (href) => {
        const raw = String(href || '').trim();
        if (!raw) return '';
        const legacy = decodeLegacyIdHash(raw);
        if (legacy) return legacy;
        // Normalize to the "#/xxxx" form
        if (raw.startsWith('#/')) return raw;
        if (raw.startsWith('#')) return '#/' + raw.slice(1).replace(/^\//, '');
        return '#/' + raw.replace(/^\//, '');
      };

      const isPaperHref = (href) => {
        const h = normalizeHref(href);
        // Match paper pages:
        // - Traditional path: #/YYYYMM/DD/slug
        // - Range path: #/YYYYMMDD-YYYYMMDD/slug
        // - Conference path: #/conference/<conference-year>/slug
        return (
          /^#\/(?:\d{6}\/\d{2}|\d{8}-\d{8})\/(?!README$).+/i.test(h) ||
          /^#\/conference\/[^/]+\/(?!README$).+/i.test(h)
        );
      };

      const isReportHref = (href) => {
        const h = normalizeHref(href);
        // Match daily-report pages:
        // - Traditional path: #/YYYYMM/DD/README
        // - Range path: #/YYYYMMDD-YYYYMMDD/README
        return /^#\/(?:\d{6}\/\d{2}|\d{8}-\d{8})\/README$/i.test(h);
      };

      const isPaperHrefFallback = (href) => {
        const h = normalizeHref(href);
        return h.startsWith('#/') && h.includes('/') && !/\/README$/i.test(h);
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

        // When centering, only a scroll animation is needed; no extra highlight animation
        const duration = prefersReducedMotion() ? 0 : DPR_TRANSITION_MS;
        animateScrollTop(scrollEl, clamped, duration);
      };

      const centerSidebarOnCurrent = () => {
        // Prefer following the Docsify active state (that is the item you actually see selected)
        const nav = document.querySelector('.sidebar-nav');
        if (nav) {
          const activeLi = nav.querySelector('li.active');
          const activeLink = nav.querySelector('a.active');
          const el = activeLi || activeLink;
          if (el) {
            const href = (activeLink && activeLink.getAttribute('href')) || '';
            // If an href is available, dedupe by href; otherwise use a stable placeholder key
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

        // Fallback: match by the current route href
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

        // Home: right-key/left-swipe (delta=+1) jumps to the first paper of the latest day
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

      // Unify the animation duration of sidebar-center-scroll and page-switch for a consistent feel
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

        // First slide the sidebar highlight layer to the target entry, in sync with the page switch
        moveSidebarActiveIndicatorToHref(target, { animate: true });
        DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = true;

        // When switching via arrow keys/swipe: pre-scroll the sidebar near the target for a more responsive feel
        if (DPR_NAV_STATE.lastNavSource !== 'click') {
          centerSidebarOnHref(target);
        }

        // Decide entry direction: forward => new page enters from the right; backward => from the left
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
        // Switch the route only after the exit animation finishes
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
        if (prev && now - prev.ts < 5 * 60 * 1000) return; // Do not refetch within 5 minutes
        try {
          const res = await fetch(url, { cache: 'force-cache' });
          if (!res.ok) return;
          // Read the body to ensure it is written to the browser cache (with an in-memory cache fallback)
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
          // Home: prefetch the first paper of the latest day
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

        // Disable the native Docsify heading-anchor click behavior
        document.addEventListener('click', (e) => {
          try {
            if (!e || e.defaultPrevented) return;
            const target = e.target;
            // Detect whether a heading or an anchor inside a heading was clicked
            if (target && target.closest) {
              const heading = target.closest('h1, h2, h3, h4, h5, h6');
              if (heading && heading.closest('.markdown-section')) {
                const link = target.closest('a');
                if (link && link.hash && link.hash.startsWith('#') && !link.hash.startsWith('#/')) {
                  // Prevent the default jump behavior of heading anchors
                  e.preventDefault();
                  e.stopPropagation();
                  return false;
                }
              }
            }
          } catch {
            // ignore
          }
        }, true); // Use the capture phase to intercept before Docsify

        const toggleGoodForCurrent = () => {
          const current = DPR_NAV_STATE.currentHref || '';
          if (!current) return;
          const m = current.match(/^#\/(.+)$/);
          if (!m) return;
          const paperId = m[1];

          const state = loadReadState();
          const cur = state[paperId];
          // Space: toggle between good and read
          if (cur === 'good') {
            state[paperId] = 'read';
          } else {
            state[paperId] = 'good';
          }
	          saveReadState(state);
	          markSidebarReadState(null);
	          // Sync the highlight-layer color (avoid a leftover green background when toggling good <-> read)
	          requestAnimationFrame(() => {
	            syncSidebarActiveIndicator({ animate: false });
	          });
	        };

        // Generic bookmark toggle: number keys 1234 map to green/blue/purple/red
        const toggleBookmarkForCurrent = (bookmarkType) => {
          const current = DPR_NAV_STATE.currentHref || '';
          if (!current) return;
          const m = current.match(/^#\/(.+)$/);
          if (!m) return;
          const paperId = m[1];

          const state = loadReadState();
          const cur = state[paperId];
          // Toggle: if already in this state, clear it (back to read); otherwise set this state
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
          // Remove focus from all buttons so number keys do not trigger them
          if (document.activeElement && document.activeElement.blur) {
            document.activeElement.blur();
          }
        };

        // Keyboard: left/right arrow keys + number keys 1234
        window.addEventListener('keydown', (e) => {
          const key = e.key || '';
          if (shouldIgnoreKeyNav(e)) return;

          // Number keys 1234: green/blue/purple/red bookmarks
          if (key === '1') {
            e.preventDefault();
            toggleBookmarkForCurrent('good');   // green
            return;
          }
          if (key === '2') {
            e.preventDefault();
            toggleBookmarkForCurrent('blue');   // blue
            return;
          }
          if (key === '3') {
            e.preventDefault();
            toggleBookmarkForCurrent('orange'); // purple (orange)
            return;
          }
          if (key === '4') {
            e.preventDefault();
            toggleBookmarkForCurrent('bad');    // red
            return;
          }

          if (key === ' ') {
            // Space key: toggle "good (green check)"
            e.preventDefault();
            toggleGoodForCurrent();
            return;
          }
          if (key !== 'ArrowLeft' && key !== 'ArrowRight') return;
          // Only works while the current page is focused: the browser window being focused is enough
          e.preventDefault();
          DPR_NAV_STATE.lastNavSource = 'key';
          navigateByDelta(key === 'ArrowRight' ? +1 : -1);
        });

        // Clicking a paper link also uses the same full-page-switch animation (so it is not limited to swipe/arrow keys)
        document.addEventListener('click', (e) => {
          try {
            if (!e || e.defaultPrevented) return;
            // Only intercept plain left clicks, to avoid affecting open-in-new-tab/copy-link behavior
            if (typeof e.button === 'number' && e.button !== 0) return;
            if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;

            const link = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (!link) return;
            if (link.hasAttribute('download')) return;
            if (link.classList && link.classList.contains('dpr-sidebar-export-link')) return;
            const rawHref = String(link.getAttribute('href') || '').trim();
            if (rawHref.startsWith('blob:')) return;
            // Skip external links (e.g. PDF URLs) and let the browser open them directly
            if (/^https?:\/\//i.test(rawHref)) return;
            const href = link.getAttribute('href') || '';
            const target = normalizeHref(href);
            if (!target || !isPaperHref(target) && !isPaperHrefFallback(target)) {
              return;
            }
            if (!target) return;
            if (target === (DPR_NAV_STATE.currentHref || '')) return;

            // Mouse click on the sidebar: do not trigger the centering logic
            DPR_NAV_STATE.lastNavSource = 'click';

            // Infer direction: determine forward/backward by sidebar order
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

            // Enable animation interception only on paper pages, to avoid a no-animation-but-delayed feel on the home page
            if (document.body && document.body.classList.contains('dpr-paper-page') && !prefersReducedMotion()) {
              e.preventDefault();
              triggerPageNav(target, direction);
            }
          } catch {
            // ignore
          }
        });

        // Mouse/trackpad horizontal scroll: switch papers and block the browser full-page-swipe/back animation
        document.addEventListener(
          'wheel',
          (e) => {
            if (shouldIgnoreKeyNav(e)) return;
            const dx = e.deltaX || 0;
            const dy = e.deltaY || 0;
            if (Math.abs(dx) < 28) return;
            if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
            e.preventDefault();
            // dx < 0: swipe left => next paper
            // dx > 0: swipe right => previous paper
            DPR_NAV_STATE.lastNavSource = 'wheel';
            navigateByDelta(dx < 0 ? +1 : -1);
          },
          { passive: false },
        );

        // Touch swipe: switch left/right
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
            // Block the browser horizontal-swipe/back animation for a smoother switch
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
          // Exclude long press, slight swipes, and clear vertical scrolling
          if (dt > 900) return;
          if (Math.abs(dx) < threshold) return;
          if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
          // dx < 0: swipe left => next paper (equivalent to ArrowRight)
          // dx > 0: swipe right => previous paper (equivalent to ArrowLeft)
          DPR_NAV_STATE.lastNavSource = 'swipe';
          navigateByDelta(dx < 0 ? +1 : -1);
        };

        document.addEventListener('touchstart', onTouchStart, { passive: true });
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd, { passive: true });
      };

      // --- Parse YAML front matter and convert to HTML ---
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

        // Simple YAML parsing (no external library)
        const meta = {};
        const lines = yamlStr.split('\n');
        for (const line of lines) {
          const colonIdx = line.indexOf(':');
          if (colonIdx === -1) continue;
          const key = line.slice(0, colonIdx).trim();
          let value = line.slice(colonIdx + 1).trim();

          // Handle array format [a, b, c]
          if (value.startsWith('[') && value.endsWith(']')) {
            const inner = value.slice(1, -1);
            // Simple split, handling commas inside quotes
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
            // Strip quotes
            meta[key] = items.map(s => s.replace(/^["']|["']$/g, ''));
          } else {
            // Strip quotes
            meta[key] = value.replace(/^["']|["']$/g, '').replace(/\\n/g, '\n').replace(/\\"/g, '"');
          }
        }
        return { meta, body };
      };

      const escapePaperHtml = (s) => {
        if (!s) return '';
        return String(s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      };

      const parseMediaMeta = (meta, key) => {
        const raw = meta && typeof meta[key] === 'string' ? meta[key].trim() : '';
        if (!raw) return [];
        try {
          const parsed = JSON.parse(raw);
          if (!Array.isArray(parsed)) return [];
          return parsed
            .filter((item) => item && typeof item === 'object')
            .map((item, index) => ({
              url: String(item.url || '').trim(),
              caption: String(item.caption || '').trim(),
              page: Number(item.page || 0),
              index: Number(item.index || index + 1),
              width: Number(item.width || 0),
              height: Number(item.height || 0),
            }))
            .filter((item) => item.url);
        } catch (_err) {
          return [];
        }
      };

      const parseFiguresMeta = (meta) => parseMediaMeta(meta, 'figures_json');
      const parseTablesMeta = (meta) => parseMediaMeta(meta, 'tables_json');

      const resolveDocsAssetUrl = (value) => {
        const url = String(value || '').trim();
        if (!url) return '';
        if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:')) return url;
        const basePath = (window.$docsify && window.$docsify.basePath) || 'docs/';
        const safeBase = /\/$/.test(basePath) ? basePath : `${basePath}/`;
        if (url.startsWith('docs/')) return url;
        return `${safeBase}${url.replace(/^\/+/, '')}`;
      };

      const renderMediaCarousel = (items, options = {}) => {
        if (!items || !items.length) return '';
        const kind = options.kind || 'figure';
        const title = options.title || 'Figures';
        const label = options.label || 'Figure';
        const labelCn = options.labelCn || 'figure';
        const slides = items.map((item, index) => {
          const pageText = item.page ? `PDF page ${item.page}` : '';
          const caption = item.caption ? `<div class="paper-figure-caption">${escapePaperHtml(item.caption)}</div>` : '';
          return [
            `<div class="paper-figure-slide${index === 0 ? ' is-active' : ''}" data-figure-slide="${index}">`,
            '<div class="paper-figure-frame">',
            `<img class="paper-figure-image" src="${escapePaperHtml(resolveDocsAssetUrl(item.url))}" alt="Paper ${label} ${index + 1}" loading="lazy">`,
            '</div>',
            '<div class="paper-figure-meta">',
            `<div class="paper-figure-badge">${label} ${index + 1}${pageText ? ` · ${escapePaperHtml(pageText)}` : ''}</div>`,
            caption,
            '</div>',
            '</div>',
          ].join('');
        }).join('');

        const thumbs = items.map((item, index) => {
          const thumbPageText = item.page ? ` · PDF page ${item.page}` : '';
          return [
            `<button class="paper-figure-thumb${index === 0 ? ' is-active' : ''}" type="button" data-figure-thumb="${index}" aria-label="Switch to ${labelCn} ${index + 1}">`,
            `<img class="paper-figure-thumb-image" src="${escapePaperHtml(resolveDocsAssetUrl(item.url))}" alt="${label} Thumbnail ${index + 1}" loading="lazy">`,
            `<span class="paper-figure-thumb-label">${label} ${index + 1}${thumbPageText ? escapePaperHtml(thumbPageText) : ''}</span>`,
            '</button>',
          ].join('');
        }).join('');

        return [
          `<div class="paper-figure-section paper-${escapePaperHtml(kind)}-section" data-paper-figure-carousel data-paper-media-kind="${escapePaperHtml(kind)}">`,
          '<div class="paper-figure-toolbar">',
          `<div class="paper-figure-title">${escapePaperHtml(title)}</div>`,
          `<div class="paper-figure-counter"><span data-figure-current>1</span> / ${items.length}</div>`,
          '</div>',
          '<div class="paper-figure-stage">',
          '<div class="paper-figure-main">',
          items.length > 1 ? '<button class="paper-figure-nav paper-figure-nav-prev" type="button" data-figure-prev aria-label="Previous">‹</button>' : '',
          `<div class="paper-figure-viewport">${slides}</div>`,
          items.length > 1 ? '<button class="paper-figure-nav paper-figure-nav-next" type="button" data-figure-next aria-label="Next">›</button>' : '',
          '</div>',
          items.length > 1 ? [
            '<div class="paper-figure-thumbs-wrap">',
            '<button class="paper-figure-thumb-nav paper-figure-thumb-nav-prev" type="button" data-figure-thumb-prev aria-label="Previous thumbnail">‹</button>',
            `<div class="paper-figure-thumbs">${thumbs}</div>`,
            '<button class="paper-figure-thumb-nav paper-figure-thumb-nav-next" type="button" data-figure-thumb-next aria-label="Next thumbnail">›</button>',
            '</div>',
          ].join('') : '',
          '</div>',
          '</div>',
          '',
        ].join('');
      };

      const renderFigureCarousel = (figures) => renderMediaCarousel(figures, {
        kind: 'figure',
        title: 'Figures',
        label: 'Figure',
        labelCn: 'figure',
      });

      const renderTableCarousel = (tables) => renderMediaCarousel(tables, {
        kind: 'table',
        title: 'Tables',
        label: 'Table',
        labelCn: 'table',
      });

      const renderPaperMediaCarousels = (figures, tables) => {
        const hasFigures = Array.isArray(figures) && figures.length;
        const hasTables = Array.isArray(tables) && tables.length;
        if (!hasFigures && !hasTables) return '';
        const defaultTab = hasFigures ? 'figures' : 'tables';
        const figureButton = hasFigures ? [
          `<button class="paper-media-card${defaultTab === 'figures' ? ' is-primary' : ''}" type="button" data-paper-media-open="figures">`,
          '<span class="paper-media-card-kicker">Figures</span>',
          `<span class="paper-media-card-title">${figures.length} paper figures</span>`,
          '<span class="paper-media-card-action">Open carousel</span>',
          '</button>',
        ].join('') : '';
        const tableButton = hasTables ? [
          `<button class="paper-media-card${defaultTab === 'tables' ? ' is-primary' : ''}" type="button" data-paper-media-open="tables">`,
          '<span class="paper-media-card-kicker">Tables</span>',
          `<span class="paper-media-card-title">${tables.length} paper tables</span>`,
          '<span class="paper-media-card-action">Open carousel</span>',
          '</button>',
        ].join('') : '';
        const tabButtons = [
          hasFigures ? `<button class="paper-media-tab${defaultTab === 'figures' ? ' is-active' : ''}" type="button" data-paper-media-tab="figures">Figures <span>${figures.length}</span></button>` : '',
          hasTables ? `<button class="paper-media-tab${defaultTab === 'tables' ? ' is-active' : ''}" type="button" data-paper-media-tab="tables">Tables <span>${tables.length}</span></button>` : '',
        ].join('');
        const figurePanel = hasFigures ? [
          `<div class="paper-media-pane${defaultTab === 'figures' ? ' is-active' : ''}" data-paper-media-pane="figures">`,
          renderFigureCarousel(figures),
          '</div>',
        ].join('') : '';
        const tablePanel = hasTables ? [
          `<div class="paper-media-pane${defaultTab === 'tables' ? ' is-active' : ''}" data-paper-media-pane="tables">`,
          renderTableCarousel(tables),
          '</div>',
        ].join('') : '';
        return [
          '<div class="paper-media-attachments" data-paper-media-root>',
          '<div class="paper-media-summary">',
          '<div>',
          '<div class="paper-media-summary-kicker">Paper Media</div>',
          '<div class="paper-media-summary-title">Figure & table attachments</div>',
          '</div>',
          '<div class="paper-media-summary-cards">',
          figureButton,
          tableButton,
          '</div>',
          '</div>',
          '<div class="paper-media-modal" data-paper-media-modal aria-hidden="true">',
          '<div class="paper-media-backdrop" data-paper-media-close></div>',
          '<div class="paper-media-dialog" role="dialog" aria-modal="true" aria-label="Paper figure & table attachments" tabindex="-1">',
          '<div class="paper-media-dialog-head">',
          '<div>',
          '<div class="paper-media-dialog-kicker">Paper Media</div>',
          '<div class="paper-media-dialog-title">Paper figure & table attachments</div>',
          '</div>',
          '<div class="paper-media-dialog-actions">',
          '<button class="paper-media-fullscreen" type="button" data-paper-media-fullscreen aria-pressed="false" aria-label="View fullscreen">Fullscreen</button>',
          '<button class="paper-media-close" type="button" data-paper-media-close aria-label="Close">×</button>',
          '</div>',
          '</div>',
          `<div class="paper-media-tabs">${tabButtons}</div>`,
          '<div class="paper-media-body">',
          figurePanel,
          tablePanel,
          '</div>',
          '</div>',
          '</div>',
          '</div>',
          '',
        ].join('');
      };

      const bindPaperMediaModals = () => {
        document.querySelectorAll('[data-paper-media-root]').forEach((root) => {
          if (root.dataset.mediaBound === '1') return;
          root.dataset.mediaBound = '1';
          const modal = root.querySelector('[data-paper-media-modal]');
          const openButtons = Array.from(root.querySelectorAll('[data-paper-media-open]'));
          if (!modal) return;
          if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
          }
          const dialog = modal.querySelector('.paper-media-dialog');
          const closeButtons = Array.from(modal.querySelectorAll('[data-paper-media-close]'));
          const fullscreenButton = modal.querySelector('[data-paper-media-fullscreen]');
          const tabs = Array.from(modal.querySelectorAll('[data-paper-media-tab]'));
          const panes = Array.from(modal.querySelectorAll('[data-paper-media-pane]'));
          let savedScrollY = 0;
          let closeTimer = 0;
          let lastTrigger = null;
          const setFullscreen = (enabled) => {
            modal.classList.toggle('is-fullscreen', !!enabled);
            if (fullscreenButton) {
              fullscreenButton.setAttribute('aria-pressed', enabled ? 'true' : 'false');
              fullscreenButton.textContent = enabled ? 'Exit fullscreen' : 'Fullscreen';
              fullscreenButton.setAttribute('aria-label', enabled ? 'Exit fullscreen view' : 'View fullscreen');
            }
          };
          const activate = (name) => {
            tabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.paperMediaTab === name));
            panes.forEach((pane) => pane.classList.toggle('is-active', pane.dataset.paperMediaPane === name));
          };
          const restorePageScroll = () => {
            const top = Number.isFinite(savedScrollY) ? savedScrollY : window.scrollY || 0;
            try {
              window.scrollTo({ top, left: 0, behavior: 'instant' });
            } catch (_err) {
              window.scrollTo(0, top);
            }
          };
          const open = (name, trigger) => {
            if (closeTimer) {
              clearTimeout(closeTimer);
              closeTimer = 0;
            }
            savedScrollY = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            lastTrigger = trigger || document.activeElement || null;
            if (name) activate(name);
            setFullscreen(false);
            modal.classList.remove('is-closing');
            modal.classList.add('is-open');
            modal.setAttribute('aria-hidden', 'false');
            if (dialog) {
              setTimeout(() => {
                try {
                  dialog.focus({ preventScroll: true });
                } catch (_err) {
                  dialog.focus();
                  restorePageScroll();
                }
              }, 0);
            }
          };
          const close = () => {
            if (!modal.classList.contains('is-open')) return;
            setFullscreen(false);
            if (closeTimer) clearTimeout(closeTimer);
            modal.classList.add('is-closing');
            modal.classList.remove('is-open');
            modal.setAttribute('aria-hidden', 'true');
            closeTimer = setTimeout(() => {
              modal.classList.remove('is-closing');
              restorePageScroll();
              if (lastTrigger && typeof lastTrigger.focus === 'function') {
                try {
                  lastTrigger.focus({ preventScroll: true });
                } catch (_err) {
                  // ignore focus failures; scroll restoration above is the important part.
                }
              }
              closeTimer = 0;
            }, 190);
          };
          openButtons.forEach((button) => {
            button.addEventListener('click', () => open(button.dataset.paperMediaOpen || 'figures', button));
          });
          closeButtons.forEach((button) => button.addEventListener('click', (event) => {
            if (modal.classList.contains('is-fullscreen') && event.currentTarget.classList.contains('paper-media-backdrop')) {
              setFullscreen(false);
              return;
            }
            close();
          }));
          if (fullscreenButton) {
            fullscreenButton.addEventListener('click', () => {
              setFullscreen(!modal.classList.contains('is-fullscreen'));
            });
          }
          tabs.forEach((tab) => {
            tab.addEventListener('click', () => activate(tab.dataset.paperMediaTab || 'figures'));
          });
          modal.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
              if (modal.classList.contains('is-fullscreen')) {
                setFullscreen(false);
                return;
              }
              close();
            }
          });
        });
      };

      const bindPaperFigureCarousels = () => {
        document.querySelectorAll('[data-paper-figure-carousel]').forEach((root) => {
          if (root.dataset.bound === '1') return;
          root.dataset.bound = '1';

          const slides = Array.from(root.querySelectorAll('[data-figure-slide]'));
          const thumbs = Array.from(root.querySelectorAll('[data-figure-thumb]'));
          const thumbsTrack = root.querySelector('.paper-figure-thumbs');
          const prevBtn = root.querySelector('[data-figure-prev]');
          const nextBtn = root.querySelector('[data-figure-next]');
          const thumbPrevBtn = root.querySelector('[data-figure-thumb-prev]');
          const thumbNextBtn = root.querySelector('[data-figure-thumb-next]');
          const counter = root.querySelector('[data-figure-current]');
          if (!slides.length) return;

          let current = 0;
          const centerActiveThumb = () => {
            if (!thumbsTrack || !thumbs[current]) return;
            const activeThumb = thumbs[current];
            const targetLeft =
              activeThumb.offsetLeft -
              (thumbsTrack.clientWidth - activeThumb.offsetWidth) / 2;
            const maxLeft = Math.max(0, thumbsTrack.scrollWidth - thumbsTrack.clientWidth);
            const left = Math.min(Math.max(0, targetLeft), maxLeft);
            try {
              thumbsTrack.scrollTo({ left, behavior: 'smooth' });
            } catch (_err) {
              thumbsTrack.scrollLeft = left;
            }
          };
          const render = () => {
            slides.forEach((slide, index) => {
              slide.classList.toggle('is-active', index === current);
            });
            thumbs.forEach((thumb, index) => {
              thumb.classList.toggle('is-active', index === current);
            });
            if (counter) {
              counter.textContent = String(current + 1);
            }
            if (prevBtn) prevBtn.disabled = slides.length <= 1;
            if (nextBtn) nextBtn.disabled = slides.length <= 1;
            if (thumbPrevBtn) thumbPrevBtn.disabled = slides.length <= 1;
            if (thumbNextBtn) thumbNextBtn.disabled = slides.length <= 1;
            centerActiveThumb();
          };

          if (prevBtn) {
            prevBtn.addEventListener('click', () => {
              current = (current - 1 + slides.length) % slides.length;
              render();
            });
          }
          if (nextBtn) {
            nextBtn.addEventListener('click', () => {
              current = (current + 1) % slides.length;
              render();
            });
          }
          if (thumbPrevBtn) {
            thumbPrevBtn.addEventListener('click', () => {
              current = (current - 1 + slides.length) % slides.length;
              render();
            });
          }
          if (thumbNextBtn) {
            thumbNextBtn.addEventListener('click', () => {
              current = (current + 1) % slides.length;
              render();
            });
          }
          thumbs.forEach((thumb, index) => {
            thumb.addEventListener('click', () => {
              current = index;
              render();
            });
          });

          render();
        });
      };

      const closePdfPreview = () => {
        document.body.classList.remove('dpr-pdf-preview-open');
        document.querySelectorAll('[data-pdf-preview-toggle]').forEach((btn) => {
          btn.setAttribute('aria-expanded', 'false');
          btn.textContent = 'Preview PDF';
        });
      };

      const buildEmbeddablePdfUrl = (url) => {
        const raw = String(url || '').trim();
        if (!raw) return '';
        try {
          const parsed = new URL(raw, window.location.href);
          if (/openreview\.net$/i.test(parsed.hostname)) {
            return `https://docs.google.com/gview?embedded=1&url=${encodeURIComponent(parsed.href)}`;
          }
          return parsed.href;
        } catch (_err) {
          return raw;
        }
      };

      const ensurePdfPreviewPanel = () => {
        let panel = document.getElementById('dpr-pdf-preview-panel');
        if (panel) return panel;
        panel = document.createElement('aside');
        panel.id = 'dpr-pdf-preview-panel';
        panel.className = 'dpr-pdf-preview-panel';
        panel.setAttribute('aria-label', 'PDF preview');
        panel.innerHTML = [
          '<div class="dpr-pdf-preview-header">',
          '<div class="dpr-pdf-preview-title">PDF preview</div>',
          '<div class="dpr-pdf-preview-actions">',
          '<a class="dpr-pdf-preview-open-link" href="#" target="_blank" rel="noopener">Open in new window</a>',
          '<button class="dpr-pdf-preview-close" type="button" aria-label="Close PDF preview">×</button>',
          '</div>',
          '</div>',
          '<iframe class="dpr-pdf-preview-frame" title="PDF preview"></iframe>',
        ].join('');
        document.body.appendChild(panel);
        panel.querySelector('.dpr-pdf-preview-close')?.addEventListener('click', closePdfPreview);
        return panel;
      };

      const bindPdfPreviewToggle = () => {
        document.querySelectorAll('[data-pdf-preview-toggle]').forEach((btn) => {
          if (btn.dataset.bound === '1') return;
          btn.dataset.bound = '1';
          btn.addEventListener('click', () => {
            const url = String(btn.getAttribute('data-pdf-url') || '').trim();
            if (!url) return;
            const panel = ensurePdfPreviewPanel();
            const frame = panel.querySelector('.dpr-pdf-preview-frame');
            const openLink = panel.querySelector('.dpr-pdf-preview-open-link');
            const previewUrl = buildEmbeddablePdfUrl(url);
            if (frame && frame.getAttribute('src') !== previewUrl) {
              frame.setAttribute('src', previewUrl);
            }
            if (openLink) {
              openLink.setAttribute('href', url);
            }
            const nextOpen = !document.body.classList.contains('dpr-pdf-preview-open');
            document.body.classList.toggle('dpr-pdf-preview-open', nextOpen);
            btn.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
            btn.textContent = nextOpen ? 'Close preview' : 'Preview PDF';
          });
        });
      };

      // Generate the paper-page HTML from front matter
      const renderPaperFromMeta = (meta) => {
        if (!meta) return '';

        // Parse tags and generate colored HTML
        const renderTags = (tags) => {
          if (!tags || !tags.length) return '';
          return tags.map(tag => {
            const [kind, label] = tag.includes(':') ? tag.split(':', 2) : ['other', tag];
            const css = { keyword: 'tag-green', query: 'tag-blue', paper: 'tag-pink' }[kind] || 'tag-pink';
            return `<span class="tag-label ${css}">${escapeHtml(label)}</span>`;
          }).join(' ');
        };
        const renderSourceChips = (source) => {
          const text = String(source || '').trim();
          if (!text) return '';
          const parts = text.split('-').map((item) => item.trim()).filter(Boolean);
          if (parts.length >= 3 && /^\d{4}$/.test(parts[1])) {
            const statusRaw = parts.slice(2).join('-');
            const statusLower = statusRaw.toLowerCase();
            let statusLabel = statusRaw;
            let statusClass = 'tag-source';
            if (statusLower.startsWith('accepted')) {
              statusLabel = 'Accepted';
              statusClass = 'tag-accepted';
            } else if (statusLower.startsWith('rejected')) {
              statusLabel = 'Rejected';
              statusClass = 'tag-rejected';
            }
            return [
              `<span class="tag-label tag-source">${escapeHtml(parts[0].toUpperCase())}</span>`,
              `<span class="tag-label tag-source">${escapeHtml(parts[1])}</span>`,
              `<span class="tag-label ${statusClass}">${escapeHtml(statusLabel)}</span>`,
            ].join(' ');
          }
          return `<span class="tag-label tag-source">${escapeHtml(text)}</span>`;
        };

        const lines = [];

        // Title area
        lines.push('<div class="paper-title-row">');
        if (meta.title_zh) {
          lines.push(`<h1 class="paper-title-zh">${escapeHtml(meta.title_zh)}</h1>`);
        }
        if (meta.title) {
          lines.push(`<h1 class="paper-title-en">${escapeHtml(meta.title)}</h1>`);
        }
        lines.push('</div>');
        lines.push('');

        // Middle area
        lines.push('<div class="paper-meta-row">');

        // Left: Evidence and TLDR
        lines.push('<div class="paper-meta-left">');
        if (meta.evidence) {
          lines.push(`<p><strong>Evidence</strong>: ${escapeHtml(meta.evidence)}</p>`);
        }
        if (meta.tldr) {
          lines.push(`<p><strong>TLDR</strong>: ${escapeHtml(meta.tldr)}</p>`);
        }
        lines.push('</div>');

        // Right: basic info
        lines.push('<div class="paper-meta-right">');
        lines.push(`<p><strong>Authors</strong>: ${escapeHtml(meta.authors || 'Unknown')}</p>`);
        if (meta.source) {
          lines.push(`<p><strong>Source</strong>: ${renderSourceChips(meta.source)}</p>`);
        }
        lines.push(`<p><strong>Date</strong>: ${escapeHtml(meta.date || 'Unknown')}</p>`);
        if (meta.pdf) {
          lines.push(
            `<p class="paper-meta-link-row"><span class="paper-meta-link-label"><strong>PDF</strong>:</span> <a class="paper-meta-link" href="${escapeHtml(meta.pdf)}" target="_blank">${escapeHtml(meta.pdf)}</a></p>`
          );
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

        // Glance area
        if (meta.motivation || meta.method || meta.result || meta.conclusion) {
          lines.push('<div class="paper-glance-section">');
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

        const figures = parseFiguresMeta(meta);
        const tables = parseTablesMeta(meta);
        if (figures.length || tables.length) {
          lines.push(renderPaperMediaCarousels(figures, tables));
        }

        // Note: after inserting an HTML block (e.g. <hr>) in Markdown, a blank line is needed for subsequent Markdown (such as `##`) to parse correctly.
        // We append two blank lines so the final output ends with `<hr>\n\n`.
        lines.push('<hr>');
        lines.push('');
        lines.push('');

        return lines.join('\n');
      };

      // --- Docsify beforeEach hook: parse front matter ---
      hook.beforeEach(function (content) {
        const file = vm && vm.route ? vm.route.file : '';
        // Only process paper pages
        if (!isPaperRouteFile(file)) {
          latestPaperRawMarkdown = '';
          return content;
        }
        latestPaperRawMarkdown = content || '';

        const { meta, body } = parseFrontMatter(content);
        if (!meta) {
          return content;
        }

        // Generate the paper-page HTML + body
        // * Protect LaTeX formulas in the body from being broken by marked
        const paperHtml = renderPaperFromMeta(meta);
        return paperHtml + protectLatex(body);
      });

      const refreshDeferredPageEnhancements = () => {
        try {
          const paperId = getPaperId();
          const routePath = vm.route && vm.route.path ? vm.route.path : '';
          const lowerId = (paperId || '').toLowerCase();
          const file = vm && vm.route ? vm.route.file : '';
          const isHomePage =
            !paperId ||
            lowerId === 'readme' ||
            routePath === '/' ||
            routePath === '';
          const isLandingLikePage = isHomePage || isReportRouteFile(file);
          const mainContent = document.querySelector('.markdown-section');
          if (mainContent) {
            const root = isPaperRouteFile(file) ? ensurePageContentRoot() : null;
            renderMathInEl(root || mainContent);
          }
          if (!isLandingLikePage && window.PrivateDiscussionChat) {
            window.PrivateDiscussionChat.initForPage(paperId);
          }
        } catch {
          // ignore
        }
      };

      document.addEventListener(
        'dpr-deferred-assets-ready',
        refreshDeferredPageEnhancements,
      );

      // --- Read-state sync initialization ---
      // After the user unlocks the key (mode=full), get the username via the GitHub Token and initialize Supabase sync
      const initReadStateSync = async () => {
        try {
          if (window.DPR_ACCESS_MODE !== 'full') return;
          if (!window.DPRReadStateSync) return;
          const secret = window.decoded_secret_private || {};
          const token = (secret.github && secret.github.token) || '';
          if (!token) return;
          // Get the GitHub username
          const resp = await fetch('https://api.github.com/user', {
            headers: { Authorization: 'Bearer ' + token },
          });
          if (!resp.ok) return;
          const user = await resp.json();
          const username = (user && user.login) || '';
          if (!username) return;
          // Read the Supabase configuration
          const supabaseUrl = (window.$docsify && window.$docsify.supabaseUrl)
            || (window.jsyaml ? '' : '')
            || 'https://lyucdwgefyfbmaiopjbk.supabase.co';
          const anonKey = 'sb_publishable_lX-oi64Uxyd7SIVv3_w2Uw_MTOojeKq';
          await window.DPRReadStateSync.init(supabaseUrl, anonKey, username);
          // Migrate existing localStorage data
          const localState = (() => {
            try {
              const raw = window.localStorage.getItem(READ_STORAGE_KEY);
              return raw ? JSON.parse(raw) : null;
            } catch { return null; }
          })();
          if (localState && Object.keys(localState).length) {
            window.DPRReadStateSync.migrateFromLocalStorage(localState);
          }
          // Re-render the sidebar state
          updateSidebarUnreadBadges();
          markSidebarReadState(null);
        } catch (e) {
          console.warn('[DPR] ReadState init error:', e);
        }
      };
      document.addEventListener('dpr-access-mode-changed', (e) => {
        const mode = e && e.detail && e.detail.mode;
        if (mode === 'full') initReadStateSync();
      });

      // --- Docsify lifecycle hooks ---
      hook.doneEach(function () {
        try {
          if (typeof window.DPRHideInitialSplash === 'function') {
            window.DPRHideInitialSplash();
          }
          document.dispatchEvent(new Event('dpr-docsify-ready'));
        } catch {
          // ignore
        }

        // Route normalization: automatically reshape #/?id=%2f... into #/...
        try {
          const canonical = decodeLegacyIdHash(window.location.hash || '');
          if (canonical && canonical !== window.location.hash) {
            window.location.replace(canonical);
            return;
          }
        } catch {
          // ignore
        }

        // The paper ID for the current route (simply the filename without .md)
        const paperId = getPaperId();
        const routePath = vm.route && vm.route.path ? vm.route.path : '';
        const lowerId = (paperId || '').toLowerCase();

        // The home page (e.g. README.md or the root path) does not show the discussion area; it only does math rendering and Zotero metadata updates
        const isHomePage =
          !paperId ||
          lowerId === 'readme' ||
          routePath === '/' ||
          routePath === '';
        const file = vm && vm.route ? vm.route.file : '';
        const isReportPage = isReportRouteFile(file);
        const isPaperPage = isPaperRouteFile(file);
        const isLandingLikePage = isHomePage || isReportPage;
        syncPageTypeClasses({ isHomePage, isReportPage, isPaperPage });
        closePdfPreview();
        document.querySelectorAll('[data-paper-media-modal]').forEach((modal) => {
          modal.classList.remove('is-open', 'is-closing', 'is-fullscreen');
          modal.setAttribute('aria-hidden', 'true');
        });

        // A. Run a global formula render over the body area (supports $...$ / $$...$$)
        const mainContent = document.querySelector('.markdown-section');
        if (mainContent) {
          // Create the body wrapper first, so later page-switch animations do not affect the chat overlay
          const root = isPaperPage ? ensurePageContentRoot() : null;
          renderMathInEl(root || mainContent);
        }

        // Paper-page title bar layout (only applies to docs/YYYYMM/DD/*.md)
        applyPaperTitleBar();
        bindPdfPreviewToggle();

        // Paper-page left/right switching: update the nav list and bind events (bind only once)
        updateNavState();
        ensureNavHandlers();
        // Prefetch adjacent papers' Markdown (using the browser cache for smoother switching)
        prefetchAdjacent();

        // Page entry animation: slide in based on the previous navigation direction
        const animEl = getPageAnimEl();
        if (animEl) {
          // Clean up leftovers from the previous exit (in case they were not cleared in edge cases)
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
              // Trigger the transition to the resting state
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

        bindPaperFigureCarousels();
        bindPaperMediaModals();

        // ----------------------------------------------------
        // E. On small screens, auto-collapse after clicking a sidebar entry
        // ----------------------------------------------------
        setupMobileSidebarAutoCloseOnItemClick();

        // ----------------------------------------------------
        // F. Collapse the sidebar by date
        // ----------------------------------------------------
        setupCollapsibleSidebarByDay();
        setupCollapsibleConferenceSidebar();
        hydrateStructuredSidebarItems();
        bindSidebarVirtualHashLinks();
        neutralizeSidebarNoactiveLinks();

        // ----------------------------------------------------
        // G. Highlight read-paper state in the sidebar
        // ----------------------------------------------------
        if (!isLandingLikePage && paperId) {
          markSidebarReadState(paperId);
        } else {
          // The home page also applies existing read highlights, but does not add new records
          markSidebarReadState(null);
        }

        // Make the sliding highlight layer follow the current active item (the active class updates after clicks/route changes)
        try {
          const movedByNavAnim = !!DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved;
          if (!movedByNavAnim) {
            // Not a "click-triggered pre-slide" case: snap into place immediately first
            syncSidebarActiveIndicator({ animate: false });
          }
          // Do a single delayed final calibration:
          // - Avoid the double jitter of "align -> jump up -> return" when switching pages by click
          // - Groups have a max-height transition on expand/collapse; calibrate again after the layout settles
          setTimeout(() => {
            try {
              requestAnimationFrame(() => {
                syncSidebarActiveIndicator({ animate: false });
              });
            } finally {
              DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = false;
            }
          }, movedByNavAnim ? 220 : 280);
        } catch {
          // ignore
          DPR_SIDEBAR_ACTIVE_INDICATOR.justMoved = false;
        }

        // Automatically scroll the current paper to the center of the sidebar for continuous reading
        if (DPR_NAV_STATE.lastNavSource !== 'click') {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              centerSidebarOnCurrent();
            });
          });
        }

        // This doneEach source only controls whether to center; clear it after use
        DPR_NAV_STATE.lastNavSource = '';

        // ----------------------------------------------------
        // H. Zotero metadata injection logic (with delay and wake-up)
        // ----------------------------------------------------
        setTimeout(() => {
          updateZoteroMetaFromPage(
            paperId,
            vm.route.file,
            latestPaperRawMarkdown,
          );
        }, 1); // Delay execution until the DOM finishes rendering
      });
      // ----------------------------------------------------
      // I. Responsive sidebar: ensure it is collapsed on first load on narrow screens (only remove the close class)
      // ----------------------------------------------------
      const SIDEBAR_AUTO_COLLAPSE_WIDTH = 1024;

      const ensureCollapsedOnNarrowScreen = () => {
        const windowWidth =
          window.innerWidth || document.documentElement.clientWidth || 0;
        if (windowWidth >= SIDEBAR_AUTO_COLLAPSE_WIDTH) return;

        const body = document.body;
        if (!body.classList) return;
        // On entering narrow screens, use the "collapsed without close" state, compatible with Docsify mobile semantics
        body.classList.remove('close');
      };

      // Run once on initialization
      ensureCollapsedOnNarrowScreen();
    },
  ],
};
