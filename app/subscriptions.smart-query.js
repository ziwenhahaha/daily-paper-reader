// 统一智能 Query 模块（简化交互版）
// 主面板：仅「输入区 + 展示区」
// 子面板：
// - 新增面板：展示模型返回候选，用户点选后应用
// - 修改面板：编辑当前词条（点击按钮即可完成主要操作）

window.SubscriptionsSmartQuery = (function () {
  let displayListEl = null;
  let createBtn = null;
  let openChatBtn = null;
  let tagInputEl = null;
  let descInputEl = null;
  let msgEl = null;
  let reloadAll = null;

  let currentProfiles = [];
  let modalOverlay = null;
  let modalPanel = null;
  let modalState = null;

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

  const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  const deepClone = (obj) => {
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
    list.forEach((x) => {
      const t = normalizeText(x);
      if (!t) return;
      const key = t.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(t);
    });
    return out;
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

  const setMessage = (text, color) => {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.color = color || '#666';
  };

  const ensureProfile = (profiles, tag, description) => {
    const t = normalizeText(tag);
    let profile = profiles.find((p) => normalizeText(p.tag) === t);
    if (profile) {
      if (normalizeText(description) && !normalizeText(profile.description)) {
        profile.description = normalizeText(description);
      }
      return profile;
    }
    profile = {
      id: `profile-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
      tag: t,
      description: normalizeText(description),
      enabled: true,
      keyword_rules: [],
      semantic_queries: [],
      updated_at: new Date().toISOString(),
    };
    profiles.push(profile);
    return profile;
  };

  const loadLlmConfig = () => {
    const secret = window.decoded_secret_private || {};
    const summarized = secret.summarizedLLM || {};
    const baseUrl = normalizeText(summarized.baseUrl || '');
    const apiKey = normalizeText(summarized.apiKey || '');
    const model = normalizeText(summarized.model || '');
    if (baseUrl && apiKey && model) return { baseUrl, apiKey, model };

    const chatLLMs = Array.isArray(secret.chatLLMs) ? secret.chatLLMs : [];
    if (chatLLMs.length > 0) {
      const first = chatLLMs[0] || {};
      const cBase = normalizeText(first.baseUrl || '');
      const cKey = normalizeText(first.apiKey || '');
      const models = Array.isArray(first.models) ? first.models : [];
      const cModel = normalizeText(models[0] || '');
      if (cBase && cKey && cModel) return { baseUrl: cBase, apiKey: cKey, model: cModel };
    }
    return null;
  };

  const extractLlmJsonText = (data) => {
    const normalizeContentPart = (part) => {
      if (typeof part === 'string') return normalizeText(part);
      if (!part || typeof part !== 'object') return '';
      return normalizeText(part.text || part.content || part.output_text || '');
    };

    const firstChoice = (((data || {}).choices || [])[0] || {});
    const message = firstChoice.message || {};
    const content = message.content;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      return content.map((p) => normalizeContentPart(p)).filter(Boolean).join('\n');
    }
    if (content && typeof content === 'object') {
      return normalizeContentPart(content);
    }

    const topContent = (data || {}).content;
    if (typeof topContent === 'string') return topContent;
    if (Array.isArray(topContent)) {
      return topContent.map((p) => normalizeContentPart(p)).filter(Boolean).join('\n');
    }

    const outputText = (data || {}).output_text;
    if (typeof outputText === 'string') return outputText;
    if (Array.isArray(outputText)) {
      return outputText.map((p) => normalizeContentPart(p)).filter(Boolean).join('\n');
    }
    return '';
  };

  const loadJsonLenient = (text) => {
    if (text && typeof text === 'object') return text;
    const raw = normalizeText(text);
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch {
      const start = raw.indexOf('{');
      const end = raw.lastIndexOf('}');
      if (start >= 0 && end > start) {
        return JSON.parse(raw.slice(start, end + 1));
      }
      throw new Error('模型返回不是合法 JSON');
    }
  };

  const normalizeGenerated = (payload) => {
    const data = payload && typeof payload === 'object' ? payload : {};
    const rawKeywords = Array.isArray(data.keywords) ? data.keywords : [];
    const rawQueries = Array.isArray(data.queries) ? data.queries : [];
    const shortZh = (text, maxLen = 20) => {
      const t = normalizeText(text || '');
      if (!t) return '';
      if (t.length <= maxLen) return t;
      return `${t.slice(0, maxLen)}...`;
    };
    const normalizePhrase = (text) =>
      normalizeText(text)
        .toLowerCase()
        .replace(/["'`]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    const genericModifierSet = new Set([
      'deep',
      'neural',
      'novel',
      'new',
      'advanced',
      'robust',
      'efficient',
      'interpretable',
      'hybrid',
      'scalable',
      'generalized',
      'improved',
    ]);
    const trimLeadingConnector = (s) =>
      s
        .replace(/^(for|of|in|on|with|using|based on)\s+/i, '')
        .replace(/\s+/g, ' ')
        .trim();

    let keywords = rawKeywords
      .map((item, idx) => {
        if (!item || typeof item !== 'object') return null;
        const expr = normalizeText(item.expr || item.keyword || '');
        if (!expr) return null;
        return {
          id: `gen-kw-${Date.now()}-${idx + 1}`,
          expr,
          logic_cn: shortZh(item.logic_cn || ''),
          must_have: uniqList(item.must_have),
          optional: uniqList(item.optional),
          exclude: uniqList(item.exclude),
          rewrite_for_embedding:
            normalizeText(item.rewrite_for_embedding || '') || cleanBooleanForEmbedding(expr),
          enabled: true,
          source: 'generated',
          note: normalizeText(item.note || ''),
        };
      })
      .filter(Boolean);

    // 关键词召回去冗余：
    // 若已有核心术语（如 symbolic regression），则将 "X symbolic regression" 归一为 "X"；
    // 若 X 只是泛形容词，则直接丢弃该冗余词条。
    const plainList = keywords.map((k) => normalizePhrase(k.expr || ''));
    const plainSet = new Set(plainList);
    const anchorCandidates = new Set();
    plainList.forEach((p) => {
      if (!p) return;
      const words = p.split(' ');
      if (words.length >= 2) {
        const suffix2 = words.slice(-2).join(' ');
        if (plainSet.has(suffix2)) anchorCandidates.add(suffix2);
      }
      if (words.length >= 3) {
        const suffix3 = words.slice(-3).join(' ');
        if (plainSet.has(suffix3)) anchorCandidates.add(suffix3);
      }
    });
    const anchors = Array.from(anchorCandidates).sort((a, b) => b.length - a.length);

    keywords = keywords
      .map((k) => {
        const expr = normalizeText(k.expr || '');
        if (!expr) return null;
        const plain = normalizePhrase(expr);
        for (const anchor of anchors) {
          if (plain === anchor) continue;
          const suffixNeedle = ` ${anchor}`;
          if (!plain.endsWith(suffixNeedle)) continue;
          const idx = plain.lastIndexOf(suffixNeedle);
          const prefixPlain = trimLeadingConnector(plain.slice(0, idx));
          if (!prefixPlain) return null;
          const parts = prefixPlain.split(' ').filter(Boolean);
          if (parts.length === 1 && genericModifierSet.has(parts[0])) {
            return null;
          }
          return {
            ...k,
            expr: prefixPlain,
            logic_cn: shortZh(k.logic_cn || '关键词直译'),
          };
        }
        return k;
      })
      .filter(Boolean);

    // 归一后再去重
    const kwSeen = new Set();
    keywords = keywords.filter((k) => {
      const key = normalizePhrase(k.expr || '');
      if (!key || kwSeen.has(key)) return false;
      kwSeen.add(key);
      return true;
    });

    const querySeen = new Set();
    const queries = rawQueries
      .map((item, idx) => {
        if (!item || typeof item !== 'object') return null;
        const text = normalizeText(item.text || item.query || '');
        if (!text) return null;
        const key = text.toLowerCase();
        if (querySeen.has(key)) return null;
        querySeen.add(key);
        return {
          id: `gen-q-${Date.now()}-${idx + 1}`,
          text,
          logic_cn: shortZh(item.logic_cn || '', 28),
          enabled: true,
          source: 'generated',
          note: normalizeText(item.note || ''),
        };
      })
      .filter(Boolean)
      .slice(0, 3);

    return { keywords, queries };
  };

  const buildPromptFromTemplate = (tag, desc, template) => {
    const retrievalContext =
      '关键词链路仅用于召回，多个关键词按 OR 关系组合；Query 链路用于 embedding + ranker + LLM 打分，请生成可多选的润色 Query。';
    return template
      .replace(/\{\{TAG\}\}/g, tag)
      .replace(/\{\{USER_DESCRIPTION\}\}/g, desc)
      .replace(/\{\{RETRIEVAL_CONTEXT\}\}/g, retrievalContext);
  };

  const requestCandidatesByDesc = async (tag, desc) => {
    const llm = loadLlmConfig();
    if (!llm) {
      throw new Error('未检测到可用大模型配置，请先完成密钥配置。');
    }
    if (!llm.apiKey) {
      throw new Error('未检测到可用 API Key，请先在密钥配置里填写摘要/Chat Token。');
    }

    const cfg = window.SubscriptionsManager.getDraftConfig ? window.SubscriptionsManager.getDraftConfig() : {};
    const subs = (cfg && cfg.subscriptions) || {};
    const template = normalizeText(subs.smart_query_prompt_template || '') || defaultPromptTemplate;
    const prompt = buildPromptFromTemplate(tag, desc, template);
    const buildEndpoints = () => {
      const out = [];
      const pushUnique = (u) => {
        if (u && !out.includes(u)) out.push(u);
      };
      const expandEndpoint = (base) => {
        const src = normalizeText(base).replace(/\/+$/, '');
        if (!src) return;
        if (src.includes('/chat/completions')) {
          pushUnique(src);
          pushUnique(src.replace(/\/chat\/completions$/, '/v1/chat/completions'));
          return;
        }
        if (/\/v\d+$/i.test(src)) {
          pushUnique(`${src}/chat/completions`);
          pushUnique(`${src}/v1/chat/completions`);
          return;
        }
        pushUnique(`${src}/v1/chat/completions`);
        pushUnique(`${src}/chat/completions`);
      };

      expandEndpoint('https://hk-api.gptbest.vip');
      expandEndpoint('https://api.bltcy.ai');

      const raw = normalizeText(llm.baseUrl);
      if (!raw) {
        return out;
      }
      expandEndpoint(raw);
      return out;
    };
    const endpoints = buildEndpoints();
    if (!endpoints.length) {
      throw new Error('LLM 配置缺少 baseUrl。');
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    const requestPayload = (useResponseFormat) => {
      const payload = {
        model: llm.model,
        messages: [
          {
            role: 'system',
            content:
              '你是检索规划助手，只能返回合法 JSON。该请求必须完全基于本次用户输入生成，不得参考或沿用任何历史会话内容。',
          },
          { role: 'user', content: prompt },
        ],
        temperature: 0.1,
      };
      if (useResponseFormat) {
        payload.response_format = { type: 'json_object' };
      }
      return payload;
    };

    const textSafeFromError = (e) => {
      if (!e) return '';
      if (typeof e.message === 'string' && e.message) return e.message;
      return '';
    };

    const isFetchFailure = (e) => {
      if (!e) return false;
      if (e.name === 'AbortError') return false;
      if (e.name === 'TypeError') return true;
      const msg = (e.message || '').toLowerCase();
      return msg.includes('failed to fetch') || msg.includes('network') || msg.includes('ERR_NETWORK');
    };

    const doFetch = async (endpoint, useResponseFormat, withApiKeyHeader = true) => {
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${llm.apiKey}`,
      };
      if (withApiKeyHeader) {
        headers['x-api-key'] = llm.apiKey;
      }
      return fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestPayload(useResponseFormat)),
        signal: controller.signal,
      });
    };

    const doFetchWithFallbackHeader = async (endpoint, useResponseFormat) => {
      try {
        return await doFetch(endpoint, useResponseFormat, true);
      } catch (e) {
        if (!isFetchFailure(e)) {
          throw e;
        }
        return doFetch(endpoint, useResponseFormat, false);
      }
    };

    let res = null;
    let errorText = '';
    let fetchError = '';
    try {
      for (let i = 0; i < endpoints.length; i++) {
        const endpoint = endpoints[i];
        try {
          let current = null;
          let txt = '';
          current = await doFetchWithFallbackHeader(endpoint, true);
          if (current && !current.ok) {
            txt = await current.text().catch(() => '');
            if (current.status === 400 && /response[\s-]*format|json_object/i.test(txt)) {
              current = await doFetchWithFallbackHeader(endpoint, false);
            }
          }
          if (current && !current.ok) {
            txt = await current.text().catch(() => '');
            if (current.status === 400 || current.status === 401 || current.status === 403) {
              throw new Error(`HTTP ${current.status} ${txt || current.statusText}`);
            }
            if (current.status === 429 || current.status >= 500) {
              errorText = txt;
              continue;
            }
            errorText = txt;
            break;
          }

          res = current;
          break;
        } catch (e) {
          fetchError = textSafeFromError(e);
          if (e && e.name === 'AbortError') {
            throw new Error('生成超时，请稍后重试。');
          }
          if (i < endpoints.length - 1) {
            // 网络类错误尝试下一个端点
            continue;
          }
        }
      }
    } catch (e) {
      clearTimeout(timeout);
      throw e;
    }
    clearTimeout(timeout);
    if (!res) {
      if (fetchError) {
        throw new Error(`模型服务请求失败：${fetchError}`);
      }
      throw new Error(errorText || '模型服务请求失败，请检查网络与密钥配置。');
    }
    const data = await res.json();
    const content = extractLlmJsonText(data);
    const parsed = loadJsonLenient(content);
    const candidates = normalizeGenerated(parsed);
    if (!candidates.keywords.length && !candidates.queries.length) {
      throw new Error('模型未返回可用候选，请调整描述后重试。');
    }
    return candidates;
  };

  const applyCandidateToProfile = (tag, description, candidates) => {
    const selectedKeywords = (candidates.keywords || []).filter((x) => x._selected);
    const selectedQueries = (candidates.queries || []).filter((x) => x._selected);
    if (!selectedKeywords.length && !selectedQueries.length) {
      return false;
    }

    window.SubscriptionsManager.updateDraftConfig((cfg) => {
      const next = cfg || {};
      if (!next.subscriptions) next.subscriptions = {};
      const subs = next.subscriptions;
      const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
      const profile = ensureProfile(profiles, tag, description);
      const kwList = Array.isArray(profile.keyword_rules) ? profile.keyword_rules.slice() : [];
      const qList = Array.isArray(profile.semantic_queries) ? profile.semantic_queries.slice() : [];

      const kwSeen = new Set(kwList.map((x) => normalizeText(x.expr).toLowerCase()).filter(Boolean));
      selectedKeywords.forEach((item, idx) => {
        const expr = normalizeText(item.expr || '');
        const key = expr.toLowerCase();
        if (!expr || kwSeen.has(key)) return;
        kwSeen.add(key);
        kwList.push({
          id: normalizeText(item.id) || `kw-${Date.now()}-${idx + 1}`,
          expr,
          logic_cn: normalizeText(item.logic_cn || ''),
          must_have: uniqList(item.must_have),
          optional: uniqList(item.optional),
          exclude: uniqList(item.exclude),
          rewrite_for_embedding:
            normalizeText(item.rewrite_for_embedding || '') || cleanBooleanForEmbedding(expr),
          enabled: true,
          source: normalizeText(item.source || 'generated'),
          note: normalizeText(item.note || ''),
        });
      });

      const qSeen = new Set(qList.map((x) => normalizeText(x.text).toLowerCase()).filter(Boolean));
      selectedQueries.forEach((item, idx) => {
        const text = normalizeText(item.text || '');
        const key = text.toLowerCase();
        if (!text || qSeen.has(key)) return;
        qSeen.add(key);
        qList.push({
          id: normalizeText(item.id) || `q-${Date.now()}-${idx + 1}`,
          text,
          logic_cn: normalizeText(item.logic_cn || ''),
          enabled: true,
          source: normalizeText(item.source || 'generated'),
          note: normalizeText(item.note || ''),
        });
      });

      profile.description = normalizeText(profile.description || description || '');
      profile.keyword_rules = kwList;
      profile.semantic_queries = qList;
      profile.updated_at = new Date().toISOString();
      subs.intent_profiles = profiles;
      next.subscriptions = subs;
      return next;
    });
    return true;
  };

  const parseCandidatesForState = (candidates, selected = true) => {
    return {
      keywords: (candidates.keywords || []).map((x) => ({ ...x, _selected: selected })),
      queries: (candidates.queries || []).map((x) => ({ ...x, _selected: selected })),
    };
  };

  const mergeCloudSelections = (existingItems, incomingItems, keyField) => {
    const normalizeCloudKey = (item, field) => normalizeText(item && item[field]).toLowerCase();
    const existingList = Array.isArray(existingItems) ? existingItems : [];
    const incomingList = Array.isArray(incomingItems) ? incomingItems : [];
    const existingMap = new Map();
    const retainedSelected = [];
    const seen = new Set();
    const merged = [];

    existingList.forEach((item) => {
      const k = normalizeCloudKey(item, keyField);
      if (!k || existingMap.has(k)) return;
      existingMap.set(k, { ...item });
    });

    existingList.forEach((item) => {
      const k = normalizeCloudKey(item, keyField);
      if (!k) return;
      if (seen.has(k)) return;
      const kept = existingMap.get(k);
      if (!kept || !kept._selected) return;
      retainedSelected.push({ ...kept, _selected: true });
      seen.add(k);
    });

    incomingList.forEach((item) => {
      const k = normalizeCloudKey(item, keyField);
      if (!k || seen.has(k)) return;
      const kept = existingMap.get(k);
      const mergedItem = kept ? { ...kept, ...item, _selected: !!kept._selected } : { ...item, _selected: false };
      merged.push(mergedItem);
      seen.add(k);
    });

    merged.unshift(...retainedSelected);
    return merged;
  };

  const renderCloudCards = (items, kind, options = {}) => {
    const textField = options.textField || 'expr';
    const descField = options.descField || 'logic_cn';
    const defaultDesc = options.defaultDesc || '';
    return (items || [])
      .map((item, idx) => {
        const text = normalizeText(item[textField] || '');
        const desc = normalizeText(item[descField] || defaultDesc || '');
        const selected = !!item._selected;
        const checked = selected ? 'checked' : '';
        return `
        <label class="dpr-cloud-item ${selected ? 'selected' : ''}" data-kind="${kind}" data-index="${idx}">
          <input
            type="checkbox"
            data-action="toggle-chat-choice"
            data-kind="${kind}"
            data-index="${idx}"
            ${checked}
          />
          <span class="dpr-cloud-item-body">
            <span class="dpr-cloud-item-title">${escapeHtml(text)}</span>
            <span class="dpr-cloud-item-desc">${escapeHtml(desc || '（无说明）')}</span>
          </span>
        </label>
      `;
      })
      .join('');
  };

  const setChatStatus = (text, color) => {
    const el = modalPanel?.querySelector('#dpr-chat-inline-status');
    if (!el) return;
    el.textContent = text || '';
    el.style.color = color || '#666';
  };

  const setSendBtnLoading = (loading) => {
    const btn = modalPanel?.querySelector('[data-action="chat-send"]');
    if (!btn) return;
    if (loading) {
      btn.disabled = true;
      btn.classList.add('dpr-btn-loading');
      const label = btn.querySelector('.dpr-chat-send-label');
      if (label) label.textContent = '生成中...';
      return;
    }
    btn.disabled = false;
    btn.classList.remove('dpr-btn-loading');
    const label = btn.querySelector('.dpr-chat-send-label');
    if (label) label.textContent = '生成候选';
  };

  const ensureModal = () => {
    if (modalOverlay && modalPanel) return;
    modalOverlay = document.getElementById('dpr-sq-modal-overlay');
    if (!modalOverlay) {
      modalOverlay = document.createElement('div');
      modalOverlay.id = 'dpr-sq-modal-overlay';
      modalOverlay.innerHTML = '<div id="dpr-sq-modal-panel"></div>';
      document.body.appendChild(modalOverlay);
    }
    modalPanel = document.getElementById('dpr-sq-modal-panel');
    if (modalOverlay && !modalOverlay._bound) {
      modalOverlay._bound = true;
      modalOverlay.addEventListener('mousedown', (e) => {
        if (e.target === modalOverlay) closeModal();
      });
    }
  };

  const openModal = () => {
    ensureModal();
    if (!modalOverlay) return;
    modalOverlay.style.display = 'flex';
    requestAnimationFrame(() => {
      modalOverlay.classList.add('show');
    });
  };

  const closeModal = () => {
    if (!modalOverlay) return;
    modalOverlay.classList.remove('show');
    setTimeout(() => {
      modalOverlay.style.display = 'none';
      if (modalPanel) modalPanel.innerHTML = '';
      modalState = null;
    }, 160);
  };

  const renderMain = () => {
    if (!displayListEl) return;
    if (!currentProfiles.length) {
      displayListEl.innerHTML = '<div style="color:#999;">暂无词条，先点「新增」打开对话生成。</div>';
      return;
    }

    displayListEl.innerHTML = currentProfiles
      .map((p) => {
        const kwCount = Array.isArray(p.keyword_rules) ? p.keyword_rules.length : 0;
        const qCount = Array.isArray(p.semantic_queries) ? p.semantic_queries.length : 0;
        return `
          <div class="dpr-entry-card" data-profile-id="${escapeHtml(p.id || '')}">
            <div class="dpr-entry-top">
              <div class="dpr-entry-headline">
                <span class="dpr-entry-title">${escapeHtml(p.tag || '')}</span>
                <span class="dpr-entry-desc-inline">${escapeHtml(p.description || '（无描述）')}</span>
              </div>
              <div class="dpr-entry-actions">
                <button class="arxiv-tool-btn dpr-entry-edit-btn" data-action="edit-profile" data-profile-id="${escapeHtml(p.id || '')}">修改</button>
                <button class="arxiv-tool-btn dpr-entry-delete-btn" data-action="delete-profile" data-profile-id="${escapeHtml(p.id || '')}">删除</button>
              </div>
            </div>
            <div class="dpr-entry-main">
              <div class="dpr-entry-meta">关键词 ${kwCount} · Query ${qCount} ${p.enabled === false ? '· 已停用' : ''}</div>
            </div>
          </div>
        `;
      })
      .join('');
  };

  const openAddModal = (tag, description, candidates) => {
    modalState = {
      type: 'add',
      tag,
      description,
      keywords: parseCandidatesForState(candidates).keywords,
      queries: parseCandidatesForState(candidates).queries,
      customKeyword: '',
      customKeywordLogic: '',
      customQuery: '',
      customQueryLogic: '',
    };
    renderAddModal();
    openModal();
  };

  const openChatModal = () => {
    modalState = {
      type: 'chat',
      keywords: [],
      queries: [],
      requestHistory: [],
      inputTag: '',
      inputDesc: '',
      pending: false,
      chatStatus: '',
    };
    renderChatModal();
    openModal();
  };

  const renderAddModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'add') return;
    const kwHtml = (modalState.keywords || [])
      .map(
        (k, idx) => `
      <button type="button" class="dpr-pick-card ${k._selected ? 'selected' : ''}" data-action="toggle-kw-card" data-index="${idx}">
        <div class="dpr-pick-title">${escapeHtml(k.expr || '')}</div>
        <div class="dpr-pick-desc">${escapeHtml(k.logic_cn || '（待补充中文直译）')}</div>
      </button>
    `,
      )
      .join('');

    const qHtml = (modalState.queries || [])
      .map(
        (q, idx) => `
      <button type="button" class="dpr-pick-card ${q._selected ? 'selected' : ''}" data-action="toggle-query-card" data-index="${idx}">
        <div class="dpr-pick-title">${escapeHtml(q.text || '')}</div>
        <div class="dpr-pick-desc">${escapeHtml(q.logic_cn || '（与原始 query 保持同主题）')}</div>
      </button>
    `,
      )
      .join('');

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">新增词条候选</div>
        <button class="arxiv-tool-btn" data-action="close">关闭</button>
      </div>
      <div class="dpr-modal-sub">标签：${escapeHtml(modalState.tag || '')} ｜ 描述：${escapeHtml(modalState.description || '（无）')}</div>
      <div class="dpr-modal-group-title">关键词候选（用于召回，勾选项之间默认 OR）</div>
      <div class="dpr-modal-list dpr-pick-grid">${kwHtml || '<div style="color:#999;">无关键词候选</div>'}</div>
      <div class="dpr-modal-actions-inline dpr-modal-add-inline">
        <input id="dpr-add-kw-text" type="text" placeholder="手动新增关键词（召回词）" value="${escapeHtml(modalState.customKeyword || '')}" />
        <input id="dpr-add-kw-logic" type="text" placeholder="关键词说明（可选）" value="${escapeHtml(modalState.customKeywordLogic || '')}" />
        <button class="arxiv-tool-btn" data-action="add-custom-kw">加入候选</button>
      </div>
      <div class="dpr-modal-group-title">语义 Query 候选</div>
      <div class="dpr-modal-list dpr-pick-grid">${qHtml || '<div style="color:#999;">无 Query 候选</div>'}</div>
      <div class="dpr-modal-actions-inline dpr-modal-add-inline">
        <input id="dpr-add-query-text" type="text" placeholder="手动新增润色 Query" value="${escapeHtml(modalState.customQuery || '')}" />
        <input id="dpr-add-query-logic" type="text" placeholder="Query 说明（可选）" value="${escapeHtml(modalState.customQueryLogic || '')}" />
        <button class="arxiv-tool-btn" data-action="add-custom-query">加入候选</button>
      </div>
      <div class="dpr-modal-actions">
        <button class="arxiv-tool-btn" data-action="apply-add" style="background:#2e7d32;color:#fff;">确认新增</button>
      </div>
    `;
  };

  const applyAddModal = () => {
    if (!modalState || modalState.type !== 'add') return;
    const selectedKeywords = (modalState.keywords || []).filter((x) => x._selected);
    const selectedQueries = (modalState.queries || []).filter((x) => x._selected);
    if (!applyCandidateToProfile(modalState.tag, modalState.description, {
      ...modalState,
      keywords: selectedKeywords,
      queries: selectedQueries,
    })) {
      setMessage('请至少选择一条候选。', '#c00');
      return;
    }

    if (typeof reloadAll === 'function') reloadAll();
    setMessage('新增词条已应用，请点击「保存」。', '#666');
    closeModal();
  };

  const renderChatModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'chat') return;

    const kwHtml = renderCloudCards(modalState.keywords || [], 'kw', {
      textField: 'expr',
      descField: 'logic_cn',
      defaultDesc: '（待补充中文直译）',
    });
    const qHtml = renderCloudCards(modalState.queries || [], 'query', {
      textField: 'text',
      descField: 'logic_cn',
      defaultDesc: '（与原始 query 保持同主题）',
    });
    const hasKeywords = Array.isArray(modalState.keywords) && modalState.keywords.length > 0;
    const hasQueries = Array.isArray(modalState.queries) && modalState.queries.length > 0;
    const hasCandidates = hasKeywords || hasQueries;
    const isFirstRound = !(Array.isArray(modalState.requestHistory) && modalState.requestHistory.length);
    const actionLabel = isFirstRound ? '生成候选' : '新增候选';
    const sections = [];
    if (qHtml) {
      sections.push(`<div class="dpr-chat-result-block">${`<div class="dpr-cloud-grid dpr-cloud-grid-query">${qHtml}</div>`}</div>`);
    }
    if (kwHtml) {
      sections.push(`<div class="dpr-chat-result-block">${`<div class="dpr-cloud-grid dpr-cloud-grid-keywords">${kwHtml}</div>`}</div>`);
    }
    const mixedHtml = sections.join('<div class="dpr-chat-result-row-gap"></div>');
    const emptyBlock = '<div class="dpr-cloud-empty"></div>';

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">新增查询（请勾选你想要了解的关键词）</div>
        <div class="dpr-chat-head-actions">
          <label class="dpr-chat-label dpr-chat-inline-tag">
            <input id="dpr-chat-tag-input" type="text" placeholder="必填，标签，如SR" value="${escapeHtml(modalState.inputTag || '')}" />
          </label>
          <button class="arxiv-tool-btn" data-action="apply-chat" style="background:#2e7d32;color:#fff;" ${hasCandidates ? '' : 'disabled'}>
            应用勾选结果
          </button>
          <button class="arxiv-tool-btn" data-action="close">关闭</button>
        </div>
      </div>
      <div class="dpr-chat-result-module">
        <div class="dpr-cloud-scroll">${mixedHtml || emptyBlock}</div>
      </div>
      <div class="dpr-modal-actions dpr-chat-action-area">
        <div class="dpr-chat-row">
          <label class="dpr-chat-label dpr-chat-inline-desc">
            <span class="dpr-chat-label-text">检索需求</span>
            <textarea id="dpr-chat-desc-input" rows="2" placeholder="请帮我去查找强化学习和diffusion model相关的论文">${escapeHtml(
              modalState.inputDesc || '',
            )}</textarea>
          </label>
          <button
            class="arxiv-tool-btn dpr-chat-send-btn"
            data-action="chat-send"
            ${modalState.pending ? 'disabled' : ''}
          >
            <span class="dpr-chat-send-label">${actionLabel}</span>
            <span class="dpr-mini-spinner" aria-hidden="true"></span>
          </button>
        </div>
        <div id="dpr-chat-inline-status" class="dpr-chat-inline-status">${escapeHtml(modalState.chatStatus || '')}</div>
      </div>
    `;
  };

  const applyChatSelection = () => {
    let hasSelection = false;
    const selectedKeywords = (modalState.keywords || []).filter((x) => x._selected);
    const selectedQueries = (modalState.queries || []).filter((x) => x._selected);
    const hasItems = selectedKeywords.length || selectedQueries.length;

    if (hasItems) {
      const tag = normalizeText(modalState.inputTag || '');
      const desc = normalizeText(modalState.lastDesc || modalState.inputDesc || '');
      const ok = applyCandidateToProfile(tag || `SR-${new Date().toISOString().slice(0, 10)}`, desc, {
        ...modalState,
        keywords: selectedKeywords,
        queries: selectedQueries,
      });
      hasSelection = ok;
    }

    if (!hasSelection) {
      setMessage(hasItems ? '应用失败，请重试。' : '请至少勾选一条候选后再应用。', '#c00');
      return;
    }
    if (typeof reloadAll === 'function') reloadAll();
    setMessage('已应用勾选结果，请点击「保存」。', '#666');
    closeModal();
  };

  const askChatOnce = async () => {
    if (!modalState || modalState.type !== 'chat') return;
    if (modalState.pending) return;
    const tag = normalizeText(document.getElementById('dpr-chat-tag-input')?.value || '');
    const desc = normalizeText(document.getElementById('dpr-chat-desc-input')?.value || '');
    const finalTag = tag || `SR-${new Date().toISOString().slice(0, 10)}`;
    const finalDesc = desc;

    if (!finalDesc) {
      setChatStatus('请先填写检索需求（描述）', '#c00');
      return;
    }

    modalState.pending = true;
    setSendBtnLoading(true);
    setChatStatus('正在生成候选，请稍候...', '#666');
    setMessage('正在生成候选，请稍候...', '#666');

    try {
      const candidates = await requestCandidatesByDesc(finalTag, finalDesc);
      const nextCandidates = parseCandidatesForState(candidates, false);
      const nextKeywords = mergeCloudSelections(modalState.keywords || [], nextCandidates.keywords, 'expr');
      const nextQueries = mergeCloudSelections(modalState.queries || [], nextCandidates.queries, 'text');
      const roundLabel = requestHistoryLength(modalState);
      const history = Array.isArray(modalState.requestHistory) ? modalState.requestHistory.slice() : [];
      history.push({
        label: roundLabel,
        desc: finalDesc,
        newKeywords: nextCandidates.keywords.length,
        newQueries: nextCandidates.queries.length,
        createdAt: new Date().toISOString(),
      });
      modalState.keywords = nextKeywords;
      modalState.queries = nextQueries;
      modalState.chatTag = finalTag;
      modalState.inputTag = finalTag;
      modalState.lastTag = finalTag;
      modalState.lastDesc = finalDesc;
      modalState.requestHistory = history;
      modalState.inputDesc = '';
      modalState.chatStatus = `已生成候选（关键词 ${nextCandidates.keywords.length} 条新增、共 ${nextKeywords.length} 条；Query ${nextCandidates.queries.length} 条新增、共 ${nextQueries.length} 条）。`;
      if (document.getElementById('dpr-chat-desc-input')) {
        document.getElementById('dpr-chat-desc-input').value = '';
      }
      if (document.getElementById('dpr-chat-tag-input')) {
        document.getElementById('dpr-chat-tag-input').value = finalTag;
      }
      renderChatModal();
      setMessage(modalState.chatStatus, '#666');
      setChatStatus(modalState.chatStatus, '#666');
    } catch (e) {
      console.error(e);
      const rawMsg = e && e.message ? String(e.message) : '未知错误';
      const hint =
        /Failed to fetch|NETWORK|network|ERR_TIMED_OUT|timed out/i.test(rawMsg) ||
        /模型服务请求失败/.test(rawMsg)
          ? '请检查当前网络是否能访问模型网关，或稍后重试（可先切换/重选模型）。'
          : '';
      const msg = `生成失败：${rawMsg}${hint ? `（${hint}）` : ''}`;
      setMessage(msg, '#c00');
      setChatStatus(msg, '#c00');
    } finally {
      modalState.pending = false;
      setSendBtnLoading(false);
    }
  };

  const openEditModal = (profileId) => {
    const profile = (currentProfiles || []).find((p) => normalizeText(p.id) === normalizeText(profileId));
    if (!profile) return;

    modalState = {
      type: 'edit',
      profile: deepClone(profile),
    };
    renderEditModal();
    openModal();
  };

  const renderEditModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'edit') return;
    const p = modalState.profile || {};
    const kwList = Array.isArray(p.keyword_rules) ? p.keyword_rules : [];
    const qList = Array.isArray(p.semantic_queries) ? p.semantic_queries : [];

    const kwHtml = kwList
      .map(
        (k, idx) => `
      <div class="dpr-edit-row">
        <span class="dpr-edit-toggle ${k.enabled === false ? 'off' : 'on'}" data-action="toggle-kw" data-index="${idx}">${k.enabled === false ? '停用' : '启用'}</span>
        <div class="dpr-edit-text">${escapeHtml(k.expr || '')}<div class="dpr-edit-sub">${escapeHtml(k.logic_cn || '（无逻辑说明）')}</div></div>
        <button class="arxiv-tool-btn dpr-mini" data-action="edit-kw" data-index="${idx}">改</button>
        <button class="arxiv-tool-btn dpr-mini" data-action="del-kw" data-index="${idx}">删</button>
      </div>
    `,
      )
      .join('');

    const qHtml = qList
      .map(
        (q, idx) => `
      <div class="dpr-edit-row">
        <span class="dpr-edit-toggle ${q.enabled === false ? 'off' : 'on'}" data-action="toggle-q" data-index="${idx}">${q.enabled === false ? '停用' : '启用'}</span>
        <div class="dpr-edit-text">${escapeHtml(q.text || '')}<div class="dpr-edit-sub">${escapeHtml(q.logic_cn || '（无逻辑说明）')}</div></div>
        <button class="arxiv-tool-btn dpr-mini" data-action="edit-q" data-index="${idx}">改</button>
        <button class="arxiv-tool-btn dpr-mini" data-action="del-q" data-index="${idx}">删</button>
      </div>
    `,
      )
      .join('');

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">修改词条</div>
        <button class="arxiv-tool-btn" data-action="close">关闭</button>
      </div>
      <div class="dpr-edit-base">
        <label>标签<input id="dpr-edit-tag" type="text" value="${escapeHtml(p.tag || '')}" /></label>
        <label>描述<input id="dpr-edit-desc" type="text" value="${escapeHtml(p.description || '')}" /></label>
        <label class="dpr-edit-enabled"><input id="dpr-edit-enabled" type="checkbox" ${p.enabled === false ? '' : 'checked'} /> 启用该词条</label>
      </div>

      <div class="dpr-modal-group-title">关键词表达式</div>
      <div class="dpr-modal-list">${kwHtml || '<div style="color:#999;">暂无关键词</div>'}</div>
      <div class="dpr-modal-actions-inline">
        <button class="arxiv-tool-btn" data-action="add-kw">新增关键词</button>
      </div>

      <div class="dpr-modal-group-title">语义 Query</div>
      <div class="dpr-modal-list">${qHtml || '<div style="color:#999;">暂无 Query</div>'}</div>
      <div class="dpr-modal-actions-inline">
        <button class="arxiv-tool-btn" data-action="add-q">新增 Query</button>
      </div>

      <div class="dpr-modal-actions">
        <button class="arxiv-tool-btn" data-action="save-edit" style="background:#2e7d32;color:#fff;">保存修改</button>
      </div>
    `;
  };

  const mutateEditState = (mutator) => {
    if (!modalState || modalState.type !== 'edit') return;
    mutator(modalState.profile);
    renderEditModal();
  };

  const handleEditAction = (action, idx) => {
    const p = modalState && modalState.profile;
    if (!p) return;

    if (action === 'toggle-kw') {
      mutateEditState((profile) => {
        if (!Array.isArray(profile.keyword_rules)) profile.keyword_rules = [];
        const i = Number(idx);
        if (i >= 0 && i < profile.keyword_rules.length) {
          profile.keyword_rules[i].enabled = profile.keyword_rules[i].enabled === false;
        }
      });
      return;
    }

    if (action === 'toggle-q') {
      mutateEditState((profile) => {
        if (!Array.isArray(profile.semantic_queries)) profile.semantic_queries = [];
        const i = Number(idx);
        if (i >= 0 && i < profile.semantic_queries.length) {
          profile.semantic_queries[i].enabled = profile.semantic_queries[i].enabled === false;
        }
      });
      return;
    }

    if (action === 'edit-kw') {
      mutateEditState((profile) => {
        const i = Number(idx);
        if (!Array.isArray(profile.keyword_rules) || i < 0 || i >= profile.keyword_rules.length) return;
        const item = profile.keyword_rules[i] || {};
        const expr = window.prompt('编辑关键词表达式：', item.expr || '');
        if (expr == null) return;
        const logic = window.prompt('编辑逻辑说明：', item.logic_cn || '');
        item.expr = normalizeText(expr);
        item.logic_cn = normalizeText(logic || '');
        item.rewrite_for_embedding =
          normalizeText(item.rewrite_for_embedding || '') || cleanBooleanForEmbedding(item.expr || '');
        profile.keyword_rules[i] = item;
      });
      return;
    }

    if (action === 'edit-q') {
      mutateEditState((profile) => {
        const i = Number(idx);
        if (!Array.isArray(profile.semantic_queries) || i < 0 || i >= profile.semantic_queries.length) return;
        const item = profile.semantic_queries[i] || {};
        const text = window.prompt('编辑语义 Query：', item.text || '');
        if (text == null) return;
        const logic = window.prompt('编辑逻辑说明：', item.logic_cn || '');
        item.text = normalizeText(text);
        item.logic_cn = normalizeText(logic || '');
        profile.semantic_queries[i] = item;
      });
      return;
    }

    if (action === 'del-kw') {
      mutateEditState((profile) => {
        const i = Number(idx);
        if (!Array.isArray(profile.keyword_rules)) return;
        if (i >= 0 && i < profile.keyword_rules.length) {
          profile.keyword_rules.splice(i, 1);
        }
      });
      return;
    }

    if (action === 'del-q') {
      mutateEditState((profile) => {
        const i = Number(idx);
        if (!Array.isArray(profile.semantic_queries)) return;
        if (i >= 0 && i < profile.semantic_queries.length) {
          profile.semantic_queries.splice(i, 1);
        }
      });
      return;
    }

    if (action === 'add-kw') {
      mutateEditState((profile) => {
        const expr = window.prompt('新增关键词表达式：', '');
        if (!expr) return;
        const logic = window.prompt('逻辑说明（可选）：', '');
        if (!Array.isArray(profile.keyword_rules)) profile.keyword_rules = [];
        profile.keyword_rules.push({
          id: `kw-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
          expr: normalizeText(expr),
          logic_cn: normalizeText(logic || ''),
          must_have: [],
          optional: [],
          exclude: [],
          rewrite_for_embedding: cleanBooleanForEmbedding(expr),
          enabled: true,
          source: 'manual',
          note: '',
        });
      });
      return;
    }

    if (action === 'add-q') {
      mutateEditState((profile) => {
        const text = window.prompt('新增语义 Query：', '');
        if (!text) return;
        const logic = window.prompt('逻辑说明（可选）：', '');
        if (!Array.isArray(profile.semantic_queries)) profile.semantic_queries = [];
        profile.semantic_queries.push({
          id: `q-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
          text: normalizeText(text),
          logic_cn: normalizeText(logic || ''),
          enabled: true,
          source: 'manual',
          note: '',
        });
      });
      return;
    }
  };

  const saveEditModal = () => {
    if (!modalState || modalState.type !== 'edit') return;
    const local = modalState.profile || {};
    const tag = normalizeText(document.getElementById('dpr-edit-tag')?.value || local.tag || '');
    const desc = normalizeText(document.getElementById('dpr-edit-desc')?.value || local.description || '');
    const enabled = !!document.getElementById('dpr-edit-enabled')?.checked;
    if (!tag) {
      setMessage('标签不能为空。', '#c00');
      return;
    }

    local.tag = tag;
    local.description = desc;
    local.enabled = enabled;
    local.keyword_rules = (Array.isArray(local.keyword_rules) ? local.keyword_rules : [])
      .map((x) => ({ ...x, expr: normalizeText(x.expr || '') }))
      .filter((x) => normalizeText(x.expr || ''));
    local.semantic_queries = (Array.isArray(local.semantic_queries) ? local.semantic_queries : [])
      .map((x) => ({ ...x, text: normalizeText(x.text || '') }))
      .filter((x) => normalizeText(x.text || ''));
    local.updated_at = new Date().toISOString();

    window.SubscriptionsManager.updateDraftConfig((cfg) => {
      const next = cfg || {};
      if (!next.subscriptions) next.subscriptions = {};
      const subs = next.subscriptions;
      const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
      const idx = profiles.findIndex((p) => normalizeText(p.id) === normalizeText(local.id));
      if (idx >= 0) {
        profiles[idx] = deepClone(local);
      }
      subs.intent_profiles = profiles;
      next.subscriptions = subs;
      return next;
    });

    if (typeof reloadAll === 'function') reloadAll();
    setMessage('词条修改已更新，请点击「保存」。', '#666');
    closeModal();
  };

  const handleModalClick = (e) => {
    const target = e.target;
    if (!target || !target.closest) return;
    const actionEl = target.closest('[data-action]');
    const action = actionEl ? actionEl.getAttribute('data-action') : '';
    if (action === 'close') {
      closeModal();
      return;
    }

    if (modalState && modalState.type === 'add') {
      if (action === 'toggle-kw-card') {
        const idx = Number(actionEl.getAttribute('data-index'));
        if (idx >= 0 && idx < (modalState.keywords || []).length) {
          modalState.keywords[idx]._selected = !modalState.keywords[idx]._selected;
          renderAddModal();
        }
        return;
      }
      if (action === 'toggle-query-card') {
        const idx = Number(actionEl.getAttribute('data-index'));
        if (idx >= 0 && idx < (modalState.queries || []).length) {
          modalState.queries[idx]._selected = !modalState.queries[idx]._selected;
          renderAddModal();
        }
        return;
      }
      if (action === 'add-custom-kw') {
        const expr = normalizeText(document.getElementById('dpr-add-kw-text')?.value || '');
        const logic = normalizeText(document.getElementById('dpr-add-kw-logic')?.value || '');
        if (!expr) {
          setMessage('请输入要新增的关键词。', '#c00');
          return;
        }
        const existed = (modalState.keywords || []).some(
          (x) => normalizeText(x.expr || '').toLowerCase() === expr.toLowerCase(),
        );
        if (existed) {
          setMessage('该关键词已在候选中。', '#c00');
          return;
        }
        modalState.keywords.push({
          id: `manual-kw-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
          expr,
          logic_cn: logic,
          must_have: [],
          optional: [],
          exclude: [],
          rewrite_for_embedding: cleanBooleanForEmbedding(expr),
          enabled: true,
          source: 'manual',
          note: '',
          _selected: true,
        });
        modalState.customKeyword = '';
        modalState.customKeywordLogic = '';
        renderAddModal();
        setMessage('已加入自定义关键词候选。', '#666');
        return;
      }
      if (action === 'add-custom-query') {
        const text = normalizeText(document.getElementById('dpr-add-query-text')?.value || '');
        const logic = normalizeText(document.getElementById('dpr-add-query-logic')?.value || '');
        if (!text) {
          setMessage('请输入要新增的 Query。', '#c00');
          return;
        }
        const existed = (modalState.queries || []).some(
          (x) => normalizeText(x.text || '').toLowerCase() === text.toLowerCase(),
        );
        if (existed) {
          setMessage('该 Query 已在候选中。', '#c00');
          return;
        }
        modalState.queries.push({
          id: `manual-q-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
          text,
          logic_cn: logic,
          enabled: true,
          source: 'manual',
          note: '',
          _selected: true,
        });
        modalState.customQuery = '';
        modalState.customQueryLogic = '';
        renderAddModal();
        setMessage('已加入自定义 Query 候选。', '#666');
        return;
      }
      if (action === 'apply-add') {
        applyAddModal();
        return;
      }
    }

    if (modalState && modalState.type === 'edit') {
      if (action === 'save-edit') {
        saveEditModal();
        return;
      }
      if (action) {
        handleEditAction(action, actionEl ? actionEl.getAttribute('data-index') : '');
      }
    }

    if (modalState && modalState.type === 'chat') {
      if (action === 'chat-send') {
        askChatOnce();
        return;
      }
      if (action === 'apply-chat') {
        applyChatSelection();
        return;
      }
    }
  };

  const handleModalChange = (e) => {
    const target = e.target;
    if (!target || !target.matches) return;
    if (!target.matches('input[type="checkbox"][data-action="toggle-chat-choice"]')) return;
    if (!modalState || modalState.type !== 'chat') return;

    const kind = target.getAttribute('data-kind');
    const idx = Number(target.getAttribute('data-index'));
    const list = kind === 'query' ? modalState.queries : modalState.keywords;
    if (!Array.isArray(list) || idx < 0 || idx >= list.length) return;
    const selected = !!target.checked;
    const card = target.closest('.dpr-cloud-item');
    if (card) {
      card.classList.toggle('selected', selected);
    }

    if (kind === 'kw' && Array.isArray(modalState.keywords) && idx >= 0 && idx < modalState.keywords.length) {
      modalState.keywords[idx]._selected = selected;
      return;
    }
    if (kind === 'query' && Array.isArray(modalState.queries) && idx >= 0 && idx < modalState.queries.length) {
      modalState.queries[idx]._selected = selected;
    }
  };

  const requestHistoryLength = (state) => {
    const history = Array.isArray(state && state.requestHistory) ? state.requestHistory : [];
    if (!history.length) {
      return '首次生成';
    }
    return `新增第 ${history.length + 1} 轮`;
  };

  const generateAndOpenAddModal = async () => {
    const tag = normalizeText(tagInputEl?.value || '');
    const desc = normalizeText(descInputEl?.value || '');
    if (!tag) {
      setMessage('请先填写标签（Tag）。', '#c00');
      return;
    }
    if (!desc) {
      setMessage('请先填写智能 Query 描述。', '#c00');
      return;
    }

    try {
      setMessage('正在生成候选，请稍候...', '#666');
      if (createBtn) createBtn.disabled = true;
      const candidates = await requestCandidatesByDesc(tag, desc);

      openAddModal(tag, desc, candidates);
      setMessage(`候选已生成（关键词 ${candidates.keywords.length} 条，Query ${candidates.queries.length} 条）。`, '#666');
    } catch (e) {
      console.error(e);
      setMessage(`生成失败：${e && e.message ? e.message : '未知错误'}`, '#c00');
    } finally {
      if (createBtn) createBtn.disabled = false;
    }
  };

  const handleDisplayClick = (e) => {
    const actionEl = e.target && e.target.closest ? e.target.closest('[data-action][data-profile-id]') : null;
    if (!actionEl) return;
    const profileId = actionEl.getAttribute('data-profile-id');
    if (!profileId) return;
    const action = actionEl.getAttribute('data-action');
    if (action === 'edit-profile') {
      openEditModal(profileId);
      return;
    }
    if (action === 'delete-profile') {
      const profile = (currentProfiles || []).find((p) => normalizeText(p.id) === normalizeText(profileId));
      const tag = normalizeText(profile && profile.tag) || '该词条';
      const desc = normalizeText(profile && profile.description);
      const kwCount = Array.isArray(profile && profile.keyword_rules) ? profile.keyword_rules.length : 0;
      const qCount = Array.isArray(profile && profile.semantic_queries) ? profile.semantic_queries.length : 0;
      const summary = desc || `关键词 ${kwCount} 条，Query ${qCount} 条`;
      const ok = window.confirm(
        `确认删除词条「${tag}」吗？\n简介：${summary}\n此操作可在未保存前通过刷新放弃。`,
      );
      if (!ok) return;
      window.SubscriptionsManager.updateDraftConfig((cfg) => {
        const next = cfg || {};
        if (!next.subscriptions) next.subscriptions = {};
        const subs = next.subscriptions;
        const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
        subs.intent_profiles = profiles.filter((p) => normalizeText(p.id) !== normalizeText(profileId));
        next.subscriptions = subs;
        return next;
      });
      if (typeof reloadAll === 'function') reloadAll();
      setMessage(`已删除词条「${tag}」，请点击「保存」。`, '#666');
    }
  };

  const attach = (context) => {
    displayListEl = context.displayListEl || null;
    createBtn = context.createBtn || null;
    openChatBtn = context.openChatBtn || null;
    tagInputEl = context.tagInputEl || null;
    descInputEl = context.descInputEl || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    if (createBtn && !createBtn._bound) {
      createBtn._bound = true;
      createBtn.addEventListener('click', generateAndOpenAddModal);
    }

    if (openChatBtn && !openChatBtn._bound) {
      openChatBtn._bound = true;
      openChatBtn.addEventListener('click', openChatModal);
    }

    const autoResizeDesc = () => {
      if (!descInputEl) return;
      descInputEl.style.height = '36px';
      const next = Math.min(Math.max(descInputEl.scrollHeight, 36), 240);
      descInputEl.style.height = `${next}px`;
    };
    if (descInputEl && !descInputEl._boundAutoResize) {
      descInputEl._boundAutoResize = true;
      descInputEl.addEventListener('input', autoResizeDesc);
      autoResizeDesc();
    }

    if (displayListEl && !displayListEl._bound) {
      displayListEl._bound = true;
      displayListEl.addEventListener('click', handleDisplayClick);
    }

    ensureModal();
    if (modalPanel && !modalPanel._boundClick) {
      modalPanel._boundClick = true;
      modalPanel.addEventListener('click', handleModalClick);
      modalPanel.addEventListener('change', handleModalChange);
    }
  };

  const render = (profiles) => {
    currentProfiles = Array.isArray(profiles) ? deepClone(profiles) : [];
    renderMain();
  };

  return {
    attach,
    render,
  };
})();
