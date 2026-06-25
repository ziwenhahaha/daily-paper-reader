const assert = require('node:assert/strict');

const { getRawPaperSections } = require('../app/zotero-meta-utils.js');

const sample = `---
title: Attention Is All You Need
---

## 📝 TLDR
This is the tldr.

## Abstract
This is the original abstract in English.

## Detailed Summary (auto-generated)
This is ai summary.
`;

const sections = getRawPaperSections(sample);

assert.equal(sections.tldrText, 'This is the tldr.');
assert.equal(sections.originalAbstractText, 'This is the original abstract in English.');
assert.equal(sections.aiSummaryText, 'This is ai summary.');

console.log('zotero meta utils tests passed');
