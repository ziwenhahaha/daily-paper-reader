// Private discussion panel module: handles chat UI, LLM configuration, and local memory (IndexedDB)
window.PrivateDiscussionChat = (function () {
  const CHAT_HISTORY_KEY = 'dpr_chat_history_v1'; // used only for legacy migration
  const CHAT_DB_NAME = 'dpr_chat_db_v1';
  const CHAT_STORE_NAME = 'paper_chats';
  const CHAT_MODEL_PREF_KEY = 'dpr_chat_model_preference_v1';

  // Recent question log (local localStorage only, recorded from now on — no backfill of prior chat history)
  const QUESTION_RECENT_KEY = 'dpr_chat_recent_questions_v1';
  const QUESTION_PINNED_KEY = 'dpr_chat_pinned_questions_v1';
  const MAX_RECENT_QUESTIONS = 10; // keep only the 10 most recent questions for both display and storage (per user request)
  const MAX_PINNED_QUESTIONS = 50; // cap to prevent unbounded growth

  const resizeChatInput = (input) => {
    if (!input) return;
    const style = window.getComputedStyle ? window.getComputedStyle(input) : null;
    const maxHeight = style ? parseFloat(style.maxHeight || '0') || 160 : 160;
    input.style.height = 'auto';
    const nextHeight = Math.min(input.scrollHeight, maxHeight);
    input.style.height = `${nextHeight}px`;
    input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden';
  };

  // Load the user's preferred Chat model name (persisted across pages)
  const loadPreferredModelName = () => {
    try {
      if (!window.localStorage) return '';
      const v = window.localStorage.getItem(CHAT_MODEL_PREF_KEY);
      return typeof v === 'string' ? v : '';
    } catch {
      return '';
    }
  };

  // Save the user's preferred Chat model name
  const savePreferredModelName = (name) => {
    try {
      if (!window.localStorage) return;
      const v = (name || '').trim();
      if (!v) return;
      window.localStorage.setItem(CHAT_MODEL_PREF_KEY, v);
    } catch {
      // ignore
    }
  };

  // Build the list of available Chat models from the decrypted secret.private result
  const getChatLLMConfig = () => {
    const secret = window.decoded_secret_private || {};
    const utils = window.DPRLLMConfigUtils || {};
    if (typeof utils.resolveChatModels === 'function') {
      return utils.resolveChatModels(secret);
    }

    const chatList = Array.isArray(secret.chatLLMs) ? secret.chatLLMs : [];
    const models = [];
    chatList.forEach((item) => {
      if (!item || !item.models || !Array.isArray(item.models)) return;
      const baseUrl = (item.baseUrl || '').trim();
      const apiKey = (item.apiKey || '').trim();
      item.models.forEach((m) => {
        const name = (m || '').trim();
        if (!name || !apiKey || !baseUrl) return;
        models.push({
          name,
          apiKey,
          baseUrl,
        });
      });
    });
    return models;
  };
  const inferChatApiProfile = (baseUrl, model) => {
    const utils = window.DPRLLMConfigUtils || {};
    if (typeof utils.inferChatApiProfile === 'function') {
      return utils.inferChatApiProfile(baseUrl, model);
    }
    const normalizedBaseUrl = String(baseUrl || '').trim().toLowerCase();
    const normalizedModel = String(model || '').trim().toLowerCase();
    if (
      /(^|\/\/)(api\.)?deepseek\.com(?:$|\/)/i.test(normalizedBaseUrl)
      || normalizedModel.startsWith('deepseek-')
    ) {
      return 'deepseek';
    }
    return 'unsupported';
  };
	  const buildStreamingChatPayload = (baseUrl, model, messages) => {
	    const utils = window.DPRLLMConfigUtils || {};
	    if (typeof utils.buildStreamingChatPayload === 'function') {
	      return utils.buildStreamingChatPayload({ baseUrl, model, messages });
	    }
	    const payload = {
	      model,
	      messages,
	      stream: true,
	    };
	    const normalizedModel = String(model || '').trim().toLowerCase();
	    const normalizedBaseUrl = String(baseUrl || '').trim().toLowerCase();
	    if (
	      (normalizedModel === 'deepseek-v4-flash' || normalizedModel === 'deepseek-v4-pro')
	      && /(^|\/\/)(api\.)?deepseek\.com(?:$|\/)/i.test(normalizedBaseUrl)
	    ) {
	      payload.max_tokens = 393216;
	    }
	    return payload;
	  };

  let chatDbPromise = null;

  const openChatDB = () => {
    if (chatDbPromise) return chatDbPromise;
    if (typeof indexedDB === 'undefined') {
      chatDbPromise = Promise.resolve(null);
      return chatDbPromise;
    }
    chatDbPromise = new Promise((resolve) => {
      try {
        const req = indexedDB.open(CHAT_DB_NAME, 1);
        req.onupgradeneeded = (event) => {
          const db = event.target.result;
          if (!db.objectStoreNames.contains(CHAT_STORE_NAME)) {
            db.createObjectStore(CHAT_STORE_NAME, { keyPath: 'paperId' });
          }
        };
        req.onsuccess = (event) => {
          const db = event.target.result;
          // Migrate legacy localStorage chat history
          try {
            if (window.localStorage) {
              const raw = window.localStorage.getItem(CHAT_HISTORY_KEY);
              if (raw) {
                const obj = JSON.parse(raw) || {};
                const tx = db.transaction(CHAT_STORE_NAME, 'readwrite');
                const store = tx.objectStore(CHAT_STORE_NAME);
                Object.keys(obj).forEach((pid) => {
                  const list = obj[pid];
                  if (pid && Array.isArray(list)) {
                    store.put({ paperId: pid, messages: list });
                  }
                });
                tx.oncomplete = () => {
                  window.localStorage.removeItem(CHAT_HISTORY_KEY);
                };
              }
            }
          } catch {
            // ignore
          }
          resolve(db);
        };
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
    return chatDbPromise;
  };

  const loadChatHistory = async (paperId) => {
    if (!paperId) return [];
    const db = await openChatDB();
    if (!db) {
      try {
        if (!window.localStorage) return [];
        const raw = window.localStorage.getItem(CHAT_HISTORY_KEY);
        if (!raw) return [];
        const obj = JSON.parse(raw);
        if (!obj || typeof obj !== 'object') return [];
        const list = obj[paperId];
        return Array.isArray(list) ? list : [];
      } catch {
        return [];
      }
    }
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(CHAT_STORE_NAME, 'readonly');
        const store = tx.objectStore(CHAT_STORE_NAME);
        const req = store.get(paperId);
        req.onsuccess = () => {
          const record = req.result;
          if (record && Array.isArray(record.messages)) {
            resolve(record.messages);
          } else {
            resolve([]);
          }
        };
        req.onerror = () => resolve([]);
      } catch {
        resolve([]);
      }
    });
  };

  const saveChatHistory = async (paperId, list) => {
    if (!paperId) return;
    const db = await openChatDB();
    if (!db) {
      try {
        if (!window.localStorage) return;
        const raw = window.localStorage.getItem(CHAT_HISTORY_KEY);
        const obj = raw ? JSON.parse(raw) || {} : {};
        obj[paperId] = list;
        window.localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(obj));
      } catch {
        // ignore
      }
      return;
    }
    try {
      const tx = db.transaction(CHAT_STORE_NAME, 'readwrite');
      const store = tx.objectStore(CHAT_STORE_NAME);
      store.put({ paperId, messages: list });
    } catch {
      // ignore
    }
  };

  const renderChatUI = () => {
    return `
      <div id="paper-chat-container">
        <div id="chat-history">
            <div style="text-align:center; color:#999">No discussion yet. Share your thoughts to start a conversation (stored locally only).</div>
        </div>
        <div class="input-area">
          <textarea id="user-input" rows="3" placeholder="Ask a question about this paper (visible to you only)..."></textarea>
          <div class="chat-input-actions">
            <button id="chat-questions-toggle-btn" class="chat-questions-toggle-btn" type="button" title="Recent questions">🕘</button>
            <button id="send-btn">Send</button>
          </div>
        </div>
        <div id="chat-questions-panel" class="chat-questions-panel" style="display:none"></div>
        <div class="chat-footer">
          <div class="chat-footer-controls">
            <button id="chat-sidebar-toggle-btn" class="chat-footer-icon-btn" type="button">☰</button>
            <button id="chat-settings-toggle-btn" class="chat-footer-icon-btn" type="button">⚙️</button>
            <button id="chat-quick-run-btn" class="chat-footer-icon-btn" type="button" title="Quick fetch">🚀</button>
            <div id="chat-quick-run-modal" class="chat-quick-run-modal" aria-hidden="true">
              <div class="chat-quick-run-modal-panel">
                <div class="chat-quick-run-modal-head">
                  <div class="chat-quick-run-title">Quick fetch</div>
                  <button id="chat-quick-run-close-btn" class="chat-quick-run-close-btn" type="button" aria-label="Close">✕</button>
                </div>
                <button id="chat-quick-run-10d-btn" class="chat-quick-run-item" type="button">Search papers from the past 10 days</button>
                <button id="chat-quick-run-30d-btn" class="chat-quick-run-item" type="button">Search papers from the past 30 days</button>
                <div class="chat-quick-run-divider" aria-hidden="true"></div>
                <div class="chat-quick-run-title">Conference papers (not yet connected)</div>
                <div class="chat-quick-run-row">
                  <label for="chat-quick-run-year-select">Year</label>
                  <select id="chat-quick-run-year-select">
                    <option value="">Select year</option>
                  </select>
                </div>
                <div class="chat-quick-run-row">
                  <label for="chat-quick-run-conference-select">Venue</label>
                  <select id="chat-quick-run-conference-select">
                    <option value="">Select venue</option>
                  </select>
                </div>
                <button id="chat-quick-run-conference-run-btn" class="chat-quick-run-run-btn" type="button">Run</button>
                <div id="chat-quick-run-conference-msg" class="chat-quick-run-msg"></div>
              </div>
            </div>
          </div>
          <div id="chat-model-picker" class="chat-model-picker">
            <button
              id="chat-model-picker-btn"
              class="chat-model-picker-btn"
              type="button"
              aria-haspopup="listbox"
              aria-expanded="false"
            >
              <span class="chat-model-picker-kicker">Model</span>
              <span id="chat-model-picker-label" class="chat-model-picker-label">Select model</span>
              <span class="chat-model-picker-chevron" aria-hidden="true">⌄</span>
            </button>
            <div
              id="chat-model-picker-menu"
              class="chat-model-picker-menu"
              role="listbox"
              aria-label="Select Chat model"
            ></div>
            <select
              id="chat-llm-model-select"
              class="chat-model-select"
              aria-hidden="true"
              tabindex="-1"
            ></select>
          </div>
          <span id="chat-status" class="chat-status"></span>
        </div>
      </div>
    `;
  };

  const QUICK_RUN_CONFERENCES = [
    'ACL',
    'AAAI',
    'COLING',
    'EMNLP',
    'ICCV',
    'ICLR',
    'ICML',
    'IJCAI',
    'NeurIPS',
    'SIGIR',
  ];

  const fillQuickRunOptions = (yearSelectEl, confSelectEl) => {
    if (yearSelectEl && !yearSelectEl._dprQuickRunOptionsFilled) {
      yearSelectEl._dprQuickRunOptionsFilled = true;
      const currentYear = new Date().getFullYear();
      for (let y = currentYear; y >= currentYear - 8; y -= 1) {
        const opt = document.createElement('option');
        opt.value = String(y);
        opt.textContent = String(y);
        yearSelectEl.appendChild(opt);
      }
    }

    if (confSelectEl && !confSelectEl._dprQuickRunOptionsFilled) {
      confSelectEl._dprQuickRunOptionsFilled = true;
      QUICK_RUN_CONFERENCES.forEach((name) => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        confSelectEl.appendChild(opt);
      });
    }
  };

  const resolveQuickRunYear = (value) => {
    const y = parseInt(value, 10);
    if (!Number.isFinite(y) || y <= 0) {
      return '';
    }
    return String(y);
  };

  const runQuickFetch = (days, statusEl, showToast = () => {}) => {
    if (!window.DPRWorkflowRunner || typeof window.DPRWorkflowRunner.runQuickFetchByDays !== 'function') {
      if (statusEl) {
        statusEl.textContent = 'Workflow runner is not loaded on the current page.';
        statusEl.style.color = '#c00';
      }
      return;
    }
    window.DPRWorkflowRunner.runQuickFetchByDays(days);
    showToast();
  };

  const runQuickConferencePlaceholder = (yearSelectEl, confSelectEl, msgEl, statusEl) => {
    const year = resolveQuickRunYear(yearSelectEl ? yearSelectEl.value : '');
    const conf = confSelectEl ? String(confSelectEl.value || '').trim() : '';
    if (!year || !conf) {
      if (msgEl) {
        msgEl.textContent = 'Please select a year and venue first.';
        msgEl.style.color = '#c00';
      }
      return;
    }
    if (msgEl) {
      msgEl.textContent = `Conference paper ingestion for ${year} ${conf} is not yet connected.`;
      msgEl.style.color = '#c90';
    }
    if (statusEl) {
      statusEl.textContent = `The ${year} ${conf} conference paper entry point is reserved for future use.`;
      statusEl.style.color = '#c90';
    }
  };

  const getQuickRunModal = () => document.getElementById('chat-quick-run-modal');

  const safeLoadList = (key) => {
    try {
      if (!window.localStorage) return [];
      const raw = window.localStorage.getItem(key);
      if (!raw) return [];
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : [];
    } catch {
      return [];
    }
  };

  const safeSaveList = (key, list) => {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(key, JSON.stringify(list || []));
    } catch {
      // ignore
    }
  };

  const normalizeQuestion = (text) => {
    const s = String(text || '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!s) return '';
    // Guard against abnormally long content breaking the UI layout
    if (s.length > 500) return s.slice(0, 500);
    return s;
  };

  const getPinnedQuestions = () => safeLoadList(QUESTION_PINNED_KEY);
  const setPinnedQuestions = (list) =>
    safeSaveList(QUESTION_PINNED_KEY, (list || []).slice(0, MAX_PINNED_QUESTIONS));

  const getRecentQuestions = () => safeLoadList(QUESTION_RECENT_KEY);
  const setRecentQuestions = (list) =>
    safeSaveList(QUESTION_RECENT_KEY, (list || []).slice(0, MAX_RECENT_QUESTIONS));

  let quickRunPanelController = null;

  const recordRecentQuestion = (question) => {
    const q = normalizeQuestion(question);
    if (!q) return;

    const pinned = getPinnedQuestions();
    // Already-pinned questions should not appear again in recent (avoid duplicates)
    if (pinned.includes(q)) return;

    const recent = getRecentQuestions().filter((x) => x !== q);
    recent.unshift(q);
    setRecentQuestions(recent);
  };

  const togglePinQuestion = (question) => {
    const q = normalizeQuestion(question);
    if (!q) return;
    const pinned = getPinnedQuestions();
    const idx = pinned.indexOf(q);
    if (idx >= 0) {
      pinned.splice(idx, 1);
      setPinnedQuestions(pinned);
      return;
    }

    pinned.unshift(q);
    setPinnedQuestions(pinned);
    // After pinning, remove from recent (ensures pinned + recent still shows 10 other questions)
    const recent = getRecentQuestions().filter((x) => x !== q);
    setRecentQuestions(recent);
  };

  const getChatRoot = () => {
    const el = document.getElementById('paper-chat-container');
    return el || null;
  };

  const getQuestionsPanel = (root) => {
    const r = root || getChatRoot();
    if (!r) return null;
    return r.querySelector('#chat-questions-panel');
  };

  const closeQuestionsPanelElement = (panel) => {
    if (!panel) return;
    if (panel.style.display === 'none') return;
    if (panel._closingTimer) {
      clearTimeout(panel._closingTimer);
    }
    panel.classList.add('is-closing');
    panel._closingTimer = setTimeout(() => {
      panel.style.display = 'none';
      panel.classList.remove('is-closing');
      panel._closingTimer = null;
    }, 170);
  };

  const closeQuestionsPanel = (root) => {
    closeQuestionsPanelElement(getQuestionsPanel(root));
  };

  const isQuestionsPanelOpen = (root) => {
    const panel = getQuestionsPanel(root);
    if (!panel) return false;
    return panel.style.display !== 'none';
  };

  const renderQuestionsPanel = (root) => {
    const panel = getQuestionsPanel(root);
    if (!panel) return;
    panel.innerHTML = '';

    const pinned = getPinnedQuestions();
    const recent = getRecentQuestions().filter((q) => !pinned.includes(q));

    const header = document.createElement('div');
    header.className = 'chat-q-header';

    const title = document.createElement('div');
    title.className = 'chat-q-title';
    title.textContent = 'Recent questions';

    const closeBtn = document.createElement('button');
    closeBtn.id = 'chat-q-close';
    closeBtn.className = 'chat-q-close';
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.textContent = '✕';

    header.appendChild(title);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    const buildSection = (label, items, pinnedFlag) => {
      const sec = document.createElement('div');
      sec.className = 'chat-q-section';

      const secTitle = document.createElement('div');
      secTitle.className = 'chat-q-section-title';
      secTitle.textContent = label;
      sec.appendChild(secTitle);

      const list = document.createElement('div');
      list.className = 'chat-q-list';

      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'chat-q-empty';
        empty.textContent = pinnedFlag
          ? 'No pinned questions yet.'
          : 'No recent questions yet (they will appear here as you chat).';
        list.appendChild(empty);
      } else {
        items.forEach((q) => {
          const item = document.createElement('div');
          item.className = `chat-q-item${pinnedFlag ? ' is-pinned' : ''}`;
          item.dataset.q = q;

          const useBtn = document.createElement('button');
          useBtn.className = 'chat-q-use';
          useBtn.type = 'button';
          useBtn.title = 'Insert into input';
          useBtn.textContent = q;

          const pinBtn = document.createElement('button');
          pinBtn.className = 'chat-q-pin';
          pinBtn.type = 'button';
          pinBtn.title = pinnedFlag ? 'Unpin' : 'Pin';
          pinBtn.textContent = pinnedFlag ? '📌' : '📍';

          item.appendChild(useBtn);
          item.appendChild(pinBtn);
          list.appendChild(item);
        });
      }

      sec.appendChild(list);
      panel.appendChild(sec);
    };

    buildSection('📌 Pinned questions', pinned, true);
    buildSection('🕘 Last 10', recent.slice(0, MAX_RECENT_QUESTIONS), false);
  };

  const openQuestionsPanel = (root) => {
    const panel = getQuestionsPanel(root);
    if (!panel) return;
    if (panel._closingTimer) {
      clearTimeout(panel._closingTimer);
      panel._closingTimer = null;
    }
    renderQuestionsPanel(root);
    panel.classList.remove('is-closing');
    panel.style.display = 'block';
  };

  const toggleQuestionsPanel = (root) => {
    if (isQuestionsPanelOpen(root)) closeQuestionsPanel(root);
    else openQuestionsPanel(root);
  };

  let questionsGlobalBound = false;
  const bindQuestionsPanelEventsOnce = () => {
    const root = getChatRoot();
    if (!root) return;

    const btn = root.querySelector('#chat-questions-toggle-btn');
    if (btn && !btn._boundQToggle) {
      btn._boundQToggle = true;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleQuestionsPanel(root);
      });
    }

    // Event delegation for panel internals
    if (!root._boundQPanelClick) {
      root._boundQPanelClick = true;
      root.addEventListener('click', (e) => {
        const panel = getQuestionsPanel(root);
        if (!panel || panel.style.display === 'none') return;

        const closeBtn =
          e.target && e.target.closest ? e.target.closest('#chat-q-close') : null;
        if (closeBtn) {
          e.preventDefault();
          closeQuestionsPanel(root);
          return;
        }

        const pinBtn =
          e.target && e.target.closest ? e.target.closest('.chat-q-pin') : null;
        if (pinBtn) {
          const item =
            e.target && e.target.closest ? e.target.closest('.chat-q-item') : null;
          const q = item ? item.dataset.q : '';
          togglePinQuestion(q);
          renderQuestionsPanel(root);
          e.preventDefault();
          e.stopPropagation();
          return;
        }

        const useBtn =
          e.target && e.target.closest ? e.target.closest('.chat-q-use') : null;
        if (useBtn) {
          const item =
            e.target && e.target.closest ? e.target.closest('.chat-q-item') : null;
          const q = item ? item.dataset.q : '';
          const input = root.querySelector('#user-input');
          if (input && q) {
            input.value = q;
            resizeChatInput(input);
            input.focus();
          }
          // Close the panel automatically after selecting an item
          closeQuestionsPanel(root);
          e.preventDefault();
          e.stopPropagation();
          return;
        }
      });
    }

    if (questionsGlobalBound) return;
    questionsGlobalBound = true;

    // Close on outside click: use pointerdown (closes on left mouse button press or touch)
    document.addEventListener(
      'pointerdown',
      (e) => {
        // Multiple chat containers may exist due to re-renders; handle all open panels uniformly
        const panels = Array.from(
          document.querySelectorAll('#paper-chat-container .chat-questions-panel'),
        );
        const openPanels = panels.filter((p) => p && p.style.display !== 'none');
        if (!openPanels.length) return;

        // Only left mouse button triggers this (ignore right/middle clicks)
        if (e && e.pointerType === 'mouse' && typeof e.button === 'number') {
          if (e.button !== 0) return;
        }

        const insideChat =
          e.target && e.target.closest
            ? e.target.closest('#paper-chat-container')
            : null;
        if (!insideChat) {
          openPanels.forEach((p) => {
            try {
              closeQuestionsPanelElement(p);
            } catch {
              // ignore
            }
          });
        }
      },
      true,
    );

    // ESC to close
    document.addEventListener('keydown', (e) => {
      if (e && e.key === 'Escape') closeQuestionsPanel(null);
    });
  };

  const renderHistory = async (paperId) => {
    const historyDiv = document.getElementById('chat-history');
    if (!historyDiv) return;

    const data = await loadChatHistory(paperId);
    if (!data || !data.length) {
      historyDiv.innerHTML =
        '<div style="text-align:center; color:#999">No discussion yet. Type a question above to get started.</div>';
      return;
    }

    const { renderMarkdownWithTables, renderMathInEl } = window.DPRMarkdown || {};
    historyDiv.innerHTML = '';
    data.forEach((msg) => {
      const item = document.createElement('div');
      item.className = 'msg-item';

      const role = (msg.role || '').toLowerCase();
      const isThinking = role === 'thinking';
      const isAi = role === 'ai' || role === 'assistant' || isThinking;
      const isUser = role === 'user';

      if (!isThinking) {
        // User messages: timestamp right-aligned; AI replies: no timestamp (only shown for thinking traces)
        if (isUser && msg.time) {
          const timeSpan = document.createElement('span');
          timeSpan.className = 'msg-time msg-time-user';
          timeSpan.textContent = msg.time;
          item.appendChild(timeSpan);
        }

        const contentDiv = document.createElement('div');
        contentDiv.className =
          'msg-content ' + (isAi ? 'msg-content-ai' : 'msg-content-user');
        const markdown = msg.content || '';

        if (isUser) {
          contentDiv.textContent = markdown;
        } else if (renderMarkdownWithTables) {
          contentDiv.innerHTML = renderMarkdownWithTables(markdown);
        } else {
          contentDiv.textContent = markdown;
        }
        if (renderMathInEl) {
          renderMathInEl(contentDiv);
        }

        item.appendChild(contentDiv);
        historyDiv.appendChild(item);
        return;
      }

      // Thinking trace: timestamp displayed above, left-aligned
      if (msg.time) {
        const timeSpan = document.createElement('span');
        timeSpan.className = 'msg-time msg-time-ai';
        timeSpan.textContent = msg.time;
        item.appendChild(timeSpan);
      }

      const thinkingContainer = document.createElement('div');
      thinkingContainer.className = 'thinking-history-container';

      const thinkingHeader = document.createElement('div');
      thinkingHeader.className = 'thinking-history-header';
      const titleSpan = document.createElement('span');
      titleSpan.textContent = 'Thinking trace';
      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'thinking-history-toggle';
      toggleBtn.textContent = 'Expand';
      thinkingHeader.appendChild(titleSpan);
      thinkingHeader.appendChild(toggleBtn);

      const thinkingContent = document.createElement('div');
      thinkingContent.className =
        'msg-content thinking-history-content thinking-collapsed';
      const markdown = msg.content || '';
      if (renderMarkdownWithTables) {
        thinkingContent.innerHTML = renderMarkdownWithTables(markdown);
      } else {
        thinkingContent.textContent = markdown;
      }
      if (renderMathInEl) {
        renderMathInEl(thinkingContent);
      }

      thinkingContainer.appendChild(thinkingHeader);
      thinkingContainer.appendChild(thinkingContent);

      toggleBtn.addEventListener('click', () => {
        const collapsed = thinkingContent.classList.toggle('thinking-collapsed');
        toggleBtn.textContent = collapsed ? 'Expand' : 'Collapse';
      });

      item.appendChild(thinkingContainer);
      historyDiv.appendChild(item);
    });

    historyDiv.scrollTop = historyDiv.scrollHeight;

    // Also update the question navigation
    ensureQuestionNavContainer();
    renderQuestionNav(paperId);

    // After chat history is rendered, notify Zotero metadata for a refresh (including the latest conversation)
    try {
      if (window.DPRZoteroMeta && window.DPRZoteroMeta.updateFromPage) {
        // vm.route.file is not visible on the frontend; only paperId is passed here; the backend function uses the current route
        window.DPRZoteroMeta.updateFromPage(paperId);
      }
    } catch {
      // Ignore refresh failures
    }
  };

  const ensureQuestionNavContainer = () => {};

  const renderQuestionNav = () => {};

  const sendMessage = async (paperId) => {
    // Block LLM calls when in guest mode or when the secret key has not been unlocked
    if (window.DPR_ACCESS_MODE === 'guest' || window.DPR_ACCESS_MODE === 'locked') {
      const statusEl = document.getElementById('chat-status');
      if (statusEl) {
        statusEl.textContent =
          'Currently in guest mode or the secret key is not unlocked. LLM chat is unavailable.';
        statusEl.style.color = '#c00';
      }
      const historyDiv = document.getElementById('chat-history');
      if (historyDiv && !historyDiv._guestHintShown) {
        historyDiv._guestHintShown = true;
        historyDiv.innerHTML =
          '<div style="text-align:center; color:#999; padding:8px 0;">Currently in guest mode. Unlock the secret key to enable LLM chat.</div>';
      }
      return;
    }
    const input = document.getElementById('user-input');
    const btn = document.getElementById('send-btn');
    const statusEl = document.getElementById('chat-status');

    if (!input || !btn) {
      if (statusEl) {
        statusEl.textContent = 'Chat input is not ready. Please refresh the page and try again.';
        statusEl.style.color = '#c00';
      }
      return;
    }

    const question = input.value.trim();
    let paperContent = '';

    if (!question) {
      if (statusEl) {
        statusEl.textContent = 'Please enter a question before sending.';
        statusEl.style.color = '#c00';
      }
      return;
    }

    // Prefer the .txt full-text extraction (consistent with the backend) as context — no truncation
    if (paperId) {
      try {
        const txtUrl = `docs/${paperId}.txt`;
        const resp = await fetch(txtUrl);
        if (resp.ok) {
          const txt = await resp.text();
          if (txt && txt.trim()) {
            paperContent = txt;
            const snippet = txt.slice(0, 50).replace(/\s+/g, ' ');
            console.log(
              `[DPR DEBUG] paper_txt_content (${paperId}): '${snippet}'`,
            );
          } else {
            console.log(
              `[DPR DEBUG] paper_txt_content (${paperId}): <empty or whitespace>`,
            );
          }
        } else {
          console.log(
            `[DPR DEBUG] paper_txt_content (${paperId}): <http ${resp.status}>`,
          );
        }
      } catch {
        console.log(
          `[DPR DEBUG] paper_txt_content (${paperId}): <fetch failed>`,
        );
      }
    }

    // Fallback: if .txt is unavailable, use the page body plain text
    if (!paperContent) {
      paperContent =
        (document.querySelector('.markdown-section') || {}).innerText ||
        '';
    }

    if (!question) return;

    // Record “recent questions” from now on (only user inputs; no backfill of old chats)
    recordRecentQuestion(question);
    // If the panel is open, refresh the list in place for a smoother experience
    if (isQuestionsPanelOpen(null)) {
      renderQuestionsPanel(null);
    }

    input.disabled = true;
    btn.disabled = true;
    btn.innerText = 'Thinking...';

    const historyDiv = document.getElementById('chat-history');
    const nowStr = new Date().toLocaleString();
    // Immediately render the user message with bubble styling (avoid waiting for a full re-render to apply msg-content-user)
    try {
      const userItem = document.createElement('div');
      userItem.className = 'msg-item';

      const time = document.createElement('span');
      time.className = 'msg-time msg-time-user';
      time.textContent = nowStr;

      const content = document.createElement('div');
      content.className = 'msg-content msg-content-user';
      content.textContent = question;

      userItem.appendChild(time);
      userItem.appendChild(content);
      historyDiv.appendChild(userItem);
    } catch {
      // Fallback: at minimum, do not inject user input as raw HTML
      const userItem = document.createElement('div');
      userItem.className = 'msg-item';
      const content = document.createElement('div');
      content.className = 'msg-content msg-content-user';
      content.textContent = question;
      userItem.appendChild(content);
      historyDiv.appendChild(userItem);
    }
    historyDiv.scrollTop = historyDiv.scrollHeight;

    const aiItem = document.createElement('div');
    aiItem.className = 'msg-item';
    aiItem.innerHTML = `
        <span class="msg-time msg-time-ai">${nowStr}</span>
        <div class="ai-response-header">
          <span class="ai-thinking-indicator">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </span>
        </div>
        <div class="thinking-container" style="margin-top:8px; border-left:3px solid #ddd; padding-left:8px; font-size:0.85rem; color:#666; display:none;">
          <div style="display:flex; align-items:center; justify-content:space-between;">
            <span>Thinking trace</span>
            <button class="thinking-toggle" style="margin-left:8px; font-size:0.75rem; padding:2px 6px;">Expand</button>
          </div>
          <div class="thinking-content" style="white-space:pre-wrap; margin-top:4px;"></div>
        </div>
        <div class="msg-content msg-content-ai"></div>
    `;
    historyDiv.appendChild(aiItem);

    // Check whether the user is near the bottom of the page (within a 50px threshold)
    let userAtBottom = true;
    const checkIfAtBottom = () => {
      const threshold = 50;
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const windowHeight = window.innerHeight;
      const docHeight = document.documentElement.scrollHeight;
      return docHeight - scrollTop - windowHeight <= threshold;
    };
    userAtBottom = checkIfAtBottom();

    // Listen for user scroll events to keep userAtBottom in sync
    const onUserScroll = () => {
      userAtBottom = checkIfAtBottom();
    };
    window.addEventListener('scroll', onUserScroll);

    // Auto-scroll to bottom only when the user was already at the bottom
    const scrollToBottomIfNeeded = () => {
      if (userAtBottom) {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: 'smooth'
        });
      }
    };

    // Scroll to bottom immediately after sending the message
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: 'smooth'
    });

    const thinkingContainer = aiItem.querySelector('.thinking-container');
    const thinkingContent = aiItem.querySelector('.thinking-content');
    const toggleBtn = aiItem.querySelector('.thinking-toggle');
    const aiAnswerDiv = aiItem.querySelector('.msg-content');

    const history = await loadChatHistory(paperId);

    // Debug: log the first 50 characters of each history message
    try {
      history.forEach((m, idx) => {
        const role = m.role || 'unknown';
        const snippet = (m.content || '').slice(0, 50).replace(/\s+/g, ' ');
        console.log(
          `[DPR DEBUG] history[${idx}] role=${role}: '${snippet}'`,
        );
      });
      const qSnippet = question.slice(0, 50).replace(/\s+/g, ' ');
      console.log(`[DPR DEBUG] current_question: '${qSnippet}'`);
    } catch {
      // Ignore debug output errors
    }
    history.push({
      role: 'user',
      content: question,
      time: nowStr,
    });
    await saveChatHistory(paperId, history);

    // Update question navigation (a new user question was added)
    renderQuestionNav(paperId);

    // Set an ID on the newly added user message (for question navigation anchoring)
    const userMessages = historyDiv.querySelectorAll('.msg-content-user');
    if (userMessages.length > 0) {
      const lastUserItem = userMessages[userMessages.length - 1].closest('.msg-item');
      if (lastUserItem && !lastUserItem.id) {
        const userQuestionCount = history.filter(m => m.role === 'user').length;
        lastUserItem.id = `user-question-${userQuestionCount - 1}`;
      }
    }

    // After the user submits a question, immediately refresh Zotero metadata (including the latest question)
    try {
      if (window.DPRZoteroMeta && window.DPRZoteroMeta.updateFromPage) {
        window.DPRZoteroMeta.updateFromPage(paperId);
      }
    } catch {
      // Ignore refresh failures
    }

    const chatModels = getChatLLMConfig();
    const modelSelect = document.getElementById('chat-llm-model-select');

    if (!chatModels.length) {
      aiAnswerDiv.textContent =
        'No usable Chat model found in the secret configuration. Please complete the "New Setup Guide" on the home page first.';
      if (statusEl) {
        statusEl.textContent =
          'No usable Chat model detected. Please check the secret configuration.';
        statusEl.style.color = '#c00';
      }
      input.disabled = false;
      btn.disabled = false;
      btn.innerText = 'Send';
      return;
    }

    // Select the default model: prefer the current dropdown value, fall back to the first available model
    let selectedModelName = '';
    if (modelSelect && modelSelect.value) {
      selectedModelName = modelSelect.value;
    } else if (chatModels.length) {
      selectedModelName = chatModels[0].name;
    }
    const modelEntry =
      chatModels.find((m) => m.name === selectedModelName) ||
      chatModels[0] ||
      null;

    const apiKey = modelEntry ? (modelEntry.apiKey || '').trim() : '';
    const model = modelEntry ? modelEntry.name : '';

    if (!apiKey) {
      aiAnswerDiv.textContent =
        'No usable Chat LLM API Key detected. Please check the secret configuration.';
      if (statusEl) {
        statusEl.textContent = 'No Chat LLM API Key configured.';
        statusEl.style.color = '#c00';
      }
      input.disabled = false;
      btn.disabled = false;
      btn.innerText = 'Send';
      return;
    }

    if (!model) {
      aiAnswerDiv.textContent =
        'No Chat model specified. Please check the secret configuration.';
      if (statusEl) {
        statusEl.textContent = 'No Chat model configured.';
        statusEl.style.color = '#c00';
      }
      input.disabled = false;
      btn.disabled = false;
      btn.innerText = 'Send';
      return;
    }

    const endpoint = (() => {
      const raw = (modelEntry && modelEntry.baseUrl ? modelEntry.baseUrl : '').trim();
      if (!raw) return '';
      if (
        window.DPRLLMConfigUtils &&
        typeof window.DPRLLMConfigUtils.buildChatCompletionsEndpoint === 'function'
      ) {
        return window.DPRLLMConfigUtils.buildChatCompletionsEndpoint(raw);
      }
      if (raw.includes('/chat/completions')) return raw;
      const normalized = raw.replace(/\/+$/, '');
      if (/\/v\d+$/i.test(normalized)) {
        return `${normalized}/chat/completions`;
      }
      return `${normalized}/v1/chat/completions`;
    })();

    if (!endpoint) {
      aiAnswerDiv.textContent = 'The current model configuration is missing a baseUrl.';
      if (statusEl) {
        statusEl.textContent = 'Chat model configuration is missing baseUrl. Please fix it in the settings page.';
        statusEl.style.color = '#c00';
      }
      input.disabled = false;
      btn.disabled = false;
      btn.innerText = 'Send';
      return;
    }

    // Save the currently used model as the user preference for reuse across pages
    savePreferredModelName(model);

    if (statusEl) {
      statusEl.textContent = `Calling Chat model ${model}...`;
      statusEl.style.color = '#666';
    }

    let thinkingBuffer = '';
    let answerBuffer = '';
    // Display the thinking trace collapsed by default, showing only the first few lines
    let thinkingCollapsed = true;
    let renderTimer = null;

    const { renderMarkdownWithTables, renderMathInEl } =
      window.DPRMarkdown || {};

    const applyThinkingView = () => {
      if (!thinkingBuffer || !thinkingContent) return;
      const source = thinkingBuffer;
      const maxLines = 6;
      let toRender = source;

      if (thinkingCollapsed) {
        const lines = source.split('\n');
        if (lines.length > maxLines) {
          toRender =
            lines.slice(0, maxLines).join('\n') +
            '\n...(collapsed — click Expand to see more of the thinking trace)';
        }
      }

      if (renderMarkdownWithTables) {
        thinkingContent.innerHTML = renderMarkdownWithTables(toRender);
      } else {
        thinkingContent.textContent = toRender;
      }
      if (renderMathInEl) {
        renderMathInEl(thinkingContent);
      }
    };

    const applyAnswerView = () => {
      if (!aiAnswerDiv) return;
      const content = answerBuffer || '(empty response)';
      if (renderMarkdownWithTables) {
        aiAnswerDiv.innerHTML = renderMarkdownWithTables(content);
      } else {
        aiAnswerDiv.textContent = content;
      }
      if (renderMathInEl) {
        renderMathInEl(aiAnswerDiv);
      }
    };

    if (toggleBtn && thinkingContainer) {
      toggleBtn.addEventListener('click', () => {
        thinkingCollapsed = !thinkingCollapsed;
        toggleBtn.textContent = thinkingCollapsed ? 'Expand' : 'Collapse';
        applyThinkingView();
      });
    }

    const scheduleRender = () => {
      if (renderTimer) return;
      renderTimer = requestAnimationFrame(() => {
        renderTimer = null;
        if (thinkingBuffer && thinkingContainer) {
          thinkingContainer.style.display = 'block';
          applyThinkingView();
        }
        if (answerBuffer) {
          applyAnswerView();
        }
        scrollToBottomIfNeeded();
      });
    };

    try {
      const messages = [];
      messages.push({
        role: 'system',
        content:
          'You are an academic discussion assistant. Your role is to conduct in-depth analysis and discussion of the current paper. Please respond in English and use Markdown + LaTeX for mathematical expressions.',
      });
      // Use full-text context (preferring .txt extraction); no 8000-character truncation
      if (paperContent) {
        messages.push({
          role: 'user',
          content: `Below is the full plain-text content of the current paper (may contain auto-extraction noise; treat as reference only):\n\n${paperContent}`,
        });
      }

          const prev = await loadChatHistory(paperId);
      prev.forEach((m) => {
        if (m.role === 'user' || m.role === 'ai') {
          messages.push({
            role: m.role === 'ai' ? 'assistant' : 'user',
            content: m.content || '',
          });
        }
      });

      messages.push({
        role: 'user',
          content: question,
      });

      const controller = new AbortController();
      const timeoutMs = 120000;
      const timerId = setTimeout(() => controller.abort(), timeoutMs);
      let resp = null;

      const baseUrl = (modelEntry && modelEntry.baseUrl ? modelEntry.baseUrl : '').trim();
	      const primaryPayload = buildStreamingChatPayload(baseUrl, model, messages);
	      const fallbackPayload = {
	        model,
	        messages,
	        stream: true,
	      };
	      if (primaryPayload && primaryPayload.max_tokens) {
	        fallbackPayload.max_tokens = primaryPayload.max_tokens;
	      }

      const doChatFetch = async (payload) => fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${apiKey}`,
          },
          signal: controller.signal,
          body: JSON.stringify(payload),
        });

      try {
        resp = await doChatFetch(primaryPayload);
        if (
          resp
          && !resp.ok
          && (
            JSON.stringify(primaryPayload).includes('"reasoning"')
            || JSON.stringify(primaryPayload).includes('"extra_body"')
            || JSON.stringify(primaryPayload).includes('"thinking"')
          )
        ) {
          let retryText = '';
          try {
            retryText = await resp.text();
          } catch {
            retryText = '';
          }
          if (
            resp.status === 400
            && /reasoning|extra_body|return_reasoning|thinking/i.test(retryText)
          ) {
            resp = await doChatFetch(fallbackPayload);
          } else {
            resp._dprErrorPreview = retryText;
          }
        }
      } finally {
        clearTimeout(timerId);
      }

      if (!resp.ok) {
        let errorText = '';
        try {
          errorText = resp._dprErrorPreview || await resp.text();
        } catch {
          errorText = '';
        }
        const preview = (errorText || '').slice(0, 300).replace(/\s+/g, ' ');
        console.error(
          '[DPR CHAT] Chat API request failed:',
          `HTTP ${resp.status} ${resp.statusText || ''}`,
          preview ? `| Response preview: ${preview}` : '',
        );
        aiAnswerDiv.textContent = `Request failed: HTTP ${resp.status} ${
          resp.statusText || ''
        }${preview ? ` - ${preview}` : ''}`;
        if (statusEl) {
          statusEl.textContent = `Chat model call failed: HTTP ${resp.status} ${
            resp.statusText || ''
          }${preview ? ` - ${preview}` : ''}`;
          statusEl.style.color = '#c00';
        }
        return;
      }

      if (!resp.body) {
        // Fallback: if streaming is not supported, handle as a one-shot response
        const data = await resp.json();
        const answer =
          data &&
          data.choices &&
          data.choices[0] &&
          data.choices[0].message &&
          data.choices[0].message.content
            ? data.choices[0].message.content
            : '(model returned no content)';
        answerBuffer = answer;
        scheduleRender();
      } else {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            const line = part.trim();
            if (!line || !line.startsWith('data:')) continue;
            const jsonStr = line.replace(/^data:\s*/, '');
            if (jsonStr === '[DONE]') continue;
            let payload;
            try {
              payload = JSON.parse(jsonStr);
            } catch {
              continue;
            }
            const choice =
              payload.choices && payload.choices[0]
                ? payload.choices[0]
                : null;
            const delta = choice ? choice.delta || {} : {};
            const reasoning =
              delta.reasoning_content || delta.thinking || '';
            const contentPiece = delta.content || '';

            if (reasoning) {
              thinkingBuffer += reasoning;
            }
            if (contentPiece) {
              answerBuffer += contentPiece;
            }
            if (reasoning || contentPiece) {
              scheduleRender();
            }
          }
        }
      }

      // Reply complete — remove the thinking animation and its container
      const responseHeader = aiItem.querySelector('.ai-response-header');
      if (responseHeader) {
        responseHeader.remove();
      }

      const nowStrAnswer = new Date().toLocaleString();
      const updated = await loadChatHistory(paperId);
      if (thinkingBuffer.trim()) {
        updated.push({
          role: 'thinking',
          content: thinkingBuffer,
          time: nowStrAnswer,
        });
      }
      updated.push({
        role: 'ai',
        content: answerBuffer || '(model returned no content)',
      time: nowStrAnswer,
    });
    await saveChatHistory(paperId, updated);

      // After each conversation round completes, refresh Zotero metadata again
      try {
        if (window.DPRZoteroMeta && window.DPRZoteroMeta.updateFromPage) {
          window.DPRZoteroMeta.updateFromPage(paperId);
        }
      } catch {
        // Ignore refresh failures
      }

      if (statusEl) {
        statusEl.textContent = `Model used: ${model}`;
        statusEl.style.color = '#4caf50';
      }

      input.value = '';
      resizeChatInput(input);
    } catch (e) {
      console.error(e);
      const isTimeout =
        e &&
        (e.name === 'AbortError' ||
          e.name === 'TimeoutError' ||
          /timed out|timed_out/i.test((e.message || '')));
      if (isTimeout) {
        aiAnswerDiv.textContent =
          'Request timed out (120 s). Please try again later or check your network connection.';
        if (statusEl) {
          statusEl.textContent = 'Chat request timed out. Please check your network.';
          statusEl.style.color = '#c00';
        }
      } else if (e && e.name === 'TypeError') {
        aiAnswerDiv.textContent = 'Network connection error (possibly a CORS or cross-origin issue).';
        if (statusEl) {
          statusEl.textContent =
            'Request failed: network error. Please verify the model endpoint is reachable (including CORS) and check your proxy settings.';
          statusEl.style.color = '#c00';
        }
      } else {
        aiAnswerDiv.textContent = 'Failed to send. Please check your network or model configuration.';
        if (statusEl) {
          statusEl.textContent = 'Failed to send. Please check your network or model configuration.';
          statusEl.style.color = '#c00';
        }
      }
      if (statusEl) {
        statusEl.style.color = '#c00';
      }
    } finally {
      // Ensure the thinking animation and its container are removed
      const responseHeader = aiItem.querySelector('.ai-response-header');
      if (responseHeader) {
        responseHeader.remove();
      }
      window.removeEventListener('scroll', onUserScroll);
      input.disabled = false;
      btn.disabled = false;
      btn.innerText = 'Send';
      input.focus();
    }
  };

  const getChatModelPickerElements = () => ({
    picker: document.getElementById('chat-model-picker'),
    button: document.getElementById('chat-model-picker-btn'),
    label: document.getElementById('chat-model-picker-label'),
    menu: document.getElementById('chat-model-picker-menu'),
    select: document.getElementById('chat-llm-model-select'),
  });

  const setChatModelPickerOpen = (open) => {
    const { picker, button } = getChatModelPickerElements();
    if (!picker || !button || picker.classList.contains('is-disabled')) return;
    picker.classList.toggle('is-open', Boolean(open));
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
  };

  const closeChatModelPicker = () => {
    const { picker, button } = getChatModelPickerElements();
    if (!picker || !button) return;
    picker.classList.remove('is-open');
    button.setAttribute('aria-expanded', 'false');
  };

  const syncChatModelPicker = (names = []) => {
    const { picker, button, label, menu, select } = getChatModelPickerElements();
    if (!picker || !button || !label || !menu || !select) return;

    const cleanNames = Array.from(
      new Set(names.map((name) => (name || '').trim()).filter(Boolean)),
    );
    const current = (select.value || cleanNames[0] || '').trim();
    const disabled = select.disabled || !cleanNames.length;

    label.textContent = current || 'Select model';
    picker.classList.toggle('is-disabled', disabled);
    button.disabled = disabled;
    button.title = disabled ? select.title || 'No Chat model available' : 'Switch Chat model';

    if (disabled) {
      closeChatModelPicker();
    }

    menu.innerHTML = '';
    cleanNames.forEach((name) => {
      const item = document.createElement('button');
      const selected = name === current;
      item.type = 'button';
      item.className = `chat-model-picker-option${selected ? ' is-selected' : ''}`;
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', selected ? 'true' : 'false');
      item.dataset.value = name;
      item.innerHTML = `
        <span class="chat-model-option-main">${name}</span>
        <span class="chat-model-option-check" aria-hidden="true">✓</span>
      `;
      item.addEventListener('click', () => {
        if (select.disabled) return;
        select.value = name;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeChatModelPicker();
        syncChatModelPicker(cleanNames);
      });
      menu.appendChild(item);
    });
  };

  const bindChatModelPickerOnce = () => {
    const { picker, button, select } = getChatModelPickerElements();
    if (!picker || !button || !select || picker._boundPicker) return;
    picker._boundPicker = true;

    button.addEventListener('click', () => {
      if (button.disabled) return;
      const shouldOpen = !picker.classList.contains('is-open');
      setChatModelPickerOpen(shouldOpen);
    });

    button.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setChatModelPickerOpen(true);
        const first = picker.querySelector('.chat-model-picker-option');
        if (first) first.focus();
      }
    });

    if (!document._dprChatModelPickerBound) {
      document._dprChatModelPickerBound = true;
      document.addEventListener('click', (e) => {
        const { picker: currentPicker } = getChatModelPickerElements();
        if (!currentPicker || currentPicker.contains(e.target)) return;
        closeChatModelPicker();
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          closeChatModelPicker();
        }
      });
    }
  };

  const initForPage = (paperId) => {
    const mainContent = document.querySelector('.markdown-section');
    if (!mainContent || !paperId) return;

    const container = document.createElement('div');
    container.innerHTML = renderChatUI();
    mainContent.appendChild(container);

    // Recent questions button/panel
    bindQuestionsPanelEventsOnce();

    const sendBtnEl = document.getElementById('send-btn');
    const inputEl = document.getElementById('user-input');
    const statusEl = document.getElementById('chat-status');
    const modelSelect = document.getElementById('chat-llm-model-select');
    const chatSidebarBtn = document.getElementById('chat-sidebar-toggle-btn');
    const chatSettingsBtn = document.getElementById('chat-settings-toggle-btn');
    const chatQuickRunBtn = document.getElementById('chat-quick-run-btn');
    const chatQuickRunCloseBtn = document.getElementById('chat-quick-run-close-btn');
    const chatQuickRun10dBtn = document.getElementById('chat-quick-run-10d-btn');
    const chatQuickRun30dBtn = document.getElementById('chat-quick-run-30d-btn');
    const chatQuickRunConferenceBtn = document.getElementById(
      'chat-quick-run-conference-run-btn',
    );
    const chatQuickRunYearSelect = document.getElementById('chat-quick-run-year-select');
    const chatQuickRunConferenceSelect = document.getElementById(
      'chat-quick-run-conference-select',
    );
    const chatQuickRunConferenceMsg = document.getElementById(
      'chat-quick-run-conference-msg',
    );
    const modal = getQuickRunModal();
    if (modal && modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    fillQuickRunOptions(chatQuickRunYearSelect, chatQuickRunConferenceSelect);
    bindChatModelPickerOnce();

    const inGuestMode =
      window.DPR_ACCESS_MODE === 'guest' || window.DPR_ACCESS_MODE === 'locked';

    const enableChatControls = () => {
      const sendBtn = document.getElementById('send-btn');
      const input = document.getElementById('user-input');
      const status = document.getElementById('chat-status');
      const select = document.getElementById('chat-llm-model-select');

      if (sendBtn && !sendBtn._boundSend) {
        sendBtn._boundSend = true;
        sendBtn.disabled = false;
        sendBtn.title = '';
        sendBtn.addEventListener('click', () => {
          sendMessage(paperId);
        });
      }

      if (input && !input._boundKey) {
        input._boundKey = true;
        input.disabled = false;
        input.placeholder = 'Ask a question about this paper (visible to you only)...';
        resizeChatInput(input);
        input.addEventListener('input', () => {
          resizeChatInput(input);
        });
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            sendMessage(paperId);
          }
        });
      }

      if (select) {
        const chatModels = getChatLLMConfig();
        // Re-enable the dropdown after unlocking
        select.disabled = false;
        select.title = '';
        select.innerHTML = '';
        const names = Array.from(
          new Set(chatModels.map((m) => (m.name || '').trim()).filter(Boolean)),
        );
        names.forEach((name) => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          select.appendChild(opt);
        });
        // Determine the default model:
        // 1. Use the stored user preference (localStorage) if available;
        // 2. Otherwise fall back to the first available model.
        const prefName = loadPreferredModelName();
        let defaultName = '';
        if (prefName && names.includes(prefName)) {
          defaultName = prefName;
        } else if (names.length) {
          defaultName = names[0];
        }
        if (defaultName) {
          select.value = defaultName;
        }
        if (!names.length && status) {
          status.textContent =
            'No usable Chat model detected. Please configure chatLLMs in the new setup guide.';
          status.style.color = '#c00';
        }
        syncChatModelPicker(names);

        // When the user manually switches the model, update the preference for cross-page reuse
        if (!select._boundChange) {
          select._boundChange = true;
          select.addEventListener('change', () => {
            const v = (select.value || '').trim();
            if (v) {
              savePreferredModelName(v);
            }
            syncChatModelPicker(names);
          });
        }
      }
    };

    if (sendBtnEl) {
      if (inGuestMode) {
        sendBtnEl.disabled = true;
        sendBtnEl.title = 'Currently in guest mode or the secret key is not unlocked. Cannot submit questions.';
      } else {
        enableChatControls();
      }
    }
    if (inputEl) {
      if (inGuestMode) {
        inputEl.disabled = true;
        inputEl.placeholder = 'Currently in guest mode. Unlock the secret key to ask the LLM questions.';
      } else {
        // Already bound inside enableChatControls
      }
    }
    if (modelSelect) {
      if (inGuestMode) {
        modelSelect.disabled = true;
        modelSelect.title = 'Currently in guest mode or the secret key is not unlocked. Cannot select a model.';
        syncChatModelPicker([]);
      }
    }

    // If currently locked/guest, wait for the key-unlock event before enabling chat controls
    if (inGuestMode) {
      const handler = (e) => {
        const mode = e && e.detail && e.detail.mode;
        if (mode === 'full') {
          document.removeEventListener('dpr-access-mode-changed', handler);
          enableChatControls();
        }
      };
      document.addEventListener('dpr-access-mode-changed', handler);
    }

    // Sidebar toggle and admin panel button in the chat area (for small screens)
    if (chatSidebarBtn && !chatSidebarBtn._bound) {
      chatSidebarBtn._bound = true;
      chatSidebarBtn.addEventListener('click', () => {
        // Prefer reusing Docsify's built-in sidebar-toggle behavior
        const toggle = document.querySelector('.sidebar-toggle');
        if (toggle) {
          toggle.click();
          return;
        }
        // Fallback: directly toggle body.close to control sidebar expand/collapse
        // const body = document.body;
        // if (!body) return;
        // body.classList.toggle('close');
      });
    }

    if (chatSettingsBtn && !chatSettingsBtn._bound) {
      chatSettingsBtn._bound = true;
      chatSettingsBtn.addEventListener('click', () => {
        // Reuse the bottom gear-button behavior: dispatch ensure-arxiv-ui and load-arxiv-subscriptions events
        const ensureEvent = new CustomEvent('ensure-arxiv-ui');
        document.dispatchEvent(ensureEvent);

        setTimeout(() => {
          const loadEvent = new CustomEvent('load-arxiv-subscriptions');
          document.dispatchEvent(loadEvent);

          const overlay = document.getElementById('arxiv-search-overlay');
          if (overlay) {
            overlay.style.display = 'flex';
            requestAnimationFrame(() => {
              requestAnimationFrame(() => {
                overlay.classList.add('show');
              });
            });
          }
        }, 100);
      });
    }

    const closeQuickRunPopover = () => {
      const modal = getQuickRunModal();
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');

      setTimeout(() => {
        if (modal.classList.contains('is-open')) return;
        modal.style.display = 'none';
      }, 300);
    };

    const openQuickRunPopover = () => {
      const modal = getQuickRunModal();
      if (!modal) return;
      modal.setAttribute('aria-hidden', 'false');
      modal.style.display = 'flex';
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          modal.classList.add('is-open');
        });
      });
    };

    const openQuickRunPanelInner = () => {
      const modal = getQuickRunModal();
      if (!modal) {
        if (chatQuickRunConferenceMsg) {
          chatQuickRunConferenceMsg.textContent = 'The Quick Fetch entry point has not been initialized on the current page.';
          chatQuickRunConferenceMsg.style.color = '#c90';
        }
        return false;
      }
      toggleQuickRunPopover();
      return true;
    };

    const flushQuickRunOpenRequest = () => {
      if (window.__dprQuickRunOpenRequested) {
        window.__dprQuickRunOpenRequested = false;
        openQuickRunPanelInner();
      }
    };

    const toggleQuickRunPopover = () => {
      const modal = getQuickRunModal();
      if (!modal) return;
      if (modal.classList.contains('is-open')) {
        closeQuickRunPopover();
        return;
      }
      if (chatQuickRunConferenceMsg) {
        chatQuickRunConferenceMsg.textContent = '';
        chatQuickRunConferenceMsg.style.color = '#999';
      }
      openQuickRunPopover();
    };

    if (chatQuickRunBtn && !chatQuickRunBtn._bound) {
      chatQuickRunBtn._bound = true;
      chatQuickRunBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleQuickRunPopover();
      });
    }

    if (chatQuickRunCloseBtn && !chatQuickRunCloseBtn._bound) {
      chatQuickRunCloseBtn._bound = true;
      chatQuickRunCloseBtn.addEventListener('click', (e) => {
        e.preventDefault();
        closeQuickRunPopover();
      });
    }

    if (chatQuickRun10dBtn && !chatQuickRun10dBtn._bound) {
      chatQuickRun10dBtn._bound = true;
      chatQuickRun10dBtn.addEventListener('click', () => {
        runQuickFetch(10, statusEl, closeQuickRunPopover);
      });
    }

    if (chatQuickRun30dBtn && !chatQuickRun30dBtn._bound) {
      chatQuickRun30dBtn._bound = true;
      chatQuickRun30dBtn.addEventListener('click', () => {
        runQuickFetch(30, statusEl, closeQuickRunPopover);
      });
    }

    if (chatQuickRunConferenceBtn && !chatQuickRunConferenceBtn._bound) {
      chatQuickRunConferenceBtn._bound = true;
      chatQuickRunConferenceBtn.addEventListener('click', () => {
        runQuickConferencePlaceholder(
          chatQuickRunYearSelect,
          chatQuickRunConferenceSelect,
          chatQuickRunConferenceMsg,
          statusEl,
        );
      });
    }

    if (!document._dprQuickRunPopoverBound) {
      document._dprQuickRunPopoverBound = true;
      document.addEventListener('click', (e) => {
        const modal = getQuickRunModal();
        if (!modal || !modal.classList.contains('is-open')) {
          return;
        }
        if (e.target === modal) {
          closeQuickRunPopover();
          return;
        }
        if (!modal.contains(e.target)) {
          closeQuickRunPopover();
        }
      });
    }

    if (!document._dprQuickRunOpenEventBound) {
      document._dprQuickRunOpenEventBound = true;
      document.addEventListener('dpr-open-quick-run', () => {
        window.__dprQuickRunOpenRequested = false;
        openQuickRunPanelInner();
      });
    }

    flushQuickRunOpenRequest();

    if (!document._dprQuickRunEscBound) {
      document._dprQuickRunEscBound = true;
      document.addEventListener('keydown', (e) => {
        if (e && e.key === 'Escape') {
          closeQuickRunPopover();
        }
      });
    }

    renderHistory(paperId).catch(() => {});

    quickRunPanelController = openQuickRunPanelInner;
  };

  return {
    initForPage,
    openQuickRunPanel: () => {
      if (typeof quickRunPanelController === 'function') {
        const ok = quickRunPanelController();
        if (ok === true) return true;
      }
      if (
        window.DPRWorkflowRunner &&
        typeof window.DPRWorkflowRunner.open === 'function'
      ) {
        window.DPRWorkflowRunner.open();
        return true;
      }
      return false;
    },
  };
})();
