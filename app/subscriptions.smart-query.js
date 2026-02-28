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
  const pendingDeletedProfileIds = new Set();
  let modalOverlay = null;
  let modalPanel = null;
  let modalState = null;

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
    '    }',
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
    '6) Do not output extra fields like must_have / optional / exclude / rewrite_for_embedding.',
    '7) Return pure JSON only, no explanations.',
    '8) Tag suggestion should be concise, preferably under 6 characters.',
  ].join('\n');

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
  const getProfileKey = (profileOrTag) => {
    if (!profileOrTag) return '';
    if (typeof profileOrTag === 'string') return toStableId(profileOrTag);
    return toStableId(profileOrTag.tag) || '';
  };

  const normalizeProfileKeywords = (profile) => {
    return normalizeKeywordEntries(profile && profile.keywords);
  };

  const normalizeKeywordEntries = (rawKeywords) => {
    const items = Array.isArray(rawKeywords) ? rawKeywords : [];
    return items
      .map((item, idx) => {
        if (typeof item === 'string') {
          const keyword = normalizeText(item);
          if (!keyword) return null;
          return {
            keyword,
            keyword_cn: '',
            query: keyword,
          };
        }
        if (!item || typeof item !== 'object') return null;
        const keyword = normalizeText(item.keyword || item.text || item.expr || '');
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
      })
      .filter(Boolean);
  };

  const normalizeIntentQueryEntries = (rawIntentQueries) => {
    const items = Array.isArray(rawIntentQueries) ? rawIntentQueries : [];
    const seen = new Set();
    return items
      .map((item, idx) => {
        if (typeof item === 'string') {
          const query = normalizeText(item);
          if (!query) return null;
          return {
            query,
            query_cn: '',
            enabled: true,
            source: 'generated',
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
          source: normalizeText(item.source || 'generated'),
          note: normalizeText(item.note || ''),
        };
      })
      .filter((item) => {
        if (!item) return false;
        const key = normalizeText(item.query).toLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  };

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

  const setMessage = (text, color) => {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.color = color || '#666';
  };

  const getProfileId = (profileId) => getProfileKey(profileId);

  const isProfileDeleted = (profileId) => {
    const normalizedId = getProfileId(profileId);
    return !!normalizedId && pendingDeletedProfileIds.has(normalizedId);
  };

  const clearPendingDeletedProfileIds = () => {
    pendingDeletedProfileIds.clear();
  };

  const filterDeletedProfiles = (profiles) => {
    return (Array.isArray(profiles) ? profiles : []).filter(
      (profile) => !isProfileDeleted(getProfileId(profile)),
    );
  };

  const ensureProfile = (profiles, tag, description) => {
    const t = normalizeText(tag);
    let profile = profiles.find((p) => getProfileKey(p) === getProfileKey(t));
    if (profile) {
      if (normalizeText(description) && !normalizeText(profile.description)) {
        profile.description = normalizeText(description);
      }
      return profile;
    }
    profile = {
      tag: t,
      description: normalizeText(description),
      enabled: true,
      keywords: [],
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

  const stripJsonWrappers = (text) => {
    let cleaned = normalizeText(text);
    if (!cleaned) return '';
    const fenceMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
    if (fenceMatch && fenceMatch[1] !== undefined) {
      return normalizeText(fenceMatch[1]);
    }
    return normalizeText(cleaned);
  };

  const repairJsonSuffix = (text) => {
    if (!text) return text;
    const stack = [];
    let inStr = false;
    let escaped = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inStr) {
        if (escaped) {
          escaped = false;
          continue;
        }
        if (ch === '\\') {
          escaped = true;
          continue;
        }
        if (ch === '"') {
          inStr = false;
        }
        continue;
      }
      if (ch === '"') {
        inStr = true;
      } else if (ch === '{') {
        stack.push('}');
      } else if (ch === '[') {
        stack.push(']');
      } else if (ch === '}' || ch === ']') {
        if (stack.length && stack[stack.length - 1] === ch) stack.pop();
      }
    }
    let repaired = text;
    if (inStr) repaired += '"';
    if (stack.length) repaired += stack.reverse().join('');
    repaired = repaired.replace(/,\s*([}\]])/g, '$1');
    return repaired;
  };

  const loadJsonLenient = (text) => {
    if (text && typeof text === 'object') return text;
    const raw = stripJsonWrappers(text);
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch {
      const candidates = [];
      const rawObjectMatch = raw.match(/\{[\s\S]*\}/);
      if (rawObjectMatch && rawObjectMatch[0]) {
        candidates.push(rawObjectMatch[0]);
      }
      const rawArrayMatch = raw.match(/\[[\s\S]*\]/);
      if (rawArrayMatch && rawArrayMatch[0]) {
        candidates.push(rawArrayMatch[0]);
      }

      for (let i = 0; i < candidates.length; i++) {
        try {
          const repaired = repairJsonSuffix(candidates[i]);
          const parsed = JSON.parse(repaired);
          if (parsed && typeof parsed === 'object') return parsed;
        } catch {}
      }
      throw new Error('模型返回不是合法 JSON');
    }
  };

  const normalizeGenerated = (payload) => {
    const resolvePayload = (value) => {
      if (!value) return {};
      if (Array.isArray(value)) {
        const candidate = value.find(
          (item) =>
            item &&
            typeof item === 'object' &&
            !Array.isArray(item) &&
            (item.keywords || item.intent_queries || item.intentQueries || item.llm_queries || item.semantic_queries || item.description || item.tag),
        );
        return candidate || {};
      }
      if (value && typeof value === 'object') return value;
      return {};
    };

    const normalizeIntentSource = (obj) => {
      if (!obj || typeof obj !== 'object') return [];
      const rawList = [];
      const pushArr = (v) => {
        if (Array.isArray(v)) rawList.push(...v);
      };
      pushArr(obj.intent_queries);
      pushArr(obj.intentQueries);
      pushArr(obj.intent_query);
      pushArr(obj.intentQuery);
      pushArr(obj.intents);
      pushArr(obj.queries);
      pushArr(obj.llm_queries);
      pushArr(obj.semantic_queries);
      if (typeof obj.intent === 'string') rawList.push(obj.intent);
      return rawList;
    };

    const data = resolvePayload(payload);
    const tag = normalizeText(
      data.tag ||
        data.标签 ||
        data.intent_tag ||
        data.profile_tag ||
        '',
    );
    const description = normalizeText(
      data.description ||
        data.中文描述 ||
        data.profile_desc ||
        data.user_description ||
        '',
    );
    const rawKeywords = Array.isArray(data.keywords) ? data.keywords : [];
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
        if (!item) return null;
        const keyword =
          typeof item === 'string' ? normalizeText(item) : normalizeText(item.keyword || item.text || item.expr || '');
        if (!keyword) return null;
        const keywordCn = normalizeText(
          typeof item === 'string'
            ? ''
            : normalizeText(item.keyword_cn || item.keyword_zh || item.zh || ''),
        );
        const query = normalizeText(
          typeof item === 'string' ? keyword : normalizeText(item.query || item.rewrite || keyword),
        );
        return {
          keyword,
          keyword_cn: keywordCn,
          query: query || keyword,
        };
      })
      .filter(Boolean);

    // 关键词召回去冗余：
    // 若已有核心术语（如 symbolic regression），则将 "X symbolic regression" 归一为 "X"；
    // 若 X 只是泛形容词，则直接丢弃该冗余词条。
    const plainList = keywords.map((k) => normalizePhrase(k.keyword || ''));
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
          const text = normalizeText(k.keyword || '');
        if (!text) return null;
        const plain = normalizePhrase(text);
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
            keyword: prefixPlain,
          };
        }
        return k;
      })
      .filter(Boolean);

    // 归一后再去重
    const kwSeen = new Set();
    keywords = keywords.filter((k) => {
      const key = normalizePhrase(k.keyword || '');
      if (!key || kwSeen.has(key)) return false;
      kwSeen.add(key);
      return true;
    });

    const rawIntentQueries = normalizeIntentSource(data);
    const intentQueries = normalizeIntentQueryEntries(rawIntentQueries);

    return {
      tag,
      description,
      keywords,
      intent_queries: intentQueries,
    };
  };

  const buildPromptFromTemplate = (tag, desc, template) => {
    const retrievalContext =
      'For each item in keywords, use keyword (atomic recall token) and query (semantic rewrite). keyword is used for BM25 OR recall, query is used for embedding/ranker/LLM. '
      + 'intent_queries are intent-matching recall candidates and also participate in final LLM re-ranking.';
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
    const template = defaultPromptTemplate;
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
    const requestPayload = ({ useResponseFormat = true, includeTools = true }) => {
      const payload = {
        model: llm.model,
        messages: [
          {
            role: 'system',
            content:
              'You are a retrieval planning assistant and can only return valid JSON. '
              + 'The response must be fully based on the current user input and must not reference prior conversation history.',
          },
          { role: 'user', content: prompt },
        ],
        temperature: 0.1,
      };
      if (includeTools) {
        payload.tools = [];
        payload.tool_choice = 'none';
      }
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

    const doFetch = async (
      endpoint,
      options = { useResponseFormat: true, includeTools: true },
      withApiKeyHeader = true,
    ) => {
      const headers = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${llm.apiKey}`,
      };
      if (withApiKeyHeader) {
        headers['x-api-key'] = llm.apiKey;
      }
      return fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestPayload(options)),
        signal: controller.signal,
      });
    };

    const doFetchWithFallbackHeader = async (endpoint, options) => {
      try {
        return await doFetch(endpoint, options, true);
      } catch (e) {
        if (!isFetchFailure(e)) {
          throw e;
        }
        return doFetch(endpoint, options, false);
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
          current = await doFetchWithFallbackHeader(endpoint, {
            useResponseFormat: true,
            includeTools: true,
          });
          if (current && !current.ok) {
            txt = await current.text().catch(() => '');
            if (current.status === 400 && /response[\s-]*format|json_object/i.test(txt)) {
              current = await doFetchWithFallbackHeader(endpoint, {
                useResponseFormat: false,
                includeTools: true,
              });
            }
            if (current && !current.ok && current.status === 400 && /tool_choice|tools/i.test(txt)) {
              current = await doFetchWithFallbackHeader(endpoint, {
                useResponseFormat: false,
                includeTools: false,
              });
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
    if (!candidates.keywords.length) {
      throw new Error('模型未返回可用候选，请调整描述后重试。');
    }
    return candidates;
  };

  const applyCandidateToProfile = (tag, description, candidates) => {
    const selectedKeywords = (candidates.keywords || []).filter((x) => x._selected);
    const selectedIntentQueries = (candidates.intent_queries || []).filter((x) => x._selected);
    if (!selectedKeywords.length && !selectedIntentQueries.length) {
      return false;
    }
    const intentQueries = normalizeIntentQueryEntries(selectedIntentQueries);

    window.SubscriptionsManager.updateDraftConfig((cfg) => {
      const next = cfg || {};
      if (!next.subscriptions) next.subscriptions = {};
      const subs = next.subscriptions;
      const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
      const profile = ensureProfile(profiles, tag, description);
      const kwList = normalizeProfileKeywords(profile).slice();
      const kwSeen = new Set(
        kwList
          .map((item) => normalizeText(item.keyword).toLowerCase())
          .filter(Boolean),
      );
      selectedKeywords.forEach((item, idx) => {
        const keyword = normalizeText(item.keyword || item.text || item.expr || '');
        if (!keyword) return;
        const key = keyword.toLowerCase();
        if (kwSeen.has(key)) return;
        kwSeen.add(key);
        kwList.push({
          keyword,
          keyword_cn: normalizeText(item.keyword_cn || item.keyword_zh || item.zh || ''),
          query: normalizeText(item.query || item.text || keyword),
        });
      });

      profile.description = normalizeText(profile.description || description || '');
      profile.keywords = kwList;
      const mergedIntentQueries = [];
      const intentSeen = new Set();
      const pushIntent = (item) => {
        const query = normalizeText(item && item.query);
        if (!query) return;
        const qKey = query.toLowerCase();
        if (intentSeen.has(qKey)) return;
        intentSeen.add(qKey);
        mergedIntentQueries.push({
          query,
          query_cn: normalizeText(item.query_cn || item.query_zh || item.zh || ''),
        });
      };

      normalizeIntentQueryEntries(profile.intent_queries).forEach(pushIntent);
      intentQueries.forEach(pushIntent);
      profile.intent_queries = mergedIntentQueries;
      profile.updated_at = new Date().toISOString();
      subs.intent_profiles = profiles;
      next.subscriptions = subs;
      return next;
    });
    return true;
  };

  const replaceProfileFromSelection = (profileId, tag, description, candidates) => {
    const profileKey = getProfileKey(profileId);
    if (!profileKey) return false;

    const selectedKeywords = (candidates.keywords || []).filter((x) => x._selected);
    const selectedIntentQueries = (candidates.intent_queries || []).filter((x) => x._selected);
    if (!selectedKeywords.length && !selectedIntentQueries.length) return false;
    const intentQueries = normalizeIntentQueryEntries(selectedIntentQueries);

    let found = false;
    window.SubscriptionsManager.updateDraftConfig((cfg) => {
      const next = cfg || {};
      if (!next.subscriptions) next.subscriptions = {};
      const subs = next.subscriptions;
      const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
      const idx = profiles.findIndex((p) => getProfileKey(p) === profileKey);
      if (idx < 0) return next;
      found = true;

      const existedProfile = profiles[idx] || {};
      const mergedIntentQueries = [];
      const intentSeen = new Set();
      const pushIntent = (queryObj) => {
        const query = normalizeText(queryObj && queryObj.query);
        if (!query || intentSeen.has(query.toLowerCase())) return;
        intentSeen.add(query.toLowerCase());
        mergedIntentQueries.push({
          query,
          query_cn: normalizeText(queryObj.query_cn || queryObj.query_zh || queryObj.zh || ''),
          enabled: queryObj.enabled !== false,
          source: normalizeText(queryObj.source || 'manual'),
          note: normalizeText(queryObj.note || ''),
        });
      };

      (normalizeIntentQueryEntries(existedProfile.intent_queries) || []).forEach(pushIntent);
      intentQueries.forEach(pushIntent);

      profiles[idx] = {
        ...existedProfile,
        tag: normalizeText(tag || existedProfile.tag || ''),
        description: normalizeText(description || existedProfile.description || ''),
        keywords:
          selectedKeywords.length > 0
            ? selectedKeywords
                .map((item, idx) => ({
                  keyword: normalizeText(item.keyword || item.text || item.expr || ''),
                  keyword_cn: normalizeText(item.keyword_cn || item.keyword_zh || item.zh || ''),
                  query: normalizeText(item.query || item.text || item.keyword || ''),
                }))
                .filter((x) => x.keyword)
            : normalizeProfileKeywords(existedProfile),
        intent_queries: mergedIntentQueries,
        updated_at: new Date().toISOString(),
      };
      subs.intent_profiles = profiles;
      next.subscriptions = subs;
      return next;
    });
    return found;
  };

  const parseCandidatesForState = (candidates, selected = true) => {
    return {
      keywords: (candidates.keywords || []).map((x) => ({ ...x, _selected: selected })),
      intent_queries: (candidates.intent_queries || []).map((x) => ({ ...x, _selected: selected })),
    };
  };

  const mergeCandidatesForNextRound = (existingItems, incomingItems, keyField) => {
    const normalizeKey = (item, field) =>
      normalizeText(item && item[field]).toLowerCase().trim();
    const incoming = Array.isArray(incomingItems) ? incomingItems.slice() : [];
    const incomingMap = new Map();
    const existing = Array.isArray(existingItems) ? existingItems : [];

    incoming.forEach((item) => {
      const key = normalizeKey(item, keyField);
      if (!key || incomingMap.has(key)) return;
      incomingMap.set(key, item);
    });

    const selectedFromExisting = [];
    const seen = new Set();

    existing.forEach((item) => {
      const key = normalizeKey(item, keyField);
      if (!key || seen.has(key) || !item || !item._selected) return;
      const incomingItem = incomingMap.get(key);
      selectedFromExisting.push({
        ...(incomingItem || item),
        _selected: true,
      });
      seen.add(key);
    });

    const nextIncoming = incoming.filter((item) => {
      if (!item || typeof item !== 'object') return false;
      const key = normalizeKey(item, keyField);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      item._selected = false;
      return true;
    });

    return selectedFromExisting.concat(nextIncoming);
  };

  const toProfileSelectableCandidates = (profile) => {
    const rawKeywords = normalizeKeywordEntries(profile && profile.keywords);
    const keywords = rawKeywords.map((k) => ({
      keyword: normalizeText(k.keyword || ''),
      query: normalizeText(k.query || k.keyword || ''),
      keyword_cn: normalizeText(k.keyword_cn || ''),
    }));

    const keywordState = parseCandidatesForState({ keywords }, false);
    return {
      keywords: keywordState.keywords,
      intent_queries: normalizeIntentQueryEntries(profile && profile.intent_queries),
    };
  };

  const renderCloudCards = (items, kind, options = {}) => {
    const textField = options.textField || 'text';
    const descField = options.descField || 'logic_cn';
    const descFallbackField = options.descFallbackField || 'logic_cn';
    const defaultDesc = options.defaultDesc || '';
    return (items || [])
      .map((item, idx) => {
        const text = normalizeText(item[textField] || '');
        const desc = normalizeText(
          item[descField] || item[descFallbackField] || defaultDesc || '',
        );
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
        return `
          <div class="dpr-entry-card" data-profile-id="${escapeHtml(getProfileKey(p) || '')}">
            <div class="dpr-entry-top">
              <div class="dpr-entry-headline">
                <span class="dpr-entry-title">${escapeHtml(p.tag || '')}</span>
                <span class="dpr-entry-desc-inline">${escapeHtml(p.description || '（无描述）')}</span>
              </div>
              <div class="dpr-entry-actions">
                <button class="arxiv-tool-btn dpr-entry-edit-btn" data-action="edit-profile" data-profile-id="${escapeHtml(getProfileKey(p) || '')}">修改</button>
                <button class="arxiv-tool-btn dpr-entry-delete-btn" data-action="delete-profile" data-profile-id="${escapeHtml(getProfileKey(p) || '')}">删除</button>
              </div>
            </div>
          </div>
        `;
      })
      .join('');
  };

  const openAddModal = (tag, description, candidates) => {
    const normalizedCandidates = parseCandidatesForState(candidates);
    const suggestedTag = normalizeText(candidates && candidates.tag) || normalizeText(tag);
    const suggestedDesc = normalizeText(candidates && candidates.description) || normalizeText(description);
    modalState = {
      type: 'add',
      tag: suggestedTag,
      description: suggestedDesc,
      keywords: normalizedCandidates.keywords,
      intent_queries: (normalizedCandidates.intent_queries || []),
      customKeyword: '',
      customKeywordLogic: '',
    };
    renderAddModal();
    openModal();
  };

  const openChatModal = () => {
    modalState = {
      type: 'chat',
      keywords: [],
      intent_queries: [],
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
        <div class="dpr-pick-title">${escapeHtml(k.keyword || k.text || '')}</div>
        <div class="dpr-pick-desc">${escapeHtml(k.keyword_cn || '（待补充中文直译）')}</div>
      </button>
        `,
      )
      .join('');
    const intentHtml = (modalState.intent_queries || [])
      .map(
        (item, idx) => `
      <button type="button" class="dpr-pick-card ${item._selected ? 'selected' : ''}" data-action="toggle-intent-query-card" data-index="${idx}">
        <div class="dpr-pick-title">${escapeHtml(item.query || item.text || '')}</div>
        <div class="dpr-pick-desc">${escapeHtml(item.query_cn || item.note || item.source || '（意图检索句）')}</div>
      </button>
        `,
      )
      .join('');
    const hasKeywords = (modalState.keywords || []).length > 0;
    const hasIntentQueries = (modalState.intent_queries || []).length > 0;
    const keywordBlock =
      `<div class="dpr-combo-block">
        <div class="dpr-modal-group-title">关键词（用于召回）</div>
        <div class="dpr-pick-grid">${kwHtml || '<div style="color:#999;">无关键词候选</div>'}</div>
      </div>`;
    const intentBlock =
      `<div class="dpr-combo-block">
        <div class="dpr-modal-group-title">意图Query（用于意图召回与最终打分）</div>
        <div class="dpr-pick-grid">${intentHtml || '<div style="color:#999;">无意图查询候选</div>'}</div>
      </div>`;
    const divider = `<div class="dpr-modal-divider"></div>`;
    const candidateBlocks = `${hasKeywords ? keywordBlock : ''}${hasKeywords && hasIntentQueries ? divider : ''}${
      hasIntentQueries ? intentBlock : ''
    }`;

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">${modalState && modalState.editProfileId ? '修改词条' : '新增词条候选'}</div>
        <button class="arxiv-tool-btn" data-action="close">关闭</button>
      </div>
      <div class="dpr-modal-group-title">
        请先在下方输入你的检索想法
      </div>
      <div class="dpr-help-examples">
        <div class="dpr-help-example">ex: 强化学习 符号回归</div>
        <div class="dpr-help-example">ex: 请帮我去查找强化学习和符号回归相关的论文</div>
        <div class="dpr-help-example">ex: 请帮我查找可解释的强化学习驱动符号回归方程发现论文</div>
      </div>
      <div class="dpr-modal-list dpr-combo-list">${candidateBlocks || '<div class="dpr-cloud-empty"></div>'}</div>
      <div class="dpr-modal-actions-inline dpr-modal-add-inline">
        <input id="dpr-add-kw-text" type="text" placeholder="手动新增关键词（召回词）" value="${escapeHtml(modalState.customKeyword || '')}" />
        <input id="dpr-add-kw-query" type="text" placeholder="对应语义 Query 改写" value="${escapeHtml(modalState.customQuery || '')}" />
        <input id="dpr-add-kw-logic" type="text" placeholder="中文直译（可选）" value="${escapeHtml(modalState.customKeywordLogic || '')}" />
        <button class="arxiv-tool-btn" data-action="add-custom-kw">加入候选</button>
      </div>
      <div class="dpr-modal-actions dpr-modal-add-footer">
        <label class="dpr-modal-field">
          <span class="dpr-modal-field-label">标签</span>
          <input id="dpr-add-profile-tag" type="text" value="${escapeHtml(modalState.tag || '')}" placeholder="请填写标签" />
        </label>
        <label class="dpr-modal-field">
          <span class="dpr-modal-field-label">中文描述</span>
          <input id="dpr-add-profile-desc" type="text" value="${escapeHtml(modalState.description || '')}" placeholder="请填写中文描述" />
        </label>
        <button class="arxiv-tool-btn" data-action="apply-add" style="background:#2e7d32;color:#fff;">保存查询</button>
      </div>
    `;
  };

  const applyAddModal = () => {
    if (!modalState || modalState.type !== 'add') return;
    const nextTag = normalizeText(document.getElementById('dpr-add-profile-tag')?.value || '');
    const nextDesc = normalizeText(document.getElementById('dpr-add-profile-desc')?.value || '');

    if (!nextTag || !nextDesc) {
      setMessage('标签和描述不能为空。', '#c00');
      return;
    }

    modalState.tag = nextTag;
    modalState.description = nextDesc;

    const selectedKeywords = (modalState.keywords || []).filter((x) => x._selected);
    const selectedIntentQueries = (modalState.intent_queries || []).filter((x) => x._selected);
    const isEditMode = !!(modalState && modalState.editProfileId);
    const ok = isEditMode
      ? replaceProfileFromSelection(
          modalState.editProfileId,
          modalState.tag,
          modalState.description,
          {
            ...modalState,
            keywords: selectedKeywords,
            intent_queries: selectedIntentQueries,
          },
        )
      : applyCandidateToProfile(modalState.tag, modalState.description, {
          ...modalState,
          keywords: selectedKeywords,
          intent_queries: selectedIntentQueries,
        });

    if (!ok) {
      setMessage('请至少选择一条候选。', '#c00');
      return;
    }

    if (typeof reloadAll === 'function') reloadAll();
    setMessage(isEditMode ? '词条修改已应用，请点击「保存」。' : '新增词条已应用，请点击「保存」。', '#666');
    closeModal();
  };

  const renderChatModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'chat') return;

    const kwHtml = renderCloudCards(modalState.keywords || [], 'kw', {
      textField: 'keyword',
      descField: 'keyword_cn',
      defaultDesc: '（待补充中文直译）',
    });
    const intentHtml = renderCloudCards(modalState.intent_queries || [], 'intent', {
      textField: 'query',
      descField: 'query_cn',
      descFallbackField: 'note',
      defaultDesc: '（待补充中文直译）',
    });
    const hasKeywords = Array.isArray(modalState.keywords) && modalState.keywords.length > 0;
    const hasIntentQueries = Array.isArray(modalState.intent_queries) && modalState.intent_queries.length > 0;
    const hasCandidates = hasKeywords || hasIntentQueries;
    const isFirstRound = !(Array.isArray(modalState.requestHistory) && modalState.requestHistory.length);
    const actionLabel = isFirstRound ? '生成候选' : '新增候选';
    const kwSection = hasKeywords
      ? `<div class="dpr-chat-result-block">
           <div class="dpr-modal-group-title">关键词（用于召回）</div>
           <div class="dpr-cloud-grid dpr-cloud-grid-keywords">${kwHtml}</div>
         </div>`
      : '';
    const intentSection = hasIntentQueries
      ? `<div class="dpr-chat-result-block">
           <div class="dpr-modal-group-title">意图Query（用于意图召回与最终打分）</div>
           <div class="dpr-cloud-grid dpr-cloud-grid-intent">${intentHtml}</div>
         </div>`
      : '';
    const mixedHtml = `${kwSection}${hasKeywords && hasIntentQueries ? '<div class="dpr-chat-divider"></div>' : ''}${intentSection}`;
    const emptyBlock = '<div class="dpr-cloud-empty"></div>';

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">新增查询</div>
        <button class="arxiv-tool-btn" data-action="close">关闭</button>
      </div>
      <div class="dpr-chat-result-module">
        <div class="dpr-modal-group-title">
          请先在下方输入你的检索想法
        </div>
        <div class="dpr-help-examples">
          <div class="dpr-help-example">ex: 强化学习 符号回归</div>
          <div class="dpr-help-example">ex: 请帮我去查找强化学习和符号回归相关的论文</div>
          <div class="dpr-help-example">ex: 请帮我查找可解释的强化学习驱动符号回归方程发现论文</div>
        </div>
        <div class="dpr-cloud-scroll">${mixedHtml || emptyBlock}</div>
      </div>
      <div class="dpr-modal-actions dpr-chat-action-area">
        <div class="dpr-chat-row">
          <label class="dpr-chat-label dpr-chat-inline-desc">
            <span class="dpr-chat-label-text">检索需求</span>
            <textarea id="dpr-chat-desc-input" rows="2" placeholder="请帮我去查找强化学习和符号回归相关的论文">${escapeHtml(
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
      <div class="dpr-modal-actions dpr-modal-add-footer">
        <label class="dpr-chat-label dpr-chat-inline-tag">
          <span class="dpr-chat-label-text">标签</span>
          <input id="dpr-chat-tag-input" type="text" placeholder="例如：SR" value="${escapeHtml(modalState.inputTag || '')}" />
        </label>
        <label class="dpr-chat-label dpr-chat-inline-desc">
          <span class="dpr-chat-label-text">中文描述</span>
          <input id="dpr-chat-required-desc" type="text" placeholder="请填写描述" value="${escapeHtml(modalState.inputDesc || '')}" />
        </label>
        <button class="arxiv-tool-btn" data-action="apply-chat" style="background:#2e7d32;color:#fff;" ${hasCandidates ? '' : 'disabled'}>
          保存查询
        </button>
      </div>
    `;
  };

  const applyChatSelection = () => {
    let hasSelection = false;
    const selectedKeywords = (modalState.keywords || []).filter((x) => x._selected);
    const selectedIntentQueries = (modalState.intent_queries || []).filter((x) => x._selected);
    const hasItems = selectedKeywords.length || selectedIntentQueries.length;
    const desc = normalizeText(document.getElementById('dpr-chat-required-desc')?.value || '');
    const tag = normalizeText(document.getElementById('dpr-chat-tag-input')?.value || modalState.inputTag || '');

    if (!tag) {
      setMessage('请先填写标签。', '#c00');
      return;
    }
    if (!desc) {
      setMessage('请先填写中文描述。', '#c00');
      return;
    }
    modalState.inputTag = tag;

    if (hasItems) {
      const ok = applyCandidateToProfile(tag || `SR-${new Date().toISOString().slice(0, 10)}`, desc, {
        ...modalState,
        keywords: selectedKeywords,
        intent_queries: selectedIntentQueries,
      });
      hasSelection = ok;
    }

    if (!hasSelection) {
      setMessage(hasItems ? '应用失败，请重试。' : '请至少勾选一条候选后再应用。', '#c00');
      return;
    }
    if (typeof reloadAll === 'function') reloadAll();
    setMessage('查询已保存，请点击「保存」。', '#666');
    closeModal();
  };

  const askChatOnce = async () => {
    if (!modalState || modalState.type !== 'chat') return;
    if (modalState.pending) return;
    const tag = normalizeText(document.getElementById('dpr-chat-tag-input')?.value || '');
    const desc = normalizeText(document.getElementById('dpr-chat-desc-input')?.value || '');
    const finalDesc = desc;
    let finalTag = tag || `SR-${new Date().toISOString().slice(0, 10)}`;

    if (!finalDesc) {
      setChatStatus('请先填写检索需求。', '#c00');
      return;
    }

    modalState.pending = true;
    setSendBtnLoading(true);
    setChatStatus('正在生成候选，请稍候...', '#666');
    setMessage('正在生成候选，请稍候...', '#666');

    try {
      const candidates = await requestCandidatesByDesc(finalTag, finalDesc);
      const isFirstRound = !(Array.isArray(modalState.requestHistory) && modalState.requestHistory.length);
      const nextCandidates = parseCandidatesForState(candidates, false);
      const nextKeywords = isFirstRound
        ? nextCandidates.keywords
        : mergeCandidatesForNextRound(modalState.keywords, nextCandidates.keywords, 'keyword');
      const nextIntentQueries = isFirstRound
        ? nextCandidates.intent_queries
        : mergeCandidatesForNextRound(modalState.intent_queries, nextCandidates.intent_queries, 'query');
      const suggestedTag = normalizeText(candidates.tag);
      const suggestedDesc = normalizeText(candidates.description);
      if (!tag && suggestedTag) {
        finalTag = suggestedTag;
      }
      if (suggestedTag && !modalState.inputTag) {
        modalState.inputTag = suggestedTag;
      }
      const finalDescForProfile = suggestedDesc || finalDesc;
      modalState.inputDesc = finalDescForProfile;
      if (document.getElementById('dpr-chat-required-desc')) {
        document.getElementById('dpr-chat-required-desc').value = finalDescForProfile;
      }
      const roundLabel = requestHistoryLength(modalState);
      const history = Array.isArray(modalState.requestHistory) ? modalState.requestHistory.slice() : [];
      history.push({
        label: roundLabel,
        desc: finalDesc,
        newKeywords: nextCandidates.keywords.length,
        newIntentQueries: nextCandidates.intent_queries.length,
        createdAt: new Date().toISOString(),
      });
      modalState.keywords = nextKeywords;
      modalState.intent_queries = nextIntentQueries;
      modalState.chatTag = finalTag;
      modalState.inputTag = finalTag;
      modalState.lastTag = finalTag;
      modalState.lastDesc = finalDesc;
      modalState.requestHistory = history;
      modalState.chatStatus = `已生成候选（关键词 ${nextKeywords.length} 条，意图 ${nextIntentQueries.length} 条）。`;
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
    const targetKey = getProfileKey(profileId);
    if (!targetKey) return;
    const profile = (currentProfiles || []).find((p) => getProfileKey(p) === targetKey);
    if (!profile) return;

    modalState = {
      type: 'add',
      editProfileId: targetKey,
      tag: profile.tag || '',
      description: profile.description || '',
      ...toProfileSelectableCandidates(profile),
      intent_queries: normalizeIntentQueryEntries(profile && profile.intent_queries).map((item) => ({
        ...item,
        _selected: item.enabled !== false,
      })),
      customKeyword: '',
      customKeywordLogic: '',
    };
    modalState.keywords = (modalState.keywords || []).map((item) => ({
      ...item,
      _selected: item.enabled !== false,
    }));
    renderAddModal();
    openModal();
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
      if (action === 'toggle-intent-query-card') {
        const idx = Number(actionEl.getAttribute('data-index'));
        if (idx >= 0 && idx < (modalState.intent_queries || []).length) {
          modalState.intent_queries[idx]._selected = !modalState.intent_queries[idx]._selected;
          renderAddModal();
        }
        return;
      }
      if (action === 'add-custom-kw') {
        const kwText = normalizeText(document.getElementById('dpr-add-kw-text')?.value || '');
        const query = normalizeText(document.getElementById('dpr-add-kw-query')?.value || '');
        const logic = normalizeText(document.getElementById('dpr-add-kw-logic')?.value || '');
        if (!kwText) {
          setMessage('请输入要新增的关键词。', '#c00');
          return;
        }
        const existed = (modalState.keywords || []).some(
          (x) => normalizeText(x.keyword || x.text || '').toLowerCase() === kwText.toLowerCase(),
        );
        if (existed) {
          setMessage('该关键词已在候选中。', '#c00');
          return;
        }
        modalState.keywords.push({
          keyword: kwText,
          keyword_cn: logic,
          query: query || kwText,
          _selected: true,
        });
        modalState.customKeyword = '';
        modalState.customKeywordLogic = '';
        modalState.customQuery = '';
        renderAddModal();
        setMessage('已加入自定义关键词候选。', '#666');
        return;
      }
      if (action === 'apply-add') {
        applyAddModal();
        return;
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
    const list = kind === 'intent' ? modalState.intent_queries : modalState.keywords;
    if (!Array.isArray(list) || idx < 0 || idx >= list.length) return;
    const selected = !!target.checked;
    const card = target.closest('.dpr-cloud-item');
    if (card) {
      card.classList.toggle('selected', selected);
    }

    list[idx]._selected = selected;
  };

  const handleModalKeydown = (e) => {
    if (!e || e.target?.id !== 'dpr-chat-desc-input') return;
    if (e.key !== 'Enter') return;
    if (e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (modalState && modalState.type === 'chat') {
      askChatOnce();
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
    const finalTag = tag || `SR-${new Date().toISOString().slice(0, 10)}`;
    if (!desc) {
      setMessage('请先填写智能 Query 描述。', '#c00');
      return;
    }

    try {
      setMessage('正在生成候选，请稍候...', '#666');
      if (createBtn) createBtn.disabled = true;
      const candidates = await requestCandidatesByDesc(finalTag, desc);

      openAddModal(finalTag, desc, candidates);
      setMessage(`候选已生成（共 ${candidates.keywords.length} 条）。`, '#666');
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
      const profile = (currentProfiles || []).find((p) => getProfileKey(p) === getProfileKey(profileId));
      const tag = normalizeText(profile && profile.tag) || '该词条';
      const desc = normalizeText(profile && profile.description);
      const keywordCount = Array.isArray(profile && profile.keywords) ? profile.keywords.length : 0;
      const summary = desc || `关键词 ${keywordCount} 条`;
      const ok = window.confirm(
        `确认删除词条「${tag}」吗？\n简介：${summary}\n此操作可在未保存前通过刷新放弃。`,
      );
      if (!ok) return;
      const normalizedProfileId = getProfileId(profileId);
      if (normalizedProfileId) {
        pendingDeletedProfileIds.add(normalizedProfileId);
      }
      currentProfiles = currentProfiles.filter((item) => getProfileKey(item) !== normalizedProfileId);
      renderMain();

      window.SubscriptionsManager.updateDraftConfig((cfg) => {
        const next = cfg || {};
        if (!next.subscriptions) next.subscriptions = {};
        const subs = next.subscriptions;
        const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
        subs.intent_profiles = profiles.filter((p) => getProfileKey(p) !== getProfileKey(profileId));
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
      modalPanel.addEventListener('keydown', handleModalKeydown);
    }
  };

  const render = (profiles) => {
    const normalizedProfiles = Array.isArray(profiles) ? deepClone(profiles) : [];
    currentProfiles = filterDeletedProfiles(normalizedProfiles);
    renderMain();
  };

  return {
    attach,
    render,
    clearPendingDeletedProfileIds,
  };
})();
