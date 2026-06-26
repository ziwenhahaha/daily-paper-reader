const assert = require('node:assert/strict');

global.window = global.window || {};
global.document = global.document || {
  readyState: 'loading',
  addEventListener() {},
};

require('../app/legacy-config-fields.js');
require('../app/subscriptions.smart-query.js');

const {
  buildPromptFromTemplate,
  containsNonEnglishScript,
  defaultPromptTemplate,
  deriveTagFromCandidates,
  isEnglishRetrievalText,
  normalizeGenerated,
  sanitizeAutoTag,
} = global.window.SubscriptionsSmartQuery.__test;

const NON_ENGLISH_SAMPLE = {
  RL: '\u5f3a\u5316\u5b66\u4e60',
  RL_ALG: '\u5f3a\u5316\u5b66\u4e60\u7b97\u6cd5\u5bf9\u6bd4',
  POLICY_GRAD: '\u7b56\u7565\u68af\u5ea6',
  RL_TUTORIAL: '\u5f3a\u5316\u5b66\u4e60\u5165\u95e8\u6559\u7a0b',
  RL_EQ: '\u5f3a\u5316\u5b66\u4e60\u65b9\u7a0b\u53d1\u73b0',
  XRL_SR: '\u53ef\u89e3\u91ca\u5f3a\u5316\u5b66\u4e60\u7b26\u53f7\u56de\u5f52',
  RL_DRIVEN: '\u5f3a\u5316\u5b66\u4e60\u9a71\u52a8',
  XRL: '\u53ef\u89e3\u91ca\u5f3a\u5316\u5b66\u4e60',
  SR: '\u7b26\u53f7\u56de\u5f52',
  XRL_SR_EQ: '\u53ef\u89e3\u91ca\u5f3a\u5316\u5b66\u4e60\u9a71\u52a8\u7b26\u53f7\u56de\u5f52\u65b9\u7a0b\u53d1\u73b0',
};

function testPromptRequiresEnglishRetrievalFieldsAndOptionalNotes() {
  const prompt = buildPromptFromTemplate('RL', NON_ENGLISH_SAMPLE.RL_ALG, defaultPromptTemplate);

  assert.match(prompt, /keyword and query MUST be English retrieval text only/);
  assert.match(prompt, /note is an optional English description or explanation/);
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
  assert.equal(sanitizeAutoTag(NON_ENGLISH_SAMPLE.RL), '');
  assert.equal(sanitizeAutoTag(`${NON_ENGLISH_SAMPLE.RL} RL`), 'RL');
  assert.equal(
    deriveTagFromCandidates({
      tag: NON_ENGLISH_SAMPLE.RL,
      keywords: [{ keyword: 'reinforcement learning', query: 'reinforcement learning algorithms comparison' }],
    }),
    'rl',
  );
  assert.equal(sanitizeAutoTag('verylongsingleword'), 'verylongsing');
}

function testGeneratedCandidatesKeepNonEnglishOutOfRetrievalFields() {
  const normalized = normalizeGenerated({
    tag: 'RL',
    description: NON_ENGLISH_SAMPLE.RL_ALG,
    keywords: [
      {
        keyword: NON_ENGLISH_SAMPLE.RL,
        query: NON_ENGLISH_SAMPLE.RL_ALG,
        note: NON_ENGLISH_SAMPLE.RL,
      },
      {
        keyword: 'reinforcement learning',
        query: NON_ENGLISH_SAMPLE.RL_ALG,
        note: NON_ENGLISH_SAMPLE.RL,
      },
      {
        keyword: 'policy gradient',
        query: 'policy gradient methods',
        note: NON_ENGLISH_SAMPLE.POLICY_GRAD,
      },
    ],
    intent_queries: [
      {
        query: NON_ENGLISH_SAMPLE.RL_TUTORIAL,
        note: NON_ENGLISH_SAMPLE.RL_TUTORIAL,
      },
      {
        query: 'reinforcement learning algorithms comparison',
        note: NON_ENGLISH_SAMPLE.RL_ALG,
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
    assert.equal(containsNonEnglishScript(item.keyword), false);
    assert.equal(containsNonEnglishScript(item.query), false);
    assert.equal(isEnglishRetrievalText(item.query), true);
  });
  normalized.intent_queries.forEach((item) => {
    assert.equal(containsNonEnglishScript(item.query), false);
    assert.equal(isEnglishRetrievalText(item.query), true);
  });
}

function testGeneratedCandidatesDropWeakAcronymKeywords() {
  const normalized = normalizeGenerated({
    tag: 'RL',
    description: NON_ENGLISH_SAMPLE.RL_EQ,
    keywords: [
      { keyword: 'rl', query: 'reinforcement learning equation discovery', note: NON_ENGLISH_SAMPLE.RL_EQ },
      { keyword: 'xrl', query: 'explainable reinforcement learning symbolic regression', note: NON_ENGLISH_SAMPLE.XRL_SR },
      { keyword: 'reinforcement learning driven', query: 'reinforcement learning driven equation discovery', note: NON_ENGLISH_SAMPLE.RL_DRIVEN },
      { keyword: 'reinforcement learning', query: 'reinforcement learning equation discovery', note: NON_ENGLISH_SAMPLE.RL },
    ],
    intent_queries: [
      { query: 'rl', note: NON_ENGLISH_SAMPLE.RL },
      { query: 'explainable reinforcement learning for symbolic regression', note: NON_ENGLISH_SAMPLE.XRL_SR },
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
    description: NON_ENGLISH_SAMPLE.XRL_SR_EQ,
    keywords: [
      { keyword: 'explainable reinforcement learning', query: 'explainable reinforcement learning for symbolic regression', note: NON_ENGLISH_SAMPLE.XRL },
      { keyword: 'reinforcement learning', query: 'reinforcement learning equation discovery', note: NON_ENGLISH_SAMPLE.RL },
      { keyword: 'symbolic regression', query: 'symbolic regression equation discovery', note: NON_ENGLISH_SAMPLE.SR },
      { keyword: 'explainable', query: 'explainable reinforcement learning', note: NON_ENGLISH_SAMPLE.XRL },
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

  smartQuery.setProfileSelection('selection-a', false);
  smartQuery.setProfileSelection('selection-b', true);
  assert.deepEqual(smartQuery.getSelectedProfileTags(), ['selection-b']);
}

function testLegacyConfigFieldsReadOldNoteKeys() {
  const reader = global.window.LegacyConfigFields;
  assert.equal(reader.readNote({ note: 'current' }), 'current');
  assert.equal(reader.readNote({ logic_cn: 'legacy note' }), 'legacy note');
  assert.equal(reader.readTitleAlt({ title_alt: 'alt title' }), 'alt title');
  assert.equal(reader.readTitleAlt({ title_zh: 'legacy alt' }), 'legacy alt');
}

testPromptRequiresEnglishRetrievalFieldsAndOptionalNotes();
testSuggestedTagIsEnglishAndAtMostTwelveChars();
testGeneratedCandidatesKeepNonEnglishOutOfRetrievalFields();
testGeneratedCandidatesDropWeakAcronymKeywords();
testGeneratedCandidatesDoNotCollapseConceptToSingleModifier();
testProfileSelectionPersistsAcrossRerender();
testLegacyConfigFieldsReadOldNoteKeys();
console.log('subscriptions smart query tests passed');
