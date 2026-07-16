const assert = require('node:assert/strict');

global.window = global.window || {};
global.document = global.document || {
  readyState: 'loading',
  addEventListener() {},
};

require('../app/subscriptions.manager.js');

const {
  normalizeSubscriptions,
  isConferenceYearSelectable,
  refreshQuickRunButtons,
  clearQuickRunUnsavedMessage,
  __setQuickRunMsgEl,
  __setQuickRunConferenceBtn,
  __setConferenceHintEl,
  __setUnsavedChanges,
  __setRunSelectionState,
  __initializeConferenceChoices,
  __getSelectedConferenceYearPairs,
  __setConferenceStatsSnapshot,
  __loadConferenceStatsSnapshot,
  __resetConferenceStatsLoadPromise,
  __buildConferenceChoiceRowsHtml,
  formatConferenceYearStatsLabel,
  runQuickConferenceRetrieval,
  runSelectedQuickFetch,
} = global.window.SubscriptionsManager.__test;

function buildBaseConfig() {
  return {
    supabase_shared: {
      kind: 'supabase',
      enabled: true,
      url: 'https://example.supabase.co',
      anon_key: 'sb_publishable_demo',
      schema: 'public',
    },
    source_backends: {
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
    },
    subscriptions: {
      schema_migration: {
        stage: 'A',
        diff_threshold_pct: 15,
      },
      keyword_recall_mode: 'or',
      intent_profiles: [
        {
          tag: 'GENE',
          description: '遗传学',
          enabled: true,
          paper_sources: ['biorxiv'],
          keywords: [
            {
              keyword: 'genetics',
              query: 'fundamental principles and study of genetics',
            },
          ],
          intent_queries: [
            {
              query: 'latest preprints in genetics',
            },
          ],
        },
      ],
    },
  };
}

function testNormalizeSubscriptionsAddsBiorxivBackend() {
  const normalized = normalizeSubscriptions(buildBaseConfig());
  const backend = normalized.source_backends.biorxiv;

  assert.ok(backend, '应自动补齐 biorxiv backend');
  assert.equal(backend.kind, 'supabase');
  assert.equal(backend.enabled, true);
  assert.equal(backend.url, 'https://example.supabase.co');
  assert.equal(backend.anon_key, 'sb_publishable_demo');
  assert.equal(backend.schema, 'public');
  assert.equal(backend.papers_table, 'biorxiv_papers');
  assert.equal(backend.vector_rpc, 'match_biorxiv_papers_exact');
  assert.equal(backend.vector_rpc_exact, 'match_biorxiv_papers_exact');
  assert.equal(backend.bm25_rpc, 'match_biorxiv_papers_bm25');
}

function testNormalizeSubscriptionsPreservesCustomBiorxivBackendFields() {
  const config = buildBaseConfig();
  config.source_backends.biorxiv = {
    enabled: false,
    papers_table: 'custom_biorxiv_papers',
    bm25_rpc: 'custom_match_biorxiv_papers_bm25',
    extra_flag: 'keep-me',
  };

  const normalized = normalizeSubscriptions(config);
  const backend = normalized.source_backends.biorxiv;

  assert.equal(backend.enabled, false);
  assert.equal(backend.papers_table, 'custom_biorxiv_papers');
  assert.equal(backend.bm25_rpc, 'custom_match_biorxiv_papers_bm25');
  assert.equal(backend.extra_flag, 'keep-me');
  assert.equal(backend.url, 'https://example.supabase.co');
  assert.equal(backend.anon_key, 'sb_publishable_demo');
  assert.equal(backend.vector_rpc, 'match_biorxiv_papers_exact');
  assert.equal(backend.vector_rpc_exact, 'match_biorxiv_papers_exact');
}

function testNormalizeSubscriptionsConvertsChineseTagToEnglishFallback() {
  const config = buildBaseConfig();
  config.subscriptions.intent_profiles[0].tag = '强化学习';
  config.subscriptions.intent_profiles[0].keywords = [
    {
      keyword: 'reinforcement learning',
      query: 'reinforcement learning algorithms comparison',
    },
  ];
  config.subscriptions.intent_profiles[0].intent_queries = [
    {
      query: 'policy gradient reinforcement learning',
    },
  ];

  const normalized = normalizeSubscriptions(config);
  assert.equal(normalized.subscriptions.intent_profiles[0].tag, 'rl');
}

async function testRunProfileQuickFetchPassesProfileTagToWorkflow() {
  const calls = [];
  global.window.DPRWorkflowRunner = {
    runQuickFetchByDays(days, options) {
      calls.push({ days, options });
    },
  };
  global.window.confirm = () => true;

  const ok = await global.window.SubscriptionsManager.runProfileQuickFetch('GENE', 30, {
    fetchMode: 'skims',
  });

  assert.equal(ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].days, 30);
  assert.equal(calls[0].options.fetchMode, 'skims');
  assert.equal(calls[0].options.dispatchInputs.profile_tag, 'GENE');
}

function testConferenceCurrentYearDisabledForPendingSources() {
  const currentYear = String(new Date().getFullYear());
  const previousYear = String(new Date().getFullYear() - 1);

  // Pending current year: NeurIPS is disabled for current year.
  assert.equal(isConferenceYearSelectable('NeurIPS', currentYear), false);
  assert.equal(isConferenceYearSelectable('NIPS', currentYear), false);
  assert.equal(isConferenceYearSelectable('NeurIPS', previousYear), true);
  assert.equal(isConferenceYearSelectable('NIPS', previousYear), true);
  // 2026 available sources are explicitly whitelisted; pending/future sources stay disabled
  assert.equal(isConferenceYearSelectable('ICLR', currentYear), true);
  assert.equal(isConferenceYearSelectable('ICML', currentYear), true);
  assert.equal(isConferenceYearSelectable('AAAI', currentYear), true);
  assert.equal(isConferenceYearSelectable('ACL', currentYear), true);
  assert.equal(isConferenceYearSelectable('OSDI', currentYear), true);
  assert.equal(isConferenceYearSelectable('IEEE S&P', currentYear), true);
  assert.equal(isConferenceYearSelectable('CVPR', currentYear), false);
  assert.equal(isConferenceYearSelectable('ECCV', currentYear), false);
  assert.equal(isConferenceYearSelectable('IJCAI', currentYear), false);
  // ECCV biennial: odd years disabled
  assert.equal(isConferenceYearSelectable('ECCV', '2024'), true);
  assert.equal(isConferenceYearSelectable('ECCV', '2025'), false);
  assert.equal(isConferenceYearSelectable('ECCV', '2023'), false);
}

function testConferenceDefaultYearOnlySelects2025() {
  __setRunSelectionState({ conferencePairs: [] });
  __initializeConferenceChoices();
  const pairs = __getSelectedConferenceYearPairs().sort();
  // 不再默认勾选，由用户手动选择
  assert.deepEqual(pairs, []);
}

function testConferenceYearChoicesShowTwoDigitYearAndStoredTotalOnly() {
  __setRunSelectionState({ conferencePairs: ['ICLR:2025'] });
  __setConferenceStatsSnapshot({
    generated_at: '2026-06-30T00:00:00Z',
    items: [
      {
        conference_key: 'iclr',
        conference_label: 'ICLR',
        year: 2025,
        official_accepted_count: 379,
        stored_total_count: 401,
        stored_accepted_count: 379,
        stored_rejected_count: 22,
      },
      {
        conference_key: 'icml',
        conference_label: 'ICML',
        year: 2026,
        official_accepted_count: 6341,
        stored_total_count: 6555,
        stored_accepted_count: 6341,
        stored_rejected_count: 214,
      },
      {
        conference_key: 'acl',
        conference_label: 'ACL',
        year: 2026,
        official_accepted_count: 4459,
        stored_total_count: 4459,
        stored_accepted_count: 4459,
        stored_rejected_count: 0,
      },
    ],
  });

  assert.equal(formatConferenceYearStatsLabel('ICLR', '2025'), '25 (401)');
  const html = __buildConferenceChoiceRowsHtml();
  assert.ok(html.includes('ICLR'));
  assert.ok(html.includes('25 (401)'));
  assert.ok(html.includes('class="dpr-choice-year">25</span>'));
  assert.ok(html.includes('class="dpr-choice-total">401</span>'));
  assert.equal(html.includes('拒稿'), false);
  assert.equal(html.includes('379'), false);
  assert.ok(html.includes('aria-pressed="true"'));
  assert.equal((html.match(/is-featured-conference-year/g) || []).length, 2);
  assert.equal((html.match(/dpr-choice-feature-star/g) || []).length, 2);
}

async function testConferenceStatsLoadReusesBootstrappedJsonPromise() {
  const oldFetch = global.fetch;
  let fetchCalls = 0;
  global.fetch = () => {
    fetchCalls += 1;
    return Promise.reject(new Error('late fetch should not be used'));
  };
  global.window.DPR_ASSET_JSON_PROMISES = {
    'app/conference-stats.json': Promise.resolve({
      items: [
        { conference_key: 'iclr', year: 2025, stored_total_count: 321 },
      ],
    }),
  };
  __resetConferenceStatsLoadPromise();

  await __loadConferenceStatsSnapshot();

  assert.equal(fetchCalls, 0);
  assert.equal(formatConferenceYearStatsLabel('ICLR', '2025'), '25 (321)');

  delete global.window.DPR_ASSET_JSON_PROMISES;
  __resetConferenceStatsLoadPromise();
  global.fetch = oldFetch;
}

function testQuickRunUnsavedMessageClearsAfterSave() {
  const msgEl = {
    textContent: '',
    style: {
      color: '',
    },
  };
  __setQuickRunMsgEl(msgEl);
  __setUnsavedChanges(true);
  refreshQuickRunButtons();
  assert.equal(msgEl.textContent, '有未保存修改，请先保存。');
  assert.equal(msgEl.style.color, '#c00');

  __setUnsavedChanges(false);
  refreshQuickRunButtons();
  clearQuickRunUnsavedMessage();
  assert.equal(msgEl.textContent, '配置已保存，可以发起快速抓取。');
  assert.equal(msgEl.style.color, '#080');
}

function buildMockButton() {
  const classes = new Set();
  return {
    disabled: false,
    title: '',
    textContent: '开始检索',
    getAttribute(name) {
      if (name === 'data-default-title') return '一次性触发会议论文拉取任务';
      return '';
    },
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
      contains(name) {
        return classes.has(name);
      },
    },
  };
}

function testConferenceRunDisabledWhenUnsaved() {
  const btn = buildMockButton();
  global.window.SubscriptionsSmartQuery = {
    getSelectedProfileTags() {
      return ['GENE'];
    },
  };
  __setQuickRunConferenceBtn(btn);
  __setRunSelectionState({ conference: true, conferencePairs: ['ICML:2025'] });
  __setUnsavedChanges(true);
  refreshQuickRunButtons();

  assert.equal(btn.disabled, true);
  assert.equal(btn.classList.contains('chat-quick-run-item--disabled'), true);
  assert.equal(btn.title, '请先保存后再检索会议论文。');

  __setUnsavedChanges(false);
  refreshQuickRunButtons();

  assert.equal(btn.disabled, false);
  assert.equal(btn.classList.contains('chat-quick-run-item--disabled'), false);
  assert.equal(btn.title, '一次性触发会议论文拉取任务');
  __setQuickRunConferenceBtn(null);
  __setRunSelectionState({});
  delete global.window.SubscriptionsSmartQuery;
}

function testConferenceRunAllowsMoreThanFiveYearsWhenStoredTotalUnderLimit() {
  const btn = buildMockButton();
  const hintEl = { textContent: '', style: { color: '' } };
  global.window.SubscriptionsSmartQuery = {
    getSelectedProfileTags() {
      return ['GENE'];
    },
  };
  __setConferenceStatsSnapshot({
    items: [
      { conference_key: 'aaai', year: 2026, stored_total_count: 1000 },
      { conference_key: 'aaai', year: 2025, stored_total_count: 1000 },
      { conference_key: 'aaai', year: 2024, stored_total_count: 1000 },
      { conference_key: 'acl', year: 2025, stored_total_count: 1000 },
      { conference_key: 'acl', year: 2024, stored_total_count: 1000 },
      { conference_key: 'ndss', year: 2026, stored_total_count: 1000 },
    ],
  });
  __setQuickRunConferenceBtn(btn);
  __setConferenceHintEl(hintEl);
  __setRunSelectionState({
    conferencePairs: ['AAAI:2026', 'AAAI:2025', 'AAAI:2024', 'ACL:2025', 'ACL:2024', 'NDSS:2026'],
  });
  __setUnsavedChanges(false);
  refreshQuickRunButtons();

  assert.equal(btn.disabled, false);
  assert.equal(hintEl.textContent.includes('最多同时选择 5 个会议年份'), false);
  assert.equal(hintEl.textContent.includes('库内约 6,000 篇'), true);
  assert.equal(hintEl.textContent.includes('预计耗时约 3 分钟'), true);
  assert.equal(hintEl.textContent.includes('费用约 ¥0.12'), true);
  assert.equal(hintEl.textContent.includes('6 组任务，预计耗时约 30 分钟'), false);

  __setQuickRunConferenceBtn(null);
  __setConferenceHintEl(null);
  __setRunSelectionState({});
  delete global.window.SubscriptionsSmartQuery;
}

function testConferenceRunDisabledWhenSelectedStoredTotalReachesLimit() {
  const btn = buildMockButton();
  const hintEl = { textContent: '', style: { color: '' } };
  global.window.SubscriptionsSmartQuery = {
    getSelectedProfileTags() {
      return ['GENE'];
    },
  };
  __setConferenceStatsSnapshot({
    items: [
      { conference_key: 'iclr', year: 2025, stored_total_count: 20000 },
      { conference_key: 'neurips', year: 2025, stored_total_count: 10000 },
    ],
  });
  __setQuickRunConferenceBtn(btn);
  __setConferenceHintEl(hintEl);
  __setRunSelectionState({ conferencePairs: ['ICLR:2025', 'NeurIPS:2025'] });
  __setUnsavedChanges(false);
  refreshQuickRunButtons();

  assert.equal(btn.disabled, true);
  assert.equal(btn.title, '会议年份库内总数需小于 30,000 篇，当前已选 30,000 篇。');
  assert.equal(hintEl.textContent, '会议年份库内总数需小于 30,000 篇，当前已选 30,000 篇，请取消部分会议年份。');
  assert.equal(hintEl.style.color, '#c00');

  __setQuickRunConferenceBtn(null);
  __setConferenceHintEl(null);
  __setRunSelectionState({});
  delete global.window.SubscriptionsSmartQuery;
}

async function testQuickFetchIncludesAnySelectedProfile() {
  const calls = [];
  const msgEl = {
    textContent: '',
    style: {
      color: '',
    },
  };
  global.window.DPRWorkflowRunner = {
    runQuickFetchByDays(days, options) {
      calls.push({ days, options });
    },
  };
  global.window.SubscriptionsSmartQuery = {
    getSelectedProfilesForRun() {
      return [
        { tag: 'ACTIVE', temporary: false, paused: false },
        { tag: 'PAUSED', temporary: false, paused: true },
        { tag: 'CONF', temporary: true, paused: false },
      ];
    },
  };
  __setQuickRunMsgEl(msgEl);
  __setUnsavedChanges(false);

  assert.equal(await runSelectedQuickFetch(10), true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.dispatchInputs.profile_tag, 'ACTIVE,PAUSED,CONF');

  global.window.SubscriptionsSmartQuery.getSelectedProfilesForRun = () => [
    { tag: 'PAUSED', temporary: false, paused: true },
    { tag: 'CONF', temporary: true, paused: false },
  ];
  assert.equal(await runSelectedQuickFetch(10), true);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].options.dispatchInputs.profile_tag, 'PAUSED,CONF');

  __setQuickRunMsgEl(null);
  delete global.window.DPRWorkflowRunner;
  delete global.window.SubscriptionsSmartQuery;
  delete global.window.confirm;
}

async function testConferenceRetrievalDispatchesUnifiedConferencePairs() {
  const calls = [];
  const msgEl = { textContent: '', style: { color: '' } };
  __setConferenceStatsSnapshot({
    items: [
      { conference_key: 'iclr', year: 2025, stored_total_count: 1000 },
      { conference_key: 'neurips', year: 2024, stored_total_count: 1000 },
      { conference_key: 'ieee_sp', year: 2026, stored_total_count: 1000 },
    ],
  });
  __setRunSelectionState({ conferencePairs: ['ICLR:2025', 'NeurIPS:2024', 'IEEE S&P:2026'] });
  __setUnsavedChanges(false);
  global.window.SubscriptionsSmartQuery = {
    getSelectedProfileTags() {
      return ['GENE'];
    },
  };
  global.window.DPRWorkflowRunner = {
    runConferenceRetrieval(conference, years, options) {
      calls.push({ conference, years, options });
      return true;
    },
  };

  assert.equal(await runQuickConferenceRetrieval(msgEl), true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].conference, 'unified');
  assert.deepEqual(calls[0].years, ['2026', '2025', '2024']);
  assert.equal(calls[0].options.dispatchInputs.conference_pairs, 'ieee_sp:2026,iclr:2025,neurips:2024');
  assert.equal(calls[0].options.dispatchInputs.profile_tag, 'GENE');

  __setRunSelectionState({});
  delete global.window.DPRWorkflowRunner;
  delete global.window.SubscriptionsSmartQuery;
}

(async () => {
  testNormalizeSubscriptionsAddsBiorxivBackend();
  testNormalizeSubscriptionsPreservesCustomBiorxivBackendFields();
  testNormalizeSubscriptionsConvertsChineseTagToEnglishFallback();
  await testRunProfileQuickFetchPassesProfileTagToWorkflow();
  testConferenceCurrentYearDisabledForPendingSources();
  testConferenceDefaultYearOnlySelects2025();
  testConferenceYearChoicesShowTwoDigitYearAndStoredTotalOnly();
  await testConferenceStatsLoadReusesBootstrappedJsonPromise();
  testQuickRunUnsavedMessageClearsAfterSave();
  testConferenceRunDisabledWhenUnsaved();
  testConferenceRunAllowsMoreThanFiveYearsWhenStoredTotalUnderLimit();
  testConferenceRunDisabledWhenSelectedStoredTotalReachesLimit();
  await testQuickFetchIncludesAnySelectedProfile();
  await testConferenceRetrievalDispatchesUnifiedConferencePairs();

  console.log('subscriptions manager tests passed');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
