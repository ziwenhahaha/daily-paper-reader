const assert = require('node:assert/strict');
const legacyPath = 'docs/starter-pack/20260912-abcdef123456/papers.md';
const standardPath = 'docs/20251125-20261124-starter-user-sim/papers.md';
let requests = 0;
let clipboardText = '';
let fallback = true;
let removed = 0;
global.window = {
  location: {href: 'https://example.test/repo/#/20251125-20261124-starter-user-sim/README', origin: 'https://example.test'},
  navigator: {clipboard: {writeText: async text => {clipboardText = text;}}},
  fetch: async () => {requests++; return {ok: true, text: async () => '# 最终清单\n' + Array.from({length: 50}, (_, i) => `- [Original ${i}](https://arxiv.org/abs/2609.${i})`).join('\n')};},
  document: {addEventListener() {}, activeElement: null, body: {appendChild() {}},
    execCommand: () => fallback,
    createElement: () => ({style: {}, setAttribute() {}, select() {}, remove() {removed++;}})},
};
const api = require('../app/topic-results.js');
(async () => {
  assert.equal(api.exportUrl(standardPath), 'https://example.test/repo/' + standardPath);
  assert.equal(api.exportUrl(legacyPath), 'https://example.test/repo/' + legacyPath);
  for (const bad of ['https://evil.test/papers.md', '../' + standardPath, 'javascript:alert(1)', standardPath + '?x=1', 'docs/starter-pack/../papers.md']) assert.throws(() => api.exportUrl(bad));
  const [a, b] = await Promise.all([api.loadList(standardPath), api.loadList(standardPath)]);
  assert.equal(a, b);
  assert.equal(requests, 1);
  await api.copyText(a);
  assert.equal(clipboardText.split('\n').length, 51);
  assert.ok(clipboardText.includes('Original 49'));
  window.navigator.clipboard.writeText = async () => {throw Error('denied');};
  await api.copyText(a);
  fallback = false;
  await assert.rejects(api.copyText(a), /浏览器拒绝复制/);
  assert.equal(removed, 2);
  await assert.rejects(api.continueContent('bad'), /任务标识无效/);
  await assert.rejects(api.continueContent('20260912-abcdef123456'), /一次全部生成完整内容/);
  console.log('topic results tests passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
