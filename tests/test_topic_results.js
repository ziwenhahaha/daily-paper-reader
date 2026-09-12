const assert = require('node:assert/strict');
const path = 'docs/starter-pack/20260912-abcdef123456/papers.md';
let requests = 0;
let clipboardText = '';
let fallback = true;
let removed = 0;
global.window = {
  location: {href: 'https://example.test/repo/#/starter-pack/run/catalog', origin: 'https://example.test'},
  navigator: {clipboard: {writeText: async text => {clipboardText = text;}}},
  fetch: async () => {requests++; return {ok: true, text: async () => '# 最终清单\n' + Array.from({length: 100}, (_, i) => `- [Original ${i}](https://arxiv.org/abs/2609.${i})`).join('\n')};},
  document: {addEventListener() {}, activeElement: null, body: {appendChild() {}},
    execCommand: () => fallback,
    createElement: () => ({style: {}, setAttribute() {}, select() {}, remove() {removed++;}})},
};
const api = require('../app/topic-results.js');
(async () => {
  assert.equal(api.exportUrl(path), 'https://example.test/repo/' + path);
  for (const bad of ['https://evil.test/papers.md', '../' + path, 'javascript:alert(1)', path + '?x=1', 'docs/starter-pack/../papers.md']) assert.throws(() => api.exportUrl(bad));
  const [a, b] = await Promise.all([api.loadList(path), api.loadList(path)]);
  assert.equal(a, b);
  assert.equal(requests, 1);
  await api.copyText(a);
  assert.equal(clipboardText.split('\n').length, 101);
  assert.ok(clipboardText.includes('Original 99'));
  window.navigator.clipboard.writeText = async () => {throw Error('denied');};
  await api.copyText(a);
  fallback = false;
  await assert.rejects(api.copyText(a), /浏览器拒绝复制/);
  assert.equal(removed, 2);
  await assert.rejects(api.continueContent('bad'), /任务标识无效/);
  await assert.rejects(api.continueContent('20260912-abcdef123456'), /入口尚未加载/);
  window.DPRTopicResearch = {continueContent: async () => undefined};
  await assert.rejects(api.continueContent('20260912-abcdef123456'), /未确认任务已提交/);
  let run;
  window.DPRTopicResearch.continueContent = async id => {run = id; return {ok: true};};
  await api.continueContent('20260912-abcdef123456');
  assert.equal(run, '20260912-abcdef123456');
  console.log('topic results tests passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
