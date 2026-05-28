const assert = require('node:assert/strict');

global.window = global.window || {};
global.document = global.document || {
  readyState: 'loading',
  addEventListener() {},
};

require('../app/subscriptions.smart-query.js');

const {
  buildPromptFromTemplate,
  containsCjk,
  defaultPromptTemplate,
  deriveTagFromCandidates,
  isEnglishRetrievalText,
  normalizeGenerated,
  sanitizeAutoTag,
} = global.window.SubscriptionsSmartQuery.__test;

function testPromptRequiresEnglishRetrievalFieldsAndChineseCnFields() {
  const prompt = buildPromptFromTemplate('RL', '强化学习算法对比', defaultPromptTemplate);

  assert.match(prompt, /keyword and query MUST be English retrieval text only/);
  assert.match(prompt, /keyword_cn and query_cn MUST be Chinese/);
  assert.match(prompt, /The query field MUST be English only/);
  assert.match(prompt, /Do NOT output acronym-only/);
  assert.match(prompt, /meaningful atomic noun phrases/);
  assert.match(prompt, /standalone adjective\/modifier keywords/);
  assert.match(prompt, /hyphen-separated words/);
  assert.match(prompt, /English words or an English acronym only/);
  assert.match(prompt, /at most 12 characters/);
}

function testSuggestedTagIsEnglishAndAtMostTwelveChars() {
  assert.equal(sanitizeAutoTag('reinforcement learning algorithms'), 'rla');
  assert.equal(sanitizeAutoTag('RL_optimization 2026'), 'ro');
  assert.equal(sanitizeAutoTag('强化学习'), '');
  assert.equal(sanitizeAutoTag('强化学习 RL'), 'RL');
  assert.equal(
    deriveTagFromCandidates({
      tag: '强化学习',
      keywords: [{ keyword: 'reinforcement learning', query: 'reinforcement learning algorithms comparison' }],
    }),
    'rl',
  );
  assert.equal(sanitizeAutoTag('verylongsingleword'), 'verylongsing');
}

function testGeneratedCandidatesKeepChineseOutOfRetrievalFields() {
  const normalized = normalizeGenerated({
    tag: 'RL',
    description: '强化学习算法对比',
    keywords: [
      {
        keyword: '强化学习',
        query: '强化学习算法对比',
        keyword_cn: '强化学习',
      },
      {
        keyword: 'reinforcement learning',
        query: '强化学习算法对比',
        keyword_cn: '强化学习',
      },
      {
        keyword: 'policy gradient',
        query: 'policy gradient methods',
        keyword_cn: '策略梯度',
      },
    ],
    intent_queries: [
      {
        query: '强化学习入门教程',
        query_cn: '强化学习入门教程',
      },
      {
        query: 'reinforcement learning algorithms comparison',
        query_cn: '强化学习算法对比',
      },
    ],
  });

  assert.deepEqual(
    normalized.keywords.map((item) => item.keyword),
    ['reinforcement learning', 'policy gradient'],
  );
  assert.deepEqual(
    normalized.keywords.map((item) => item.query),
    ['reinforcement learning', 'policy gradient methods'],
  );
  assert.deepEqual(
    normalized.intent_queries.map((item) => item.query),
    ['reinforcement learning algorithms comparison'],
  );
  normalized.keywords.forEach((item) => {
    assert.equal(containsCjk(item.keyword), false);
    assert.equal(containsCjk(item.query), false);
    assert.equal(isEnglishRetrievalText(item.query), true);
  });
  normalized.intent_queries.forEach((item) => {
    assert.equal(containsCjk(item.query), false);
    assert.equal(isEnglishRetrievalText(item.query), true);
  });
}

function testGeneratedCandidatesDropWeakAcronymKeywords() {
  const normalized = normalizeGenerated({
    tag: 'RL',
    description: '强化学习方程发现',
    keywords: [
      { keyword: 'rl', query: 'reinforcement learning equation discovery', keyword_cn: '强化学习方程发现' },
      { keyword: 'xrl', query: 'explainable reinforcement learning symbolic regression', keyword_cn: '可解释强化学习符号回归' },
      { keyword: 'reinforcement learning driven', query: 'reinforcement learning driven equation discovery', keyword_cn: '强化学习驱动' },
      { keyword: 'reinforcement learning', query: 'reinforcement learning equation discovery', keyword_cn: '强化学习' },
    ],
    intent_queries: [
      { query: 'rl', query_cn: '强化学习' },
      { query: 'explainable reinforcement learning for symbolic regression', query_cn: '可解释强化学习符号回归' },
    ],
  });

  assert.deepEqual(
    normalized.keywords.map((item) => item.keyword),
    ['reinforcement learning'],
  );
  assert.deepEqual(
    normalized.intent_queries.map((item) => item.query),
    ['explainable reinforcement learning for symbolic regression'],
  );
}

function testGeneratedCandidatesDoNotCollapseConceptToSingleModifier() {
  const normalized = normalizeGenerated({
    tag: 'xrl-sr',
    description: '可解释强化学习驱动符号回归方程发现',
    keywords: [
      { keyword: 'explainable reinforcement learning', query: 'explainable reinforcement learning for symbolic regression', keyword_cn: '可解释强化学习' },
      { keyword: 'reinforcement learning', query: 'reinforcement learning equation discovery', keyword_cn: '强化学习' },
      { keyword: 'symbolic regression', query: 'symbolic regression equation discovery', keyword_cn: '符号回归' },
      { keyword: 'explainable', query: 'explainable reinforcement learning', keyword_cn: '可解释强化学习' },
    ],
  });

  assert.deepEqual(
    normalized.keywords.map((item) => item.keyword),
    ['explainable reinforcement learning', 'reinforcement learning', 'symbolic regression'],
  );
}

function testProfileSelectionPersistsAcrossRerender() {
  const smartQuery = global.window.SubscriptionsSmartQuery;
  smartQuery.render([
    { tag: 'selection-a', description: 'A' },
    { tag: 'selection-b', description: 'B' },
  ]);
  assert.deepEqual(
    smartQuery.getSelectedProfileTags(),
    ['selection-a', 'selection-b'],
  );

  smartQuery.setProfileSelection('selection-b', false);
  assert.deepEqual(smartQuery.getSelectedProfileTags(), ['selection-a']);

  smartQuery.render([
    { tag: 'selection-a', description: 'A updated' },
    { tag: 'selection-b', description: 'B updated' },
  ]);
  assert.deepEqual(smartQuery.getSelectedProfileTags(), ['selection-a']);

  smartQuery.render([
    { tag: 'selection-a', description: 'A updated' },
    { tag: 'selection-b', description: 'B updated' },
    { tag: 'selection-c', description: 'C new' },
  ]);
  assert.deepEqual(
    smartQuery.getSelectedProfileTags(),
    ['selection-a', 'selection-c'],
  );
}

testPromptRequiresEnglishRetrievalFieldsAndChineseCnFields();
testSuggestedTagIsEnglishAndAtMostTwelveChars();
testGeneratedCandidatesKeepChineseOutOfRetrievalFields();
testGeneratedCandidatesDropWeakAcronymKeywords();
testGeneratedCandidatesDoNotCollapseConceptToSingleModifier();
testProfileSelectionPersistsAcrossRerender();

console.log('subscriptions smart query tests passed');
