const assert = require('node:assert/strict');

const {
  stripFrontMatter,
  buildShareMarkdown,
} = require('../app/gist-share-utils.js');

const samplePageMarkdown = `---
title: Attention Is All You Need
authors: "Ashish Vaswani, Noam Shazeer"
date: 20170612
pdf: "https://arxiv.org/pdf/1706.03762v1"
tags: ["query:transformer", "query:attention"]
evidence: Proposes the Transformer, a pure-attention architecture.
tldr: A classic paper.
abstract_en: |
  The dominant sequence transduction models...
---

## Abstract
English abstract content.
`;

function testStripFrontMatter() {
  const parsed = stripFrontMatter(samplePageMarkdown);
  assert.equal(parsed.meta.title, 'Attention Is All You Need');
  assert.deepEqual(parsed.meta.tags, ['query:transformer', 'query:attention']);
  assert.ok(parsed.body.startsWith('## Abstract'));
  assert.ok(!parsed.body.startsWith('---'));
}

function testBuildShareMarkdownRemovesFrontMatterAndBuildsHeader() {
  const output = buildShareMarkdown({
    paperId: '201706/12/1706.03762v1-attention-is-all-you-need',
    pageMd: samplePageMarkdown,
    chatMessages: [
      { role: 'user', time: '10:00', content: 'What is the core contribution of this paper?' },
      { role: 'ai', time: '10:01', content: 'The core idea is the Transformer.' },
    ],
    origin: 'https://ziwenhahaha.github.io/daily-paper-reader',
    generatedAt: '2026-03-09T08:00:00.000Z',
  });

  assert.ok(output.includes('# Attention Is All You Need'));
  assert.ok(output.includes('- **PDF**: https://arxiv.org/pdf/1706.03762v1'));
  assert.ok(output.includes('## Abstract'));
  assert.ok(output.includes('## 💬 Chat History (local records)'));
  assert.ok(!output.includes('\n---\ntitle:'));
  assert.ok(!output.includes('\ntitle: Attention Is All You Need\n'));
}

testStripFrontMatter();
testBuildShareMarkdownRemovesFrontMatterAndBuildsHeader();

console.log('gist share markdown tests passed');
