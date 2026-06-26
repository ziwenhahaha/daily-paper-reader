(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRGistShareUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const normalizeText = (value) => String(value || '').replace(/\r\n/g, '\n').trim();

  const parseInlineArray = (value) => {
    const text = normalizeText(value);
    if (!text.startsWith('[') || !text.endsWith(']')) return [];
    const inner = text.slice(1, -1);
    const items = [];
    let current = '';
    let inQuote = false;
    let quoteChar = '';
    for (let i = 0; i < inner.length; i += 1) {
      const ch = inner[i];
      if (!inQuote && (ch === '"' || ch === "'")) {
        inQuote = true;
        quoteChar = ch;
        current += ch;
        continue;
      }
      if (inQuote && ch === quoteChar) {
        inQuote = false;
        current += ch;
        continue;
      }
      if (!inQuote && ch === ',') {
        if (current.trim()) items.push(current.trim());
        current = '';
        continue;
      }
      current += ch;
    }
    if (current.trim()) items.push(current.trim());
    return items.map((item) => item.replace(/^["']|["']$/g, '').trim()).filter(Boolean);
  };

  const parseSimpleFrontMatter = (yamlText) => {
    const meta = {};
    const lines = String(yamlText || '').replace(/\r\n/g, '\n').split('\n');
    let blockKey = '';
    for (const line of lines) {
      const raw = String(line || '');
      if (blockKey) {
        if (/^\s+/.test(raw)) {
          continue;
        }
        blockKey = '';
      }
      if (!raw.trim()) continue;
      if (/^\s/.test(raw)) continue;
      const colonIdx = raw.indexOf(':');
      if (colonIdx === -1) continue;
      const key = raw.slice(0, colonIdx).trim();
      let value = raw.slice(colonIdx + 1).trim();
      if (!key) continue;
      if (value === '|' || value === '>') {
        meta[key] = '';
        blockKey = key;
        continue;
      }
      if (value.startsWith('[') && value.endsWith(']')) {
        meta[key] = parseInlineArray(value);
        continue;
      }
      meta[key] = value.replace(/^["']|["']$/g, '').replace(/\\"/g, '"');
    }
    return meta;
  };

  const stripFrontMatter = (content) => {
    const text = String(content || '').replace(/\r\n/g, '\n');
    if (!text.startsWith('---\n')) {
      return { meta: null, body: text };
    }
    const endIdx = text.indexOf('\n---\n', 4);
    if (endIdx === -1) {
      return { meta: null, body: text };
    }
    const yamlText = text.slice(4, endIdx);
    const body = text.slice(endIdx + 5).trim();
    return {
      meta: parseSimpleFrontMatter(yamlText),
      body,
    };
  };

  const readTitleAlt = (meta) => {
    const reader = globalThis.LegacyConfigFields
      || (typeof window !== 'undefined' ? window.LegacyConfigFields : null);
    if (reader && typeof reader.readTitleAlt === 'function') {
      return normalizeText(reader.readTitleAlt(meta));
    }
    return normalizeText((reader && reader.readTitleAlt && reader.readTitleAlt(meta)) || '');
  };

  const buildMetaSection = (meta, pageUrl, generatedAt) => {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const titleAlt = readTitleAlt(safeMeta);
    const title = normalizeText(safeMeta.title);
    const heading = titleAlt || title || 'Paper Share';
    const subtitle = titleAlt && title ? title : '';
    const tags = Array.isArray(safeMeta.tags) ? safeMeta.tags : [];

    const lines = [];
    lines.push(`# ${heading}`);
    if (subtitle) {
      lines.push('');
      lines.push(`_${subtitle}_`);
    }
    lines.push('');
    if (safeMeta.authors) lines.push(`- **Authors**: ${String(safeMeta.authors).trim()}`);
    if (safeMeta.date) lines.push(`- **Date**: ${String(safeMeta.date).trim()}`);
    if (safeMeta.pdf) lines.push(`- **PDF**: ${String(safeMeta.pdf).trim()}`);
    if (tags.length) lines.push(`- **Tags**: ${tags.join(', ')}`);
    if (safeMeta.evidence) lines.push(`- **Evidence**: ${String(safeMeta.evidence).trim()}`);
    if (safeMeta.tldr) lines.push(`- **TLDR**: ${String(safeMeta.tldr).trim()}`);
    if (pageUrl) lines.push(`- **Source page**: ${pageUrl}`);
    if (generatedAt) lines.push(`- **Generated at**: ${generatedAt}`);
    return lines.join('\n').trim();
  };

  const buildChatSection = (chatMessages) => {
    const parts = [];
    parts.push('---');
    parts.push('');
    parts.push('## 💬 Chat History (local records)');
    parts.push('');
    if (!chatMessages || !chatMessages.length) {
      parts.push('No conversation yet.');
      return parts.join('\n');
    }
    chatMessages.forEach((message) => {
      const role = message && message.role ? String(message.role) : 'unknown';
      const time = message && message.time ? String(message.time) : '';
      const content = message && message.content ? String(message.content) : '';
      if (role === 'thinking') {
        parts.push('<details>');
        parts.push(`<summary>🧠 Thinking ${time ? `(${time})` : ''}</summary>`);
        parts.push('');
        parts.push('```');
        parts.push(content);
        parts.push('```');
        parts.push('</details>');
        parts.push('');
        return;
      }
      const label = role === 'ai' ? '🤖 AI' : role === 'user' ? '👤 You' : role;
      parts.push(`### ${label}${time ? ` (${time})` : ''}`);
      parts.push(content);
      parts.push('');
    });
    return parts.join('\n').trimEnd();
  };

  const buildShareMarkdown = ({ paperId, pageMd, chatMessages, origin, generatedAt }) => {
    const parts = [];
    const pageUrl = paperId ? `${String(origin || '').replace(/\/+$/, '')}/#/${paperId}` : '';
    const parsed = stripFrontMatter(pageMd || '');

    parts.push('<!-- Shared by Daily Paper Reader -->');
    parts.push('');
    parts.push(buildMetaSection(parsed.meta, pageUrl, generatedAt || new Date().toISOString()));
    parts.push('');
    parts.push('---');
    parts.push('');
    parts.push(parsed.body || String(pageMd || '').trim());
    parts.push('');
    parts.push(buildChatSection(chatMessages));
    return parts.join('\n').trim();
  };

  return {
    parseSimpleFrontMatter,
    stripFrontMatter,
    buildShareMarkdown,
  };
});
