/**
 * DPR Workflow Status Sync — 通过公共 Supabase 实时同步 GitHub Actions 任务运行状态与步骤进度
 *
 * 特点：
 * - 前端点击触发任务时立即登记 pending 行，拿到 run_id 后升级为 gh:<run_id>
 * - Python 流水线在关键 Step 及逐篇生成阶段实时 upsert 细粒度进度（如 18/50）
 * - 页面打开后仅读公共 Supabase（不消耗 GitHub API 额度，游客与跨设备均可查看）
 * - 有进行中任务时每 6 秒轮询，页面隐藏自动暂停，无活跃任务时自动停止轮询
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(root);
    return;
  }
  var api = factory(root);
  if (root) {
    root.DPRWorkflowStatusSync = api;
  }
})(typeof window !== 'undefined' ? window : globalThis, function (win) {
  'use strict';

  var DEFAULT_SUPABASE_URL = 'https://lyucdwgefyfbmaiopjbk.supabase.co';
  var DEFAULT_SUPABASE_KEY = 'sb_publishable_lX-oi64Uxyd7SIVv3_w2Uw_MTOojeKq';
  var TABLE = 'workflow_run_status';
  var POLL_INTERVAL_MS = 6000;
  var ACTIVE_STALE_MS = 120 * 60 * 1000;
  var PENDING_STALE_MS = 10 * 60 * 1000;
  var COMPLETED_WINDOW_MS = 30 * 60 * 1000;
  var DISMISSED_STORAGE_KEY = 'dpr_workflow_status_dismissed_v1';

  var state = {
    supabaseUrl: DEFAULT_SUPABASE_URL,
    supabaseKey: DEFAULT_SUPABASE_KEY,
    repoFullName: '',
    runs: [],
    activeRuns: [],
    recentCompleted: null,
    pollTimer: null,
    fetching: false,
    started: false,
    lastCheckedAt: 0,
    dismissedKeys: new Set(),
    repoResolvePromise: null,
  };

  function getDoc() {
    return win && win.document ? win.document : null;
  }

  function getFetch() {
    return win && typeof win.fetch === 'function' ? win.fetch.bind(win) : null;
  }

  function safeClip(value, limit) {
    var text = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    if (text.length <= limit) return text;
    return text.slice(0, Math.max(limit - 1, 1)).trim() + '…';
  }

  function isValidRepoFullName(value) {
    return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(String(value || '').trim());
  }

  function isValidRunUrl(value) {
    return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/actions\/runs\/[0-9]+$/.test(
      String(value || '').trim()
    );
  }

  function loadDismissedKeys() {
    var out = new Set();
    try {
      var raw = win && win.localStorage && win.localStorage.getItem(DISMISSED_STORAGE_KEY);
      if (!raw) return out;
      var parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        parsed.slice(-50).forEach(function (k) {
          if (typeof k === 'string' && k) out.add(k);
        });
      }
    } catch (_) {}
    return out;
  }

  function persistDismissedKeys() {
    try {
      if (!win || !win.localStorage) return;
      var arr = Array.from(state.dismissedKeys).slice(-50);
      win.localStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify(arr));
    } catch (_) {}
  }

  function restBaseUrl() {
    return state.supabaseUrl.replace(/\/$/, '') + '/rest/v1/' + TABLE;
  }

  function buildHeaders(extra) {
    var h = {
      apikey: state.supabaseKey,
      Authorization: 'Bearer ' + state.supabaseKey,
      'Content-Type': 'application/json',
    };
    if (extra) {
      Object.keys(extra).forEach(function (k) { h[k] = extra[k]; });
    }
    return h;
  }

  function inferRepoFromLocation(loc) {
    if (!loc) return '';
    var host = String(loc.hostname || '').trim().toLowerCase();
    var pathname = String(loc.pathname || '').trim();
    if (!host) return '';
    if (host.endsWith('.github.io')) {
      var owner = host.slice(0, -'.github.io'.length);
      var parts = pathname.split('/').filter(Boolean);
      var repo = parts[0] || (owner ? owner + '.github.io' : '');
      var candidate = owner && repo ? owner + '/' + repo : '';
      return isValidRepoFullName(candidate) ? candidate : '';
    }
    return '';
  }

  function resolveRepoFullName() {
    if (isValidRepoFullName(state.repoFullName)) {
      return Promise.resolve(state.repoFullName);
    }
    var override = win && typeof win.DPR_REPO_FULL_NAME === 'string' ? win.DPR_REPO_FULL_NAME.trim() : '';
    if (isValidRepoFullName(override)) {
      state.repoFullName = override;
      return Promise.resolve(override);
    }
    if (state.repoResolvePromise) return state.repoResolvePromise;

    var fetchFn = getFetch();
    state.repoResolvePromise = (async function () {
      if (fetchFn) {
        try {
          var res = await fetchFn('docs/.repo-owner.json', { cache: 'no-cache' });
          if (res && res.ok) {
            var data = await res.json().catch(function () { return null; });
            var owner = data && typeof data.owner === 'string' ? data.owner.trim() : '';
            var repo = data && typeof data.repo === 'string' ? data.repo.trim() : '';
            var full = owner && repo ? owner + '/' + repo : '';
            if (isValidRepoFullName(full)) {
              state.repoFullName = full;
              return full;
            }
          }
        } catch (_) {}
      }
      var inferred = inferRepoFromLocation(win && win.location);
      if (isValidRepoFullName(inferred)) {
        state.repoFullName = inferred;
        return inferred;
      }
      return '';
    })();

    state.repoResolvePromise.then(function () {
      state.repoResolvePromise = null;
    });
    return state.repoResolvePromise;
  }

  function normalizeRow(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var runKey = String(raw.run_key || '').trim();
    var repo = String(raw.repo_full_name || '').trim();
    if (!runKey || !isValidRepoFullName(repo)) return null;
    var status = String(raw.status || 'queued').trim();
    if (status !== 'queued' && status !== 'in_progress' && status !== 'completed') {
      status = 'in_progress';
    }
    var conclusion = String(raw.conclusion || '').trim();
    var runId = raw.run_id != null && Number.isFinite(Number(raw.run_id)) && Number(raw.run_id) > 0
      ? Number(raw.run_id)
      : null;
    var runNumber = raw.run_number != null && Number.isFinite(Number(raw.run_number))
      ? Number(raw.run_number)
      : null;
    var runUrl = isValidRunUrl(raw.run_url) ? String(raw.run_url).trim() : '';
    if (!runUrl && runId) {
      runUrl = 'https://github.com/' + repo + '/actions/runs/' + runId;
    }
    return {
      repo_full_name: repo,
      run_key: runKey,
      workflow_key: String(raw.workflow_key || '').trim(),
      workflow_file: String(raw.workflow_file || '').trim(),
      display_label: String(raw.display_label || '').trim() || defaultWorkflowLabel(raw.workflow_key, raw.workflow_file),
      run_id: runId,
      run_number: runNumber,
      run_url: runUrl,
      status: status,
      conclusion: conclusion,
      step_code: String(raw.step_code || '').trim(),
      step_label: String(raw.step_label || '').trim(),
      progress_current: Math.max(0, Number(raw.progress_current) || 0),
      progress_total: Math.max(0, Number(raw.progress_total) || 0),
      detail: String(raw.detail || '').trim(),
      started_at: String(raw.started_at || '').trim(),
      updated_at: String(raw.updated_at || '').trim(),
      completed_at: String(raw.completed_at || '').trim(),
    };
  }

  function defaultWorkflowLabel(workflowKey, workflowFile) {
    var k = String(workflowKey || '').trim();
    var f = String(workflowFile || '').trim();
    if (k === 'topic-research' || f === 'topic-research.yml') return '专题研究';
    if (k === 'conference-retrieval' || f === 'conference-paper-retrieval.yml') return '会议论文检索';
    if (k === 'daily-now' || f === 'daily-paper-reader.yml') return '每日论文';
    if (k === 'sync' || f === 'sync.yml') return '同步上游代码';
    if (k === 'reset-content' || f === 'reset-content.yml') return '重置论文内容';
    return '后台任务';
  }

  function classifyRuns(rows, nowMs) {
    var now = typeof nowMs === 'number' ? nowMs : Date.now();
    var normalized = (Array.isArray(rows) ? rows : []).map(normalizeRow).filter(Boolean);
    var activeByWorkflow = {};
    var active = [];
    var completed = [];

    normalized.forEach(function (row) {
      var updatedMs = Date.parse(row.updated_at || row.started_at || '') || 0;
      var ageMs = updatedMs ? Math.max(0, now - updatedMs) : 0;
      if (row.status === 'queued' || row.status === 'in_progress') {
        var maxAge = row.run_key.indexOf('pending:') === 0 ? PENDING_STALE_MS : ACTIVE_STALE_MS;
        if (updatedMs && ageMs > maxAge) return;
        if (row.run_key.indexOf('gh:') === 0 && row.workflow_file) {
          activeByWorkflow[row.workflow_file] = true;
        }
        active.push(row);
      } else if (row.status === 'completed') {
        var doneMs = Date.parse(row.completed_at || row.updated_at || '') || 0;
        var doneAge = doneMs ? Math.max(0, now - doneMs) : 0;
        if (doneMs && doneAge <= COMPLETED_WINDOW_MS && !state.dismissedKeys.has(row.run_key)) {
          completed.push(row);
        }
      }
    });

    // 若同一 workflow 已有真实 gh:<run_id> 在跑，隐藏对应的 pending 占位行
    active = active.filter(function (row) {
      if (row.run_key.indexOf('pending:') === 0 && row.workflow_file && activeByWorkflow[row.workflow_file]) {
        return false;
      }
      return true;
    });

    active.sort(function (a, b) {
      return (Date.parse(b.updated_at || b.started_at || '') || 0) - (Date.parse(a.updated_at || a.started_at || '') || 0);
    });
    completed.sort(function (a, b) {
      return (Date.parse(b.completed_at || b.updated_at || '') || 0) - (Date.parse(a.completed_at || a.updated_at || '') || 0);
    });

    return {
      runs: normalized,
      activeRuns: active,
      recentCompleted: active.length === 0 ? (completed[0] || null) : null,
    };
  }

  function emitChange() {
    var doc = getDoc();
    if (!doc || typeof doc.dispatchEvent !== 'function') return;
    var detail = getSnapshot();
    try {
      doc.dispatchEvent(new CustomEvent('dpr-workflow-status-changed', { detail: detail }));
    } catch (_) {
      try {
        var ev = doc.createEvent('CustomEvent');
        ev.initCustomEvent('dpr-workflow-status-changed', false, false, detail);
        doc.dispatchEvent(ev);
      } catch (__) {}
    }
  }

  function getSnapshot() {
    return {
      repoFullName: state.repoFullName,
      activeRuns: state.activeRuns.slice(),
      recentCompleted: state.recentCompleted,
      runs: state.runs.slice(),
    };
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function ensurePolling() {
    if (state.activeRuns.length === 0) {
      stopPolling();
      return;
    }
    var doc = getDoc();
    if (doc && doc.visibilityState === 'hidden') {
      stopPolling();
      return;
    }
    if (!state.pollTimer) {
      state.pollTimer = setInterval(function () {
        refresh();
      }, POLL_INTERVAL_MS);
    }
  }

  function applyRows(rows) {
    var prevActiveIds = state.activeRuns.map(function (r) { return r.run_key; }).join(',');
    var classified = classifyRuns(rows);
    state.runs = classified.runs;
    state.activeRuns = classified.activeRuns;
    state.recentCompleted = classified.recentCompleted;
    state.lastCheckedAt = Date.now();
    ensurePolling();
    emitChange();
    return {
      hadActive: !!prevActiveIds,
      snapshot: getSnapshot(),
    };
  }

  async function refresh() {
    if (state.fetching) return getSnapshot();
    var fetchFn = getFetch();
    if (!fetchFn) return getSnapshot();
    var repo = await resolveRepoFullName();
    if (!repo) return getSnapshot();

    state.fetching = true;
    try {
      var url =
        restBaseUrl() +
        '?repo_full_name=eq.' + encodeURIComponent(repo) +
        '&order=updated_at.desc&limit=8';
      var res = await fetchFn(url, {
        headers: buildHeaders(),
        cache: 'no-store',
      });
      if (!res || !res.ok) return getSnapshot();
      var rows = await res.json().catch(function () { return []; });
      applyRows(rows);
    } catch (_) {
      // 静默降级，绝不影响主阅读体验
    } finally {
      state.fetching = false;
    }
    return getSnapshot();
  }

  async function upsertRow(row) {
    var fetchFn = getFetch();
    if (!fetchFn || !row || !isValidRepoFullName(row.repo_full_name) || !row.run_key) return false;
    try {
      var res = await fetchFn(restBaseUrl() + '?on_conflict=repo_full_name,run_key', {
        method: 'POST',
        headers: buildHeaders({ Prefer: 'resolution=merge-duplicates,return=minimal' }),
        body: JSON.stringify(row),
      });
      return !!(res && res.ok);
    } catch (_) {
      return false;
    }
  }

  async function deletePendingKey(repoFullName, pendingKey) {
    var fetchFn = getFetch();
    if (!fetchFn || !isValidRepoFullName(repoFullName) || !pendingKey || pendingKey.indexOf('pending:') !== 0) {
      return false;
    }
    try {
      var url =
        restBaseUrl() +
        '?repo_full_name=eq.' + encodeURIComponent(repoFullName) +
        '&run_key=eq.' + encodeURIComponent(pendingKey);
      var res = await fetchFn(url, {
        method: 'DELETE',
        headers: buildHeaders({ Prefer: 'return=minimal' }),
      });
      return !!(res && res.ok);
    } catch (_) {
      return false;
    }
  }

  async function recordDispatched(opts) {
    var o = opts || {};
    var repo = o.owner && o.repo ? o.owner + '/' + o.repo : await resolveRepoFullName();
    if (!isValidRepoFullName(repo)) return '';
    state.repoFullName = repo;
    var wfFile = safeClip(o.workflowFile || '', 100);
    var wfKey = safeClip(o.workflowKey || '', 64);
    var ts = Number(o.dispatchedAt) || Date.now();
    var pendingKey = 'pending:' + (wfFile.replace(/[^A-Za-z0-9_.-]/g, '_') || 'workflow') + ':' + ts;
    var nowIso = new Date().toISOString();
    var row = {
      repo_full_name: repo,
      run_key: pendingKey,
      workflow_key: wfKey,
      workflow_file: wfFile,
      display_label: safeClip(o.displayLabel || defaultWorkflowLabel(wfKey, wfFile), 160),
      run_id: null,
      run_number: null,
      run_url: '',
      status: 'queued',
      conclusion: '',
      step_code: 'queued',
      step_label: '已派发，等待启动',
      progress_current: 0,
      progress_total: 0,
      detail: '',
      started_at: nowIso,
      updated_at: nowIso,
    };
    // 乐观更新本地视图，让侧栏立刻出现状态条
    applyRows([row].concat(state.runs));
    await upsertRow(row);
    return pendingKey;
  }

  async function recordRunStarted(opts) {
    var o = opts || {};
    var repo = o.owner && o.repo ? o.owner + '/' + o.repo : await resolveRepoFullName();
    var runId = Number(o.runId);
    if (!isValidRepoFullName(repo) || !Number.isFinite(runId) || runId <= 0) return false;
    state.repoFullName = repo;
    var wfFile = safeClip(o.workflowFile || '', 100);
    var wfKey = safeClip(o.workflowKey || '', 64);
    var nowIso = new Date().toISOString();
    var runKey = 'gh:' + runId;
    var runUrl = 'https://github.com/' + repo + '/actions/runs/' + runId;
    var row = {
      repo_full_name: repo,
      run_key: runKey,
      workflow_key: wfKey,
      workflow_file: wfFile,
      display_label: safeClip(o.displayLabel || defaultWorkflowLabel(wfKey, wfFile), 160),
      run_id: runId,
      run_number: o.runNumber != null && Number.isFinite(Number(o.runNumber)) ? Number(o.runNumber) : null,
      run_url: runUrl,
      status: o.status === 'in_progress' || o.status === 'completed' ? o.status : 'queued',
      conclusion: String(o.conclusion || '').trim(),
      step_code: safeClip(o.stepCode || 'started', 64),
      step_label: safeClip(o.stepLabel || 'Actions 已启动', 120),
      progress_current: Math.max(0, Number(o.progressCurrent) || 0),
      progress_total: Math.max(0, Number(o.progressTotal) || 0),
      detail: safeClip(o.detail || '', 240),
      updated_at: nowIso,
    };
    if (o.pendingKey) {
      await deletePendingKey(repo, o.pendingKey);
    }
    var ok = await upsertRow(row);
    await refresh();
    return ok;
  }

  async function recordRunUpdate(opts) {
    var o = opts || {};
    var repo = o.owner && o.repo ? o.owner + '/' + o.repo : await resolveRepoFullName();
    var runId = Number(o.runId);
    if (!isValidRepoFullName(repo) || !Number.isFinite(runId) || runId <= 0) return false;
    var runKey = 'gh:' + runId;
    var existing = state.runs.find(function (r) { return r.run_key === runKey; }) || {};
    var status = o.status === 'queued' || o.status === 'in_progress' || o.status === 'completed'
      ? o.status
      : (existing.status || 'in_progress');
    var nowIso = new Date().toISOString();
    var row = {
      repo_full_name: repo,
      run_key: runKey,
      workflow_key: safeClip(o.workflowKey || existing.workflow_key || '', 64),
      workflow_file: safeClip(o.workflowFile || existing.workflow_file || '', 100),
      display_label: safeClip(o.displayLabel || existing.display_label || '', 160),
      run_id: runId,
      run_number: o.runNumber != null ? Number(o.runNumber) : (existing.run_number || null),
      run_url: 'https://github.com/' + repo + '/actions/runs/' + runId,
      status: status,
      conclusion: String(o.conclusion != null ? o.conclusion : (existing.conclusion || '')).trim(),
      step_code: safeClip(o.stepCode || existing.step_code || '', 64),
      step_label: safeClip(o.stepLabel || existing.step_label || '', 120),
      progress_current: o.progressCurrent != null ? Math.max(0, Number(o.progressCurrent) || 0) : (existing.progress_current || 0),
      progress_total: o.progressTotal != null ? Math.max(0, Number(o.progressTotal) || 0) : (existing.progress_total || 0),
      detail: safeClip(o.detail != null ? o.detail : (existing.detail || ''), 240),
      updated_at: nowIso,
    };
    if (status === 'completed') {
      row.completed_at = nowIso;
    }
    var ok = await upsertRow(row);
    applyRows([row].concat(state.runs.filter(function (r) { return r.run_key !== runKey; })));
    return ok;
  }

  function dismissRun(runKey) {
    var key = String(runKey || '').trim();
    if (!key) return;
    state.dismissedKeys.add(key);
    persistDismissedKeys();
    applyRows(state.runs);
  }

  function configure(options) {
    var opts = options || {};
    if (opts.supabaseUrl) state.supabaseUrl = String(opts.supabaseUrl).replace(/\/$/, '');
    if (opts.supabaseKey) state.supabaseKey = String(opts.supabaseKey);
    if (isValidRepoFullName(opts.repoFullName)) state.repoFullName = opts.repoFullName;
  }

  function start() {
    if (state.started) return;
    state.started = true;
    state.dismissedKeys = loadDismissedKeys();
    var doc = getDoc();
    if (doc && doc.addEventListener) {
      doc.addEventListener('visibilitychange', function () {
        if (doc.visibilityState === 'hidden') {
          stopPolling();
        } else {
          if (state.activeRuns.length > 0 || (Date.now() - state.lastCheckedAt > 60000)) {
            refresh();
          }
        }
      });
    }
    refresh();
  }

  return {
    start: start,
    refresh: refresh,
    configure: configure,
    getSnapshot: getSnapshot,
    recordDispatched: recordDispatched,
    recordRunStarted: recordRunStarted,
    recordRunUpdate: recordRunUpdate,
    dismissRun: dismissRun,
    stopPolling: stopPolling,
    __test: {
      inferRepoFromLocation: inferRepoFromLocation,
      normalizeRow: normalizeRow,
      classifyRuns: classifyRuns,
      defaultWorkflowLabel: defaultWorkflowLabel,
      applyRows: applyRows,
      reset: function () {
        stopPolling();
        state.repoFullName = '';
        state.runs = [];
        state.activeRuns = [];
        state.recentCompleted = null;
        state.fetching = false;
        state.started = false;
        state.lastCheckedAt = 0;
        state.dismissedKeys = new Set();
        state.repoResolvePromise = null;
      },
    },
  };
});
