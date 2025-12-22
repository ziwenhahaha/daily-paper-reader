// Docsify 配置与核心插件逻辑
window.$docsify = {
  name: 'Daily Paper Reader',
  repo: '',
  // 文档内容与侧边栏都存放在 docs/ 下
  basePath: 'docs/', // 所有 Markdown 路由以 docs/ 为前缀
  loadSidebar: '_sidebar.md', // 在 basePath 下加载 _sidebar.md
  subMaxLevel: 2,

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
        let text = markdown.replace(/\[ANS\]/g, '').replace(/\[THINK\]/g, '');

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

      // 渲染评论区 HTML 结构
      const renderChatUI = () => {
        return `
          <div id="paper-chat-container">
            <div class="chat-header">💬 公共研讨区 (Public Discussion)</div>
            <div id="chat-history">
                <div style="text-align:center; color:#999">正在加载讨论记录...</div>
            </div>
            <div class="input-area">
              <textarea id="user-input" rows="3" placeholder="针对这篇论文提问，所有人可见..."></textarea>
              <button id="send-btn">发送</button>
            </div>
          </div>
        `;
      };

      // 加载历史评论
      const loadHistory = async (paperId) => {
        try {
          const res = await fetch(
            `${window.API_BASE_URL}/api/history?paper_id=${encodeURIComponent(
              paperId,
            )}`,
          );
          const data = await res.json();

          const historyDiv = document.getElementById('chat-history');
          if (!data || !data.length) {
            historyDiv.innerHTML =
              '<div style="text-align:center; color:#999">暂无讨论，快来抢沙发！</div>';
            return;
          }

          historyDiv.innerHTML = '';
          data.forEach((msg) => {
            const item = document.createElement('div');
            item.className = 'msg-item';

            const roleSpan = document.createElement('div');
            roleSpan.className = `msg-role ${msg.role}`;
            roleSpan.textContent = msg.role === 'user' ? '用户' : 'AI';

            const timeSpan = document.createElement('span');
            timeSpan.className = 'msg-time';
            timeSpan.textContent = msg.time || '';

            const contentDiv = document.createElement('div');
            contentDiv.className = 'msg-content';
            contentDiv.textContent = msg.content || '';

            const headerDiv = document.createElement('div');
            headerDiv.appendChild(roleSpan);
            headerDiv.appendChild(timeSpan);

            item.appendChild(headerDiv);
            item.appendChild(contentDiv);
            historyDiv.appendChild(item);
          });

          historyDiv.scrollTop = historyDiv.scrollHeight;
        } catch (e) {
          console.error(e);
        }
      };

      // 发送消息
      const sendMessage = async (paperId, question) => {
        const historyDiv = document.getElementById('chat-history');
        const sendBtn = document.getElementById('send-btn');
        const userInput = document.getElementById('user-input');

        if (!question.trim()) return;
        if (!historyDiv) return;

        const userItem = document.createElement('div');
        userItem.className = 'msg-item';

        const userRole = document.createElement('div');
        userRole.className = 'msg-role user';
        userRole.textContent = '用户';

        const userContent = document.createElement('div');
        userContent.className = 'msg-content';
        userContent.textContent = question;

        userItem.appendChild(userRole);
        userItem.appendChild(userContent);
        historyDiv.appendChild(userItem);
        historyDiv.scrollTop = historyDiv.scrollHeight;

        userInput.value = '';
        if (sendBtn) sendBtn.disabled = true;

        const aiItem = document.createElement('div');
        aiItem.className = 'msg-item';
        const aiRole = document.createElement('div');
        aiRole.className = 'msg-role ai';
        aiRole.textContent = 'AI';
        const aiContent = document.createElement('div');
        aiContent.className = 'msg-content';
        aiContent.textContent = '思考中...';
        aiItem.appendChild(aiRole);
        aiItem.appendChild(aiContent);
        historyDiv.appendChild(aiItem);
        historyDiv.scrollTop = historyDiv.scrollHeight;

        try {
          const res = await fetch(`${window.API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              paper_id: paperId,
              question,
            }),
          });

          const data = await res.json();
          const answer = data.answer || data.content || data.result || '';
          aiContent.textContent = answer || '（空响应）';
        } catch (e) {
          console.error(e);
          aiContent.textContent = '请求失败，请稍后重试。';
        } finally {
          if (sendBtn) sendBtn.disabled = false;
          historyDiv.scrollTop = historyDiv.scrollHeight;
        }
      };

      // hook：每次路由切换后渲染聊天 UI 与评论区
      hook.afterEach(function (html, next) {
        const paperId = getPaperId();
        const chatHtml = renderChatUI();
        const merged = `${html}\n\n${chatHtml}`;
        next(merged);
      });

      hook.doneEach(function () {
        const paperId = getPaperId();
        const historyDiv = document.getElementById('chat-history');
        const sendBtn = document.getElementById('send-btn');
        const userInput = document.getElementById('user-input');

        if (paperId && historyDiv) {
          loadHistory(paperId);
        }

        if (sendBtn && userInput && !sendBtn._bound) {
          sendBtn._bound = true;
          sendBtn.addEventListener('click', () => {
            sendMessage(paperId, userInput.value);
          });
        }

        if (userInput && !userInput._boundEnter) {
          userInput._boundEnter = true;
          userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
              e.preventDefault();
              sendMessage(paperId, userInput.value);
            }
          });
        }

        // 渲染公式
        const markdownEl = document.querySelector('.markdown-section');
        if (markdownEl) {
          renderMathInEl(markdownEl);
        }
      });

      // ==================== 以下省略的部分 ====================
      // - Arxiv 搜索订阅 UI（搜索面板、订阅关键词、订阅论文列表）
      // - Zotero 账号配置与测试
      // - GitHub Token 管理与权限校验
      // - Zotero meta 标签更新事件
      //
      // 这些逻辑仍然可以继续放在此文件中，或按需拆分为更细的模块。
    },
  ],
};

