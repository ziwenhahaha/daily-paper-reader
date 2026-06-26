/**
 * Legacy config field readers for profiles generated before English localization.
 * Legacy key names are centralized here so the rest of the codebase stays English-only.
 */
(function (root) {
  const LEGACY_NOTE_KEYS = [
    'note',
    'logic_cn',
    'keyword_cn',
    'query_cn',
    'keyword_zh',
    'query_zh',
    'zh',
  ];
  const LEGACY_TITLE_ALT_KEYS = ['title_alt', 'title_zh'];

  function readFirstString(obj, keys) {
    if (!obj || typeof obj !== 'object') return '';
    for (const key of keys) {
      const val = String(obj[key] || '').trim();
      if (val) return val;
    }
    return '';
  }

  function readNote(item) {
    return readFirstString(item, LEGACY_NOTE_KEYS);
  }

  function readTitleAlt(meta) {
    return readFirstString(meta, LEGACY_TITLE_ALT_KEYS);
  }

  root.LegacyConfigFields = {
    readNote,
    readTitleAlt,
  };
})(typeof window !== 'undefined' ? window : globalThis);
