const assert = require('node:assert/strict');
global.window = {};
require('../app/workflows.runner.js');
const api = window.DPRWorkflowRunner.__test;
const base = { profile_tag: 'ATSP', as_of: '2026-09-11', conferences: ['icml', 'icml'], max_new_reviews: 1000, content_limit: 12 };
const result = api.buildStarterPackRequest(base);
assert.equal(result.key, 'starter-pack');
assert.equal(result.inputs.conferences, 'icml');
assert.equal(result.inputs.as_of, base.as_of);
assert.equal(result.inputs.max_new_reviews, '1000');
assert.equal(result.inputs.content_limit, '12');
assert.ok(!('fetch_days' in result.inputs));
assert.ok(api.buildStarterPackRequest({ ...base, conferences: [] }).inputs.conferences.includes('sosp'));
assert.equal(api.buildStarterPackRequest({ ...base, max_new_reviews: 0 }).inputs.max_new_reviews, '0');
for (const invalid of [{ profile_tag: '' }, { profile_tag: 'ATSP,SR' }, { as_of: '2026-02-30' }, { as_of: '' }, { conferences: ['invalid'] }, { max_new_reviews: -1 }, { max_new_reviews: 5001 }, { max_new_reviews: '1abc' }, { content_limit: 0 }, { content_limit: 21 }, { content_limit: 1.2 }]) {
  assert.throws(() => api.buildStarterPackRequest({ ...base, ...invalid }));
}
let profiles = [{ tag: 'ATSP' }];
let confirmation = '';
let dispatched = [];
const elements = {
  'arxiv-admin-starter-pack-as-of': { value: '2026-09-11' },
  'arxiv-admin-starter-pack-budget': { value: '1000' },
  'arxiv-admin-starter-pack-content-limit': { value: '12' },
  'arxiv-admin-starter-pack-msg': { textContent: '', style: {} },
};
global.document = { readyState: 'loading', addEventListener() {}, getElementById: id => elements[id] || null };
window.location = { hostname: 'example.github.io' };
window.SubscriptionsSmartQuery = { getSelectedProfilesForRun: () => profiles };
window.confirm = text => { confirmation = text; return true; };
window.DPRWorkflowRunner.runWorkflowByKey = async (key, inputs) => { dispatched.push({ key, inputs }); return true; };
global.fetch = () => { throw new Error('Tests must not dispatch a paid workflow'); };
require('../app/subscriptions.manager.js');
const manager = window.SubscriptionsManager.__test;
(async () => {
  manager.__setUnsavedChanges(true);
  assert.equal(await manager.runStarterPack(), false);
  manager.__setUnsavedChanges(false);
  profiles = [{ tag: 'ATSP' }, { tag: 'SR' }];
  assert.equal(await manager.runStarterPack(), false);
  profiles = [{ tag: 'ATSP' }];
  window.location.hostname = 'localhost';
  assert.equal(await manager.runStarterPack(), false);
  assert.ok(elements['arxiv-admin-starter-pack-msg'].textContent.includes('GitHub Pages'));
  window.location.hostname = 'example.github.io';
  assert.equal(dispatched.length, 0);
  manager.__setRunSelectionState({ conferencePairs: ['icml:2024', 'icml:2025'] });
  assert.equal(await manager.runStarterPack(), true);
  assert.equal(dispatched[0].key, 'starter-pack');
  assert.equal(dispatched[0].inputs.conferences, 'icml');
  assert.equal(dispatched[0].inputs.as_of, '2026-09-11');
  assert.ok(confirmation.includes('近365天 arXiv + 近24个月会议'));
  assert.ok(confirmation.includes('内容生成仍可能调用模型'));
  assert.ok(!('fetch_days' in dispatched[0].inputs));
  elements['arxiv-admin-starter-pack-as-of'].value = '2026-09-01';
  assert.equal(await manager.runStarterPack(), true);
  assert.equal(dispatched[1].inputs.as_of, '2026-09-01');
  window.confirm = () => false;
  assert.equal(await manager.runStarterPack(), false);
  assert.equal(dispatched.length, 2);
  console.log('starter pack workflow tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
