(function (root) {
  'use strict';
  const THRESHOLD = 1500;
  const cache = new Map();
  const inflight = new Map();
  const enabled = value => value == null || !['false', '0', 'no', 'off'].includes(String(value).toLowerCase());
  function englishGroups(profile) {
    let groups = profile.constraint_groups;
    if (groups != null) {
      if (!Array.isArray(groups) || !groups.length || groups.some(g => !Array.isArray(g) || !g.length)) throw new Error('英文约束无效');
    } else {
      groups = [(profile.keywords || []).filter(x => typeof x === 'string' || (x && enabled(x.enabled))).map(x => typeof x === 'string' ? x : x.keyword || x.query || x.text || '')];
    }
    if (profile.constraint_groups != null && (groups.length > 3 || groups.some(g => g.length > 8) || groups.reduce((n, g) => n * g.length, 1) > 32)) throw new Error('约束超出预览预算');
    if (profile.constraint_groups == null && groups[0].length > 24) throw new Error('关键词超出预览预算');
    return groups.map(group => {
      const terms = group.map(value => {
        const text = typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : '';
        if (!/[A-Za-z]/.test(text) || /[^\x20-\x7e]/.test(text) || text.length > 240) throw new Error('需要英文关键词');
        return text;
      });
      if (!terms.length) throw new Error('需要英文关键词');
      return Array.from(new Set(terms));
    });
  }
  function scopeFor(mode, asOf) {
    if (!['90', '365', 'starter'].includes(mode) || !/^\d{4}-\d{2}-\d{2}$/.test(asOf || '')) throw new Error('范围无效');
    const end = new Date(asOf + 'T00:00:00Z');
    if (!Number.isFinite(end.getTime()) || end.toISOString().slice(0, 10) !== asOf) throw new Error('日期无效');
    const start = new Date(end.getTime() - (mode === '90' ? 90 : 365) * 86400000);
    const scope = { mode, arxiv: { start: start.toISOString().slice(0, 10), end_exclusive: asOf } };
    if (mode === 'starter') {
      const year = end.getUTCFullYear() - 2, month = end.getUTCMonth();
      const day = Math.min(end.getUTCDate(), new Date(Date.UTC(year, month + 1, 0)).getUTCDate());
      scope.conference = { start: new Date(Date.UTC(year, month, day)).toISOString().slice(0, 10), end_exclusive: asOf };
    }
    return scope;
  }
  function countFilter(groups, start, end) {
    const quote = value => '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
    return '(' + ['published.gte.' + start, 'published.lt.' + end, ...groups.map(group => 'or(' + group.map(t => 'search_tsv.plfts(english).' + quote(t)).join(',') + ')')].join(',') + ')';
  }
  function publicKey(key) {
    if (/^sb_publishable_[A-Za-z0-9_-]+$/.test(key || '')) return true;
    try {
      let text = key.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      text += '='.repeat((4 - text.length % 4) % 4);
      const decoded = typeof atob === 'function' ? atob(text) : Buffer.from(text, 'base64').toString();
      return JSON.parse(decoded).role === 'anon';
    } catch (_) { return false; }
  }
  function backendFor(config) {
    const cfg = config || {};
    const shared = cfg.supabase_shared || {}, legacy = cfg.supabase || {};
    const specific = (cfg.source_backends || {}).arxiv || {};
    const backend = { ...legacy, ...shared, ...specific };
    const key = String(backend.publishable_key || backend.anon_key || '');
    const url = new URL(String(backend.url || ''));
    if (!enabled(backend.enabled) || !publicKey(key) || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('匿名连接不可用');
    const schema = backend.schema || 'public', table = backend.papers_table || 'arxiv_papers';
    if (![schema, table].every(x => /^[A-Za-z_][A-Za-z0-9_]*$/.test(x))) throw new Error('数据库配置无效');
    let base = url.href.replace(/\/$/, '');
    if (!base.endsWith('/rest/v1')) base += '/rest/v1';
    return { endpoint: base + '/' + table, key, schema };
  }
  async function preview(options) {
    options = options || {};
    const { profile = {}, mode, asOf, conferences = [] } = options || {};
    const result = { status: 'unknown', count: null, threshold: THRESHOLD, scope: null, reason: '范围未确认', coverage: { arxiv: { status: 'unknown', completed_windows: 0 }, conference: { status: mode === 'starter' ? 'unavailable' : 'not_requested', selected: conferences } } };
    let groups, backend;
    const config = options.config || (root.SubscriptionsManager && root.SubscriptionsManager.getDraftConfig ? root.SubscriptionsManager.getDraftConfig() : {});
    try { result.threshold = previewThreshold(options.threshold, config); }
    catch (_) { result.threshold = null; result.reason = '预览阈值必须是1–10000整数；范围未确认'; return result; }
    try {
      groups = englishGroups(profile);
      result.scope = scopeFor(mode, asOf);
      backend = backendFor(config);
    } catch (_) {
      result.reason = '英文研究约束、时间范围或匿名连接不可用；未把未确认结果记为0';
      return result;
    }
    // 不把密钥写入缓存键、输出或日志。缓存只在当前页面内短暂保留。
    const identity = JSON.stringify([backend.endpoint, backend.schema, groups, result.scope, conferences, result.threshold]);
    const hit = cache.get(identity);
    if (hit && Date.now() - hit.time < 30000) return JSON.parse(JSON.stringify(hit.result));
    if (inflight.has(identity)) return JSON.parse(JSON.stringify(await inflight.get(identity)));
    const run = async () => {
      const windows = [], start = Date.parse(result.scope.arxiv.start + 'T00:00:00Z');
      let end = Date.parse(asOf + 'T00:00:00Z');
      while (end > start) {
        const lower = Math.max(start, end - 30 * 86400000);
        windows.push([new Date(lower).toISOString().slice(0, 10), new Date(end).toISOString().slice(0, 10)]);
        end = lower;
      }
      result.coverage.arxiv.total_windows = windows.length;
      let total = 0, completed = 0;
      const deadline = Date.now() + 25000;
      for (const [lower, upper] of windows.slice(0, 16)) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) break;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), Math.min(6000, remaining));
        try {
          const url = new URL(backend.endpoint);
          url.searchParams.set('select', 'id'); url.searchParams.set('limit', '1');
          url.searchParams.set('and', countFilter(groups, lower, upper));
          const headers = { apikey: backend.key, 'Accept-Profile': backend.schema, Prefer: 'count=exact', Range: '0-0' };
          if (!backend.key.startsWith('sb_publishable_')) headers.Authorization = 'Bearer ' + backend.key;
          const response = await fetch(url.href, { method: 'HEAD', headers, signal: controller.signal, redirect: 'error' });
          if (![200, 206].includes(response.status)) break;
          const match = /^(?:\d+-\d+|\*)\/(\d+)$/.exec((response.headers.get('Content-Range') || '').trim());
          if (!match || !Number.isSafeInteger(Number(match[1]))) break;
          total += Number(match[1]); completed++;
          if (total > result.threshold) break;
        } catch (_) { break; }
        finally { clearTimeout(timer); }
      }
      result.coverage.arxiv.status = completed === windows.length ? 'exact' : completed ? 'partial' : 'unknown';
      result.coverage.arxiv.completed_windows = completed;
      result.count = completed ? total : null;
      if (total > result.threshold) {
        result.status = 'lower_bound'; result.reason = '已计数的不重叠时间片已超过' + result.threshold + '；这是范围规模，不是相关性判断';
      } else if (completed === windows.length && mode !== 'starter') {
        result.status = 'exact'; result.reason = '英文关键词FTS命中数已确认；不等于相关论文数量';
      } else {
        result.status = completed ? 'partial' : 'unknown';
        result.reason = mode === 'starter' ? '仅确认arXiv部分规模，会议总量未确认' : '计数预算耗尽或请求未完成，完整规模未确认';
      }
      if (cache.size >= 64) cache.delete(cache.keys().next().value);
      cache.set(identity, { time: Date.now(), result: JSON.parse(JSON.stringify(result)) });
      return result;
    };
    const promise = run(); inflight.set(identity, promise);
    try { return await promise; } finally { inflight.delete(identity); }
  }
  function previewThreshold(value, config) {
    if (value == null) value = config && config.topic_research && config.topic_research.preview_threshold !== undefined ? config.topic_research.preview_threshold : THRESHOLD;
    if (!['number', 'string'].includes(typeof value) || !/^\d+$/.test(String(value)) || !Number.isInteger(Number(value)) || Number(value) < 1 || Number(value) > 10000) throw new Error('预览阈值无效');
    return Number(value);
  }
  const api = { preview, __test: { englishGroups, scopeFor, countFilter, publicKey, backendFor, previewThreshold, clearCache: () => cache.clear() } };
  root.TopicResearchPreview = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
