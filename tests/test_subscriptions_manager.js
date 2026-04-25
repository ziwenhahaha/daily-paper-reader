const assert = require('node:assert/strict');

global.window = global.window || {};
global.document = global.document || {
  readyState: 'loading',
  addEventListener() {},
};

require('../app/subscriptions.manager.js');

const { normalizeSubscriptions } = global.window.SubscriptionsManager.__test;

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

function testRunProfileQuickFetchPassesProfileTagToWorkflow() {
  const calls = [];
  global.window.DPRWorkflowRunner = {
    runQuickFetchByDays(days, options) {
      calls.push({ days, options });
    },
  };

  const ok = global.window.SubscriptionsManager.runProfileQuickFetch('GENE', 30, {
    fetchMode: 'skims',
  });

  assert.equal(ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].days, 30);
  assert.equal(calls[0].options.fetchMode, 'skims');
  assert.equal(calls[0].options.dispatchInputs.profile_tag, 'GENE');
}

testNormalizeSubscriptionsAddsBiorxivBackend();
testNormalizeSubscriptionsPreservesCustomBiorxivBackendFields();
testRunProfileQuickFetchPassesProfileTagToWorkflow();

console.log('subscriptions manager tests passed');
