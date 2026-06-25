(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRZoteroMetaUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const normalize = (value) => String(value || '').replace(/\r\n/g, '\n').trim();

  const stripFrontMatter = (content) => {
    const text = String(content || '').replace(/\r\n/g, '\n');
    if (!text.startsWith('---\n')) return text;
    const endIdx = text.indexOf('\n---\n', 4);
    if (endIdx === -1) return text;
    return text.slice(endIdx + 5).trim();
  };

  const parseSections = (content) => {
    const body = stripFrontMatter(content);
    const lines = body.split('\n');
    const sections = [];
    let currentTitle = '';
    let buffer = [];

    const flush = () => {
      if (!currentTitle) return;
      const text = buffer.join('\n').trim();
      sections.push({ title: currentTitle, text });
      buffer = [];
    };

    for (const line of lines) {
      const match = line.match(/^#{1,6}\s+(.*)$/);
      if (match) {
        flush();
        currentTitle = normalize(match[1]).toLowerCase();
        continue;
      }
      buffer.push(line);
    }
    flush();
    return sections;
  };

  const pickFirstSectionText = (sections, matcher) => {
    for (const section of sections) {
      if (matcher(section.title)) {
        return normalize(section.text);
      }
    }
    return '';
  };

  const getRawPaperSections = (rawContent) => {
    const sections = parseSections(rawContent);
    return {
      aiSummaryText: pickFirstSectionText(
        sections,
        (title) =>
          title.includes('detailed summary') ||
          title.includes('论文详细总结') ||
          title.includes('ai summary'),
      ),
      originalAbstractText: pickFirstSectionText(
        sections,
        (title) =>
          title === 'abstract' ||
          title.includes('original abstract') ||
          title.includes('原文摘要'),
      ),
      tldrText: pickFirstSectionText(
        sections,
        (title) => title.includes('tldr') || title.includes('tl;dr') || title.includes('摘要要点'),
      ),
      chineseAbstractText: pickFirstSectionText(
        sections,
        (title) => title === '摘要',
      ),
    };
  };

  return {
    stripFrontMatter,
    parseSections,
    getRawPaperSections,
  };
});
