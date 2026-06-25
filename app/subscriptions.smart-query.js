// Unified smart-query module (simplified interaction version)
// Main panel: only an input area + a display area
// Sub-panels:
// - Add panel: show model-returned candidates; apply after the user selects them
// - Edit panel: reuse the conversational flow to generate/update entries via dialogue

window.SubscriptionsSmartQuery = (function () {
  const MAX_KEYWORDS_PER_PROFILE = 6;
  const MAX_INTENT_QUERIES_PER_PROFILE = 4;
  const MAX_PROFILE_TAG_CHARS = 12;
  let displayListEl = null;
  let createBtn = null;
  let openChatBtn = null;
  let tagInputEl = null;
  let descInputEl = null;
  let msgEl = null;
  let reloadAll = null;

  let currentProfiles = [];
  const pendingDeletedProfileIds = new Set();
  const selectedProfileKeys = new Set();
  let runSelectionMode = '';
  let selectionChangeHandler = null;
  let selectionInitialized = false;
  let modalOverlay = null;
  let modalPanel = null;
  let modalState = null;

  const defaultPromptTemplate = [
    'You are a retrieval planning assistant.',
    'Tag: {{TAG}}',
    'Description: {{USER_DESCRIPTION}}',
    'Retrieval context: {{RETRIEVAL_CONTEXT}}',
    '',
    'Return JSON only:',
    '{',
    '  "tag": "optional tag suggestion (for user convenience)",',
    '  "description": "optional description (for user convenience)",',
    '  "keywords": [',
    '    {',
    '      "keyword": "short keyword phrase for BM25 recall",',
    '      "query": "semantic rewrite for this keyword",',
    '      "keyword_cn": "optional secondary label, e.g. a translation",',
    '    }',
    '  ],',
    '  "intent_queries": [',
    '    {',
    '      "query": "intent-oriented semantic query 1",',
    '      "query_cn": "optional secondary label, e.g. a translation",',
    '    },',
    '    {',
      '      "query": "intent-oriented semantic query 2",',
      '      "query_cn": "optional secondary label, e.g. a translation",',
    '    }',
    '  ],',
    '}',
    'Requirements:',
    '1) keywords: output 5-12 objects; each item must include keyword and query, keyword_cn optional.',
    '2) keyword and query MUST be English retrieval text only. Do not put Chinese in keyword or query.',
    '3) keyword_cn and query_cn are optional secondary labels (e.g. a translation in the user native language) when present.',
    '4) keywords are used for BM25 recall and should be meaningful atomic noun phrases, normally 2-4 English words.',
    '5) Do NOT output acronym-only or abbreviation-only keywords such as "rl", "xrl", "sr", "llm". Expand them to full phrases like "reinforcement learning" or "large language model".',
    '6) Do NOT output incomplete modifier phrases ending with generic words like "driven", "based", "related", "guided", "enhanced", "for", or "with".',
    '7) Do NOT output standalone adjective/modifier keywords like "explainable", "interpretable", "deep", or "neural"; attach the target concept, e.g. "explainable reinforcement learning".',
    '8) Keep keywords atomic and avoid packing multiple concepts into one phrase.',
    '9) Do not include concrete example topics in the prompt.',
    '10) intent_queries: output 1-4 actionable intent queries. The query field MUST be English only; query_cn is an optional secondary label.',
    '11) intent_queries must be specific semantic search sentences, not acronym-only strings.',
    '12) Do not output extra fields like must_have / optional / exclude / rewrite_for_embedding.',
    '13) Return pure JSON only, no explanations.',
    '14) intent_queries should be concise, timeless, and must not include years or year-like tokens.',
    '15) Tag suggestion must be concise: at most 12 characters total, counting hyphens.',
    '16) Tag suggestion must NOT include any year. Do not append or embed years (including digits like 2026/2025/2024 etc.) in tag.',
    '17) Tag suggestion must be English words or an English acronym only. Never output Chinese in tag.',
    '18) Tag suggestion must use hyphen-separated words when multiple words are needed, for example "reinforcement-learning". Do not use spaces or underscores in tag.',
    '19) If the descriptive tag would exceed 12 characters, output an English acronym or a shorter hyphenated label.',
  ].join('\n');

  const normalizeText = (v) => String(v || '').trim();
  const containsCjk = (v) => /[\u3400-\u9fff\uf900-\ufaff]/.test(String(v || ''));
  const isEnglishRetrievalText = (v) => {
    const text = normalizeText(v);
    return !!text && !containsCjk(text);
  };
  const PAPER_SOURCE_ORDER = [
    'arxiv',
    'biorxiv',
    'medrxiv',
    'chemrxiv',
    'neurips',
    'iclr',
    'icml',
    'acl',
    'emnlp',
    'aaai',
  ];
  const VISIBLE_PAPER_SOURCES = ['arxiv', 'biorxiv'];
  const PAPER_SOURCE_LABELS = {
    arxiv: 'arXiv',
    biorxiv: 'bioRxiv',
    medrxiv: 'medRxiv',
    chemrxiv: 'ChemRxiv',
    neurips: 'NeurIPS',
    iclr: 'ICLR',
    icml: 'ICML',
    acl: 'ACL',
    emnlp: 'EMNLP',
    aaai: 'AAAI',
  };
  const getSelectionLimit = (kind) => (
    normalizeCandidateKind(kind) === 'intent'
      ? MAX_INTENT_QUERIES_PER_PROFILE
      : MAX_KEYWORDS_PER_PROFILE
  );

  const getKindLabel = (kind) => (
    normalizeCandidateKind(kind) === 'intent' ? 'Intent Query' : 'Keyword'
  );

  const countSelectedCandidates = (items) =>
    (Array.isArray(items) ? items : []).filter((item) => item && !item._isDraftSlot && item._selected).length;

  const clampSelectionsByLimit = (items, kind) => {
    const limit = getSelectionLimit(kind);
    let selectedCount = 0;
    return (Array.isArray(items) ? items : []).map((item) => {
      if (!item || item._isDraftSlot) return item;
      const next = { ...item };
      if (next._selected) {
        selectedCount += 1;
        if (selectedCount > limit) {
          next._selected = false;
        }
      }
      return next;
    });
  };

  const validateProfileSelection = (keywords, intentQueries) => {
    const selectedKeywords = (Array.isArray(keywords) ? keywords : []).filter(
      (item) => item && !item._isDraftSlot && item._selected,
    );
    const selectedIntentQueries = (Array.isArray(intentQueries) ? intentQueries : []).filter(
      (item) => item && !item._isDraftSlot && item._selected,
    );
    if (!selectedKeywords.length) {
      return 'Please keep at least 1 keyword.';
    }
    if (selectedKeywords.length > MAX_KEYWORDS_PER_PROFILE) {
      return `You can keep at most ${MAX_KEYWORDS_PER_PROFILE} keywords.`;
    }
    if (!selectedIntentQueries.length) {
      return 'Please keep at least 1 intent query.';
    }
    if (selectedIntentQueries.length > MAX_INTENT_QUERIES_PER_PROFILE) {
      return `You can keep at most ${MAX_INTENT_QUERIES_PER_PROFILE} intent queries.`;
    }
    return '';
  };

  const canSelectMoreCandidates = (items, nextSelected, kind) => {
    if (!nextSelected) return true;
    return countSelectedCandidates(items) < getSelectionLimit(kind);
  };

  const isCandidateDisabled = (items, item, kind) => {
    if (!item || item._isDraftSlot || item._selected) return false;
    return countSelectedCandidates(items) >= getSelectionLimit(kind);
  };

  const buildSelectionTitle = (kind, suffix) => {
    const realKind = normalizeCandidateKind(kind);
    const currentItems =
      modalState && Array.isArray(realKind === 'intent' ? modalState.intent_queries : modalState.keywords)
        ? (realKind === 'intent' ? modalState.intent_queries : modalState.keywords)
        : [];
    const selectedCount = countSelectedCandidates(currentItems);
    return `${getKindLabel(realKind)}（${selectedCount}/${getSelectionLimit(realKind)}，${suffix}）`;
  };

  const sanitizeNoYear = (value) => {
    const base = normalizeText(value);
    if (!base) return '';
    let text = base
      .replace(/\((?:19|20)\d{2}(?:年)?\)/g, '')
      .replace(/（(?:19|20)\d{2}(?:年)?）/g, '')
      .replace(/(?:19|20)\d{2}(?:年)?/g, '')
      .replace(/[\s_-]{2,}/g, ' ')
      .trim();
    if (text) {
      text = text
        .replace(/\s+/g, ' ')
        .replace(/[_-]+/g, ' ')
        .trim();
    }
    return text;
  };

  const sanitizeAutoTag = (value) => {
    const base = normalizeText(value);
    if (!base) return '';
    let tag = base
      .replace(/\((?:19|20)\d{2}(?:年)?\)/g, '')
      .replace(/（(?:19|20)\d{2}(?:年)?）/g, '')
      .replace(/([\u4e00-\u9fffA-Za-z]+)\s*(?:19|20)\d{2}(?!\d)/g, '$1')
      .replace(/(?:19|20)\d{2}(?!\d)([\u4e00-\u9fffA-Za-z]+)/g, '$1')
      .replace(/[\s_-]*(?:19|20)\d{2}(?:年)[\s_-]*/g, '')
      .replace(/[\s_-]*(?:19|20)\d{2}[\s_-]*/g, '');
    tag = tag
      .replace(/\+/g, '-')
      .replace(/[\s_]+/g, '-')
      .replace(/[^A-Za-z-]+/g, '')
      .replace(/-+/g, '-')
      .replace(/-+$/g, '')
      .replace(/^-+/g, '')
      .trim();
    if (!/[A-Za-z]/.test(tag)) return '';
    if (tag.length <= MAX_PROFILE_TAG_CHARS) return tag;
    const words = tag.split('-').filter(Boolean);
    if (words.length > 1) {
      const acronym = words
        .map((word) => word[0] || '')
        .join('')
        .replace(/[^A-Za-z]/g, '');
      if (acronym.length >= 2 && acronym.length <= MAX_PROFILE_TAG_CHARS) {
        const allCapsSource = words.every((word) => word === word.toUpperCase());
        return allCapsSource ? acronym.toUpperCase() : acronym.toLowerCase();
      }
    }
    return tag.slice(0, MAX_PROFILE_TAG_CHARS).replace(/-+$/g, '');
  };
  const deriveTagFromCandidates = (candidates, fallbacks = []) => {
    const values = [];
    if (candidates && typeof candidates === 'object') {
      values.push(candidates.tag);
      const keywords = Array.isArray(candidates.keywords) ? candidates.keywords : [];
      keywords.forEach((item) => {
        if (typeof item === 'string') {
          values.push(item);
          return;
        }
        if (item && typeof item === 'object') {
          values.push(item.keyword, item.query);
        }
      });
      const intentQueries = Array.isArray(candidates.intent_queries)
        ? candidates.intent_queries
        : Array.isArray(candidates.intentQueries)
          ? candidates.intentQueries
          : [];
      intentQueries.forEach((item) => {
        if (typeof item === 'string') {
          values.push(item);
          return;
        }
        if (item && typeof item === 'object') {
          values.push(item.query);
        }
      });
    }
    values.push(...(Array.isArray(fallbacks) ? fallbacks : [fallbacks]));
    for (let idx = 0; idx < values.length; idx += 1) {
      const tag = sanitizeAutoTag(values[idx]);
      if (tag) return tag;
    }
    return '';
  };
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
  const isConferenceOnlyProfile = (profile) =>
    !!(
      profile &&
      (
        profile.temporary === true ||
        profile.conference_only === true ||
        normalizeText(profile.scope).toLowerCase() === 'conference'
      )
    );
  const canSelectProfileForRunMode = (profile) => {
    return !!profile;
  };
  const notifySelectionChange = () => {
    if (typeof selectionChangeHandler !== 'function') return;
    const selectedProfiles = (currentProfiles || []).filter((profile) =>
      selectedProfileKeys.has(getProfileKey(profile)),
    );
    selectionChangeHandler(selectedProfiles.map((profile) => ({
      tag: normalizeText(profile && profile.tag),
      description: normalizeText(profile && profile.description),
      scope: normalizeText(profile && profile.scope),
      temporary: isConferenceOnlyProfile(profile),
    })));
  };
  const toggleProfileSelection = (profileId) => {
    const profile = findCurrentProfile(profileId);
    if (!profile || !canSelectProfileForRunMode(profile)) return;
    const key = getProfileKey(profile);
    if (!key) return;
    if (selectedProfileKeys.has(key)) {
      selectedProfileKeys.delete(key);
    } else {
      selectedProfileKeys.add(key);
    }
    renderMain();
    notifySelectionChange();
  };
  const setProfileSelection = (profileId, selected) => {
    const profile = findCurrentProfile(profileId);
    if (!profile || !canSelectProfileForRunMode(profile)) return;
    const key = getProfileKey(profile);
    if (!key) return;
    if (selected) {
      selectedProfileKeys.add(key);
    } else {
      selectedProfileKeys.delete(key);
    }
    renderMain();
    notifySelectionChange();
  };
  const selectProfilesForRun = (filterFn, selected = true) => {
    (currentProfiles || []).forEach((profile) => {
      if (!canSelectProfileForRunMode(profile)) return;
      if (typeof filterFn === 'function' && !filterFn(profile)) return;
      const key = getProfileKey(profile);
      if (!key) return;
      if (selected) {
        selectedProfileKeys.add(key);
      } else {
        selectedProfileKeys.delete(key);
      }
    });
    renderMain();
    notifySelectionChange();
  };
  const getProfilesForRun = () =>
    (currentProfiles || []).map((profile) => ({
      id: getProfileKey(profile),
      tag: normalizeText(profile && profile.tag),
      description: normalizeText(profile && profile.description),
      scope: normalizeText(profile && profile.scope),
      temporary: isConferenceOnlyProfile(profile),
      paused: !!(profile && profile.paused),
      selected: selectedProfileKeys.has(getProfileKey(profile)),
    })).filter((profile) => profile.id && profile.tag);

  const filterVisiblePaperSources = (values) => {
    const visible = new Set(VISIBLE_PAPER_SOURCES);
    return (Array.isArray(values) ? values : []).filter((value) => visible.has(normalizeText(value).toLowerCase()));
  };

  const normalizePaperSources = (values, options = {}) => {
    const fallbackToArxiv = options.fallbackToArxiv !== false;
    const fallbackToAll = options.fallbackToAll === true;
    const rawList = Array.isArray(values)
      ? values
      : (typeof values === 'string' && values ? [values] : []);
    const seen = new Set();
    const out = [];
    rawList.forEach((value) => {
      const key = normalizeText(value).toLowerCase();
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push(key);
    });
    const visibleOut = filterVisiblePaperSources(out);
    if (!visibleOut.length && fallbackToArxiv) {
      return ['arxiv'];
    }
    if (!visibleOut.length && fallbackToAll) {
      return getAvailablePaperSources();
    }
    return visibleOut;
  };

  const getAvailablePaperSources = () => {
    const cfg = window.SubscriptionsManager.getDraftConfig ? window.SubscriptionsManager.getDraftConfig() : {};
    const rawBackends = cfg && cfg.source_backends && typeof cfg.source_backends === 'object'
      ? cfg.source_backends
      : {};
    const seen = new Set();
    const out = [];
    const runtimeCandidates = [];
    if (window.DPR_RUNTIME_SOURCE_BACKENDS && typeof window.DPR_RUNTIME_SOURCE_BACKENDS === 'object') {
      runtimeCandidates.push(...Object.keys(window.DPR_RUNTIME_SOURCE_BACKENDS || {}));
    }
    ['arxiv', ...Object.keys(rawBackends || {}), ...runtimeCandidates].forEach((value) => {
      const key = normalizeText(value).toLowerCase();
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push(key);
    });
    const visibleOut = filterVisiblePaperSources(out);
    visibleOut.sort((a, b) => {
      const idxA = PAPER_SOURCE_ORDER.indexOf(a);
      const idxB = PAPER_SOURCE_ORDER.indexOf(b);
      const rankA = idxA >= 0 ? idxA : Number.MAX_SAFE_INTEGER;
      const rankB = idxB >= 0 ? idxB : Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      return a.localeCompare(b);
    });
    return visibleOut;
  };

  const getPaperSourceLabel = (source) => {
    const key = normalizeText(source).toLowerCase();
    if (key === 'all') return 'all';
    return PAPER_SOURCE_LABELS[key] || key || 'Unknown source';
  };

  const renderPaperSourceChoices = (selectedSources) => {
    const availableSources = getAvailablePaperSources();
    const selected = new Set(normalizePaperSources(selectedSources, { fallbackToArxiv: false }));
    const allChecked =
      availableSources.length > 0 &&
      availableSources.every((source) => selected.has(source));
    const allItem = `
      <label class="dpr-paper-source-item dpr-paper-source-item-all">
        <input
          type="checkbox"
          data-action="toggle-paper-source-all"
          ${allChecked ? 'checked' : ''}
        />
        <span>${escapeHtml(getPaperSourceLabel('all'))}</span>
      </label>
    `;
    const sourceItems = availableSources.map((source) => {
      const checked = selected.has(source) ? 'checked' : '';
      return `
        <label class="dpr-paper-source-item">
          <input type="checkbox" data-action="toggle-paper-source" data-source="${escapeHtml(source)}" ${checked} />
          <span>${escapeHtml(getPaperSourceLabel(source))}</span>
        </label>
      `;
    }).join('');
    return `${allItem}${sourceItems}`;
  };

  const renderProfileSourceChips = (selectedSources) => {
    const availableSources = getAvailablePaperSources();
    const normalized = normalizePaperSources(selectedSources, { fallbackToArxiv: false });
    const allSelected =
      normalized.length > 0 &&
      availableSources.length > 0 &&
      availableSources.every((source) => normalized.includes(source));
    const visibleSources = allSelected ? ['all'] : normalized;
    return visibleSources
      .map((source) => `<span class="dpr-entry-source-chip">${escapeHtml(getPaperSourceLabel(source))}</span>`)
      .join('');
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
          embedding_cache:
            item.embedding_cache && typeof item.embedding_cache === 'object'
              ? deepClone(item.embedding_cache)
              : undefined,
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
          const query = sanitizeNoYear(item);
          if (!query) return null;
          return {
            query,
            query_cn: '',
            enabled: true,
            source: 'generated',
          };
        }
        if (!item || typeof item !== 'object') return null;
        const query = sanitizeNoYear(item.query || item.text || item.keyword || item.expr || '');
        if (!query) return null;
        const queryCn = sanitizeNoYear(item.query_cn || item.query_zh || item.zh || item.note || '');
        return {
          query,
          query_cn: queryCn,
          enabled: item.enabled !== false,
          source: normalizeText(item.source || 'generated'),
          note: normalizeText(item.note || ''),
          embedding_cache:
            item.embedding_cache && typeof item.embedding_cache === 'object'
              ? deepClone(item.embedding_cache)
              : undefined,
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
    const t = sanitizeAutoTag(tag);
    if (!t) return null;
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

  const findCurrentProfile = (profileId) => (
    (currentProfiles || []).find((profile) => getProfileKey(profile) === getProfileKey(profileId))
  );

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
      throw new Error('The model response is not valid JSON');
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
        data.intent_tag ||
        data.profile_tag ||
        '',
    );
    const cleanedTag = sanitizeAutoTag(tag);
    const description = normalizeText(
      data.description ||
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
      'explainable',
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
    const trimWeakKeywordSuffix = (s) =>
      normalizeText(s)
        .replace(/\b(driven|based|related|guided|enhanced|oriented|focused|for|with)$/i, '')
        .replace(/\s+/g, ' ')
        .trim();
    const isWeakAcronymKeyword = (s) => /^[A-Za-z]{1,3}$/.test(normalizeText(s));
    const isLowQualityKeyword = (s) => {
      const text = normalizeText(s);
      if (!text) return true;
      if (isWeakAcronymKeyword(text)) return true;
      if (!/\s/.test(text) && genericModifierSet.has(text.toLowerCase())) return true;
      return /\b(driven|based|related|guided|enhanced|oriented|focused|for|with)$/i.test(text);
    };

    let keywords = rawKeywords
      .map((item, idx) => {
        if (!item) return null;
        const rawKeyword = trimWeakKeywordSuffix(
          typeof item === 'string' ? normalizeText(item) : normalizeText(item.keyword || item.text || item.expr || ''),
        );
        if (!isEnglishRetrievalText(rawKeyword)) return null;
        if (isLowQualityKeyword(rawKeyword)) return null;
        const keywordCn = normalizeText(
          typeof item === 'string'
            ? ''
            : normalizeText(item.keyword_cn || item.keyword_zh || item.zh || ''),
        );
        const rawQuery = normalizeText(
          typeof item === 'string' ? rawKeyword : normalizeText(item.query || item.rewrite || rawKeyword),
        );
        const queryCn = normalizeText(
          typeof item === 'string'
            ? ''
            : normalizeText(item.query_cn || item.query_zh || item.note || ''),
        );
        const query = isEnglishRetrievalText(rawQuery) && !isWeakAcronymKeyword(rawQuery) ? rawQuery : rawKeyword;
        return {
          keyword: rawKeyword,
          keyword_cn: keywordCn,
          query: query || rawKeyword,
          query_cn: queryCn || (containsCjk(rawQuery) ? rawQuery : ''),
        };
      })
      .filter(Boolean);

    // Keyword recall de-duplication:
    // If a core term already exists (e.g. symbolic regression), normalize "X symbolic regression" to "X";
    // but do not trim a complete concept like "explainable reinforcement learning" down to a single generic adjective.
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
          if (parts.length === 1) {
            return k;
          }
          return {
            ...k,
            keyword: prefixPlain,
          };
        }
        return k;
      })
      .filter(Boolean);

    // Normalize first, then de-duplicate
    const kwSeen = new Set();
    keywords = keywords.filter((k) => {
      const key = normalizePhrase(k.keyword || '');
      if (!key || kwSeen.has(key)) return false;
      kwSeen.add(key);
      return true;
    });

    const rawIntentQueries = normalizeIntentSource(data);
    const intentQueries = normalizeIntentQueryEntries(rawIntentQueries).filter((item) =>
      isEnglishRetrievalText(item && item.query) && !isWeakAcronymKeyword(item && item.query),
    );

    return {
      tag: cleanedTag,
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
      throw new Error('No usable LLM configuration detected. Please complete the key configuration first.');
    }
    if (!llm.apiKey) {
      throw new Error('No usable API key detected. Please fill in the Summary/Chat Token in the key configuration first.');
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

      const raw = normalizeText(llm.baseUrl);
      if (!raw) {
        return out;
      }
      expandEndpoint(raw);
      return out;
    };
    const endpoints = buildEndpoints();
    if (!endpoints.length) {
      throw new Error('The LLM configuration is missing baseUrl.');
    }

    const resolveJsonResponseMode = () => {
      const utils = window.DPRLLMConfigUtils || {};
      if (typeof utils.resolveJsonResponseMode === 'function') {
        return utils.resolveJsonResponseMode({
          baseUrl: llm.baseUrl,
          model: llm.model,
          preferSchema: false,
        });
      }
      return 'json_object';
    };
    const jsonResponseMode = resolveJsonResponseMode();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
	    const requestPayload = ({ useResponseFormat = true } = {}) => {
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
	      const utils = window.DPRLLMConfigUtils || {};
	      if (typeof utils.resolveMaxOutputTokens === 'function') {
	        const maxTokens = utils.resolveMaxOutputTokens({
	          baseUrl: llm.baseUrl,
	          model: llm.model,
	        });
	        if (maxTokens) {
	          payload.max_tokens = maxTokens;
	        }
	      }
	      if (useResponseFormat && jsonResponseMode === 'json_object') {
	        payload.response_format = { type: 'json_object' };
	      }
      return payload;
    };

    const textSafeFromError = (e) => {
      if (!e) return '';
      if (typeof e.message === 'string' && e.message) return e.message;
      return '';
    };

    const doFetch = async (
      endpoint,
      options = { useResponseFormat: true, includeTools: true },
    ) => {
      const headers = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${llm.apiKey}`,
      };
      return fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestPayload(options)),
        signal: controller.signal,
      });
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
          current = await doFetch(endpoint, {
            useResponseFormat: jsonResponseMode !== 'prompt_only',
          });
          if (current && !current.ok) {
            txt = await current.text().catch(() => '');
            if (current.status === 400 && /response[\s-]*format|json_object/i.test(txt)) {
              current = await doFetch(endpoint, {
                useResponseFormat: false,
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
            throw new Error('Generation timed out, please try again later.');
          }
          if (i < endpoints.length - 1) {
            // On network errors, try the next endpoint
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
        throw new Error(`Model service request failed: ${fetchError}`);
      }
      throw new Error(errorText || 'Model service request failed. Please check the network and key configuration.');
    }
    const data = await res.json();
    const content = extractLlmJsonText(data);
    const parsed = loadJsonLenient(content);
    const candidates = normalizeGenerated(parsed);
    if (!candidates.keywords.length) {
      throw new Error('The model did not return usable English candidates. Please adjust the description and retry.');
    }
    return candidates;
  };

  const applyCandidateToProfile = (tag, description, paperSources, candidates) => {
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
      const safeTag = sanitizeAutoTag(tag) || deriveTagFromCandidates(candidates) || 'topic';
      const profile = ensureProfile(profiles, safeTag, description);
      if (!profile) return next;
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
          embedding_cache:
            item.embedding_cache && typeof item.embedding_cache === 'object'
              ? deepClone(item.embedding_cache)
              : undefined,
        });
      });

      profile.description = normalizeText(profile.description || description || '');
      profile.paper_sources = normalizePaperSources(paperSources, { fallbackToArxiv: false });
      if (candidates && candidates.temporaryProfile) {
        profile.scope = 'conference';
        profile.temporary = true;
        profile.conference_only = true;
      }
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
          embedding_cache:
            item.embedding_cache && typeof item.embedding_cache === 'object'
              ? deepClone(item.embedding_cache)
              : undefined,
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

  const replaceProfileFromSelection = (profileId, tag, description, paperSources, candidates) => {
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

      profiles[idx] = {
        ...existedProfile,
        tag: sanitizeAutoTag(tag || existedProfile.tag || '') || deriveTagFromCandidates(candidates) || `profile-${idx + 1}`,
        description: normalizeText(description || existedProfile.description || ''),
        paper_sources: normalizePaperSources(paperSources, { fallbackToArxiv: false }),
        ...(candidates && candidates.temporaryProfile
          ? { scope: 'conference', temporary: true, conference_only: true }
          : {}),
        keywords:
          selectedKeywords.length > 0
            ? selectedKeywords
                .map((item, idx) => ({
                  keyword: normalizeText(item.keyword || item.text || item.expr || ''),
                  keyword_cn: normalizeText(item.keyword_cn || item.keyword_zh || item.zh || ''),
                  query: normalizeText(item.query || item.text || item.keyword || ''),
                  embedding_cache:
                    item.embedding_cache && typeof item.embedding_cache === 'object'
                      ? deepClone(item.embedding_cache)
                      : undefined,
                }))
                .filter((x) => x.keyword)
            : normalizeProfileKeywords(existedProfile),
        intent_queries: intentQueries
          .map((queryObj) => ({
            query: normalizeText(queryObj && queryObj.query),
            query_cn: normalizeText(queryObj.query_cn || queryObj.query_zh || queryObj.zh || ''),
            enabled: queryObj.enabled !== false,
            source: normalizeText(queryObj.source || 'manual'),
            note: normalizeText(queryObj.note || ''),
            embedding_cache:
              queryObj.embedding_cache && typeof queryObj.embedding_cache === 'object'
                ? deepClone(queryObj.embedding_cache)
                : undefined,
          }))
          .filter((x) => x.query),
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
      keywords: clampSelectionsByLimit(
        (candidates.keywords || []).map((x) => ({ ...x, _selected: selected })),
        'keyword',
      ),
      intent_queries: clampSelectionsByLimit(
        (candidates.intent_queries || []).map((x) => ({ ...x, _selected: selected })),
        'intent',
      ),
    };
  };

  const getEditableMeta = (kind) => {
    if (kind === 'intent') {
      return {
        primary: 'query',
        secondary: 'query_cn',
        primaryPlaceholder: '(English intent)',
        secondaryPlaceholder: '(optional secondary label)',
      };
    }
    return {
      primary: 'keyword',
      secondary: 'keyword_cn',
      primaryPlaceholder: '(English keyword)',
      secondaryPlaceholder: '(optional secondary label)',
    };
  };

  const createDraftSlot = (kind) => {
    const meta = getEditableMeta(kind);
    const item = {
      _isDraftSlot: true,
      _selected: true,
      source: kind === 'intent' ? 'generated' : 'manual',
      enabled: true,
    };
    item[meta.primary] = '';
    item[meta.secondary] = '';
    return item;
  };

  const isDraftSlot = (item) => item && item._isDraftSlot;

  const hasRealCandidates = (items) =>
    (Array.isArray(items) ? items : []).some((item) => item && !isDraftSlot(item));

  const ensureDraftSlot = (items, kind) => {
    const list = Array.isArray(items) ? items : [];
    const next = list.filter((item) => item && !isDraftSlot(item));
    return [createDraftSlot(kind)].concat(next);
  };

  const getCandidatesByKind = (state, kind) => {
    if (!state) return [];
    return kind === 'intent' ? state.intent_queries : state.keywords;
  };

  const getCandidatesByKindForState = (state, kind) => {
    return Array.isArray(getCandidatesByKind(state, kind)) ? getCandidatesByKind(state, kind) : [];
  };

  const getSelectedItemsForSave = (items) => {
    return (Array.isArray(items) ? items : [])
      .filter((item) => item && !isDraftSlot(item) && item._selected)
      .map((item) => item);
  };

  const normalizeCandidateKind = (kind) => (kind === 'intent' ? 'intent' : 'keyword');

  const buildDraftItemFromSlot = (kind, slot) => {
    const meta = getEditableMeta(kind);
    if (!slot) return null;
    const primaryValue = normalizeText(slot[meta.primary]);
    const secondaryValue = normalizeText(slot[meta.secondary]);
    if (!primaryValue && !secondaryValue) return null;
    const item = {
      ...slot,
      [meta.primary]: primaryValue,
      [meta.secondary]: secondaryValue,
      _selected: true,
      _isDraftSlot: false,
    };
    if (kind !== 'intent' && !normalizeText(item.query)) {
      item.query = primaryValue;
    }
    return item;
  };

  const appendDraftSlotItem = (kind, state = modalState) => {
    const realKind = normalizeCandidateKind(kind);
    const list = getCandidatesByKindForState(state, realKind);
    const meta = getEditableMeta(realKind);
    if (!Array.isArray(list) || !list.length) return false;

    const slot = list[0];
    if (!slot || !isDraftSlot(slot)) return false;

    const primaryValue = normalizeText(slot[meta.primary]);
    if (!primaryValue) {
      setMessage(`Please fill in ${meta.primaryPlaceholder || 'the English text'} first.`, '#c00');
      return false;
    }

    const key = primaryValue.toLowerCase();
    const existedIndex = list.findIndex(
      (item, idx) => idx > 0 && !isDraftSlot(item) && normalizeText(item[meta.primary]).toLowerCase() === key,
    );
    if (existedIndex >= 0) {
      list[existedIndex]._selected = true;
      list[0] = createDraftSlot(realKind);
      if (realKind === 'intent') {
        state.intent_queries = list;
      } else {
        state.keywords = list;
      }
      return true;
    }

    const created = buildDraftItemFromSlot(realKind, slot);
    if (!created) return false;
    if (!canSelectMoreCandidates(list, true, realKind)) {
      setMessage(`You can select at most ${getSelectionLimit(realKind)} ${getKindLabel(realKind)} items.`, '#c00');
      return false;
    }
    const next = list.slice();
    next[0] = createDraftSlot(realKind);
    next.splice(1, 0, created);
    if (realKind === 'intent') {
      state.intent_queries = next;
    } else {
      state.keywords = next;
    }
    return true;
  };

  const applyDraftSlotValue = (kind, index, field, value, state = modalState) => {
    const realKind = normalizeCandidateKind(kind);
    const candidates = getCandidatesByKindForState(state, realKind);
    const meta = getEditableMeta(realKind);
    if (!Array.isArray(candidates) || index < 0 || index >= candidates.length) return;
    if (field !== meta.primary && field !== meta.secondary) return;
    const item = candidates[index];
    if (!item) return;
    const prevValue = normalizeText(item[field]);
    item[field] = normalizeText(value);
    if (realKind !== 'intent' && field === meta.primary && !normalizeText(item.query)) {
      item.query = normalizeText(value);
    }
    if (realKind === 'intent' && field === meta.primary && prevValue !== normalizeText(value)) {
      delete item.embedding_cache;
    }
    candidates[index] = item;
  };

  const startInlineEditField = (target, state = modalState) => {
    if (!target || !state || !target.matches('.dpr-inline-field')) return;

    const kind = normalizeCandidateKind(target.getAttribute('data-kind') || '');
    const index = Number(target.getAttribute('data-index'));
    const field = target.getAttribute('data-field') || '';
    const candidates = getCandidatesByKindForState(state, kind);
    if (!Array.isArray(candidates) || index < 0 || index >= candidates.length) return;
    const item = candidates[index];
    if (!item) return;

    const meta = getEditableMeta(kind);
    if (field !== meta.primary && field !== meta.secondary) return;

    const current = normalizeText(item[field] || '');
    const editor = document.createElement('input');
    editor.type = 'text';
    editor.className = 'dpr-inline-editor';
    editor.value = current;

    let finished = false;
    const end = (save) => {
      if (finished) return;
      finished = true;
      if (save) {
        applyDraftSlotValue(kind, index, field, editor.value, state);
      }
      if (state.type === 'add') {
        renderAddModal();
      } else if (state.type === 'chat') {
        renderChatModal();
      }
    };

    editor.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        end(true);
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        end(false);
      }
      e.stopPropagation();
    });
    editor.addEventListener('blur', () => {
      end(true);
    });
    target.classList.add('dpr-inline-field-editing');
    target.innerHTML = '';
    target.appendChild(editor);
    editor.focus();
    editor.select();
  };

  const escapeValueForRender = (value, fallback) => {
    const normalized = normalizeText(value);
    return normalized || fallback || '';
  };

  const renderEditableField = (kind, idx, field, value, placeholder, isPrimary = false) => {
    const text = normalizeText(value);
    const classes = ['dpr-inline-field'];
    if (!text) classes.push('is-empty');
    if (isPrimary) classes.push('is-primary');
    return `
      <div
        class="${classes.join(' ')}"
        data-action="edit-inline-field"
        data-kind="${escapeHtml(kind)}"
        data-index="${idx}"
        data-field="${escapeHtml(field)}"
      >
        <span class="dpr-inline-text">${escapeHtml(escapeValueForRender(value, placeholder))}</span>
        <span class="dpr-inline-pencil" aria-hidden="true">✎</span>
      </div>
    `;
  };

  const renderChoiceField = (value, placeholder, isPrimary = false) => {
    const text = normalizeText(value);
    const classes = ['dpr-inline-field', 'dpr-choice-field'];
    if (!text) classes.push('is-empty');
    if (isPrimary) classes.push('is-primary');
    return `
      <span class="${classes.join(' ')}">
        <span class="dpr-inline-text">${escapeHtml(escapeValueForRender(value, placeholder))}</span>
      </span>
    `;
  };

  const getCandidateItem = (kind, index, state = modalState) => {
    const realKind = normalizeCandidateKind(kind);
    const list = getCandidatesByKindForState(state, realKind);
    if (!Array.isArray(list) || index < 0 || index >= list.length) {
      return { realKind, list: null, item: null };
    }
    return { realKind, list, item: list[index] || null };
  };

  const getCandidateEditDraft = (item, primaryField, secondaryField, fallbackDesc) => {
    const draft = item && item._editDraft && typeof item._editDraft === 'object'
      ? item._editDraft
      : {};
    return {
      primary: normalizeText(draft.primary ?? item?.[primaryField] ?? ''),
      secondary: normalizeText(draft.secondary ?? item?.[secondaryField] ?? fallbackDesc ?? ''),
    };
  };

  const startCandidateEdit = (kind, index, fields) => {
    const { item } = getCandidateItem(kind, index);
    if (!item || isDraftSlot(item)) return;
    const primaryField = fields.primary || '';
    const secondaryField = fields.secondary || '';
    item._editing = true;
    item._editDraft = {
      primary: normalizeText(item[primaryField] || ''),
      secondary: normalizeText(item[secondaryField] || item[fields.fallback] || ''),
    };
    renderChatModal();
  };

  const cancelCandidateEdit = (kind, index) => {
    const { item } = getCandidateItem(kind, index);
    if (!item) return;
    delete item._editing;
    delete item._editDraft;
    renderChatModal();
  };

  const saveCandidateEdit = (kind, index, fields) => {
    const { item, realKind } = getCandidateItem(kind, index);
    if (!item) return;
    const primaryField = fields.primary || '';
    const secondaryField = fields.secondary || '';
    const draft = getCandidateEditDraft(item, primaryField, secondaryField, item[fields.fallback]);
    applyDraftSlotValue(realKind, index, primaryField, draft.primary, modalState);
    applyDraftSlotValue(realKind, index, secondaryField, draft.secondary, modalState);
    delete item._editing;
    delete item._editDraft;
    renderChatModal();
  };

  const updateCandidateEditDraft = (target) => {
    if (!target || !modalState) return;
    const kind = target.getAttribute('data-kind') || '';
    const index = Number(target.getAttribute('data-index'));
    const draftField = target.getAttribute('data-candidate-edit-field') || '';
    const { item } = getCandidateItem(kind, index);
    if (!item || !item._editing) return;
    if (!item._editDraft || typeof item._editDraft !== 'object') {
      item._editDraft = {};
    }
    if (draftField === 'primary' || draftField === 'secondary') {
      item._editDraft[draftField] = target.value;
    }
  };

  const renderCandidateEditCard = (kind, idx, item, fields, selected, disabled) => {
    const primaryField = fields.primary || '';
    const secondaryField = fields.secondary || '';
    const draft = getCandidateEditDraft(item, primaryField, secondaryField, item[fields.fallback]);
    return `
      <div class="dpr-cloud-item dpr-cloud-item-editing ${selected ? 'selected' : ''} ${disabled ? 'dpr-choice-disabled' : ''}" data-kind="${kind}" data-index="${idx}" data-disabled="${disabled ? '1' : '0'}" aria-disabled="${disabled ? 'true' : 'false'}">
        <span class="dpr-cloud-item-body dpr-cloud-edit-body">
          <input
            type="text"
            class="dpr-candidate-edit-input"
            data-kind="${escapeHtml(kind)}"
            data-index="${idx}"
            data-candidate-edit-field="primary"
            value="${escapeHtml(draft.primary)}"
            placeholder="${escapeHtml(fields.primaryPlaceholder || 'English retrieval text')}"
          />
          <input
            type="text"
            class="dpr-candidate-edit-input"
            data-kind="${escapeHtml(kind)}"
            data-index="${idx}"
            data-candidate-edit-field="secondary"
            value="${escapeHtml(draft.secondary)}"
            placeholder="${escapeHtml(fields.secondaryPlaceholder || 'Optional note')}"
          />
        </span>
        <span class="dpr-cloud-edit-actions">
          <button type="button" class="arxiv-tool-btn dpr-cloud-edit-save" data-action="save-candidate-edit" data-kind="${escapeHtml(kind)}" data-index="${idx}" data-primary-field="${escapeHtml(primaryField)}" data-secondary-field="${escapeHtml(secondaryField)}" data-fallback-field="${escapeHtml(fields.fallback || '')}" title="Save changes">✓</button>
          <button type="button" class="arxiv-tool-btn dpr-cloud-edit-cancel" data-action="cancel-candidate-edit" data-kind="${escapeHtml(kind)}" data-index="${idx}" title="Cancel changes">×</button>
        </span>
      </div>
    `;
  };

  const renderDraftInputField = (kind, idx, field, value, placeholder) => {
    return `
      <input
        type="text"
        class="dpr-inline-draft-input"
        data-draft-input="1"
        data-kind="${escapeHtml(kind)}"
        data-index="${idx}"
        data-field="${escapeHtml(field)}"
        value="${escapeHtml(normalizeText(value || ''))}"
        placeholder="${escapeHtml(placeholder || '')}"
      />
    `;
  };

  const renderEditableSlot = (kind, idx, item, isChat) => {
    const meta = getEditableMeta(kind);
    if (isChat) {
      return `
        <div class="dpr-cloud-item dpr-inline-slot dpr-inline-slot-chat">
        <div class="dpr-inline-slot-fields">
            ${renderDraftInputField(kind, idx, meta.primary, item[meta.primary], meta.primaryPlaceholder)}
            ${renderDraftInputField(
              kind,
              idx,
              meta.secondary,
              item[meta.secondary],
              meta.secondaryPlaceholder,
            )}
          </div>
        <button
          type="button"
          class="arxiv-tool-btn dpr-inline-slot-add dpr-inline-slot-add-side"
          data-action="append-draft-slot"
          data-kind="${kind}"
          data-index="${idx}"
          title="Add"
        >
          +
        </button>
      </div>
      `;
    }
    const wrapperClass = isChat ? 'dpr-cloud-item dpr-inline-slot' : 'dpr-pick-card dpr-inline-slot';
    return `
      <div class="${wrapperClass}">
        <div class="dpr-cloud-item-body">
          ${renderEditableField(kind, idx, meta.primary, item[meta.primary], meta.primaryPlaceholder, true)}
          ${renderEditableField(
            kind,
            idx,
            meta.secondary,
            item[meta.secondary],
            meta.secondaryPlaceholder,
            false,
          )}
        </div>
        <button
          type="button"
          class="arxiv-tool-btn dpr-inline-slot-add"
          data-action="append-draft-slot"
          data-kind="${kind}"
          data-index="${idx}"
          title="Add"
        >
          +
        </button>
      </div>
    `;
  };

  const renderPickCards = (items, kind) => {
    const realKind = normalizeCandidateKind(kind);
    const meta = getEditableMeta(realKind);
    return (items || [])
      .map((item, idx) => {
        if (isDraftSlot(item)) {
          return renderEditableSlot(realKind, idx, item, false);
        }
        const action = realKind === 'intent' ? 'toggle-intent-query-card' : 'toggle-kw-card';
        const selected = !!item._selected;
        const disabled = isCandidateDisabled(items, item, realKind);
        return `
          <div
            class="dpr-pick-card ${selected ? 'selected' : ''} ${disabled ? 'dpr-choice-disabled' : ''}"
            data-action="${action}"
            data-kind="${realKind}"
            data-index="${idx}"
            data-disabled="${disabled ? '1' : '0'}"
            aria-disabled="${disabled ? 'true' : 'false'}"
          >
            ${renderEditableField(
              realKind,
              idx,
              meta.primary,
              item[meta.primary],
              meta.primaryPlaceholder,
              true,
            )}
            ${renderEditableField(
              realKind,
              idx,
              meta.secondary,
              item[meta.secondary],
              meta.secondaryPlaceholder,
            )}
          </div>
        `;
      })
      .join('');
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

    const keptExisting = [];
    const seen = new Set();

    existing.forEach((item) => {
      const key = normalizeKey(item, keyField);
      if (!key || seen.has(key) || !item || isDraftSlot(item)) return;
      const incomingItem = incomingMap.get(key);
      keptExisting.push({
        ...item,
        ...(incomingItem || {}),
        _selected: item._selected !== false,
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

    return keptExisting.concat(nextIncoming);
  };

  const toProfileSelectableCandidates = (profile) => {
    const rawKeywords = normalizeKeywordEntries(profile && profile.keywords);
    const keywords = rawKeywords.map((k) => ({
      keyword: normalizeText(k.keyword || ''),
      query: normalizeText(k.query || k.keyword || ''),
      keyword_cn: normalizeText(k.keyword_cn || ''),
      embedding_cache:
        k.embedding_cache && typeof k.embedding_cache === 'object'
          ? deepClone(k.embedding_cache)
          : undefined,
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
    const realKind = normalizeCandidateKind(kind);
    return (items || [])
      .map((item, idx) => {
        if (isDraftSlot(item)) {
          return renderEditableSlot(realKind, idx, item, true);
        }
        const text = normalizeText(item[textField] || '');
        const desc = normalizeText(
          item[descField] || item[descFallbackField] || defaultDesc || '',
        );
        const selected = !!item._selected;
        const checked = selected ? 'checked' : '';
        const disabled = isCandidateDisabled(items, item, realKind);
        const fieldMeta = {
          primary: textField,
          secondary: descField,
          fallback: descFallbackField,
          primaryPlaceholder: options.defaultPrimaryPlaceholder || 'English retrieval text',
          secondaryPlaceholder: defaultDesc || 'Optional note',
        };
        if (item._editing) {
          return renderCandidateEditCard(realKind, idx, item, fieldMeta, selected, disabled);
        }
        return `
        <div class="dpr-cloud-item ${selected ? 'selected' : ''} ${disabled ? 'dpr-choice-disabled' : ''}" data-action="toggle-chat-choice-card" data-kind="${realKind}" data-index="${idx}" data-disabled="${disabled ? '1' : '0'}" aria-disabled="${disabled ? 'true' : 'false'}">
          <input
            type="checkbox"
            data-action="toggle-chat-choice"
            data-kind="${realKind}"
            data-index="${idx}"
            ${checked}
            ${disabled ? 'disabled' : ''}
          />
          <span class="dpr-cloud-item-body">
            ${renderChoiceField(text, options.defaultPrimaryPlaceholder || '(English)', true)}
            ${renderChoiceField(desc || item[descFallbackField] || item.source || '', defaultDesc || '(no note)', false)}
          </span>
          <button
            type="button"
            class="arxiv-tool-btn dpr-cloud-edit-trigger"
            data-action="edit-candidate-choice"
            data-kind="${realKind}"
            data-index="${idx}"
            data-primary-field="${escapeHtml(textField)}"
            data-secondary-field="${escapeHtml(descField)}"
            data-fallback-field="${escapeHtml(descFallbackField)}"
            title="Edit the English text and the note"
          >✎</button>
        </div>
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

  const isChatAppendRound = (state = modalState) =>
    Array.isArray(state && state.requestHistory) && state.requestHistory.length > 0;

  const getChatActionMeta = (state = modalState) =>
    isChatAppendRound(state)
      ? { label: 'Generate more', className: 'dpr-chat-send-btn--append' }
      : { label: 'Generate candidates', className: 'dpr-chat-send-btn--initial' };

  const setSendBtnLoading = (loading) => {
    const btn = modalPanel?.querySelector('[data-action="chat-send"]');
    if (!btn) return;
    const meta = getChatActionMeta();
    if (loading) {
      btn.disabled = true;
      btn.classList.add('dpr-btn-loading');
      const label = btn.querySelector('.dpr-chat-send-label');
      if (label) label.textContent = 'Generating';
      return;
    }
    btn.disabled = false;
    btn.classList.remove('dpr-btn-loading');
    const label = btn.querySelector('.dpr-chat-send-label');
    if (label) label.textContent = meta.label;
  };

  const toggleChatChoice = (kind, index, nextSelected = null) => {
    if (!modalState || modalState.type !== 'chat') return;
    const realKind = normalizeCandidateKind(kind);
    const list = realKind === 'intent' ? modalState.intent_queries : modalState.keywords;
    if (
      !Array.isArray(list) ||
      index < 0 ||
      index >= list.length ||
      isDraftSlot(list[index]) ||
      list[index]._editing
    ) {
      return;
    }
    const selected = typeof nextSelected === 'boolean' ? nextSelected : !list[index]._selected;
    if (!canSelectMoreCandidates(list, selected, realKind)) {
      setMessage(`You can select at most ${getSelectionLimit(realKind)} ${getKindLabel(realKind)} items.`, '#c00');
      return;
    }
    list[index]._selected = selected;
    renderChatModal();
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
      displayListEl.innerHTML = '<div class="dpr-entry-empty">No entries yet. Click Add to open the dialogue and generate some.</div>';
      notifySelectionChange();
      return;
    }

    displayListEl.innerHTML = currentProfiles
      .map((p) => {
        const isPaused = !!p.paused;
        const isTemporary = isConferenceOnlyProfile(p);
        const selectable = canSelectProfileForRunMode(p);
        const selected = selectedProfileKeys.has(getProfileKey(p));
        const pauseLabel = isPaused ? 'Enable daily' : 'Pause daily';
        const pauseBtnClass = isPaused ? 'dpr-entry-resume-btn' : 'dpr-entry-pause-btn';
        const profileId = escapeHtml(getProfileKey(p) || '');
        const pauseButton = isTemporary
          ? ''
          : `<button class="arxiv-tool-btn ${pauseBtnClass}" data-action="pause-profile" data-profile-id="${profileId}">${pauseLabel}</button>`;
        const cardClass = [
          'dpr-entry-card',
          isPaused ? 'dpr-entry-card--paused' : '',
          isTemporary ? 'dpr-entry-card--temporary' : '',
          'dpr-entry-card--selection-mode',
          selectable ? 'dpr-entry-card--selectable' : '',
          selected ? 'is-selected' : '',
          !selectable ? 'dpr-entry-card--selection-disabled' : '',
        ].filter(Boolean).join(' ');
        const isDailyEnabled = !isTemporary && !isPaused;
        const dailyBadge = isDailyEnabled
          ? '<span class="dpr-entry-daily-badge dpr-entry-daily-badge--active">Daily</span>'
          : '<span class="dpr-entry-daily-badge dpr-entry-daily-badge--off">Daily paused</span>';
        const selectionControl = `<span class="dpr-entry-select-dot" aria-hidden="true">${selected ? '✓' : ''}</span>`;
        return `
          <div class="${cardClass}" data-profile-id="${profileId}">
            <div class="dpr-entry-top">
              <div class="dpr-entry-headline">
                ${selectionControl}
                <span class="dpr-entry-title">${escapeHtml(p.tag || '')}</span>
                ${dailyBadge}
                <span class="dpr-entry-desc-inline">${escapeHtml(p.description || '(no description)')}</span>
                <span class="dpr-entry-source-inline">${renderProfileSourceChips(p.paper_sources)}</span>
              </div>
              <div class="dpr-entry-actions">
                ${pauseButton}
                <button class="arxiv-tool-btn dpr-entry-edit-btn" data-action="edit-profile" data-profile-id="${profileId}">Edit</button>
                <button class="arxiv-tool-btn dpr-entry-delete-btn" data-action="delete-profile" data-profile-id="${profileId}">Delete</button>
              </div>
            </div>
          </div>
        `;
      })
      .join('');
    notifySelectionChange();
  };

  const openAddModal = (tag, description, candidates) => {
    const normalizedCandidates = parseCandidatesForState(candidates);
    const suggestedTag = deriveTagFromCandidates(candidates, [tag]) || 'topic';
    const suggestedDesc = normalizeText(candidates && candidates.description) || normalizeText(description);
    modalState = {
      type: 'add',
      tag: suggestedTag,
      description: suggestedDesc,
      keywords: ensureDraftSlot(normalizedCandidates.keywords, 'keyword'),
      intent_queries: ensureDraftSlot((normalizedCandidates.intent_queries || []), 'intent'),
      customKeyword: '',
      customKeywordLogic: '',
      customQuery: '',
      paper_sources: normalizePaperSources(candidates && candidates.paper_sources, { fallbackToAll: true }),
    };
    modalState.keywords = clampSelectionsByLimit(modalState.keywords, 'keyword');
    modalState.intent_queries = clampSelectionsByLimit(modalState.intent_queries, 'intent');
    renderAddModal();
    openModal();
  };

  const openChatModal = (options = {}) => {
    const normalizedCandidates = Array.isArray(options.keywords) ? options.keywords : [];
    const normalizedIntentQueries = Array.isArray(options.intent_queries) ? options.intent_queries : [];
    modalState = {
      type: 'chat',
      editProfileId: options.editProfileId || '',
      keywords: ensureDraftSlot(
        normalizedCandidates.map((item) => ({ ...item, _selected: item._selected !== false })),
        'keyword',
      ),
      intent_queries: ensureDraftSlot(
        normalizedIntentQueries.map((item) => ({
          ...item,
          _selected: item._selected !== false,
        })),
        'intent',
      ),
      requestHistory: [],
      inputTag: sanitizeAutoTag(options.tag || ''),
      inputDesc: normalizeText(options.description || ''),
      temporaryProfile: !!options.temporaryProfile,
      paper_sources: normalizePaperSources(options.paper_sources, { fallbackToAll: true }),
      pending: false,
      chatStatus: '',
    };
    modalState.keywords = clampSelectionsByLimit(modalState.keywords, 'keyword');
    modalState.intent_queries = clampSelectionsByLimit(modalState.intent_queries, 'intent');
    renderChatModal();
    openModal();
  };

  const renderAddModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'add') return;
    const kwHtml = renderPickCards(modalState.keywords || [], 'keyword');
    const intentHtml = renderPickCards(modalState.intent_queries || [], 'intent');
    const hasKeywords = (modalState.keywords || []).length > 0;
    const hasIntentQueries = (modalState.intent_queries || []).length > 0;
    const keywordBlock =
      `<div class="dpr-combo-block">
        <div class="dpr-modal-group-title">${buildSelectionTitle('keyword', 'used for recall')}</div>
        <div class="dpr-pick-grid">${kwHtml || '<div style="color:#999;">No keyword candidates</div>'}</div>
      </div>`;
    const intentBlock =
      `<div class="dpr-combo-block">
        <div class="dpr-modal-group-title">${buildSelectionTitle('intent', 'used for intent recall and final scoring')}</div>
        <div class="dpr-pick-grid">${intentHtml || '<div style="color:#999;">No intent query candidates</div>'}</div>
      </div>`;
    const divider = `<div class="dpr-modal-divider"></div>`;
    const candidateBlocks = `${hasKeywords ? keywordBlock : ''}${hasKeywords && hasIntentQueries ? divider : ''}${
      hasIntentQueries ? intentBlock : ''
    }`;
    const sourceChoices = renderPaperSourceChoices(modalState.paper_sources || []);

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">${modalState && modalState.editProfileId ? 'Edit entry' : 'Add entry candidates'}</div>
        <button class="arxiv-tool-btn" data-action="close">Close</button>
      </div>
      <div class="dpr-modal-group-title">
        Enter your retrieval idea below first
      </div>
      <div class="dpr-help-examples">
        <div class="dpr-help-example">ex: reinforcement learning symbolic regression</div>
        <div class="dpr-help-example">ex: please help me find papers related to reinforcement learning and symbolic regression</div>
        <div class="dpr-help-example">ex: please help me find papers on explainable reinforcement-learning-driven symbolic regression for equation discovery</div>
      </div>
      <div class="dpr-modal-list dpr-combo-list">${candidateBlocks || '<div class="dpr-cloud-empty"></div>'}</div>
      <div class="dpr-modal-actions-inline dpr-modal-add-inline">
        <input id="dpr-add-kw-text" type="text" placeholder="Manually add a keyword (recall term)" value="${escapeHtml(modalState.customKeyword || '')}" />
        <input id="dpr-add-kw-query" type="text" placeholder="Corresponding semantic query rewrite" value="${escapeHtml(modalState.customQuery || '')}" />
        <input id="dpr-add-kw-logic" type="text" placeholder="Optional secondary label" value="${escapeHtml(modalState.customKeywordLogic || '')}" />
        <button class="arxiv-tool-btn" data-action="add-custom-kw">Add to candidates</button>
      </div>
      <div class="dpr-modal-actions dpr-modal-add-footer">
        <label class="dpr-modal-field">
          <span class="dpr-modal-field-label">Tag</span>
          <input id="dpr-add-profile-tag" type="text" value="${escapeHtml(modalState.tag || '')}" placeholder="Enter a tag" />
        </label>
        <label class="dpr-modal-field">
          <span class="dpr-modal-field-label">Description</span>
          <input id="dpr-add-profile-desc" type="text" value="${escapeHtml(modalState.description || '')}" placeholder="Enter a description" />
        </label>
        <div class="dpr-modal-field dpr-modal-field-sources">
          <span class="dpr-modal-field-label">Paper source</span>
          <div class="dpr-paper-source-row">${sourceChoices}</div>
        </div>
        <button class="arxiv-tool-btn" data-action="apply-add" style="background:#2e7d32;color:#fff;">Save query</button>
      </div>
    `;
  };

  const applyAddModal = () => {
    if (!modalState || modalState.type !== 'add') return;
    const rawNextTag = normalizeText(document.getElementById('dpr-add-profile-tag')?.value || '');
    const nextTag = sanitizeAutoTag(rawNextTag) || deriveTagFromCandidates(modalState) || '';
    const nextDesc = normalizeText(document.getElementById('dpr-add-profile-desc')?.value || '');

    if (!nextTag || !nextDesc) {
      setMessage('The tag must be English, an English abbreviation, or an English hyphenated phrase, and the description cannot be empty.', '#c00');
      return;
    }

    modalState.tag = nextTag;
    modalState.description = nextDesc;
    const nextPaperSources = normalizePaperSources(modalState.paper_sources, { fallbackToArxiv: false });
    if (!nextPaperSources.length) {
      setMessage('Please select at least 1 paper source.', '#c00');
      return;
    }

    const selectedKeywords = getSelectedItemsForSave(modalState.keywords || []);
    const selectedIntentQueries = getSelectedItemsForSave(modalState.intent_queries || []);
    const validationError = validateProfileSelection(selectedKeywords, selectedIntentQueries);
    if (validationError) {
      setMessage(validationError, '#c00');
      return;
    }
    const isEditMode = !!(modalState && modalState.editProfileId);
    const ok = isEditMode
      ? replaceProfileFromSelection(
          modalState.editProfileId,
          modalState.tag,
          modalState.description,
          nextPaperSources,
          {
            ...modalState,
            keywords: selectedKeywords,
            intent_queries: selectedIntentQueries,
          },
        )
      : applyCandidateToProfile(modalState.tag, modalState.description, nextPaperSources, {
          ...modalState,
          keywords: selectedKeywords,
          intent_queries: selectedIntentQueries,
        });

    if (!ok) {
      setMessage('Please select at least 1 keyword and 1 intent query.', '#c00');
      return;
    }

    if (typeof reloadAll === 'function') reloadAll();
    setMessage(isEditMode ? 'Entry changes applied. Please click Save.' : 'New entry applied. Please click Save.', '#666');
    closeModal();
  };

  const renderChatModal = () => {
    if (!modalPanel || !modalState || modalState.type !== 'chat') return;

    const kwHtml = renderCloudCards(modalState.keywords || [], 'kw', {
      textField: 'keyword',
      descField: 'keyword_cn',
      defaultDesc: '(optional secondary label to be filled in)',
    });
    const intentHtml = renderCloudCards(modalState.intent_queries || [], 'intent', {
      textField: 'query',
      descField: 'query_cn',
      descFallbackField: 'note',
      defaultDesc: '(optional secondary label to be filled in)',
    });
    const hasKeywordSection = Array.isArray(modalState.keywords) && modalState.keywords.length > 0;
    const hasIntentSection = Array.isArray(modalState.intent_queries) && modalState.intent_queries.length > 0;
    const hasKeywords = hasKeywordSection && modalState.keywords.some((item) => !isDraftSlot(item));
    const hasIntentQueries =
      hasIntentSection && modalState.intent_queries.some((item) => !isDraftSlot(item));
    const hasCandidates = hasKeywords || hasIntentQueries;
    const sourceChoices = renderPaperSourceChoices(modalState.paper_sources || []);
    const actionMeta = getChatActionMeta(modalState);
    const kwSection = hasKeywordSection
      ? `<div class="dpr-chat-result-block">
           <div class="dpr-modal-group-title">${buildSelectionTitle('keyword', 'used for recall')}</div>
           <div class="dpr-chat-slot-area ${hasKeywords ? 'has-candidates' : 'draft-only'}">
             <div class="dpr-chat-slot-scroll">
               <div class="dpr-cloud-grid dpr-cloud-grid-keywords">${kwHtml}</div>
             </div>
           </div>
         </div>`
      : '';
    const intentSection = hasIntentSection
      ? `<div class="dpr-chat-result-block">
           <div class="dpr-modal-group-title">${buildSelectionTitle('intent', 'used for intent recall and final scoring')}</div>
           <div class="dpr-chat-slot-area ${hasIntentQueries ? 'has-candidates' : 'draft-only'}">
             <div class="dpr-chat-slot-scroll">
               <div class="dpr-cloud-grid dpr-cloud-grid-intent">${intentHtml}</div>
             </div>
           </div>
         </div>`
      : '';
    const mixedHtml = `${kwSection}${hasKeywords && hasIntentQueries ? '<div class="dpr-chat-divider"></div>' : ''}${intentSection}`;
    const emptyBlock = '<div class="dpr-cloud-empty"></div>';

    modalPanel.innerHTML = `
      <div class="dpr-modal-head">
        <div class="dpr-modal-title">
          ${modalState && modalState.editProfileId ? 'Edit query' : (modalState.temporaryProfile ? 'Add conference-only query' : 'Add query')}
          ${modalState.temporaryProfile ? '<span class="dpr-entry-temp-badge">Conference only</span>' : ''}
        </div>
        <button class="arxiv-tool-btn" data-action="close">Close</button>
      </div>
      <div class="dpr-modal-actions dpr-chat-action-area">
        <div class="dpr-chat-row dpr-chat-main-row">
          <div class="dpr-chat-composer">
            <label class="dpr-chat-label dpr-chat-inline-desc">
              <span class="dpr-chat-label-text">Retrieval requirement</span>
              <textarea id="dpr-chat-desc-input" rows="5" placeholder="Describe your retrieval need here, like chatting with ChatGPT. For example:&#10;Please help me find papers related to reinforcement learning and symbolic regression&#10;Please help me find papers on explainable reinforcement-learning-driven symbolic regression for equation discovery">${escapeHtml(
                modalState.inputDesc || '',
              )}</textarea>
            </label>
            <button
              class="arxiv-tool-btn dpr-chat-send-btn ${actionMeta.className}"
              data-action="chat-send"
              ${modalState.pending ? 'disabled' : ''}
            >
              <span class="dpr-chat-send-label">${actionMeta.label}</span>
              <span class="dpr-mini-spinner" aria-hidden="true"></span>
            </button>
          </div>
        </div>
        <div id="dpr-chat-inline-status" class="dpr-chat-inline-status">${escapeHtml(modalState.chatStatus || '')}</div>
      </div>
      <div class="dpr-chat-result-module">
        <div class="dpr-chat-result-content">${mixedHtml || emptyBlock}</div>
      </div>
      <div class="dpr-chat-bottom-bar">
        <div class="dpr-chat-meta-bar">
          <label class="dpr-chat-label dpr-chat-inline-tag">
            <span class="dpr-chat-label-text">Tag</span>
            <input id="dpr-chat-tag-input" type="text" placeholder="e.g. symbolic-regression" value="${escapeHtml(modalState.inputTag || '')}" />
          </label>
          <label class="dpr-chat-label dpr-chat-inline-profile-desc">
            <span class="dpr-chat-label-text">Description</span>
            <input id="dpr-chat-required-desc" type="text" placeholder="Shown in the daily report; can be auto-completed by the model" value="${escapeHtml(modalState.inputDesc || '')}" />
          </label>
          <div class="dpr-chat-label dpr-chat-inline-sources">
            <span class="dpr-chat-label-text">Paper source</span>
            <div class="dpr-paper-source-row">${sourceChoices}</div>
          </div>
        </div>
        <button class="arxiv-tool-btn dpr-chat-save-btn" data-action="apply-chat" ${hasCandidates ? '' : 'disabled'}>
          Save query
        </button>
      </div>
    `;

    requestAnimationFrame(() => {
      if (!modalPanel) return;
      const rows = 3;
      const slotScrolls = modalPanel.querySelectorAll('.dpr-chat-slot-scroll');
      slotScrolls.forEach((slot) => {
        const grid = slot.querySelector('.dpr-cloud-grid');
        const firstItem = slot.querySelector('.dpr-cloud-item');
        if (!grid || !firstItem) return;

        const style = getComputedStyle(grid);
        const gap = Number.parseFloat(style.rowGap || style.gap || '0') || 0;
        const itemHeight = firstItem.getBoundingClientRect().height;
        if (!itemHeight || Number.isNaN(itemHeight)) return;

        slot.style.maxHeight = `${itemHeight * rows + gap * (rows - 1)}px`;
      });
    });
  };

  const applyChatSelection = () => {
    let hasSelection = false;
    const selectedKeywords = getSelectedItemsForSave(modalState.keywords || []);
    const selectedIntentQueries = getSelectedItemsForSave(modalState.intent_queries || []);
    const hasItems = selectedKeywords.length || selectedIntentQueries.length;
    const validationError = validateProfileSelection(selectedKeywords, selectedIntentQueries);
    const desc = normalizeText(document.getElementById('dpr-chat-required-desc')?.value || '');
    const rawTag = normalizeText(document.getElementById('dpr-chat-tag-input')?.value || modalState.inputTag || '');
    const tag = sanitizeAutoTag(rawTag) || deriveTagFromCandidates(modalState) || '';
    const paperSources = normalizePaperSources(modalState.paper_sources, { fallbackToArxiv: false });

    if (!tag) {
      setMessage('Please first enter an English tag, an English abbreviation, or an English hyphenated phrase.', '#c00');
      return;
    }
    if (!desc) {
      setMessage('Please fill in the description first.', '#c00');
      return;
    }
    if (!paperSources.length) {
      setMessage('Please select at least 1 paper source.', '#c00');
      return;
    }
    if (validationError) {
      setMessage(validationError, '#c00');
      return;
    }
    modalState.inputTag = tag;

    const profileTag = tag || `SR-${new Date().toISOString().slice(0, 10)}`;
    if (hasItems) {
      const ok = modalState.editProfileId
        ? replaceProfileFromSelection(modalState.editProfileId, profileTag, desc, paperSources, {
            ...modalState,
            keywords: selectedKeywords,
            intent_queries: selectedIntentQueries,
          })
        : applyCandidateToProfile(profileTag, desc, paperSources, {
            ...modalState,
            keywords: selectedKeywords,
            intent_queries: selectedIntentQueries,
          });
      hasSelection = ok;
    }

    if (!hasSelection) {
      setMessage(hasItems ? 'Apply failed, please retry.' : 'Please select at least 1 keyword and 1 intent query before applying.', '#c00');
      return;
    }
    if (typeof reloadAll === 'function') reloadAll();
    setMessage(modalState.editProfileId ? 'Entry changes applied. Please click Save.' : 'Query saved. Please click Save.', '#666');
    closeModal();
  };

  const askChatOnce = async () => {
    if (!modalState || modalState.type !== 'chat') return;
    if (modalState.pending) return;
    const tag = sanitizeAutoTag(document.getElementById('dpr-chat-tag-input')?.value || '');
    const desc = normalizeText(document.getElementById('dpr-chat-desc-input')?.value || '');
    const finalDesc = desc;
    let finalTag = tag || 'topic';

    if (!finalDesc) {
      setChatStatus('Please fill in the retrieval requirement first.', '#c00');
      return;
    }

    modalState.pending = true;
    setSendBtnLoading(true);
    setChatStatus('Generating candidates, please wait...', '#666');
    setMessage('Generating candidates, please wait...', '#666');

    try {
      const candidates = await requestCandidatesByDesc(finalTag, finalDesc);
      const isFirstRound = !(Array.isArray(modalState.requestHistory) && modalState.requestHistory.length);
      const nextCandidates = parseCandidatesForState(candidates, false);
      const shouldMergeKeywords = !isFirstRound || hasRealCandidates(modalState.keywords);
      const shouldMergeIntentQueries =
        !isFirstRound || hasRealCandidates(modalState.intent_queries);
      const nextKeywords = shouldMergeKeywords
        ? mergeCandidatesForNextRound(modalState.keywords, nextCandidates.keywords, 'keyword')
        : nextCandidates.keywords;
      const nextIntentQueries = shouldMergeIntentQueries
        ? mergeCandidatesForNextRound(
            modalState.intent_queries,
            nextCandidates.intent_queries,
            'query',
          )
        : nextCandidates.intent_queries;
      const suggestedTag = normalizeText(candidates.tag);
      const suggestedDesc = normalizeText(candidates.description);
      const safeSuggestedTag = deriveTagFromCandidates(candidates);
      if (!tag && safeSuggestedTag) {
        finalTag = safeSuggestedTag;
      }
      if (safeSuggestedTag && !modalState.inputTag) {
        modalState.inputTag = safeSuggestedTag;
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
      modalState.keywords = ensureDraftSlot(nextKeywords, 'keyword');
      modalState.intent_queries = ensureDraftSlot(nextIntentQueries, 'intent');
      modalState.chatTag = finalTag;
      modalState.inputTag = finalTag;
      modalState.lastTag = finalTag;
      modalState.lastDesc = finalDesc;
      modalState.requestHistory = history;
      modalState.chatStatus = `Candidates generated (${nextCandidates.keywords.length} keywords, ${nextCandidates.intent_queries.length} intents).`;
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
      const rawMsg = e && e.message ? String(e.message) : 'Unknown error';
      const hint =
        /Failed to fetch|NETWORK|network|ERR_TIMED_OUT|timed out/i.test(rawMsg) ||
        /Model service request failed/.test(rawMsg)
          ? 'Please check whether your network can reach the model gateway, or retry later (you may switch/reselect the model first).'
          : '';
      const msg = `Generation failed: ${rawMsg}${hint ? ` (${hint})` : ''}`;
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

    const candidates = toProfileSelectableCandidates(profile);
    const existingKeywords = (candidates.keywords || []).map((item) => ({
      ...item,
      _selected: true,
    }));
    const existingIntentQueries = (candidates.intent_queries || []).map((item) => ({
      ...item,
      _selected: item.enabled !== false,
    }));
    openChatModal({
      editProfileId: targetKey,
      tag: profile.tag || '',
      description: profile.description || '',
      paper_sources: normalizePaperSources(profile.paper_sources, { fallbackToAll: true }),
      keywords: existingKeywords,
      intent_queries: existingIntentQueries,
    });
  };

  const handleModalClick = (e) => {
    const target = e.target;
    if (!target || !target.closest) return;
    const actionEl = target.closest('[data-action]');
    const action = actionEl ? actionEl.getAttribute('data-action') : '';
    if (!actionEl) return;
    if (action === 'close') {
      closeModal();
      return;
    }
    if (action === 'edit-inline-field') {
      if (!actionEl) return;
      e.preventDefault();
      e.stopPropagation();
      startInlineEditField(actionEl, modalState);
      return;
    }
    if (action === 'append-draft-slot') {
      e.preventDefault();
      e.stopPropagation();
      const kind = actionEl ? actionEl.getAttribute('data-kind') : '';
      const appended = appendDraftSlotItem(kind, modalState);
      if (appended) {
        if (modalState && modalState.type === 'add') renderAddModal();
        if (modalState && modalState.type === 'chat') renderChatModal();
      }
      return;
    }
    if (modalState && modalState.type === 'chat') {
      if (action === 'toggle-chat-choice-card') {
        e.preventDefault();
        e.stopPropagation();
        const kind = actionEl.getAttribute('data-kind') || '';
        const idx = Number(actionEl.getAttribute('data-index'));
        toggleChatChoice(kind, idx);
        return;
      }
      if (action === 'edit-candidate-choice') {
        e.preventDefault();
        e.stopPropagation();
        startCandidateEdit(actionEl.getAttribute('data-kind') || '', Number(actionEl.getAttribute('data-index')), {
          primary: actionEl.getAttribute('data-primary-field') || '',
          secondary: actionEl.getAttribute('data-secondary-field') || '',
          fallback: actionEl.getAttribute('data-fallback-field') || '',
        });
        return;
      }
      if (action === 'save-candidate-edit') {
        e.preventDefault();
        e.stopPropagation();
        saveCandidateEdit(actionEl.getAttribute('data-kind') || '', Number(actionEl.getAttribute('data-index')), {
          primary: actionEl.getAttribute('data-primary-field') || '',
          secondary: actionEl.getAttribute('data-secondary-field') || '',
          fallback: actionEl.getAttribute('data-fallback-field') || '',
        });
        return;
      }
      if (action === 'cancel-candidate-edit') {
        e.preventDefault();
        e.stopPropagation();
        cancelCandidateEdit(actionEl.getAttribute('data-kind') || '', Number(actionEl.getAttribute('data-index')));
        return;
      }
    }

    if (modalState && modalState.type === 'add') {
      if (action === 'toggle-kw-card') {
        const idx = Number(actionEl.getAttribute('data-index'));
        if (
          idx >= 0 &&
          idx < (modalState.keywords || []).length &&
          !isDraftSlot(modalState.keywords[idx])
        ) {
          const nextSelected = !modalState.keywords[idx]._selected;
          if (!canSelectMoreCandidates(modalState.keywords, nextSelected, 'keyword')) {
            setMessage(`You can select at most ${MAX_KEYWORDS_PER_PROFILE} keywords.`, '#c00');
            return;
          }
          modalState.keywords[idx]._selected = nextSelected;
          renderAddModal();
        }
        return;
      }
      if (action === 'toggle-intent-query-card') {
        const idx = Number(actionEl.getAttribute('data-index'));
        if (
          idx >= 0 &&
          idx < (modalState.intent_queries || []).length &&
          !isDraftSlot(modalState.intent_queries[idx])
        ) {
          const nextSelected = !modalState.intent_queries[idx]._selected;
          if (!canSelectMoreCandidates(modalState.intent_queries, nextSelected, 'intent')) {
            setMessage(`You can select at most ${MAX_INTENT_QUERIES_PER_PROFILE} intent queries.`, '#c00');
            return;
          }
          modalState.intent_queries[idx]._selected = nextSelected;
          renderAddModal();
        }
        return;
      }
      if (action === 'add-custom-kw') {
        const kwText = normalizeText(document.getElementById('dpr-add-kw-text')?.value || '');
        const query = normalizeText(document.getElementById('dpr-add-kw-query')?.value || '');
        const logic = normalizeText(document.getElementById('dpr-add-kw-logic')?.value || '');
        if (!kwText) {
          setMessage('Please enter a keyword to add.', '#c00');
          return;
        }
        const existed = (modalState.keywords || []).some(
          (x) => normalizeText(x.keyword || x.text || '').toLowerCase() === kwText.toLowerCase(),
        );
        if (existed) {
          setMessage('That keyword is already in the candidates.', '#c00');
          return;
        }
        if (!canSelectMoreCandidates(modalState.keywords, true, 'keyword')) {
          setMessage(`You can select at most ${MAX_KEYWORDS_PER_PROFILE} keywords.`, '#c00');
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
        setMessage('Added the custom keyword candidate.', '#666');
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
    if (target.matches('input[type="checkbox"][data-action="toggle-paper-source-all"]')) {
      if (!modalState) return;
      const availableSources = getAvailablePaperSources();
      const shouldSelectAll = !!target.checked;
      modalState.paper_sources = shouldSelectAll ? availableSources.slice() : [];
      if (modalPanel) {
        modalPanel
          .querySelectorAll('input[type="checkbox"][data-action="toggle-paper-source"]')
          .forEach((input) => {
            input.checked = shouldSelectAll;
          });
      }
      return;
    }
    if (target.matches('input[type="checkbox"][data-action="toggle-paper-source"]')) {
      if (!modalState) return;
      const source = normalizeText(target.getAttribute('data-source') || '').toLowerCase();
      if (!source) return;
      const availableSources = getAvailablePaperSources();
      const current = new Set(normalizePaperSources(modalState.paper_sources, { fallbackToArxiv: false }));
      if (target.checked) {
        current.add(source);
      } else {
        current.delete(source);
      }
      modalState.paper_sources = Array.from(current);
      const allToggle = modalPanel
        ? modalPanel.querySelector('input[type="checkbox"][data-action="toggle-paper-source-all"]')
        : null;
      if (allToggle) {
        allToggle.checked =
          availableSources.length > 0 &&
          availableSources.every((item) => current.has(item));
      }
      return;
    }
    if (!target.matches('input[type="checkbox"][data-action="toggle-chat-choice"]')) return;
    if (!modalState || modalState.type !== 'chat') return;

    const kind = target.getAttribute('data-kind');
    const idx = Number(target.getAttribute('data-index'));
    const list = kind === 'intent' ? modalState.intent_queries : modalState.keywords;
    if (
      !Array.isArray(list) ||
      idx < 0 ||
      idx >= list.length ||
      isDraftSlot(list[idx])
    ) {
      return;
    }
    const selected = !!target.checked;
    const card = target.closest('.dpr-cloud-item');
    if (!canSelectMoreCandidates(list, selected, kind)) {
      target.checked = false;
      if (card) {
        card.classList.remove('selected');
      }
      setMessage(`You can select at most ${getSelectionLimit(kind)} ${getKindLabel(kind)} items.`, '#c00');
      return;
    }
    if (card) {
      card.classList.toggle('selected', selected);
    }

    list[idx]._selected = selected;
  };

  const handleModalInput = (e) => {
    const target = e.target;
    if (!target || !target.matches) return;
    if (target.matches('input[data-candidate-edit-field]')) {
      updateCandidateEditDraft(target);
      return;
    }
    if (!target.matches('input[data-draft-input="1"]')) return;
    if (!modalState) return;
    const kind = target.getAttribute('data-kind') || '';
    const idx = Number(target.getAttribute('data-index'));
    const field = target.getAttribute('data-field') || '';
    applyDraftSlotValue(kind, idx, field, target.value, modalState);
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
      return 'First generation';
    }
    return `Round ${history.length + 1}`;
  };

  const generateAndOpenAddModal = async () => {
    const tag = sanitizeAutoTag(tagInputEl?.value || '');
    const desc = normalizeText(descInputEl?.value || '');
    const finalTag = tag || 'topic';
    if (!desc) {
      setMessage('Please fill in the smart-query description first.', '#c00');
      return;
    }

    try {
      setMessage('Generating candidates, please wait...', '#666');
      if (createBtn) createBtn.disabled = true;
      const candidates = await requestCandidatesByDesc(finalTag, desc);

      openAddModal(finalTag, desc, candidates);
      setMessage(`Candidates generated (${candidates.keywords.length} total).`, '#666');
    } catch (e) {
      console.error(e);
      setMessage(`Generation failed: ${e && e.message ? e.message : 'Unknown error'}`, '#c00');
    } finally {
      if (createBtn) createBtn.disabled = false;
    }
  };

  const handleDisplayClick = (e) => {
    const actionEl = e.target && e.target.closest ? e.target.closest('[data-action][data-profile-id]') : null;
    if (!actionEl) {
      const card = e.target && e.target.closest ? e.target.closest('.dpr-entry-card[data-profile-id]') : null;
      if (card) {
        toggleProfileSelection(card.getAttribute('data-profile-id') || '');
      }
      return;
    }
    const profileId = actionEl.getAttribute('data-profile-id');
    if (!profileId) return;
    const action = actionEl.getAttribute('data-action');
    if (action === 'edit-profile') {
      openEditModal(profileId);
      return;
    }
    if (action === 'pause-profile') {
      const profile = findCurrentProfile(profileId);
      if (!profile) return;
      const isPaused = !!profile.paused;
      const nextPaused = !isPaused;
      profile.paused = nextPaused;
      renderMain();

      window.SubscriptionsManager.updateDraftConfig((cfg) => {
        const next = cfg || {};
        if (!next.subscriptions) next.subscriptions = {};
        const subs = next.subscriptions;
        const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles.slice() : [];
        const idx = profiles.findIndex((p) => getProfileKey(p) === getProfileKey(profileId));
        if (idx >= 0 && profiles[idx]) {
          profiles[idx] = { ...profiles[idx], paused: nextPaused };
        }
        subs.intent_profiles = profiles;
        next.subscriptions = subs;
        return next;
      });
      const tag = normalizeText(profile.tag) || 'this entry';
      const statusText = nextPaused ? 'Daily fetching disabled' : 'Daily fetching enabled';
      setMessage(`Entry "${tag}" ${statusText}. Please click Save.`, '#666');
      return;
    }
    if (action === 'delete-profile') {
      const profile = findCurrentProfile(profileId);
      const tag = normalizeText(profile && profile.tag) || 'this entry';
      const desc = normalizeText(profile && profile.description);
      const keywordCount = Array.isArray(profile && profile.keywords) ? profile.keywords.length : 0;
      const summary = desc || `${keywordCount} keywords`;
      const ok = window.confirm(
        `Delete entry "${tag}"?\nSummary: ${summary}\nYou can discard this by refreshing before saving.`,
      );
      if (!ok) return;
      const normalizedProfileId = getProfileId(profileId);
      if (normalizedProfileId) {
        pendingDeletedProfileIds.add(normalizedProfileId);
        selectedProfileKeys.delete(normalizedProfileId);
      }
      currentProfiles = currentProfiles.filter((item) => getProfileKey(item) !== normalizedProfileId);
      renderMain();
      notifySelectionChange();

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
      setMessage(`Entry "${tag}" deleted. Please click Save.`, '#666');
    }
  };

  const attach = (context) => {
    displayListEl = context.displayListEl || null;
    createBtn = context.createBtn || null;
    openChatBtn = context.openChatBtn || null;
    const openTemporaryBtn = context.openTemporaryBtn || null;
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
    if (openTemporaryBtn && !openTemporaryBtn._bound) {
      openTemporaryBtn._bound = true;
      openTemporaryBtn.addEventListener('click', () => {
        openChatModal({ temporaryProfile: true });
      });
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
      modalPanel.addEventListener('input', handleModalInput);
      modalPanel.addEventListener('keydown', handleModalKeydown);
    }
  };

  const render = (profiles) => {
    const normalizedProfiles = Array.isArray(profiles) ? deepClone(profiles) : [];
    const previousLiveKeys = new Set(currentProfiles.map((profile) => getProfileKey(profile)).filter(Boolean));
    currentProfiles = filterDeletedProfiles(normalizedProfiles);
    const liveKeys = new Set(currentProfiles.map((profile) => getProfileKey(profile)).filter(Boolean));
    Array.from(selectedProfileKeys).forEach((key) => {
      if (!liveKeys.has(key)) selectedProfileKeys.delete(key);
    });
    currentProfiles.forEach((profile) => {
      const key = getProfileKey(profile);
      if (!key) return;
      if (!selectionInitialized || !previousLiveKeys.has(key)) {
        selectedProfileKeys.add(key);
      }
    });
    selectionInitialized = true;
    renderMain();
  };
  const setRunSelectionMode = (mode, onSelectionChange) => {
    runSelectionMode = mode === 'conference' || mode === 'daily' ? mode : '';
    selectionChangeHandler = typeof onSelectionChange === 'function' ? onSelectionChange : null;
    renderMain();
    notifySelectionChange();
  };
  const getSelectedProfilesForRun = () =>
    (currentProfiles || [])
      .filter((profile) => selectedProfileKeys.has(getProfileKey(profile)))
      .map((profile) => ({
        tag: normalizeText(profile && profile.tag),
        description: normalizeText(profile && profile.description),
        scope: normalizeText(profile && profile.scope),
        temporary: isConferenceOnlyProfile(profile),
        paused: !!(profile && profile.paused),
      }))
      .filter((profile) => profile.tag);
  const getSelectedProfileTags = () =>
    getSelectedProfilesForRun().map((profile) => profile.tag);
  const clearRunSelection = () => {
    selectedProfileKeys.clear();
    renderMain();
    notifySelectionChange();
  };

  return {
    attach,
    render,
    clearPendingDeletedProfileIds,
    setRunSelectionMode,
    getSelectedProfilesForRun,
    getSelectedProfileTags,
    clearRunSelection,
    setProfileSelection,
    selectProfilesForRun,
    getProfilesForRun,
    __test: {
      buildPromptFromTemplate,
      defaultPromptTemplate,
      containsCjk,
      deriveTagFromCandidates,
      isEnglishRetrievalText,
      normalizeGenerated,
      sanitizeAutoTag,
    },
  };
})();
