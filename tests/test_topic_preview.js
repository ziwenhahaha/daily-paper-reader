const assert = require('node:assert/strict');
const api = require('../app/topic-preview.js');
const t = api.__test;
assert.deepEqual(t.englishGroups({ keywords: [{ keyword: 'RL', query: 'offline reinforcement learning' }] }), [['RL']]);
assert.deepEqual(t.englishGroups({ keywords: [{ query: 'offline reinforcement learning' }] }), [['offline reinforcement learning']]);
const config = { supabase_shared: { url: 'https://example.invalid', anon_key: 'sb_publishable_test' } };
const options = { profile: { keywords: ['ATSP', 'asymmetric TSP'] }, mode: '90', asOf: '2026-09-12', config };
let calls = [];
function mock(values) {
  calls = []; t.clearCache();
  global.fetch = async (url, init) => {
    calls.push({ url, init });
    if (!values.length) throw new Error('unexpected request');
    const value = values.shift();
    return { status: 200, headers: { get: () => value } };
  };
}
(async () => {
  mock(['0-0/600', '0-0/500', '0-0/100']);
  let result = await api.preview(options);
  assert.equal(result.status, 'exact'); assert.equal(result.count, 1200);
  assert.equal(calls.length, 3); assert.equal(calls[0].init.method, 'HEAD');
  assert.equal(calls[0].init.headers.Prefer, 'count=exact');
  assert.equal(calls[0].init.headers.Authorization, undefined);
  await api.preview(options); assert.equal(calls.length, 3);
  mock(['0-0/1501']); result = await api.preview(options);
  assert.equal(result.status, 'lower_bound'); assert.equal(calls.length, 1);
  mock(['0-999/*']); result = await api.preview(options);
  assert.equal(result.status, 'unknown'); assert.equal(result.count, null);
  mock(Array(13).fill('*/0')); result = await api.preview({ ...options, mode: 'starter' });
  assert.equal(result.status, 'partial'); assert.equal(result.coverage.arxiv.status, 'exact');
  assert.equal(result.coverage.conference.status, 'unavailable');
  mock([]); result = await api.preview({ ...options, profile: { keywords: ['强化学习'] } });
  assert.equal(result.status, 'unknown'); assert.equal(calls.length, 0);
  const groups = t.englishGroups({ constraint_groups: [['ATSP', 'asymmetric TSP'], ['approximation']] });
  assert.equal((t.countFilter(groups, 'a', 'b').match(/or\(/g) || []).length, 2);
  assert.ok(t.countFilter([['a"),evil']], 'a', 'b').includes('\\"'));
  assert.equal(t.scopeFor('starter', '2024-02-29').conference.start, '2022-02-28');
  assert.throws(() => t.scopeFor('90', '2026-02-30'));
  assert.equal(t.publicKey('sb_secret_test'), false);
  const secretJwt = 'a.' + Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url') + '.z';
  assert.equal(t.publicKey(secretJwt), false);
  assert.ok(!JSON.stringify(result).includes('sb_publishable'));
  mock(['0-0/400']); result = await api.preview({ ...options, threshold: 300 });
  assert.equal(result.threshold, 300); assert.equal(result.status, 'lower_bound');
  const oldCalls = calls.length;
  global.fetch = async () => { calls.push({}); return { status: 200, headers: { get: () => '0-0/400' } }; };
  result = await api.preview({ ...options, threshold: 1500 });
  assert.equal(result.status, 'exact'); assert.equal(calls.length, oldCalls + 3);
  assert.equal(t.previewThreshold(undefined, { topic_research: { preview_threshold: 300 } }), 300);
  for (const invalid of [0, 10001, true, '1abc', NaN, 1.5]) {
    result = await api.preview({ ...options, threshold: invalid });
    assert.equal(result.status, 'unknown'); assert.equal(result.threshold, null);
  }
  for (const groups of [[['ATSP'], ['ATSP'], ['ATSP'], ['ATSP']], [Array(9).fill('a')], [Array(4).fill('a'), Array(3).fill('b'), Array(3).fill('c')]]) assert.throws(() => t.englishGroups({ constraint_groups: groups }));
  assert.equal(t.englishGroups({ keywords: Array.from({ length: 24 }, (_, i) => 'word' + i) })[0].length, 24);
  assert.throws(() => t.englishGroups({ keywords: Array.from({ length: 25 }, (_, i) => 'word' + i) }));
  console.log('topic preview tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
