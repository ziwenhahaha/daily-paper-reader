// 订阅管理总模块（智能 Query）
// 负责：
// 1) 维护本地草稿配置
// 2) 统一渲染 intent_profiles
// 3) 保存前仅保留 intent_profiles

window.SubscriptionsManager = (function () {
  const MAX_KEYWORDS_PER_PROFILE = 6;
  const MAX_INTENT_QUERIES_PER_PROFILE = 4;
  let overlay = null;
  let panel = null;
  let saveBtn = null;
  let closeBtn = null;
  let msgEl = null;
  let quickRun10dBtn = null;
  let quickRun30dBtn = null;
  let quickRun30dStandardBtn = null;
  let quickRunOpenWorkflowPanelBtn = null;
  let quickRunConferenceBtn = null;
  let quickRunMsgEl = null;
  let quickRunSelectionCountEl = null;
  let conferenceSelectionCountEl = null;
  let dailyProfilePickerEl = null;
  let conferenceProfilePickerEl = null;
  let dailySelectAllBtn = null;
  let dailyClearAllBtn = null;
  let conferenceSelectAllBtn = null;
  let conferenceClearAllBtn = null;
  let quickRunStartBtn = null;
  let quickRunHintEl = null;
  let conferenceHintEl = null;
  let quickRunMode = '10';
  const selectedConferenceYearPairs = new Set();
  let resetContentBtn = null;
  let resetContentMsgEl = null;
  let adminDailyTabBtn = null;
  let adminConferenceTabBtn = null;
  let adminDailyPanel = null;
  let adminConferencePanel = null;
  let activeAdminPanelTab = 'daily';

  let draftConfig = null;
  let hasUnsavedChanges = false;
  let isSavingDraftConfig = false;
  let conferenceStatsSnapshot = { schema_version: 1, generated_at: '', items: [], byKey: new Map() };
  let conferenceStatsLoadPromise = null;

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
    '2) keyword and query MUST be English retrieval text only. Do not put Chinese in keyword or query.',
    '3) keyword_cn and query_cn MUST be Chinese translations/explanations when present.',
    '4) keywords are used for recall and should be meaningful atomic noun phrases, normally 2-4 English words.',
    '5) Do NOT output acronym-only or abbreviation-only keywords such as "rl", "xrl", "sr", "llm". Expand them to full phrases like "reinforcement learning" or "large language model".',
    '6) Do NOT output incomplete modifier phrases ending with generic words like "driven", "based", "related", "guided", "enhanced", "for", or "with".',
    '7) Avoid coupling core terms (e.g., "symbolic regression", "reinforcement learning", "genetic programming", "Transformer") with extra qualifiers into one keyword. Keep core terms atomic in keyword and use query for full intent.',
    '8) Suggested example:',
    '   {"keyword":"symbolic regression","query":"deep symbolic regression methods","keyword_cn":"符号回归","query_cn":"符号回归深度方法"},',
    '   {"keyword":"reinforcement learning","query":"policy gradient symbolic regression","keyword_cn":"强化学习","query_cn":"策略梯度在符号回归中的应用"},',
    '   {"keyword":"Monte Carlo tree search","query":"Monte Carlo tree search for symbolic regression"}',
    '9) intent_queries: output 1-4 actionable intent queries. The query field MUST be English only; query_cn should be Chinese.',
    '10) intent_queries must be specific semantic search sentences, not acronym-only strings.',
    '11) Do not output extra fields like must_have / optional / exclude / rewrite_for_embedding / must_have.',
    '12) Return pure JSON only, no explanations.',
    '13) Tag suggestion must be concise: at most 12 characters total, counting hyphens.',
    '14) Tag suggestion must be English words or an English acronym only. Never output Chinese in tag.',
    '15) Tag suggestion must use hyphen-separated words when multiple words are needed, for example "reinforcement-learning". Do not use spaces or underscores in tag.',
    '16) If the descriptive tag would exceed 12 characters, output an English acronym or a shorter hyphenated label.',
  ].join('\n');

  const QUICK_RUN_CONFERENCES = [
    'ICLR',
    'ICML',
    'NeurIPS',
    'AAAI',
    'CVPR',
    'ECCV',
    'IJCAI',
    'ACL',
    'EMNLP',
    'OSDI',
    'SOSP',
    'IEEE S&P',
    'NDSS',
  ];
  const CONFERENCE_STATS_SNAPSHOT_URL = 'app/conference-stats.json';
  // 2026 年会议数据可用性（截至 2026-07）：
  // 有数据: ICLR 2026, ICML 2026, AAAI 2026, ACL 2026, OSDI 2026, IEEE S&P 2026, NDSS 2026
  // 无数据: CVPR/SOSP 2026（论文 PDF 尚未全量公开或未上传）
  const CONFERENCE_2026_AVAILABLE = new Set(['ICLR', 'ICML', 'AAAI', 'ACL', 'OSDI', 'IEEE S&P', 'NDSS']);
  const FEATURED_CONFERENCE_YEAR_PAIRS = new Set(['acl:2026', 'icml:2026']);
  // ECCV 是双年会议（偶数年）
  const BIENNIAL_EVEN_CONFERENCES = new Set(['ECCV']);
  const CONFERENCES_WITH_PENDING_CURRENT_YEAR = new Set([
    'NIPS',
    'NEURIPS',
  ]);
  const MAX_CONFERENCE_STORED_TOTAL = 30000;
  const CONFERENCE_ESTIMATE_PAPERS_UNIT = 10000;
  const CONFERENCE_ESTIMATE_MINUTES_PER_UNIT = 5;
  const CONFERENCE_ESTIMATE_COST_PER_UNIT = 0.2;

  const normalizeText = (v) => String(v || '').trim();
  const truncateDisplayText = (value, maxChars) => {
    const chars = Array.from(normalizeText(value));
    if (chars.length <= maxChars) return chars.join('');
    return chars.slice(0, maxChars).join('');
  };
  const escapeHtml = (str) => String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  const toSafeInteger = (value) => {
    const num = parseInt(String(value ?? '').trim(), 10);
    return Number.isFinite(num) ? num : 0;
  };
  const formatCount = (value) => toSafeInteger(value).toLocaleString('en-US');
  const formatEstimateMinutes = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) return '0';
    if (Math.abs(num - Math.round(num)) < 0.05) return String(Math.round(num));
    return num.toFixed(1);
  };
  const estimateConferenceRetrieval = (storedTotal, profileCount) => {
    const estimatedPapers = Math.max(0, toSafeInteger(storedTotal)) * Math.max(0, toSafeInteger(profileCount));
    const units = estimatedPapers / CONFERENCE_ESTIMATE_PAPERS_UNIT;
    return {
      estimatedPapers,
      minutes: units * CONFERENCE_ESTIMATE_MINUTES_PER_UNIT,
      cost: units * CONFERENCE_ESTIMATE_COST_PER_UNIT,
    };
  };
  const normalizeConferenceStatsKey = (value) => {
    const compact = normalizeText(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
    if (!compact) return '';
    if (['ieee_s_p', 'ieee_sp', 's_p', 'sp'].includes(compact)) return 'ieee_sp';
    if (compact === 'nips') return 'neurips';
    return compact;
  };
  const normalizeConferenceStatsSnapshot = (snapshot) => {
    const rawItems = Array.isArray(snapshot && snapshot.items) ? snapshot.items : [];
    const byKey = new Map();
    const items = rawItems
      .map((item) => {
        const conferenceKey = normalizeConferenceStatsKey(item && (item.conference_key || item.conference_label));
        const year = toSafeInteger(item && item.year);
        if (!conferenceKey || !year) return null;
        return {
          id: normalizeText(item.id || `${conferenceKey}-${year}`),
          conference_key: conferenceKey,
          conference_label: normalizeText(item.conference_label || conferenceKey.toUpperCase()),
          year,
          official_accepted_count: toSafeInteger(item.official_accepted_count),
          stored_total_count: toSafeInteger(item.stored_total_count),
          stored_accepted_count: toSafeInteger(item.stored_accepted_count),
          stored_rejected_count: toSafeInteger(item.stored_rejected_count),
          stored_other_count: toSafeInteger(item.stored_other_count),
          generated_at: normalizeText(item.generated_at || snapshot.generated_at || ''),
        };
      })
      .filter(Boolean);
    items.forEach((item) => byKey.set(`${item.conference_key}:${item.year}`, item));
    return {
      schema_version: toSafeInteger(snapshot && snapshot.schema_version) || 1,
      generated_at: normalizeText(snapshot && snapshot.generated_at),
      items,
      byKey,
    };
  };
  const setConferenceStatsSnapshot = (snapshot) => {
    conferenceStatsSnapshot = normalizeConferenceStatsSnapshot(snapshot || {});
  };
  const getConferenceYearStats = (conference, year) => {
    const conferenceKey = normalizeConferenceStatsKey(conference);
    const yearNum = toSafeInteger(year);
    if (!conferenceKey || !yearNum) return null;
    return conferenceStatsSnapshot.byKey.get(`${conferenceKey}:${yearNum}`) || null;
  };
  const getConferenceYearStoredTotal = (conference, year) => {
    const stats = getConferenceYearStats(conference, year);
    return stats ? toSafeInteger(stats.stored_total_count) : 0;
  };
  const getSelectedConferenceStoredTotal = () => {
    let total = 0;
    selectedConferenceYearPairs.forEach((item) => {
      const [conference, year] = String(item || '').split(':');
      if (!conference || !year) return;
      total += getConferenceYearStoredTotal(conference, year);
    });
    return total;
  };
  const getSelectedConferencePairSpecs = () => {
    const out = [];
    const seen = new Set();
    selectedConferenceYearPairs.forEach((item) => {
      const [conferenceRaw, yearRaw] = String(item || '').split(':');
      const conference = normalizeConferenceStatsKey(conferenceRaw);
      const year = toSafeInteger(yearRaw);
      if (!conference || !year) return;
      const pair = `${conference}:${year}`;
      if (seen.has(pair)) return;
      seen.add(pair);
      out.push({ conference, year, pair });
    });
    out.sort((a, b) => (b.year - a.year) || a.conference.localeCompare(b.conference));
    return out.map((item) => item.pair);
  };
  const getSelectedConferenceYearsForWorkflow = () => {
    const seen = new Set();
    return getSelectedConferencePairSpecs()
      .map((item) => item.split(':')[1])
      .filter((year) => {
        if (!year || seen.has(year)) return false;
        seen.add(year);
        return true;
      });
  };
  const formatConferenceShortYear = (year) => {
    const yearText = normalizeText(year);
    return yearText.length === 4 ? yearText.slice(2) : yearText;
  };
  const formatConferenceYearStatsLabel = (conference, year) => {
    const shortYear = formatConferenceShortYear(year);
    const stats = getConferenceYearStats(conference, year);
    if (!stats) return shortYear;
    return `${shortYear} (${stats.stored_total_count})`;
  };
  const buildConferenceChoiceRowsHtml = () => QUICK_RUN_CONFERENCES
    .map((name) => {
      const yearButtons = getConferenceYearOptions()
        .map((year) => {
          const active = selectedConferenceYearPairs.has(`${name}:${year}`);
          const reason = getConferenceYearDisabledReason(name, year);
          const disabled = !!reason;
          const stats = getConferenceYearStats(name, year);
          const classes = [
            'dpr-choice-pill',
            stats ? 'has-conference-stats' : '',
            FEATURED_CONFERENCE_YEAR_PAIRS.has(`${normalizeConferenceStatsKey(name)}:${year}`) ? 'is-featured-conference-year' : '',
            active ? 'is-active' : '',
            disabled ? 'is-disabled' : '',
          ].filter(Boolean).join(' ');
          const shortYear = formatConferenceShortYear(year);
          const visibleLabel = formatConferenceYearStatsLabel(name, year);
          const labelHtml = stats
            ? `<span class="dpr-choice-year">${escapeHtml(shortYear)}</span><span class="dpr-choice-total-wrap"> (<span class="dpr-choice-total">${escapeHtml(String(stats.stored_total_count))}</span>)</span>`
            : `<span class="dpr-choice-year">${escapeHtml(shortYear)}</span>`;
          const featureStar = FEATURED_CONFERENCE_YEAR_PAIRS.has(`${normalizeConferenceStatsKey(name)}:${year}`)
            ? '<span class="dpr-choice-feature-star" aria-hidden="true">★</span>'
            : '';
          return `<button
            class="${classes}"
            type="button"
            data-conference="${escapeHtml(name)}"
            data-conference-year="${escapeHtml(year)}"
            aria-pressed="${active ? 'true' : 'false'}"
            aria-label="${escapeHtml(`${name} ${visibleLabel}`)}"
            ${disabled ? `disabled title="${escapeHtml(reason)}"` : ''}
          ><span class="dpr-choice-pill-main">${labelHtml}</span>${featureStar}</button>`;
        })
        .join('');
      return `<div class="dpr-conference-choice-row">
        <div class="dpr-conference-choice-label">${escapeHtml(name)}</div>
        <div class="dpr-choice-row">${yearButtons}</div>
      </div>`;
    })
    .join('');
  const loadConferenceStatsSnapshot = () => {
    if (conferenceStatsLoadPromise) return conferenceStatsLoadPromise;
    const preloadedStats =
      window.DPR_ASSET_JSON_PROMISES &&
      window.DPR_ASSET_JSON_PROMISES[CONFERENCE_STATS_SNAPSHOT_URL];
    if (!preloadedStats && typeof fetch !== 'function') return Promise.resolve(null);
    conferenceStatsLoadPromise = (preloadedStats
      ? Promise.resolve(preloadedStats)
      : fetch(CONFERENCE_STATS_SNAPSHOT_URL, { cache: 'force-cache' })
      .then((response) => {
        if (!response || !response.ok) {
          throw new Error(`conference stats load failed: ${response ? response.status : 'no-response'}`);
        }
        return response.json();
      }))
      .then((snapshot) => {
        if (!snapshot) return null;
        setConferenceStatsSnapshot(snapshot);
        renderConferenceChoiceButtons();
        return snapshot;
      })
      .catch((error) => {
        console.warn('[DPR] 会议统计快照加载失败', error);
        return null;
      });
    return conferenceStatsLoadPromise;
  };
  const MAX_PROFILE_TAG_CHARS = 12;
  const sanitizeProfileTag = (value) => {
    const base = normalizeText(value);
    if (!base) return '';
    const tag = base
      .replace(/\((?:19|20)\d{2}(?:年)?\)/g, '')
      .replace(/（(?:19|20)\d{2}(?:年)?）/g, '')
      .replace(/([\u4e00-\u9fffA-Za-z]+)\s*(?:19|20)\d{2}(?!\d)/g, '$1')
      .replace(/(?:19|20)\d{2}(?!\d)([\u4e00-\u9fffA-Za-z]+)/g, '$1')
      .replace(/[\s_-]*(?:19|20)\d{2}(?:年)?[\s_-]*/g, '')
      .replace(/\+/g, '-')
      .replace(/[\s_]+/g, '-')
      .replace(/[^A-Za-z-]+/g, '')
      .replace(/-+/g, '-')
      .replace(/^-+|-+$/g, '')
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
  const deriveProfileTag = (profile, fallback) => {
    const values = [profile && profile.tag];
    (Array.isArray(profile && profile.keywords) ? profile.keywords : []).forEach((item) => {
      if (typeof item === 'string') {
        values.push(item);
        return;
      }
      if (item && typeof item === 'object') {
        values.push(item.keyword, item.query);
      }
    });
    (Array.isArray(profile && profile.intent_queries) ? profile.intent_queries : []).forEach((item) => {
      if (typeof item === 'string') {
        values.push(item);
        return;
      }
      if (item && typeof item === 'object') {
        values.push(item.query);
      }
    });
    values.push(fallback);
    for (let idx = 0; idx < values.length; idx += 1) {
      const tag = sanitizeProfileTag(values[idx]);
      if (tag) return tag;
    }
    return '';
  };
  const normalizeSourceKey = (v) => normalizeText(v).toLowerCase();
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

  const isPlainObject = (value) => !!value && typeof value === 'object' && !Array.isArray(value);

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
  const SOURCE_BACKEND_DEFAULTS = {
    arxiv: {
      papers_table: 'arxiv_papers',
      use_vector_rpc: true,
      vector_rpc: 'match_arxiv_papers_exact',
      vector_rpc_exact: 'match_arxiv_papers_exact',
      use_bm25_rpc: true,
      bm25_rpc: 'match_arxiv_papers_bm25',
      sync_table: 'arxiv_sync_status',
      sync_success_value: 'success',
      schema: 'public',
    },
    biorxiv: {
      papers_table: 'biorxiv_papers',
      use_vector_rpc: true,
      vector_rpc: 'match_biorxiv_papers_exact',
      vector_rpc_exact: 'match_biorxiv_papers_exact',
      use_bm25_rpc: true,
      bm25_rpc: 'match_biorxiv_papers_bm25',
      schema: 'public',
    },
  };

  const filterVisiblePaperSources = (values) => {
    const visible = new Set(VISIBLE_PAPER_SOURCES);
    return (Array.isArray(values) ? values : []).filter((value) => visible.has(normalizeSourceKey(value)));
  };

  const getAvailablePaperSources = (config) => {
    const cfg = config && typeof config === 'object' ? config : {};
    const rawBackends = cfg.source_backends && typeof cfg.source_backends === 'object'
      ? cfg.source_backends
      : {};
    const seen = new Set();
    const out = [];
    const runtimeCandidates = [];
    if (window.DPR_RUNTIME_SOURCE_BACKENDS && typeof window.DPR_RUNTIME_SOURCE_BACKENDS === 'object') {
      runtimeCandidates.push(...Object.keys(window.DPR_RUNTIME_SOURCE_BACKENDS || {}));
    }
    ['arxiv', ...Object.keys(rawBackends || {}), ...runtimeCandidates].forEach((key) => {
      const normalized = normalizeSourceKey(key);
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      out.push(normalized);
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

  const normalizePaperSources = (values, options = {}) => {
    const fallbackToArxiv = options.fallbackToArxiv !== false;
    const rawList = Array.isArray(values)
      ? values
      : (typeof values === 'string' && values ? [values] : []);
    const seen = new Set();
    const out = [];
    rawList.forEach((value) => {
      const key = normalizeSourceKey(value);
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push(key);
    });
    const visibleOut = filterVisiblePaperSources(out);
    if (!visibleOut.length && fallbackToArxiv) {
      return ['arxiv'];
    }
    return visibleOut;
  };

  const mergeDefinedFields = (base, override) => {
    const next = { ...(isPlainObject(base) ? base : {}) };
    if (!isPlainObject(override)) return next;
    Object.keys(override).forEach((key) => {
      const value = override[key];
      if (value === undefined) return;
      next[key] = value;
    });
    return next;
  };

  const buildDefaultSourceBackend = (sourceKey, config) => {
    const normalizedKey = normalizeSourceKey(sourceKey);
    const defaults = SOURCE_BACKEND_DEFAULTS[normalizedKey];
    if (!defaults) return null;

    const cfg = isPlainObject(config) ? config : {};
    const shared = isPlainObject(cfg.supabase_shared) ? cfg.supabase_shared : {};
    const legacy = isPlainObject(cfg.supabase) ? cfg.supabase : {};

    let base = {
      kind: normalizeText(shared.kind || legacy.kind || 'supabase') || 'supabase',
      enabled: shared.enabled !== false && legacy.enabled !== false,
      url: normalizeText(shared.url || legacy.url || ''),
      anon_key: normalizeText(shared.anon_key || legacy.anon_key || ''),
      schema: normalizeText(shared.schema || legacy.schema || defaults.schema || 'public') || 'public',
    };

    if (normalizedKey === 'arxiv') {
      base = mergeDefinedFields(base, {
        enabled: Object.prototype.hasOwnProperty.call(legacy, 'enabled') ? legacy.enabled !== false : undefined,
        papers_table: normalizeText(legacy.papers_table || ''),
        use_vector_rpc: Object.prototype.hasOwnProperty.call(legacy, 'use_vector_rpc') ? legacy.use_vector_rpc !== false : undefined,
        vector_rpc: normalizeText(legacy.vector_rpc || ''),
        vector_rpc_exact: normalizeText(legacy.vector_rpc_exact || legacy.vector_rpc || ''),
        use_bm25_rpc: Object.prototype.hasOwnProperty.call(legacy, 'use_bm25_rpc') ? legacy.use_bm25_rpc !== false : undefined,
        bm25_rpc: normalizeText(legacy.bm25_rpc || ''),
        sync_table: normalizeText(legacy.sync_table || ''),
        sync_success_value: normalizeText(legacy.sync_success_value || ''),
      });
    }

    return mergeDefinedFields(defaults, base);
  };

  const ensureSourceBackendsForProfiles = (config) => {
    const next = isPlainObject(config) ? config : {};
    const subs = isPlainObject(next.subscriptions) ? next.subscriptions : {};
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    const existingBackends = isPlainObject(next.source_backends) ? next.source_backends : {};
    const mergedBackends = cloneDeep(existingBackends);
    let changed = !isPlainObject(next.source_backends);

    profiles.forEach((profile) => {
      if (!isPlainObject(profile)) return;
      const fallbackToArxiv = !Object.prototype.hasOwnProperty.call(profile, 'paper_sources');
      const paperSources = normalizePaperSources(profile.paper_sources, { fallbackToArxiv });
      paperSources.forEach((sourceKey) => {
        const template = buildDefaultSourceBackend(sourceKey, next);
        if (!template) return;
        const current = isPlainObject(mergedBackends[sourceKey]) ? mergedBackends[sourceKey] : {};
        const merged = mergeDefinedFields(template, current);
        const before = JSON.stringify(current);
        const after = JSON.stringify(merged);
        if (before !== after) {
          mergedBackends[sourceKey] = merged;
          changed = true;
        }
      });
    });

    if (changed) {
      next.source_backends = mergedBackends;
    }
    return next;
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
      embedding_cache:
        item.embedding_cache && typeof item.embedding_cache === 'object'
          ? cloneDeep(item.embedding_cache)
          : undefined,
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
      embedding_cache:
        item.embedding_cache && typeof item.embedding_cache === 'object'
          ? cloneDeep(item.embedding_cache)
          : undefined,
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

  const initializeConferenceChoices = () => {
    // 不默认勾选任何会议年份，由用户手动选择
  };

  const getConferenceYearOptions = () => {
    const currentYear = new Date().getFullYear();
    return [currentYear, currentYear - 1, currentYear - 2].map((year) => String(year));
  };

  const isConferenceYearSelectable = (conference, year) => {
    return !getConferenceYearDisabledReason(conference, year);
  };

  /**
   * 返回不可选的原因文案；可选时返回空字符串。
   */
  const getConferenceYearDisabledReason = (conference, year) => {
    const conf = normalizeText(conference).toUpperCase();
    const yearNum = parseInt(normalizeText(year), 10);
    if (!Number.isFinite(yearNum)) return '无效年份';
    // ECCV 双年（偶数年才有）
    if (BIENNIAL_EVEN_CONFERENCES.has(conf) && yearNum % 2 !== 0) {
      return `${conf} 为双年会议，仅偶数年举办（如 2024、2026）`;
    }
    // 2026 年可用性
    const currentYear = new Date().getFullYear();
    if (yearNum >= currentYear && !CONFERENCE_2026_AVAILABLE.has(conf)) {
      const ESTIMATED_DATES = {
        CVPR:    '2026 年 7 月（论文上传后）',
        ICML:    '2026 年 7 月会后',
        IJCAI:   '2026 年 8 月会后',
        ACL:     '2026 年 7 月会后',
        EMNLP:   '2026 年 11 月会后',
        NEURIPS: '2026 年 12 月会后',
        NIPS:    '2026 年 12 月会后',
        ECCV:    '2026 年秋季会后',
        OSDI:    '2026 年会后论文 PDF 公开后',
        SOSP:    '2026 年会后论文 PDF 公开后',
        'IEEE S&P': '2026 年 CSDL 论文 PDF 公开后',
      };
      const est = ESTIMATED_DATES[conf];
      if (est) return `预计 ${est} 纳入`;
      return `${yearNum} 年暂无数据`;
    }
    // 原有的"当年待定"逻辑
    if (
      CONFERENCES_WITH_PENDING_CURRENT_YEAR.has(conf)
      && yearNum === currentYear
    ) {
      const PENDING_DATES = {
        ICML:    '预计 2026 年 7 月会后纳入',
        NEURIPS: '预计 2026 年 12 月会后纳入',
        NIPS:    '预计 2026 年 12 月会后纳入',
      };
      return PENDING_DATES[conf] || `${yearNum} 年论文尚未公开`;
    }
    return '';
  };

  const renderConferenceChoiceButtons = () => {
    if (!document || typeof document.getElementById !== 'function') return;
    const conferenceWrap = document.getElementById('arxiv-admin-conference-choice-group');
    if (conferenceWrap) {
      conferenceWrap.innerHTML = buildConferenceChoiceRowsHtml();
    }
  };

  const getSelectedProfileTagsForRun = () => {
    if (!window.SubscriptionsSmartQuery || typeof window.SubscriptionsSmartQuery.getSelectedProfileTags !== 'function') {
      return [];
    }
    return window.SubscriptionsSmartQuery.getSelectedProfileTags();
  };
  const getSelectedProfilesForRun = () => {
    if (window.SubscriptionsSmartQuery && typeof window.SubscriptionsSmartQuery.getSelectedProfilesForRun === 'function') {
      return window.SubscriptionsSmartQuery.getSelectedProfilesForRun();
    }
    return getSelectedProfileTagsForRun().map((tag) => ({ tag, temporary: false, paused: false }));
  };
  const getDailySelectedProfileTagsForRun = () =>
    getSelectedProfilesForRun()
      .map((profile) => normalizeText(profile && profile.tag))
      .filter(Boolean);
  const getProfilesForRun = () => {
    if (window.SubscriptionsSmartQuery && typeof window.SubscriptionsSmartQuery.getProfilesForRun === 'function') {
      return window.SubscriptionsSmartQuery.getProfilesForRun();
    }
    return getSelectedProfilesForRun().map((profile) => ({
      id: toStableId(profile.tag),
      ...profile,
      selected: true,
    }));
  };
  const renderProfilePicker = (targetEl, mode) => {
    if (!targetEl) return;
    const profiles = getProfilesForRun();
    const filtered = mode === 'daily'
      ? profiles
      : profiles;
    if (!filtered.length) {
      targetEl.innerHTML = `<div class="dpr-profile-picker-empty">${
        mode === 'daily' ? '暂无可快速抓取的词条。' : '暂无可检索的词条。'
      }</div>`;
      return;
    }
    targetEl.innerHTML = filtered.map((profile) => {
      const selected = !!profile.selected;
      const tag = normalizeText(profile.tag);
      const desc = normalizeText(profile.description);
      const shortDesc = truncateDisplayText(desc, 10);
      return `<button
        class="dpr-profile-picker-chip${selected ? ' is-selected' : ''}"
        type="button"
        data-profile-id="${escapeHtml(profile.id)}"
        data-picker-mode="${mode}"
        aria-pressed="${selected ? 'true' : 'false'}"
        title="${escapeHtml(desc || tag)}"
      >
        <span class="dpr-profile-picker-check" aria-hidden="true">${selected ? '✓' : ''}</span>
        <span class="dpr-profile-picker-tag">${escapeHtml(tag)}</span>
        ${shortDesc ? `<span class="dpr-profile-picker-desc">${escapeHtml(shortDesc)}</span>` : ''}
      </button>`;
    }).join('');
  };
  const renderProfilePickers = () => {
    renderProfilePicker(dailyProfilePickerEl, 'daily');
    renderProfilePicker(conferenceProfilePickerEl, 'conference');
  };
  const setProfileSelection = (profileId, selected) => {
    if (!window.SubscriptionsSmartQuery || typeof window.SubscriptionsSmartQuery.setProfileSelection !== 'function') {
      return;
    }
    window.SubscriptionsSmartQuery.setProfileSelection(profileId, selected);
  };
  const selectProfilesByMode = (mode, selected) => {
    if (!window.SubscriptionsSmartQuery || typeof window.SubscriptionsSmartQuery.selectProfilesForRun !== 'function') {
      return;
    }
    window.SubscriptionsSmartQuery.selectProfilesForRun((profile) => {
      const isTemporary = !!(
        profile &&
        (
          profile.temporary === true ||
          profile.conference_only === true ||
          normalizeText(profile.scope).toLowerCase() === 'conference'
        )
      );
      if (mode === 'daily') return true;
      return true;
    }, selected);
  };
  const showWorkflowSuccessEffects = () => {
    if (!document || !document.body || typeof document.createElement !== 'function') return;
    const layer = document.createElement('div');
    layer.className = 'dpr-firework-layer';
    const colors = ['#ff7ab6', '#7cdbff', '#ffe27a', '#9ff0bd', '#b69cff'];
    for (let idx = 0; idx < 18; idx += 1) {
      const burst = document.createElement('span');
      burst.className = 'dpr-firework-burst';
      burst.style.left = `${12 + Math.random() * 76}%`;
      burst.style.top = `${14 + Math.random() * 56}%`;
      burst.style.setProperty('--dpr-firework-color', colors[idx % colors.length]);
      burst.style.animationDelay = `${Math.random() * 0.35}s`;
      layer.appendChild(burst);
    }
    document.body.appendChild(layer);
    setTimeout(() => {
      layer.remove();
    }, 1700);
  };
  const syncRunSelectionMode = () => {
    if (!window.SubscriptionsSmartQuery || typeof window.SubscriptionsSmartQuery.setRunSelectionMode !== 'function') {
      return;
    }
    window.SubscriptionsSmartQuery.setRunSelectionMode(activeAdminPanelTab, () => {
      refreshQuickRunButtons();
    });
  };

  const refreshQuickRunButtons = () => {
    const selectedProfiles = getSelectedProfilesForRun();
    const selectedProfileCount = selectedProfiles.length;
    const dailySelectedProfileCount = selectedProfileCount;
    const MAX_CONFERENCE_PROFILES = 2;
    const profileOverLimit = selectedProfileCount > MAX_CONFERENCE_PROFILES;
    const conferenceStoredTotal = getSelectedConferenceStoredTotal();
    const conferenceTotalOverLimit = conferenceStoredTotal >= MAX_CONFERENCE_STORED_TOTAL;
    const dailyBlocked = hasUnsavedChanges || dailySelectedProfileCount < 1;
    const conferenceBlocked =
      hasUnsavedChanges
      || selectedProfileCount < 1
      || selectedConferenceYearPairs.size < 1
      || profileOverLimit
      || conferenceTotalOverLimit;
    renderProfilePickers();
    [
      [quickRunStartBtn, dailyBlocked],
      [quickRunConferenceBtn, conferenceBlocked],
    ].forEach(([btn, blocked]) => {
      if (!btn) return;
      btn.disabled = blocked;
      btn.classList.toggle('chat-quick-run-item--disabled', blocked);
      let title = btn.getAttribute('data-default-title') || btn.textContent || '';
      if (blocked) {
        if (hasUnsavedChanges) {
          title = btn === quickRunConferenceBtn ? '请先保存后再检索会议论文。' : '请先保存后再抓取。';
        } else if (btn === quickRunConferenceBtn && profileOverLimit) {
          title = `会议检索最多选择 ${MAX_CONFERENCE_PROFILES} 个词条，当前已选 ${selectedProfileCount} 个。`;
        } else if (btn === quickRunConferenceBtn && conferenceTotalOverLimit) {
          title = `会议年份库内总数需小于 ${formatCount(MAX_CONFERENCE_STORED_TOTAL)} 篇，当前已选 ${formatCount(conferenceStoredTotal)} 篇。`;
        } else if (selectedProfileCount < 1) {
          title = '请先在上方选择至少一个词条。';
        } else if (btn === quickRunConferenceBtn && !selectedConferenceYearPairs.size) {
          title = '请先选择至少一个会议年份。';
        } else {
          title = btn === quickRunConferenceBtn ? '请先选择至少一个会议年份。' : '请先选择至少一个词条。';
        }
      }
      btn.title = title;
    });
    if (quickRunHintEl) {
      quickRunHintEl.textContent = dailySelectedProfileCount > 0
        ? `已选 ${dailySelectedProfileCount} 个词条。`
        : '请选择至少一个词条。';
    }
    if (conferenceHintEl) {
      const confCount = selectedConferenceYearPairs.size;
      const profCount = selectedProfileCount;
      if (profCount > MAX_CONFERENCE_PROFILES) {
        conferenceHintEl.textContent = `会议检索最多选择 ${MAX_CONFERENCE_PROFILES} 个词条，当前已选 ${profCount} 个，请取消部分词条。`;
        conferenceHintEl.style.color = '#c00';
      } else if (conferenceTotalOverLimit) {
        conferenceHintEl.textContent = `会议年份库内总数需小于 ${formatCount(MAX_CONFERENCE_STORED_TOTAL)} 篇，当前已选 ${formatCount(conferenceStoredTotal)} 篇，请取消部分会议年份。`;
        conferenceHintEl.style.color = '#c00';
      } else if (confCount > 0 && profCount > 0) {
        const totalTasks = confCount * profCount;
        const estimate = estimateConferenceRetrieval(conferenceStoredTotal, profCount);
        conferenceHintEl.textContent = `${profCount} 个词条 × ${confCount} 个会议（库内约 ${formatCount(conferenceStoredTotal)} 篇，估算处理 ${formatCount(estimate.estimatedPapers)} 篇）= ${totalTasks} 组任务，预计耗时约 ${formatEstimateMinutes(estimate.minutes)} 分钟，费用约 ¥${estimate.cost.toFixed(2)}`;
        conferenceHintEl.style.color = '';
      } else if (confCount > 0 && profCount === 0) {
        conferenceHintEl.textContent = '请先在上方勾选词条（最多 2 个）。';
        conferenceHintEl.style.color = '';
      } else if (profCount > 0 && confCount === 0) {
        conferenceHintEl.textContent = `请勾选会议年份。库内总数需小于 ${formatCount(MAX_CONFERENCE_STORED_TOTAL)} 篇；每组任务约需 5 分钟，费用约 ¥0.2`;
        conferenceHintEl.style.color = '';
      } else {
        conferenceHintEl.textContent = `先勾选词条（最多 2 个），再勾选会议年份（库内总数 < ${formatCount(MAX_CONFERENCE_STORED_TOTAL)} 篇）。每组约 5 分钟 / ¥0.2`;
        conferenceHintEl.style.color = '';
      }
    }
    if (hasUnsavedChanges && quickRunMsgEl) {
      quickRunMsgEl.textContent = '有未保存修改，请先保存。';
      quickRunMsgEl.style.color = '#c00';
    }
    const conferenceMsgEl = document && typeof document.getElementById === 'function'
      ? document.getElementById('arxiv-admin-conference-run-msg')
      : null;
    if (hasUnsavedChanges && conferenceMsgEl) {
      conferenceMsgEl.textContent = '有未保存修改，请先保存。';
      conferenceMsgEl.style.color = '#c00';
    }
  };

  const clearQuickRunUnsavedMessage = () => {
    if (!quickRunMsgEl) return;
    if (/未保存修改|先保存|先点击/.test(quickRunMsgEl.textContent || '')) {
      quickRunMsgEl.textContent = '配置已保存，可以发起快速抓取。';
      quickRunMsgEl.style.color = '#080';
    }
    const conferenceMsgEl = document && typeof document.getElementById === 'function'
      ? document.getElementById('arxiv-admin-conference-run-msg')
      : null;
    if (conferenceMsgEl && /未保存修改|先保存|先点击/.test(conferenceMsgEl.textContent || '')) {
      conferenceMsgEl.textContent = '配置已保存，可以发起会议论文检索。';
      conferenceMsgEl.style.color = '#080';
    }
  };

  const setQuickRunMessage = (text, color) => {
    if (quickRunMsgEl) {
      quickRunMsgEl.textContent = text || '';
      quickRunMsgEl.style.color = color || '#666';
    }
    if (msgEl && msgEl !== quickRunMsgEl) {
      msgEl.textContent = text || '';
      msgEl.style.color = color || '#666';
    }
  };

  const syncAdminPanelTabs = () => {
    const active = activeAdminPanelTab === 'conference' ? 'conference' : 'daily';
    [
      [adminDailyTabBtn, active === 'daily'],
      [adminConferenceTabBtn, active === 'conference'],
    ].forEach(([btn, isActive]) => {
      if (!btn) return;
      btn.classList.toggle('is-active', !!isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    if (adminDailyPanel) {
      adminDailyPanel.hidden = active !== 'daily';
    }
    if (adminConferencePanel) {
      adminConferencePanel.hidden = active !== 'conference';
    }
    if (panel) {
      panel.classList.toggle('is-conference-tab', active === 'conference');
    }
  };

  const switchAdminPanelTab = (tab) => {
    const nextTab = tab === 'conference' ? 'conference' : 'daily';
    if (activeAdminPanelTab === nextTab) {
      syncAdminPanelTabs();
      return;
    }
    activeAdminPanelTab = nextTab;
    syncRunSelectionMode();
    syncAdminPanelTabs();
  };

  const runQuickFetch = async (days, msgEl, tipText, runOptions) => {
    if (hasUnsavedChanges) {
      const text = '检测到未保存修改，请先点击“保存”后再发起快速抓取。';
      if (msgEl) {
        msgEl.textContent = text;
        msgEl.style.color = '#c00';
      }
      setQuickRunMessage(text, '#c00');
      return false;
    }
    if (!window.DPRWorkflowRunner || typeof window.DPRWorkflowRunner.runQuickFetchByDays !== 'function') {
      const text = '工作流触发器未加载到当前页面。';
      if (msgEl) {
        msgEl.textContent = text;
        msgEl.style.color = '#c00';
      }
      setQuickRunMessage(text, '#c00');
      return false;
    }
    const options = runOptions && typeof runOptions === 'object' ? runOptions : {};
    const result = await window.DPRWorkflowRunner.runQuickFetchByDays(days, options);
    if (result === false) {
      const text = '工作流未成功触发，请检查权限或工作流配置。';
      if (msgEl) {
        msgEl.textContent = text;
        msgEl.style.color = '#c00';
      }
      setQuickRunMessage(text, '#c00');
      return false;
    }
    const finalTip = (typeof tipText === 'string' ? tipText : null) || `已发起 ${days} 天内抓取任务。`;
    if (msgEl) {
      msgEl.textContent = finalTip;
      msgEl.style.color = '#080';
    }
    setQuickRunMessage(finalTip, '#080');
    return true;
  };

  const runProfileQuickFetch = async (profileTag, days, runOptions) => {
    const normalizedTag = normalizeText(profileTag);
    if (!normalizedTag) {
      setQuickRunMessage('词条标签为空，无法发起单词条抓取。', '#c00');
      return false;
    }
    const options = runOptions && typeof runOptions === 'object' ? cloneDeep(runOptions) : {};
    const dispatchInputs = isPlainObject(options.dispatchInputs) ? options.dispatchInputs : {};
    options.dispatchInputs = {
      ...dispatchInputs,
      profile_tag: normalizedTag,
    };
    const fetchMode = normalizeText(options.fetchMode).toLowerCase();
    const modeText = fetchMode === 'standard'
      ? '30 天标准抓取任务'
      : (fetchMode === 'skims' ? '30 天速览抓取任务' : `${days} 天抓取任务`);
    const tip = `已发起词条「${normalizedTag}」的${modeText}。`;
    return runQuickFetch(days, quickRunMsgEl || msgEl, tip, options);
  };

  const runSelectedQuickFetch = async (days, runOptions = {}) => {
    const tags = getDailySelectedProfileTagsForRun();
    if (!tags.length) {
      setQuickRunMessage('请先勾选至少一个词条。快速抓取支持任意词条。', '#c00');
      refreshQuickRunButtons();
      return false;
    }
    const fetchMode = normalizeText(runOptions.fetchMode).toLowerCase();
    const modeText = fetchMode === 'standard'
      ? '30 天全标准 / 精读'
      : (fetchMode === 'skims' ? '30 天全速览' : `${days} 天`);
    const options = runOptions && typeof runOptions === 'object' ? cloneDeep(runOptions) : {};
    const dispatchInputs = isPlainObject(options.dispatchInputs) ? options.dispatchInputs : {};
    options.dispatchInputs = {
      ...dispatchInputs,
      profile_tag: tags.join(','),
    };
    const tip = `已对 ${tags.length} 个词条发起${modeText}抓取任务。`;
    const success = await runQuickFetch(days, quickRunMsgEl || msgEl, tip, options);
    if (success) showWorkflowSuccessEffects();
    return success;
  };
  const runSelectedQuickFetchByMode = () => {
    if (quickRunMode === '30-skims') {
      return runSelectedQuickFetch(30, { fetchMode: 'skims' });
    }
    if (quickRunMode === '30-standard') {
      return runSelectedQuickFetch(30, { fetchMode: 'standard' });
    }
    return runSelectedQuickFetch(10);
  };

  const runQuickConferenceRetrieval = async (msgEl) => {
    if (hasUnsavedChanges) {
      const text = '检测到未保存修改，请先点击“保存”后再发起会议论文检索。';
      if (msgEl) {
        msgEl.textContent = text;
        msgEl.style.color = '#c00';
      }
      setQuickRunMessage(text, '#c00');
      refreshQuickRunButtons();
      return false;
    }
    const profileTags = getSelectedProfileTagsForRun();
    if (!profileTags.length) {
      if (msgEl) {
        msgEl.textContent = '请先勾选至少一个词条。';
        msgEl.style.color = '#c00';
      }
      refreshQuickRunButtons();
      return false;
    }
    const selectedPairSpecs = getSelectedConferencePairSpecs();
    if (!selectedPairSpecs.length) {
      if (msgEl) {
        msgEl.textContent = '请先选择至少一个会议年份。';
        msgEl.style.color = '#c00';
      }
      return false;
    }
    const selectedStoredTotal = getSelectedConferenceStoredTotal();
    if (selectedStoredTotal >= MAX_CONFERENCE_STORED_TOTAL) {
      if (msgEl) {
        msgEl.textContent = `会议年份库内总数需小于 ${formatCount(MAX_CONFERENCE_STORED_TOTAL)} 篇，当前已选 ${formatCount(selectedStoredTotal)} 篇，请取消部分会议年份。`;
        msgEl.style.color = '#c00';
      }
      refreshQuickRunButtons();
      return false;
    }
    if (!window.DPRWorkflowRunner || typeof window.DPRWorkflowRunner.runConferenceRetrieval !== 'function') {
      if (msgEl) {
        msgEl.textContent = '工作流触发器未加载到当前页面。';
        msgEl.style.color = '#c00';
      }
      return false;
    }
    const selectedPairText = selectedPairSpecs.join(',');
    const selectedYears = getSelectedConferenceYearsForWorkflow();
    const success = await window.DPRWorkflowRunner.runConferenceRetrieval('unified', selectedYears, {
      dispatchInputs: {
        profile_tag: profileTags.join(','),
        conference_pairs: selectedPairText,
      },
    });
    if (success === false) {
      if (msgEl) {
        msgEl.textContent = '会议检索工作流未成功触发，请检查权限或配置。';
        msgEl.style.color = '#c00';
      }
      return false;
    }
    if (msgEl) {
      msgEl.textContent = `已发起 ${selectedPairSpecs.length} 个会议年份的统一会议论文检索任务。`;
      msgEl.style.color = '#080';
    }
    showWorkflowSuccessEffects();
    return true;
  };

  const runResetContent = (msgEl) => {
    if (String(window.DPR_ACCESS_MODE || '') !== 'full') {
      if (msgEl) {
        msgEl.textContent = '未检测到完整登录权限，危险操作未开启。';
        msgEl.style.color = '#c00';
      }
      return;
    }

    const confirmText = window.prompt(
      '危险区域：仅重置论文内容。会将 docs 备份为 docs_backup_xxx 后恢复为 docs_init，并清空 archive；不会删除配置、密钥或词条设置。输入「RESET_ALL」确认。',
    );
    if (confirmText !== 'RESET_ALL') {
      if (msgEl) {
        msgEl.textContent = '已取消危险操作。';
        msgEl.style.color = '#666';
      }
      return;
    }

    if (!window.DPRWorkflowRunner || typeof window.DPRWorkflowRunner.runWorkflowByKey !== 'function') {
      if (msgEl) {
        msgEl.textContent = '工作流触发器未加载到当前页面。';
        msgEl.style.color = '#c00';
      }
      return;
    }

    window.DPRWorkflowRunner.runWorkflowByKey('reset-content');
    if (msgEl) {
      msgEl.textContent = '已发起论文内容重置任务。';
      msgEl.style.color = '#080';
    }
  };

  const normalizeProfiles = (subs, availableSources) => {
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    return profiles
      .map((p, idx) => {
        if (!p || typeof p !== 'object') return null;
        const tag = deriveProfileTag(p, `profile-${idx + 1}`) || `profile-${idx + 1}`;
        const description = normalizeText(p.description || '');
        const enabled = p.enabled !== false;
        const fallbackToArxiv = !Object.prototype.hasOwnProperty.call(p, 'paper_sources');
        const paperSources = normalizePaperSources(p.paper_sources, { fallbackToArxiv });
        const keywordRules = (Array.isArray(p.keywords) ? p.keywords : []).map(normalizeKeywordItem).filter(Boolean);
        const normalizedKeywords = dedupeKeywords(keywordRules);
        const normalizedIntentQueries = normalizeIntentQueries(p.intent_queries);
        if (!keywordRules.length && !normalizedKeywords.length && !normalizedIntentQueries.length) {
          return null;
        }

        const result = {
          tag,
          description,
          enabled,
          paper_sources: paperSources,
          keywords: normalizedKeywords,
          intent_queries: normalizedIntentQueries,
          updated_at: normalizeText(p.updated_at) || new Date().toISOString(),
        };
        if ('paused' in p) {
          result.paused = !!p.paused;
        }
        if (p.temporary === true || p.conference_only === true || normalizeText(p.scope).toLowerCase() === 'conference') {
          result.scope = 'conference';
          result.temporary = true;
          result.conference_only = true;
        }
        return result;
      })
      .filter(Boolean);
  };

  const validateIntentProfiles = (config) => {
    const cfg = ensureSourceBackendsForProfiles(cloneDeep(config || {}));
    const subs = (cfg && cfg.subscriptions) || {};
    const availableSources = getAvailablePaperSources(cfg);
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    for (let idx = 0; idx < profiles.length; idx += 1) {
      const profile = profiles[idx];
      if (!profile || typeof profile !== 'object') continue;
      const tag = deriveProfileTag(profile, `profile-${idx + 1}`) || `profile-${idx + 1}`;
      const fallbackToArxiv = !Object.prototype.hasOwnProperty.call(profile, 'paper_sources');
      const paperSources = normalizePaperSources(profile.paper_sources, { fallbackToArxiv });
      const keywords = dedupeKeywords(
        (Array.isArray(profile.keywords) ? profile.keywords : [])
          .map(normalizeKeywordItem)
          .filter(Boolean),
      );
      const intentQueries = normalizeIntentQueries(profile.intent_queries);
      if (!paperSources.length) {
        return `词条「${tag}」至少需要 1 个论文源。`;
      }
      const unknownSources = paperSources.filter((item) => !availableSources.includes(item));
      if (unknownSources.length) {
        return `词条「${tag}」包含未配置的论文源：${unknownSources.join(', ')}。`;
      }
      if (!keywords.length) {
        return `词条「${tag}」至少需要 1 条关键词。`;
      }
      if (keywords.length > MAX_KEYWORDS_PER_PROFILE) {
        return `词条「${tag}」的关键词最多只能保留 ${MAX_KEYWORDS_PER_PROFILE} 条。`;
      }
      if (!intentQueries.length) {
        return `词条「${tag}」至少需要 1 条意图Query。`;
      }
      if (intentQueries.length > MAX_INTENT_QUERIES_PER_PROFILE) {
        return `词条「${tag}」的意图Query 最多只能保留 ${MAX_INTENT_QUERIES_PER_PROFILE} 条。`;
      }
    }
    return '';
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
      subs.intent_profiles = normalizeProfiles(subs, getAvailablePaperSources(next));

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
    ensureSourceBackendsForProfiles(next);
    return stripIntentProfileIds(next);
  };

  const setMessage = (text, color) => {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.color = color || '#666';
  };
  const updateSaveReminder = () => {
    if (!msgEl) return;
    if (hasUnsavedChanges) {
      msgEl.innerHTML = '<span class="dpr-save-reminder">⚠ 有未保存修改，请点击右上角「保存」。</span>';
      msgEl.style.color = '#9a6500';
    } else if (/未保存修改/.test(msgEl.textContent || '')) {
      setMessage('', '#666');
    }
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
          <div class="dpr-admin-header-left">
            <div style="font-weight:600;">后台管理</div>
            <div class="dpr-admin-tabs" role="tablist" aria-label="后台管理面板切换">
              <button
                id="dpr-admin-tab-daily"
                class="dpr-admin-tab is-active"
                type="button"
                role="tab"
                aria-selected="true"
                aria-controls="arxiv-search-quick-run-side"
              >
                日常管理
              </button>
              <button
                id="dpr-admin-tab-conference"
                class="dpr-admin-tab"
                type="button"
                role="tab"
                aria-selected="false"
                aria-controls="arxiv-conference-control-side"
              >
                会议论文
              </button>
            </div>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <button id="arxiv-config-save-btn" class="arxiv-tool-btn" style="padding:2px 10px; background:#2e7d32; color:white;">保存</button>
            <button id="arxiv-open-secret-setup-btn" class="arxiv-tool-btn" style="padding:2px 10px;">密钥配置</button>
            <button id="arxiv-search-close-btn" class="arxiv-tool-btn" style="padding:2px 6px;">关闭</button>
          </div>
        </div>

        <div id="arxiv-search-panel-body" class="dpr-admin-panel-body">
          <div id="arxiv-search-panel-main">
            <div id="dpr-smart-query-section" class="arxiv-pane dpr-smart-pane">
              <div class="dpr-display-card">
                <div id="dpr-sq-display" class="dpr-sq-display"></div>
                <div class="dpr-input-card">
                  <div class="dpr-inline-row">
                    <button id="dpr-sq-open-chat-btn" class="arxiv-tool-btn" style="background:#2e7d32; color:#fff;">新增</button>
                  </div>
                </div>
              </div>
            </div>

            <div id="dpr-smart-msg" style="font-size:12px; color:#666; margin-top:10px;">提示：修改后点击「保存」才会写入 config.yaml。</div>
          </div>

          <div id="arxiv-search-quick-run-divider" class="dpr-task-divider" aria-hidden="true"></div>

          <div
            id="arxiv-search-quick-run-side"
            class="dpr-admin-task-panel"
            role="tabpanel"
            aria-labelledby="dpr-admin-tab-daily"
          >
            <div class="dpr-bulk-bar-head">
              <div>
                <div class="chat-quick-run-title">快速抓取</div>
                <div id="arxiv-admin-quick-run-hint" class="dpr-task-hint">默认全选词条，快速抓取不区分日常状态。</div>
              </div>
              <button id="arxiv-admin-open-workflow-panel-btn" class="arxiv-tool-btn dpr-task-workflow-btn" type="button">打开工作流</button>
            </div>
            <div class="dpr-task-picker-tools">
              <button id="arxiv-admin-daily-select-all-btn" class="arxiv-tool-btn" type="button">全选</button>
              <button id="arxiv-admin-daily-clear-all-btn" class="arxiv-tool-btn" type="button">取消全选</button>
            </div>
            <div id="arxiv-admin-daily-profile-picker" class="dpr-profile-picker-row"></div>
            <div class="dpr-task-content-row">
              <div class="dpr-task-primary-column">
                <div class="dpr-task-action-grid dpr-task-action-grid--radio" role="radiogroup" aria-label="快速抓取模式">
                  <label class="chat-quick-run-item dpr-task-radio-card">
                    <input type="radio" name="dpr-quick-run-mode" value="10" checked>
                    <span class="dpr-task-action-title">立即抓取十天论文</span>
                    <span class="dpr-task-action-cost">约 ¥0.10</span>
                  </label>
                  <label class="chat-quick-run-item dpr-task-radio-card">
                    <input type="radio" name="dpr-quick-run-mode" value="30-skims">
                    <span class="dpr-task-action-title">立即抓取三十天速览</span>
                    <span class="dpr-task-action-cost">约 ¥0.20</span>
                  </label>
                  <label class="chat-quick-run-item dpr-task-radio-card">
                    <input type="radio" name="dpr-quick-run-mode" value="30-standard">
                    <span class="dpr-task-action-title">立即抓取三十天精读</span>
                    <span class="dpr-task-action-cost">约 ¥0.50</span>
                  </label>
                </div>
                <button id="arxiv-admin-quick-run-start-btn" class="chat-quick-run-run-btn dpr-task-start-btn" type="button">开始检索</button>
                <div id="arxiv-admin-quick-run-msg" class="chat-quick-run-msg"></div>
              </div>

              <div class="dpr-task-danger-module">
                <div class="chat-quick-run-title">危险区域</div>
                <div class="dpr-task-danger-desc">恢复初始论文；不删除设置</div>
                <button
                  id="arxiv-admin-reset-content-btn"
                  class="chat-quick-run-run-btn"
                  type="button"
                >
                  删除所有
                </button>
                <div id="arxiv-admin-reset-content-msg" class="chat-quick-run-msg"></div>
              </div>
            </div>
          </div>

          <div
            id="arxiv-conference-control-side"
            class="dpr-admin-task-panel"
            role="tabpanel"
            aria-labelledby="dpr-admin-tab-conference"
            hidden
          >
            <div class="dpr-conference-pane">
              <div class="dpr-bulk-bar-head">
                <div>
                  <div class="dpr-title-inline">
                    <div class="chat-quick-run-title">会议论文检索</div>
                    <div id="arxiv-admin-conference-hint" class="dpr-conference-note">默认全选词条。</div>
                  </div>
                </div>
              </div>

              <div class="dpr-task-picker-tools">
                <button id="arxiv-admin-conference-select-all-btn" class="arxiv-tool-btn" type="button">全选</button>
                <button id="arxiv-admin-conference-clear-all-btn" class="arxiv-tool-btn" type="button">取消全选</button>
              </div>
              <div id="arxiv-admin-conference-profile-picker" class="dpr-profile-picker-row"></div>

              <div class="dpr-choice-field">
                <div class="chat-quick-run-title">会议年份</div>
                <div id="arxiv-admin-conference-choice-group" class="dpr-conference-choice-grid"></div>
              </div>
              <button
                id="arxiv-admin-quick-run-conference-run-btn"
                class="chat-quick-run-run-btn dpr-task-start-btn"
                type="button"
              >
                开始检索
              </button>
              <div id="arxiv-admin-conference-run-msg" class="chat-quick-run-msg">
                触发 Supabase 会议检索。
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    panel = document.getElementById('arxiv-search-panel');

    saveBtn = document.getElementById('arxiv-config-save-btn');
    closeBtn = document.getElementById('arxiv-search-close-btn');
    msgEl = document.getElementById('dpr-smart-msg');
    adminDailyTabBtn = document.getElementById('dpr-admin-tab-daily');
    adminConferenceTabBtn = document.getElementById('dpr-admin-tab-conference');
    adminDailyPanel = document.getElementById('arxiv-search-quick-run-side');
    adminConferencePanel = document.getElementById('arxiv-conference-control-side');

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
    syncAdminPanelTabs();
  };

  const renderFromDraft = () => {
    const cfg = draftConfig || {};
    const subs = (cfg && cfg.subscriptions) || {};
    const profiles = Array.isArray(subs.intent_profiles) ? subs.intent_profiles : [];
    if (window.SubscriptionsSmartQuery && window.SubscriptionsSmartQuery.render) {
      window.SubscriptionsSmartQuery.render(profiles);
      syncRunSelectionMode();
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
      setMessage('', '#666');
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
      const toSave = normalizeSubscriptions(draftConfig || {});
      const validationError = validateIntentProfiles(toSave);
      if (validationError) {
        setMessage(validationError, '#c00');
        return;
      }
      setMessage('正在保存配置...', '#666');
      await window.SubscriptionsGithubToken.saveConfig(
        toSave,
        'chore: save smart query config from dashboard',
      );
      draftConfig = toSave;
      hasUnsavedChanges = false;
      refreshQuickRunButtons();
      clearQuickRunUnsavedMessage();
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
      syncRunSelectionMode();
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

    if (adminDailyTabBtn && !adminDailyTabBtn._bound) {
      adminDailyTabBtn._bound = true;
      adminDailyTabBtn.addEventListener('click', () => {
        switchAdminPanelTab('daily');
      });
    }

    if (adminConferenceTabBtn && !adminConferenceTabBtn._bound) {
      adminConferenceTabBtn._bound = true;
      adminConferenceTabBtn.addEventListener('click', () => {
        switchAdminPanelTab('conference');
      });
    }

    quickRun10dBtn = null;
    quickRun30dBtn = null;
    quickRun30dStandardBtn = null;
    quickRunStartBtn = document.getElementById('arxiv-admin-quick-run-start-btn');
    quickRunOpenWorkflowPanelBtn = document.getElementById('arxiv-admin-open-workflow-panel-btn');
    quickRunConferenceBtn = document.getElementById(
      'arxiv-admin-quick-run-conference-run-btn',
    );
    quickRunMsgEl = document.getElementById('arxiv-admin-quick-run-msg');
    quickRunSelectionCountEl = null;
    conferenceSelectionCountEl = null;
    quickRunHintEl = document.getElementById('arxiv-admin-quick-run-hint');
    conferenceHintEl = document.getElementById('arxiv-admin-conference-hint');
    dailyProfilePickerEl = document.getElementById('arxiv-admin-daily-profile-picker');
    conferenceProfilePickerEl = document.getElementById('arxiv-admin-conference-profile-picker');
    dailySelectAllBtn = document.getElementById('arxiv-admin-daily-select-all-btn');
    dailyClearAllBtn = document.getElementById('arxiv-admin-daily-clear-all-btn');
    conferenceSelectAllBtn = document.getElementById('arxiv-admin-conference-select-all-btn');
    conferenceClearAllBtn = document.getElementById('arxiv-admin-conference-clear-all-btn');
    resetContentBtn = document.getElementById('arxiv-admin-reset-content-btn');
    resetContentMsgEl = document.getElementById('arxiv-admin-reset-content-msg');
    if (quickRunConferenceBtn) {
      quickRunConferenceBtn.setAttribute('data-default-title', '一次性触发会议论文拉取任务');
      quickRunConferenceBtn.title = '一次性触发会议论文拉取任务';
    }
    initializeConferenceChoices();
    renderConferenceChoiceButtons();
    loadConferenceStatsSnapshot();
    if (quickRunStartBtn && !quickRunStartBtn.dataset.defaultTitle) {
      quickRunStartBtn.setAttribute('data-default-title', quickRunStartBtn.textContent || '');
    }
    refreshQuickRunButtons();

    if (quickRunStartBtn && !quickRunStartBtn._bound) {
      quickRunStartBtn._bound = true;
      quickRunStartBtn.addEventListener('click', () => {
        runSelectedQuickFetchByMode();
      });
    }

    document
      .querySelectorAll('input[name="dpr-quick-run-mode"]')
      .forEach((input) => {
        if (input._bound) return;
        input._bound = true;
        input.addEventListener('change', () => {
          if (input.checked) {
            quickRunMode = input.value || '10';
          }
        });
      });

    [
      [dailyProfilePickerEl, 'daily'],
      [conferenceProfilePickerEl, 'conference'],
    ].forEach(([picker]) => {
      if (!picker || picker._bound) return;
      picker._bound = true;
      picker.addEventListener('click', (event) => {
        const chip = event.target && event.target.closest
          ? event.target.closest('.dpr-profile-picker-chip[data-profile-id]')
          : null;
        if (!chip) return;
        const profileId = chip.getAttribute('data-profile-id') || '';
        const selected = chip.getAttribute('aria-pressed') !== 'true';
        setProfileSelection(profileId, selected);
      });
    });

    if (dailySelectAllBtn && !dailySelectAllBtn._bound) {
      dailySelectAllBtn._bound = true;
      dailySelectAllBtn.addEventListener('click', () => selectProfilesByMode('daily', true));
    }
    if (dailyClearAllBtn && !dailyClearAllBtn._bound) {
      dailyClearAllBtn._bound = true;
      dailyClearAllBtn.addEventListener('click', () => selectProfilesByMode('daily', false));
    }
    if (conferenceSelectAllBtn && !conferenceSelectAllBtn._bound) {
      conferenceSelectAllBtn._bound = true;
      conferenceSelectAllBtn.addEventListener('click', () => selectProfilesByMode('conference', true));
    }
    if (conferenceClearAllBtn && !conferenceClearAllBtn._bound) {
      conferenceClearAllBtn._bound = true;
      conferenceClearAllBtn.addEventListener('click', () => selectProfilesByMode('conference', false));
    }

    if (quickRunOpenWorkflowPanelBtn && !quickRunOpenWorkflowPanelBtn._bound) {
      quickRunOpenWorkflowPanelBtn._bound = true;
      quickRunOpenWorkflowPanelBtn.addEventListener('click', () => {
        try {
          if (window.DPRWorkflowRunner && typeof window.DPRWorkflowRunner.open === 'function') {
            window.DPRWorkflowRunner.open();
            return;
          }
        } catch (e) {
          console.error(e);
        }
        if (quickRunMsgEl) {
          quickRunMsgEl.textContent = '工作流触发面板未加载，请刷新页面后重试。';
          quickRunMsgEl.style.color = '#c00';
        }
      });
    }

    if (quickRunConferenceBtn && !quickRunConferenceBtn._bound) {
      quickRunConferenceBtn._bound = true;
      quickRunConferenceBtn.addEventListener('click', () => {
        const conferenceMsgEl = document.getElementById('arxiv-admin-conference-run-msg');
        runQuickConferenceRetrieval(conferenceMsgEl || quickRunMsgEl);
      });
    }

    const conferenceChoiceGroup = document.getElementById('arxiv-admin-conference-choice-group');
    if (conferenceChoiceGroup && !conferenceChoiceGroup._bound) {
      conferenceChoiceGroup._bound = true;
      conferenceChoiceGroup.addEventListener('click', (e) => {
        const btn = e.target && e.target.closest
          ? e.target.closest('[data-conference-year]')
          : null;
        if (!btn) return;
        const year = normalizeText(btn.getAttribute('data-conference-year') || '');
        const conference = normalizeText(btn.getAttribute('data-conference') || '');
        if (!year || !conference) return;
        if (!isConferenceYearSelectable(conference, year)) return;
        const key = `${conference}:${year}`;
        if (selectedConferenceYearPairs.has(key)) {
          selectedConferenceYearPairs.delete(key);
        } else {
          selectedConferenceYearPairs.add(key);
        }
        renderConferenceChoiceButtons();
        refreshQuickRunButtons();
      });
    }

    if (resetContentBtn && !resetContentBtn._bound) {
      resetContentBtn._bound = true;
      resetContentBtn.addEventListener('click', () => {
        runResetContent(resetContentMsgEl);
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
      updateSaveReminder();
    },
    updateDraftConfig: (updater) => {
      const base = draftConfig || {};
      const next = typeof updater === 'function' ? updater(cloneDeep(base)) || base : base;
      draftConfig = normalizeSubscriptions(next);
      hasUnsavedChanges = true;
      refreshQuickRunButtons();
      updateSaveReminder();
    },
    getDraftConfig: () => cloneDeep(draftConfig || {}),
    validateDraftConfig: () => validateIntentProfiles(draftConfig || {}),
    runProfileQuickFetch: (profileTag, days, runOptions) => runProfileQuickFetch(profileTag, days, runOptions),
    __test: {
      normalizeSubscriptions: (config) => normalizeSubscriptions(config),
      ensureSourceBackendsForProfiles: (config) => ensureSourceBackendsForProfiles(cloneDeep(config || {})),
      buildDefaultSourceBackend: (sourceKey, config) => buildDefaultSourceBackend(sourceKey, cloneDeep(config || {})),
      normalizePaperSources: (values, options) => normalizePaperSources(values, options),
      isConferenceYearSelectable: (conference, year) => isConferenceYearSelectable(conference, year),
      __setConferenceStatsSnapshot: (snapshot) => setConferenceStatsSnapshot(snapshot),
      __loadConferenceStatsSnapshot: () => loadConferenceStatsSnapshot(),
      __resetConferenceStatsLoadPromise: () => {
        conferenceStatsLoadPromise = null;
        setConferenceStatsSnapshot(null);
      },
      __buildConferenceChoiceRowsHtml: () => buildConferenceChoiceRowsHtml(),
      formatConferenceYearStatsLabel: (conference, year) => formatConferenceYearStatsLabel(conference, year),
      __setQuickRunMsgEl: (el) => {
        quickRunMsgEl = el || null;
      },
      __setQuickRunConferenceBtn: (el) => {
        quickRunConferenceBtn = el || null;
      },
      __setConferenceHintEl: (el) => {
        conferenceHintEl = el || null;
      },
      __setUnsavedChanges: (value) => {
        hasUnsavedChanges = !!value;
      },
      __setRunSelectionState: (value) => {
        selectedConferenceYearPairs.clear();
        (Array.isArray(value && value.conferencePairs) ? value.conferencePairs : []).forEach((item) => {
          const text = normalizeText(item);
          if (text) selectedConferenceYearPairs.add(text);
        });
      },
      __initializeConferenceChoices: () => initializeConferenceChoices(),
      __getSelectedConferenceYearPairs: () => Array.from(selectedConferenceYearPairs),
      runQuickConferenceRetrieval,
      runSelectedQuickFetch,
      refreshQuickRunButtons,
      clearQuickRunUnsavedMessage,
    },
  };
})();
