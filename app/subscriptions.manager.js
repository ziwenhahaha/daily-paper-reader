// 订阅管理总模块（智能 Query）
// 负责：
// 1) 维护本地草稿配置
// 2) 统一渲染 intent_profiles
// 3) 保存前仅保留 intent_profiles

window.SubscriptionsManager = (function () {
  let overlay = null;
  let panel = null;
  let saveBtn = null;
  let closeBtn = null;
  let msgEl = null;
  let quickRun10dBtn = null;
  let quickRun30dBtn = null;
  let quickRunConferenceBtn = null;
  let quickRunYearSelect = null;
  let quickRunConferenceSelect = null;
  let quickRunMsgEl = null;

  let draftConfig = null;
  let hasUnsavedChanges = false;
  let isSavingDraftConfig = false;

  const defaultPromptTemplate = [
    'You are a retrieval planning assistant.',
    '标签 (Tag): {{TAG}}',
    '中文描述 (Description): {{USER_DESCRIPTION}}',
    'Retrieval context: {{RETRIEVAL_CONTEXT}}',
    '',
    'Return JSON only:',
    '{',
    '  "tag": "optional tag suggestion (for user convenience)",',
    '  "description": "optional Chinese description (for user convenience)",',
    '  "keywords": [',
    '    {',
      '      "keyword": "short keyword phrase for BM25 recall",',
      '      "query": "semantic rewrite for this keyword",',
      '      "keyword_cn": "中文直译（可选）",',
    '    },',
    '  ],',
    '  "intent_queries": [',
    '    {',
      '      "query": "intent-oriented semantic query 1",',
      '      "query_cn": "中文直译（可选）",',
    '    },',
    '    {',
      '      "query": "intent-oriented semantic query 2",',
      '      "query_cn": "中文直译（可选）",',
    '    }',
    '  ],',
    '}',
    'Requirements:',
    '1) keywords: output 5-12 objects; each item must include keyword and query, keyword_cn optional.',
    '2) keywords are used for recall and should be atomic phrases (prefer 1-3 core words).',
    '3) Avoid coupling core terms (e.g., "symbolic regression", "reinforcement learning", "genetic programming", "Transformer") with extra qualifiers into one keyword. Keep core terms atomic in keyword and use query for full intent.',
    '4) Suggested example:',
    '   {"keyword":"symbolic regression","query":"deep symbolic regression methods","keyword_cn":"符号回归","query_cn":"符号回归深度方法"},',
    '   {"keyword":"reinforcement learning","query":"policy gradient symbolic regression","keyword_cn":"强化学习","query_cn":"策略梯度在符号回归中的应用"},',
    '   {"keyword":"MCTS","query":"MCTS for symbolic regression"}',
    '5) intent_queries: output 3-8 actionable intent queries. Each item should include query and optional query_cn.',
    '6) Do not output extra fields like must_have / optional / exclude / rewrite_for_embedding / must_have.',
    '7) Return pure JSON only, no explanations.',
    '8) Tag suggestion should be concise, preferably under 6 characters.',
  ].join('\n');

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

  const normalizeText = (v) => String(v || '').trim();
  const toStableId = (value) => {
    const text = normalizeText(value).toLowerCase();
    const slug = text
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-+|-+$/g, '')
      .trim();
    return slug || 'item';
  };

  const cloneDeep = (obj) => {
    try {
      return JSON.parse(JSON.stringify(obj || {}));
    } catch {
      return obj || {};
    }
  };

  const normalizeKeywordItem = (item) => {
    if (typeof item === 'string') {
      const text = normalizeText(item);
      if (!text) return null;
      return {
        keyword: text,
        keyword_cn: '',
        query: text,
      };
    }
    if (!item || typeof item !== 'object') return null;

    const keyword = normalizeText(item.keyword || item.expr || item.text || '');
    if (!keyword) return null;
    const query = normalizeText(
      item.query ||
        item.rewrite ||
        item.rewrite_for_embedding ||
        item.text ||
        item.keyword ||
        '',
    );
    const keywordCn = normalizeText(item.keyword_cn || item.keyword_zh || item.zh || '');

    return {
      keyword,
      keyword_cn: keywordCn,
      query: query || keyword,
    };
  };

  const dedupeKeywords = (items) => {
    const list = Array.isArray(items) ? items : [];
    const seen = new Set();
    const out = [];
    for (const item of list) {
      if (!item || typeof item !== 'object') continue;
      const key = normalizeText(item.keyword || '').toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  };

  const normalizeIntentQueryItem = (item) => {
    if (typeof item === 'string') {
      const query = normalizeText(item);
      if (!query) return null;
      return {
        query,
        query_cn: '',
        enabled: true,
        source: 'manual',
      };
    }
    if (!item || typeof item !== 'object') return null;

    const query = normalizeText(item.query || item.text || item.keyword || item.expr || '');
    if (!query) return null;
    const queryCn = normalizeText(item.query_cn || item.query_zh || item.zh || item.note || '');

    return {
      query,
      query_cn: queryCn,
      enabled: item.enabled !== false,
      source: normalizeText(item.source || 'manual'),
      note: normalizeText(item.note || ''),
    };
  };

  const normalizeIntentQueries = (items) => {
    const list = Array.isArray(items) ? items : [];
    const seen = new Set();
    const out = [];
    for (const item of list) {
      const normalized = normalizeIntentQueryItem(item);
      if (!normalized) continue;
      const key = normalizeText(normalized.query).toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(normalized);
    }
    return out;
  };

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

  const refreshQuickRunButtons = () => {
    const blocked = hasUnsavedChanges;
    [quickRun10dBtn, quickRun30dBtn].forEach((btn) => {
      if (!btn) return;
      btn.disabled = blocked;
      btn.classList.toggle('chat-quick-run-item--disabled', blocked);
      btn.title = blocked
        ? '请先点击“保存”后再发起快速抓取。'
        : (btn.getAttribute('data-default-title') || btn.textContent || '');
    });
    if (blocked && quickRunMsgEl) {
      quickRunMsgEl.textContent = '检测到未保存修改，请先保存后再发起快速抓取。';
      quickRunMsgEl.style.color = '#c00';
    }
  };

  const runQuickFetch = (days, msgEl, tipText) => {
    if (hasUnsavedChanges) {
      if (msgEl) {
        msgEl.textContent = '检测到未保存修改，请先点击“保存”后再发起快速抓取。';
        msgEl.style.color = '#c00';
      }
      return;
    }
    if (!window.DPRWorkflowRunner || typeof window.DPRWorkflowRunner.runQuickFetchByDays !== 'function') {
      if (msgEl) {
        msgEl.textContent = '工作流触发器未加载到当前页面。';
        msgEl.style.color = '#c00';
      }
      return;
    }
    window.DPRWorkflowRunner.runQuickFetchByDays(days);
    if (msgEl) {
      msgEl.textContent = tipText || `已发起 ${days} 天内抓取任务。`;
      msgEl.style.color = '#080';
    }
  };

  const runQuickConferencePlaceholder = (yearSelectEl, confSelectEl, msgEl) => {
    const year = (yearSelectEl && yearSelectEl.value) || '';
    const conf = String((confSelectEl && confSelectEl.value) || '').trim();
    if (!year || !conf) {
      if (msgEl) {
        msgEl.textContent = '请先选择年份和会议名。';
        msgEl.style.color = '#c00';
      }
      return;
    }
    if (msgEl) {
      msgEl.textContent = `${year} ${conf} 的会议论文抓取功能暂未接入。`;
      msgEl.style.color = '#c90';
    }
  };

  const normalizeProfiles = (subs) => {
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    return profiles
      .map((p, idx) => {
        if (!p || typeof p !== 'object') return null;
        const tag = normalizeText(p.tag) || toStableId(p.description || `profile-${idx + 1}`);
        const description = normalizeText(p.description || '');
        const enabled = p.enabled !== false;
        const keywordRules = (Array.isArray(p.keywords) ? p.keywords : []).map(normalizeKeywordItem).filter(Boolean);
        const normalizedKeywords = dedupeKeywords(keywordRules);
        const normalizedIntentQueries = normalizeIntentQueries(p.intent_queries);
        if (!keywordRules.length && !normalizedKeywords.length && !normalizedIntentQueries.length) {
          return null;
        }

        return {
          tag,
          description,
          enabled,
          keywords: normalizedKeywords,
          intent_queries: normalizedIntentQueries,
          updated_at: normalizeText(p.updated_at) || new Date().toISOString(),
        };
      })
      .filter(Boolean);
  };

  const stripIntentProfileIds = (config) => {
    const next = cloneDeep(config || {});
    if (!next || typeof next !== 'object') return next;
    const subscriptions = next.subscriptions;
    if (!subscriptions || typeof subscriptions !== 'object') return next;
    const profiles = Array.isArray(subscriptions.intent_profiles) ? subscriptions.intent_profiles : [];
    if (!profiles.length) return next;

    subscriptions.intent_profiles = profiles
      .filter((p) => p && typeof p === 'object')
      .map((p) => {
        const profile = cloneDeep(p) || {};
        delete profile.id;

        if (Array.isArray(profile.keywords)) {
          profile.keywords = profile.keywords
            .filter((k) => k && typeof k === 'object')
            .map((k) => {
              const keyword = cloneDeep(k);
              delete keyword.id;
              return keyword;
            });
        }

        if (Array.isArray(profile.intent_queries)) {
          profile.intent_queries = profile.intent_queries
            .filter((item) => item && typeof item === 'object')
            .map((item) => {
              const intentQuery = cloneDeep(item);
              delete intentQuery.id;
              return intentQuery;
            });
        }

        return profile;
      });

    next.subscriptions = subscriptions;
    return next;
  };

  const migrateLegacyToProfilesIfNeeded = (subs) => {
    const existingProfiles = normalizeProfiles(subs);
    if (existingProfiles.length > 0) {
      subs.intent_profiles = existingProfiles;
    } else {
      subs.intent_profiles = [];
    }
    delete subs.keywords;
    delete subs.llm_queries;
    return subs;
  };

  const normalizeSubscriptions = (config) => {
    const next = cloneDeep(config || {});
    if (!next.subscriptions) next.subscriptions = {};
    const subs = next.subscriptions;

    migrateLegacyToProfilesIfNeeded(subs);
      subs.intent_profiles = normalizeProfiles(subs);

    if (!subs.schema_migration || typeof subs.schema_migration !== 'object') {
      subs.schema_migration = {};
    }
    if (!normalizeText(subs.schema_migration.stage)) {
      subs.schema_migration.stage = 'A';
    }
    if (!normalizeText(subs.schema_migration.diff_threshold_pct)) {
      subs.schema_migration.diff_threshold_pct = 15;
    }

    if (!normalizeText(subs.keyword_recall_mode)) {
      subs.keyword_recall_mode = 'or';
    }

    next.subscriptions = subs;
    return stripIntentProfileIds(next);
  };

  const setMessage = (text, color) => {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.color = color || '#666';
  };

  const ensureOverlay = () => {
    if (overlay && panel) return;
    overlay = document.getElementById('arxiv-search-overlay');
    if (overlay) {
      panel = document.getElementById('arxiv-search-panel');
      return;
    }

    overlay = document.createElement('div');
    overlay.id = 'arxiv-search-overlay';
    overlay.innerHTML = `
      <div id="arxiv-search-panel">
        <div id="arxiv-search-panel-header">
          <div style="font-weight:600;">后台管理</div>
          <div style="display:flex; gap:8px; align-items:center;">
            <button id="arxiv-config-save-btn" class="arxiv-tool-btn" style="padding:2px 10px; background:#2e7d32; color:white;">保存</button>
            <button id="arxiv-open-secret-setup-btn" class="arxiv-tool-btn" style="padding:2px 10px;">密钥配置</button>
            <button id="arxiv-search-close-btn" class="arxiv-tool-btn" style="padding:2px 6px;">关闭</button>
          </div>
        </div>

        <div id="arxiv-search-panel-body">
          <div id="arxiv-search-panel-main">
            <div id="dpr-smart-query-section" class="arxiv-pane dpr-smart-pane">
              <div class="dpr-display-card">
                <div id="dpr-sq-display" class="dpr-sq-display"></div>
              </div>

              <div class="dpr-input-card">
                <div class="dpr-inline-row">
                  <button id="dpr-sq-open-chat-btn" class="arxiv-tool-btn" style="background:#2e7d32; color:#fff;">新增</button>
                </div>
              </div>
            </div>

            <div id="dpr-smart-msg" style="font-size:12px; color:#666; margin-top:10px;">提示：修改后点击「保存」才会写入 config.yaml。</div>
          </div>

          <div id="arxiv-search-quick-run-divider" aria-hidden="true"></div>

          <div id="arxiv-search-quick-run-side">
            <div class="chat-quick-run-title">快速抓取</div>
            <button id="arxiv-admin-quick-run-10d-btn" class="chat-quick-run-item" type="button">立即搜寻十天内论文</button>
            <button id="arxiv-admin-quick-run-30d-btn" class="chat-quick-run-item" type="button">立即搜寻三十天内论文</button>
            <div class="chat-quick-run-divider" aria-hidden="true"></div>
            <div class="chat-quick-run-title">会议论文（先保留）</div>
            <div class="chat-quick-run-row">
              <label for="arxiv-admin-quick-run-year-select">年份</label>
              <select id="arxiv-admin-quick-run-year-select">
                <option value="">选择年份</option>
              </select>
            </div>
            <div class="chat-quick-run-row">
              <label for="arxiv-admin-quick-run-conference-select">会议名</label>
              <select id="arxiv-admin-quick-run-conference-select">
                <option value="">选择会议名</option>
              </select>
            </div>
            <button id="arxiv-admin-quick-run-conference-run-btn" class="chat-quick-run-run-btn" type="button">运行</button>
            <div id="arxiv-admin-quick-run-msg" class="chat-quick-run-msg"></div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    panel = document.getElementById('arxiv-search-panel');

    saveBtn = document.getElementById('arxiv-config-save-btn');
    closeBtn = document.getElementById('arxiv-search-close-btn');
    msgEl = document.getElementById('dpr-smart-msg');

    const reloadAll = () => {
      renderFromDraft();
    };

    if (window.SubscriptionsSmartQuery) {
      window.SubscriptionsSmartQuery.attach({
        displayListEl: document.getElementById('dpr-sq-display'),
        openChatBtn: document.getElementById('dpr-sq-open-chat-btn'),
        msgEl,
        reloadAll,
      });
    }

    bindBaseEvents();
  };

  const renderFromDraft = () => {
    const cfg = draftConfig || {};
    const subs = (cfg && cfg.subscriptions) || {};
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.render) {
      window.SubscriptionsSmartQuery.render(profiles);
    }
    if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds) {
      window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds();
    }
  };

  const loadSubscriptions = async () => {
    try {
      if (!window.SubscriptionsGithubToken || !window.SubscriptionsGithubToken.loadConfig) {
        throw new Error('SubscriptionsGithubToken.loadConfig 不可用');
      }
      const { config } = await window.SubscriptionsGithubToken.loadConfig();
      draftConfig = normalizeSubscriptions(config || {});
      hasUnsavedChanges = false;
      refreshQuickRunButtons();
      if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds) {
        window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds();
      }
      renderFromDraft();
      setMessage('已加载配置，可开始编辑。', '#666');
    } catch (e) {
      console.error(e);
      setMessage('加载配置失败，请确认 GitHub Token 可用。', '#c00');
    }
  };

  const saveDraftConfig = async () => {
    if (isSavingDraftConfig) {
      setMessage('正在保存中，请稍后...', '#666');
      return;
    }
    if (!window.SubscriptionsGithubToken || !window.SubscriptionsGithubToken.saveConfig) {
      setMessage('当前无法保存配置，请先完成 GitHub 登录。', '#c00');
      return;
    }
    if (!draftConfig) {
      setMessage('配置尚未加载完成，请先等待配置读取完成后再试。', '#c00');
      return;
    }
    try {
      isSavingDraftConfig = true;
      if (saveBtn) {
        saveBtn.disabled = true;
      }
      setMessage('正在保存配置...', '#666');
      const toSave = normalizeSubscriptions(draftConfig || {});
      await window.SubscriptionsGithubToken.saveConfig(
        toSave,
        'chore: save smart query config from dashboard',
      );
      draftConfig = toSave;
      hasUnsavedChanges = false;
      refreshQuickRunButtons();
      if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds) {
        window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds();
      }
      setMessage('配置已保存。', '#080');
    } catch (e) {
      console.error(e);
      const msg = e && e.message ? e.message : '未知错误';
      setMessage(`保存配置失败：${msg}`.slice(0, 180), '#c00');
    } finally {
      isSavingDraftConfig = false;
      if (saveBtn) {
        saveBtn.disabled = false;
      }
    }
  };

  const reallyCloseOverlay = () => {
    if (!overlay) return;
    overlay.classList.remove('show');
    setTimeout(() => {
      overlay.style.display = 'none';
    }, 300);
  };

  const closeOverlay = () => {
    if (hasUnsavedChanges) {
      const ok = window.confirm('检测到未保存修改，确认直接关闭并丢弃本地草稿吗？');
      if (!ok) return;
      if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds) {
        window.SubscriptionsSmartQuery.clearPendingDeletedProfileIds();
      }
      draftConfig = null;
      hasUnsavedChanges = false;
      refreshQuickRunButtons();
    }
    reallyCloseOverlay();
  };

  const openOverlay = () => {
    ensureOverlay();
    if (!overlay) return;
    overlay.style.display = 'flex';
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        overlay.classList.add('show');
      });
    });

    if (draftConfig) {
      renderFromDraft();
    } else {
      loadSubscriptions();
    }
  };

  const bindBaseEvents = () => {
    if (closeBtn && !closeBtn._bound) {
      closeBtn._bound = true;
      closeBtn.addEventListener('click', closeOverlay);
    }

    if (overlay && !overlay._boundClick) {
      overlay._boundClick = true;
      overlay.addEventListener('mousedown', (e) => {
        if (e.target === overlay) closeOverlay();
      });
    }

    if (saveBtn && !saveBtn._bound) {
      saveBtn._bound = true;
      saveBtn.addEventListener('click', saveDraftConfig);
    }

    const secretBtn = document.getElementById('arxiv-open-secret-setup-btn');
    if (secretBtn && !secretBtn._bound) {
      secretBtn._bound = true;
      secretBtn.addEventListener('click', () => {
        try {
          if (window.DPRSecretSetup && window.DPRSecretSetup.openStep2) {
            window.DPRSecretSetup.openStep2();
          } else {
            alert('当前页面尚未加载密钥配置向导脚本，请刷新后重试。');
          }
        } catch (e) {
          console.error(e);
        }
      });
    }

    quickRun10dBtn = document.getElementById('arxiv-admin-quick-run-10d-btn');
    quickRun30dBtn = document.getElementById('arxiv-admin-quick-run-30d-btn');
    quickRunConferenceBtn = document.getElementById(
      'arxiv-admin-quick-run-conference-run-btn',
    );
    quickRunYearSelect = document.getElementById('arxiv-admin-quick-run-year-select');
    quickRunConferenceSelect = document.getElementById(
      'arxiv-admin-quick-run-conference-select',
    );
    quickRunMsgEl = document.getElementById('arxiv-admin-quick-run-msg');
    fillQuickRunOptions(quickRunYearSelect, quickRunConferenceSelect);
    [quickRun10dBtn, quickRun30dBtn].forEach((btn) => {
      if (!btn) return;
      if (!btn.dataset.defaultTitle) {
        btn.setAttribute('data-default-title', btn.textContent || '');
      }
    });
    refreshQuickRunButtons();

    if (quickRun10dBtn && !quickRun10dBtn._bound) {
      quickRun10dBtn._bound = true;
      quickRun10dBtn.addEventListener('click', () => {
        runQuickFetch(10, quickRunMsgEl);
      });
    }

    if (quickRun30dBtn && !quickRun30dBtn._bound) {
      quickRun30dBtn._bound = true;
      quickRun30dBtn.addEventListener('click', () => {
        runQuickFetch(30, quickRunMsgEl);
      });
    }

    if (quickRunConferenceBtn && !quickRunConferenceBtn._bound) {
      quickRunConferenceBtn._bound = true;
      quickRunConferenceBtn.addEventListener('click', () => {
        runQuickConferencePlaceholder(
          quickRunYearSelect,
          quickRunConferenceSelect,
          quickRunMsgEl,
        );
      });
    }

  };

  const init = () => {
    const run = () => {
      ensureOverlay();
      document.addEventListener('ensure-arxiv-ui', () => {
        ensureOverlay();
      });
      if (!document._arxivLoadSubscriptionsEventBound) {
        document._arxivLoadSubscriptionsEventBound = true;
        document.addEventListener('load-arxiv-subscriptions', () => {
          ensureOverlay();
          loadSubscriptions();
          openOverlay();
        });
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run);
    } else {
      run();
    }
  };

  return {
    init,
    openOverlay,
    closeOverlay,
    loadSubscriptions,
    markConfigDirty: () => {
      hasUnsavedChanges = true;
      refreshQuickRunButtons();
    },
    updateDraftConfig: (updater) => {
      const base = draftConfig || {};
      const next = typeof updater === 'function' ? updater(cloneDeep(base)) || base : base;
      draftConfig = normalizeSubscriptions(next);
      hasUnsavedChanges = true;
      refreshQuickRunButtons();
    },
    getDraftConfig: () => cloneDeep(draftConfig || {}),
  };
})();
