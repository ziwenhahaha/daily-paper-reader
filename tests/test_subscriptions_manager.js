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
  __setUnsavedChanges,
  __setRunSelectionState,
  __initializeConferenceChoices,
  __getSelectedConferenceYearPairs,
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

  assert.equal(isConferenceYearSelectable('NeurIPS', currentYear), false);
  assert.equal(isConferenceYearSelectable('NIPS', currentYear), false);
  assert.equal(isConferenceYearSelectable('ICML', currentYear), false);
  assert.equal(isConferenceYearSelectable('NeurIPS', previousYear), true);
  assert.equal(isConferenceYearSelectable('NIPS', previousYear), true);
  assert.equal(isConferenceYearSelectable('ICML', previousYear), true);
}

function testConferenceDefaultYearOnlySelects2025() {
  __setRunSelectionState({ conferencePairs: [] });
  __initializeConferenceChoices();
  const pairs = __getSelectedConferenceYearPairs().sort();
  assert.deepEqual(pairs, ['ICML:2025', 'NeurIPS:2025']);
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

(async () => {
  testNormalizeSubscriptionsAddsBiorxivBackend();
  testNormalizeSubscriptionsPreservesCustomBiorxivBackendFields();
  testNormalizeSubscriptionsConvertsChineseTagToEnglishFallback();
  await testRunProfileQuickFetchPassesProfileTagToWorkflow();
  testConferenceCurrentYearDisabledForPendingSources();
  testConferenceDefaultYearOnlySelects2025();
  testQuickRunUnsavedMessageClearsAfterSave();
  testConferenceRunDisabledWhenUnsaved();
  await testQuickFetchIncludesAnySelectedProfile();

  console.log('subscriptions manager tests passed');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
