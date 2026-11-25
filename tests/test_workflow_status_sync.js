const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadSyncModule(overrides = {}) {
  const events = [];
  const storage = new Map();
  const calls = [];
  const mockWin = {
    location: overrides.location || {
      hostname: 'alice.github.io',
      pathname: '/daily-paper-reader/',
    },
    localStorage: {
      getItem: (k) => (storage.has(k) ? storage.get(k) : null),
      setItem: (k, v) => storage.set(k, String(v)),
      removeItem: (k) => storage.delete(k),
    },
    document: {
      visibilityState: 'visible',
      addEventListener() {},
      dispatchEvent(ev) {
        events.push(ev);
      },
    },
    CustomEvent: class CustomEvent {
      constructor(type, init) {
        this.type = type;
        this.detail = init && init.detail;
      }
    },
    fetch: overrides.fetch || (async (url, opts) => {
      calls.push({ url, opts: opts || {} });
      return { ok: true, json: async () => [] };
    }),
    setInterval: () => 1,
    clearInterval: () => {},
  };
  const code = fs.readFileSync(path.join(__dirname, '..', 'app', 'workflow-status-sync.js'), 'utf8');
  const mod = { exports: {} };
  vm.runInNewContext(code, {
    window: mockWin,
    globalThis: mockWin,
    CustomEvent: mockWin.CustomEvent,
    setInterval: mockWin.setInterval,
    clearInterval: mockWin.clearInterval,
    module: mod,
    exports: mod.exports,
    console,
    Date,
    Set,
    Promise,
  }, { filename: 'app/workflow-status-sync.js' });
  return { api: mod.exports, events, calls, storage, win: mockWin };
}

function loadWorkflowRunnerTestHelpers() {
  const code = fs.readFileSync(path.join(__dirname, '..', 'app', 'workflows.runner.js'), 'utf8');
  const sandbox = {
    window: { location: { hostname: 'alice.github.io', pathname: '/daily-paper-reader/' } },
    document: {
      addEventListener() {},
      getElementById: () => null,
      querySelector: () => null,
    },
    console,
    Date,
    Set,
    Promise,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    URLSearchParams,
    encodeURIComponent,
  };
  vm.runInNewContext(code, sandbox, { filename: 'app/workflows.runner.js' });
  return sandbox.window.DPRWorkflowRunner;
}

function loadSidebarWorkflowRenderer() {
  const code = fs.readFileSync(path.join(__dirname, '..', 'app', 'dpr-sidebar.js'), 'utf8');
  const mod = { exports: {} };
  const doc = {
    readyState: 'loading',
    addEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    createElement() {
      let text = '';
      return {
        set textContent(v) { text = String(v == null ? '' : v); },
        get textContent() { return text; },
        get innerHTML() {
          return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        },
      };
    },
    body: { classList: { toggle() {}, add() {}, remove() {} } },
  };
  const win = {
    location: { hash: '#/', hostname: 'alice.github.io', pathname: '/daily-paper-reader/' },
    addEventListener() {},
    document: doc,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    matchMedia: () => ({ matches: false }),
  };
  vm.runInNewContext(code, {
    window: win,
    document: doc,
    module: mod,
    exports: mod.exports,
    console,
    Date,
    Set,
    Promise,
    setTimeout,
    clearTimeout,
  }, { filename: 'app/dpr-sidebar.js' });
  return mod.exports.__test.renderWorkflowStatusHtml;
}

async function runTests() {
  // 1. Repo inference from GitHub Pages hostname + pathname
  {
    const { api } = loadSyncModule();
    assert.equal(
      api.__test.inferRepoFromLocation({ hostname: '5-xj.github.io', pathname: '/daily-paper-reader/' }),
      '5-xj/daily-paper-reader',
    );
    assert.equal(
      api.__test.inferRepoFromLocation({ hostname: 'alice.github.io', pathname: '/' }),
      'alice/alice.github.io',
    );
    assert.equal(
      api.__test.inferRepoFromLocation({ hostname: 'localhost', pathname: '/' }),
      '',
    );
  }

  // 2. normalizeRow rejects unsafe run_url and derives canonical GitHub Actions URL
  {
    const { api } = loadSyncModule();
    const row = api.__test.normalizeRow({
      repo_full_name: 'alice/daily-paper-reader',
      run_key: 'gh:4242',
      run_id: 4242,
      run_url: 'javascript:alert(1)',
      status: 'in_progress',
      workflow_key: 'topic-research',
      workflow_file: 'topic-research.yml',
      progress_current: -5,
      progress_total: 50,
    });
    assert.equal(row.run_url, 'https://github.com/alice/daily-paper-reader/actions/runs/4242');
    assert.equal(row.display_label, '专题研究');
    assert.equal(row.progress_current, 0);
    assert.equal(row.progress_total, 50);

    const pendingUnsafe = api.__test.normalizeRow({
      repo_full_name: 'alice/daily-paper-reader',
      run_key: 'pending:topic-research.yml:1700000000000',
      run_url: 'https://evil.example/phish',
      status: 'queued',
    });
    assert.equal(pendingUnsafe.run_url, '');
  }

  // 3. classifyRuns deduplicates pending rows when matching gh:<run_id> is active,
  //    filters stale pending/active rows, and exposes recentCompleted only when idle
  {
    const { api } = loadSyncModule();
    const now = Date.parse('2026-11-25T10:00:00Z');
    const classified = api.__test.classifyRuns([
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'pending:topic-research.yml:1700000000000',
        workflow_file: 'topic-research.yml',
        display_label: '专题研究 · llm',
        status: 'queued',
        updated_at: '2026-11-25T09:59:00Z',
      },
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'gh:9001',
        run_id: 9001,
        workflow_file: 'topic-research.yml',
        display_label: '专题研究 · llm',
        status: 'in_progress',
        step_label: '生成论文文档',
        progress_current: 12,
        progress_total: 50,
        updated_at: '2026-11-25T09:59:30Z',
      },
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'pending:daily-paper-reader.yml:1600000000000',
        workflow_file: 'daily-paper-reader.yml',
        status: 'queued',
        // > 10 min old pending row should be dropped
        updated_at: '2026-11-25T09:40:00Z',
      },
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'gh:8999',
        run_id: 8999,
        workflow_file: 'daily-paper-reader.yml',
        status: 'completed',
        conclusion: 'success',
        completed_at: '2026-11-25T09:55:00Z',
        updated_at: '2026-11-25T09:55:00Z',
      },
    ], now);
    assert.equal(classified.activeRuns.length, 1);
    assert.equal(classified.activeRuns[0].run_key, 'gh:9001');
    // recentCompleted is hidden while another task is still active
    assert.equal(classified.recentCompleted, null);

    // When idle, recentCompleted within 30 min is surfaced
    const idleClassified = api.__test.classifyRuns([
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'gh:8999',
        run_id: 8999,
        workflow_file: 'daily-paper-reader.yml',
        status: 'completed',
        conclusion: 'success',
        completed_at: '2026-11-25T09:55:00Z',
        updated_at: '2026-11-25T09:55:00Z',
      },
      {
        repo_full_name: 'alice/daily-paper-reader',
        run_key: 'gh:8000',
        run_id: 8000,
        workflow_file: 'daily-paper-reader.yml',
        status: 'completed',
        conclusion: 'success',
        // > 30 min old completed row should not be surfaced
        completed_at: '2026-11-25T09:00:00Z',
        updated_at: '2026-11-25T09:00:00Z',
      },
    ], now);
    assert.equal(idleClassified.activeRuns.length, 0);
    assert.equal(idleClassified.recentCompleted.run_key, 'gh:8999');
  }

  // 4. recordDispatched -> recordRunStarted -> recordRunUpdate -> dismissRun lifecycle
  {
    const dbRows = [];
    const { api, events, calls } = loadSyncModule({
      fetch: async (url, opts = {}) => {
        calls.push({ url, opts });
        const method = String(opts.method || 'GET').toUpperCase();
        if (method === 'POST') {
          const row = JSON.parse(opts.body);
          const idx = dbRows.findIndex((r) => r.run_key === row.run_key);
          if (idx >= 0) dbRows[idx] = row;
          else dbRows.push(row);
          return { ok: true, json: async () => [] };
        }
        if (method === 'DELETE') {
          const match = /run_key=eq\.([^&]+)/.exec(url);
          if (match) {
            const key = decodeURIComponent(match[1]);
            for (let i = dbRows.length - 1; i >= 0; i -= 1) {
              if (dbRows[i].run_key === key) dbRows.splice(i, 1);
            }
          }
          return { ok: true, json: async () => [] };
        }
        return { ok: true, json: async () => dbRows.slice() };
      },
    });

    const pendingKey = await api.recordDispatched({
      owner: 'alice',
      repo: 'daily-paper-reader',
      workflowKey: 'topic-research',
      workflowFile: 'topic-research.yml',
      displayLabel: '专题研究 · user-sim（大礼包）',
      dispatchedAt: 1700000001234,
    });
    assert.equal(pendingKey, 'pending:topic-research.yml:1700000001234');
    assert.equal(api.getSnapshot().activeRuns.length, 1);
    assert.equal(api.getSnapshot().activeRuns[0].run_key, pendingKey);
    assert.ok(events.some((e) => e.type === 'dpr-workflow-status-changed'));

    await api.recordRunStarted({
      owner: 'alice',
      repo: 'daily-paper-reader',
      workflowKey: 'topic-research',
      workflowFile: 'topic-research.yml',
      displayLabel: '专题研究 · user-sim（大礼包）',
      runId: 334455,
      runNumber: 7,
      status: 'in_progress',
      pendingKey,
    });
    assert.ok(calls.some((c) => c.opts.method === 'DELETE' && c.url.includes(encodeURIComponent(pendingKey))));
    assert.equal(api.getSnapshot().activeRuns.length, 1);
    assert.equal(api.getSnapshot().activeRuns[0].run_key, 'gh:334455');

    await api.recordRunUpdate({
      owner: 'alice',
      repo: 'daily-paper-reader',
      runId: 334455,
      status: 'completed',
      conclusion: 'success',
      stepCode: 'done',
      stepLabel: '任务已完成',
    });
    assert.equal(api.getSnapshot().activeRuns.length, 0);
    assert.equal(api.getSnapshot().recentCompleted.run_key, 'gh:334455');

    api.dismissRun('gh:334455');
    assert.equal(api.getSnapshot().recentCompleted, null);
  }

  // 5. workflows.runner.js buildWorkflowDisplayLabel formatting
  {
    const runner = loadWorkflowRunnerTestHelpers();
    const buildLabel = runner.__test.buildWorkflowDisplayLabel;
    assert.equal(
      buildLabel({ key: 'topic-research' }, { profile_tag: 'user-sim', mode: 'starter' }),
      '专题研究 · user-sim（大礼包）',
    );
    assert.equal(
      buildLabel({ key: 'topic-research' }, { profile_tag: 'agents', mode: '90' }),
      '专题研究 · agents（90天）',
    );
    assert.equal(
      buildLabel({ key: 'conference-retrieval' }, { conference: 'NeurIPS', years: '2025', profile_tag: 'sr' }),
      '会议论文 · NeurIPS 2025 · sr',
    );
    assert.equal(
      buildLabel({ key: 'daily-now' }, { fetch_days: '30' }),
      '每日论文（30天）',
    );
  }

  // 6. dpr-sidebar.js renderWorkflowStatusHtml states (running / completed / failed / idle)
  {
    const renderWorkflowStatusHtml = loadSidebarWorkflowRenderer();

    const idle = renderWorkflowStatusHtml({ activeRuns: [], recentCompleted: null });
    assert.equal(idle.html, '');
    assert.equal(idle.hasActive, false);

    const runningDeterminate = renderWorkflowStatusHtml({
      activeRuns: [
        {
          repo_full_name: 'alice/daily-paper-reader',
          run_key: 'gh:9001',
          run_id: 9001,
          run_url: 'https://github.com/alice/daily-paper-reader/actions/runs/9001',
          display_label: '专题研究 · user-sim（大礼包）',
          status: 'in_progress',
          step_label: '正在生成论文文档',
          progress_current: 18,
          progress_total: 50,
        },
        {
          repo_full_name: 'alice/daily-paper-reader',
          run_key: 'gh:9002',
          run_id: 9002,
          display_label: '每日论文',
          status: 'queued',
        },
      ],
      recentCompleted: null,
    });
    assert.equal(runningDeterminate.hasActive, true);
    assert.match(runningDeterminate.html, /dpr-wf-pill is-running/);
    assert.match(runningDeterminate.html, /专题研究 · user-sim（大礼包）/);
    assert.match(runningDeterminate.html, /正在生成论文文档 · 18\/50/);
    assert.match(runningDeterminate.html, /width:36%/);
    assert.match(runningDeterminate.html, /\+1/);

    const runningIndeterminate = renderWorkflowStatusHtml({
      activeRuns: [
        {
          repo_full_name: 'alice/daily-paper-reader',
          run_key: 'pending:topic-research.yml:1700000000000',
          display_label: '专题研究 · agents（90天）',
          status: 'queued',
          step_label: '已派发，等待启动',
          progress_current: 0,
          progress_total: 0,
        },
      ],
      recentCompleted: null,
    });
    assert.equal(runningIndeterminate.hasActive, true);
    assert.match(runningIndeterminate.html, /is-indeterminate/);

    const doneSuccess = renderWorkflowStatusHtml({
      activeRuns: [],
      recentCompleted: {
        run_key: 'gh:9001',
        display_label: '专题研究 · user-sim（大礼包）',
        status: 'completed',
        conclusion: 'success',
      },
    });
    assert.equal(doneSuccess.hasActive, false);
    assert.match(doneSuccess.html, /dpr-wf-pill is-success/);
    assert.match(doneSuccess.html, /data-wf-refresh-done="gh:9001"/);
    assert.match(doneSuccess.html, /data-wf-dismiss="gh:9001"/);

    const doneFailed = renderWorkflowStatusHtml({
      activeRuns: [],
      recentCompleted: {
        run_key: 'gh:9003',
        run_url: 'https://github.com/alice/daily-paper-reader/actions/runs/9003',
        display_label: '会议论文 · ICLR 2026',
        status: 'completed',
        conclusion: 'failure',
      },
    });
    assert.equal(doneFailed.hasActive, false);
    assert.match(doneFailed.html, /dpr-wf-pill is-failed/);
    assert.match(doneFailed.html, /执行失败/);
    assert.match(doneFailed.html, /https:\/\/github\.com\/alice\/daily-paper-reader\/actions\/runs\/9003/);
  }

  // 7. index.html loads workflow-status-sync.js before dpr-sidebar.js
  {
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    const syncIdx = html.indexOf("path: 'app/workflow-status-sync.js'");
    const sidebarIdx = html.indexOf("path: 'app/dpr-sidebar.js'");
    assert.ok(syncIdx >= 0, 'index.html must load app/workflow-status-sync.js');
    assert.ok(sidebarIdx > syncIdx, 'workflow-status-sync.js should load before dpr-sidebar.js');
  }

  console.log('workflow status sync tests passed');
}

runTests().catch((err) => {
  console.error(err);
  process.exit(1);
});
