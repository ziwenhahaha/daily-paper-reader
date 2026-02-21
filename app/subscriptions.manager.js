// 订阅管理总模块（统一智能 Query + 禁用引用模块）
// 负责：
// 1) 维护本地草稿配置
// 2) 统一渲染 intent_profiles
// 3) 保存前双写兼容（自动镜像到 keywords / llm_queries）

window.SubscriptionsManager = (function () {
  let overlay = null;
  let panel = null;
  let saveBtn = null;
  let closeBtn = null;
  let msgEl = null;

  let draftConfig = null;
  let hasUnsavedChanges = false;

  const defaultPromptTemplate = [
    '你是一名检索规划助手。',
    '用户主题标签: {{TAG}}',
    '用户描述: {{USER_DESCRIPTION}}',
    '检索链路说明: {{RETRIEVAL_CONTEXT}}',
    '',
    '请输出 JSON：',
    '{',
    '  "keywords": [',
    '    {',
      '      "expr": "关键词短语（单条用于召回，多个关键词之间默认 OR）",',
    '      "logic_cn": "仅做中文直译（尽量短，不超过20字）",',
      '      "must_have": ["可选：该关键词关注的核心概念"],',
      '      "optional": ["可选：该关键词相关扩展概念"],',
      '      "exclude": ["可选：尽量避开的概念"],',
      '      "rewrite_for_embedding": "与该关键词语义一致的自然语言短语"',
    '    }',
    '  ],',
    '  "queries": [',
    '    {',
    '      "text": "润色后的语义 Query（供 embedding+ranker+LLM 链路）",',
    '      "logic_cn": "一句中文说明该改写与原始 query 的差异"',
    '    }',
    '  ]',
    '}',
    '要求：',
    '1) keywords 请给出 5~12 条短语，便于用户多选；',
    '2) 避免输出大量“X + 核心术语”冗余形式（如 "deep symbolic regression"）。若核心术语已出现（如 "symbolic regression"），优先输出可独立召回的前缀概念（如 "machine learning"）；',
    '3) queries 最多 3 条，且必须基于原始 query 做同义改写，不要引入新领域/新主题；',
    '4) 如果原始 query 偏学术方向，保持该方向，不做发散；',
    '5) 只输出 JSON，不要输出其它文本。',
  ].join('\n');

  const normalizeText = (v) => String(v || '').trim();

  const cloneDeep = (obj) => {
    try {
      return JSON.parse(JSON.stringify(obj || {}));
    } catch {
      return obj || {};
    }
  };

  const uniqList = (arr) => {
    const list = Array.isArray(arr) ? arr : [];
    const seen = new Set();
    const out = [];
    list.forEach((item) => {
      const t = normalizeText(item);
      if (!t) return;
      const key = t.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(t);
    });
    return out;
  };

  const hasBooleanSyntax = (text) => {
    const s = normalizeText(text);
    if (!s) return false;
    if (s.includes('(') || s.includes(')')) return true;
    return /\b(AND|OR|NOT)\b|&&|\|\||!/.test(s.toUpperCase());
  };

  const cleanBooleanForEmbedding = (expr) => {
    let s = normalizeText(expr);
    if (!s) return '';
    s = s.replace(/\(/g, ' ').replace(/\)/g, ' ');
    s = s.replace(/\bAND\b|\bOR\b|\bNOT\b|&&|\|\||!/gi, ' ');
    s = s.replace(/\bauthor\s*:\s*/gi, ' ');
    s = s.replace(/\s+/g, ' ').trim();
    return s;
  };

  const normalizeProfiles = (subs) => {
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    return profiles
      .map((p, idx) => {
        if (!p || typeof p !== 'object') return null;
        const id = normalizeText(p.id) || `profile-${idx + 1}`;
        const tag = normalizeText(p.tag) || id;
        const description = normalizeText(p.description || '');
        const enabled = p.enabled !== false;

        const keywordRules = (Array.isArray(p.keyword_rules) ? p.keyword_rules : [])
          .map((k, kIdx) => {
            if (!k || typeof k !== 'object') return null;
            const expr = normalizeText(k.expr || k.keyword || '');
            if (!expr) return null;
            const rewrite =
              normalizeText(k.rewrite_for_embedding || '') ||
              (hasBooleanSyntax(expr) ? cleanBooleanForEmbedding(expr) : expr);
            return {
              id: normalizeText(k.id) || `${id}-kw-${kIdx + 1}`,
              expr,
              logic_cn: normalizeText(k.logic_cn || ''),
              must_have: uniqList(k.must_have),
              optional: uniqList(k.optional),
              exclude: uniqList(k.exclude),
              rewrite_for_embedding: rewrite,
              enabled: k.enabled !== false,
              source: normalizeText(k.source || 'manual'),
              note: normalizeText(k.note || ''),
            };
          })
          .filter(Boolean);

        const semanticQueries = (Array.isArray(p.semantic_queries) ? p.semantic_queries : [])
          .map((q, qIdx) => {
            if (!q || typeof q !== 'object') return null;
            const text = normalizeText(q.text || q.query || '');
            if (!text) return null;
            return {
              id: normalizeText(q.id) || `${id}-q-${qIdx + 1}`,
              text,
              logic_cn: normalizeText(q.logic_cn || ''),
              enabled: q.enabled !== false,
              source: normalizeText(q.source || 'manual'),
              note: normalizeText(q.note || ''),
            };
          })
          .filter(Boolean);

        return {
          id,
          tag,
          description,
          enabled,
          keyword_rules: keywordRules,
          semantic_queries: semanticQueries,
          updated_at: normalizeText(p.updated_at) || new Date().toISOString(),
        };
      })
      .filter(Boolean);
  };

  const migrateLegacyToProfilesIfNeeded = (subs) => {
    const existingProfiles = normalizeProfiles(subs);
    if (existingProfiles.length > 0) {
      subs.intent_profiles = existingProfiles;
      return subs;
    }

    const profilesByTag = {};
    const ensureProfile = (tag) => {
      const key = normalizeText(tag) || 'default';
      if (!profilesByTag[key]) {
        profilesByTag[key] = {
          id: `profile-${Object.keys(profilesByTag).length + 1}`,
          tag: key,
          description: '',
          enabled: true,
          keyword_rules: [],
          semantic_queries: [],
          updated_at: new Date().toISOString(),
        };
      }
      return profilesByTag[key];
    };

    const keywords = Array.isArray(subs.keywords) ? subs.keywords : [];
    keywords.forEach((item) => {
      if (typeof item === 'string') {
        const kw = normalizeText(item);
        if (!kw) return;
        const p = ensureProfile('default');
        p.keyword_rules.push({
          id: `kw-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
          expr: kw,
          logic_cn: '',
          must_have: [],
          optional: [],
          exclude: [],
          rewrite_for_embedding: hasBooleanSyntax(kw)
            ? cleanBooleanForEmbedding(kw)
            : kw,
          enabled: true,
          source: 'legacy',
          note: '',
        });
        return;
      }
      if (!item || typeof item !== 'object') return;
      const kw = normalizeText(item.keyword || '');
      if (!kw) return;
      const tag = normalizeText(item.tag || item.alias || 'default');
      const p = ensureProfile(tag);
      p.keyword_rules.push({
        id: `kw-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
        expr: kw,
        logic_cn: normalizeText(item.logic_cn || ''),
        must_have: uniqList(item.must_have),
        optional: uniqList(item.optional || item.related),
        exclude: uniqList(item.exclude),
        rewrite_for_embedding:
          normalizeText(item.rewrite || '') ||
          (hasBooleanSyntax(kw) ? cleanBooleanForEmbedding(kw) : kw),
        enabled: item.enabled !== false,
        source: 'legacy',
        note: '',
      });
    });

    const queries = Array.isArray(subs.llm_queries) ? subs.llm_queries : [];
    queries.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const q = normalizeText(item.query || '');
      if (!q) return;
      const tag = normalizeText(item.tag || item.alias || 'default');
      const p = ensureProfile(tag);
      p.semantic_queries.push({
        id: `q-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
        text: q,
        logic_cn: normalizeText(item.logic_cn || ''),
        enabled: item.enabled !== false,
        source: 'legacy',
        note: '',
      });
    });

    subs.intent_profiles = Object.values(profilesByTag);
    return subs;
  };

  const compileLegacyMirrorFromProfiles = (subs) => {
    const profiles = normalizeProfiles(subs);
    const keywords = [];
    const llmQueries = [];

    profiles.forEach((p) => {
      if (p.enabled === false) return;
      const tag = normalizeText(p.tag || '');
      if (!tag) return;

      (Array.isArray(p.keyword_rules) ? p.keyword_rules : []).forEach((k) => {
        if (k.enabled === false) return;
        const expr = normalizeText(k.expr || '');
        if (!expr) return;
        keywords.push({
          keyword: expr,
          tag,
          logic_cn: normalizeText(k.logic_cn || ''),
          must_have: uniqList(k.must_have),
          optional: uniqList(k.optional),
          exclude: uniqList(k.exclude),
          related: uniqList(k.optional),
          rewrite:
            normalizeText(k.rewrite_for_embedding || '') ||
            (hasBooleanSyntax(expr) ? cleanBooleanForEmbedding(expr) : expr),
          enabled: k.enabled !== false,
          source: normalizeText(k.source || 'manual'),
        });
      });

      (Array.isArray(p.semantic_queries) ? p.semantic_queries : []).forEach((q) => {
        if (q.enabled === false) return;
        const text = normalizeText(q.text || '');
        if (!text) return;
        llmQueries.push({
          query: text,
          tag,
          logic_cn: normalizeText(q.logic_cn || ''),
          enabled: q.enabled !== false,
          source: normalizeText(q.source || 'manual'),
        });
      });
    });

    subs.keywords = keywords;
    subs.llm_queries = llmQueries;
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

    if (!normalizeText(subs.smart_query_prompt_template)) {
      subs.smart_query_prompt_template = defaultPromptTemplate;
    }
    if (!normalizeText(subs.keyword_recall_mode)) {
      subs.keyword_recall_mode = 'or';
    }

    compileLegacyMirrorFromProfiles(subs);
    next.subscriptions = subs;
    return next;
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

        <div id="dpr-smart-query-section" class="arxiv-pane dpr-smart-pane">
          <div class="dpr-smart-head">统一智能 Query 决策</div>

          <div class="dpr-display-card">
            <div id="dpr-sq-display" class="dpr-sq-display"></div>
          </div>

          <div class="dpr-input-card">
            <div class="dpr-input-layout">
              <textarea id="dpr-sq-desc" class="dpr-desc-compact" rows="1" placeholder="用户描述（示例见右侧 ! ）"></textarea>
              <div class="dpr-inline-row dpr-side-row">
                <input id="dpr-sq-tag" type="text" placeholder="标签（必填）" />
                <button id="dpr-sq-create-btn" class="arxiv-tool-btn" style="background:#2e7d32; color:#fff;">新增</button>
                <span class="dpr-help-tip" tabindex="0">!
                  <span class="dpr-help-pop">
                    示例：帮我关注符号回归与科学发现交叉领域，偏向近期可复现实证研究。<br/>
                    建议：标签尽量使用英文，且小于等于 6 个字母，体验更好。
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="dpr-section-divider"></div>

        <div id="dpr-tracked-disabled" class="arxiv-pane dpr-disabled-pane">
          <div style="font-weight:600; margin-bottom:6px;">新增论文引用（暂未实现）</div>
          <div style="font-size:12px; color:#666; line-height:1.6;">
            该模块已按当前改造方案禁用为只读提示，不再提供搜索与写入操作。
            历史 tracked_papers 数据会保留在配置中，不会被自动删除。
          </div>
        </div>

        <div id="dpr-smart-msg" style="font-size:12px; color:#666; margin-top:10px;">提示：修改后点击「保存」才会写入 config.yaml。</div>
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
        createBtn: document.getElementById('dpr-sq-create-btn'),
        tagInputEl: document.getElementById('dpr-sq-tag'),
        descInputEl: document.getElementById('dpr-sq-desc'),
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
  };

  const loadSubscriptions = async () => {
    try {
      if (!window.SubscriptionsGithubToken || !window.SubscriptionsGithubToken.loadConfig) {
        throw new Error('SubscriptionsGithubToken.loadConfig 不可用');
      }
      const { config } = await window.SubscriptionsGithubToken.loadConfig();
      draftConfig = normalizeSubscriptions(config || {});
      hasUnsavedChanges = false;
      renderFromDraft();
      setMessage('已加载配置，可开始编辑。', '#666');
    } catch (e) {
      console.error(e);
      setMessage('加载配置失败，请确认 GitHub Token 可用。', '#c00');
    }
  };

  const saveDraftConfig = async () => {
    if (!window.SubscriptionsGithubToken || !window.SubscriptionsGithubToken.saveConfig) {
      setMessage('当前无法保存配置，请先完成 GitHub 登录。', '#c00');
      return;
    }
    try {
      setMessage('正在保存配置...', '#666');
      const toSave = normalizeSubscriptions(draftConfig || {});
      await window.SubscriptionsGithubToken.saveConfig(
        toSave,
        'chore: save smart query config from dashboard',
      );
      draftConfig = toSave;
      hasUnsavedChanges = false;
      setMessage('配置已保存。', '#080');
    } catch (e) {
      console.error(e);
      setMessage('保存配置失败，请稍后重试。', '#c00');
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
      draftConfig = null;
      hasUnsavedChanges = false;
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
    },
    updateDraftConfig: (updater) => {
      const base = draftConfig || {};
      const next = typeof updater === 'function' ? updater(cloneDeep(base)) || base : base;
      draftConfig = normalizeSubscriptions(next);
      hasUnsavedChanges = true;
    },
    getDraftConfig: () => cloneDeep(draftConfig || {}),
  };
})();
