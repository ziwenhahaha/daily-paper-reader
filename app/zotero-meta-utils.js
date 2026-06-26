(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRZoteroMetaUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const L = (typeof window !== 'undefined' && window.LegacyPaperMarkers) || {};
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
          (L.DETAILED_SUMMARY && title.includes(L.DETAILED_SUMMARY)) ||
          title.includes('ai summary'),
      ),
      originalAbstractText: pickFirstSectionText(
        sections,
        (title) =>
          title === 'abstract' ||
          title.includes('original abstract') ||
          (L.ORIGINAL_ABSTRACT && title.includes(L.ORIGINAL_ABSTRACT)),
      ),
      tldrText: pickFirstSectionText(
        sections,
        (title) =>
          title.includes('tldr') ||
          title.includes('tl;dr') ||
          (L.TLDR_POINTS && title.includes(L.TLDR_POINTS)),
      ),
      legacyAbstractText: pickFirstSectionText(
        sections,
        (title) => L.ABSTRACT_SHORT && title === L.ABSTRACT_SHORT,
      ),
    };
  };

  return {
    stripFrontMatter,
    parseSections,
    getRawPaperSections,
  };
});
