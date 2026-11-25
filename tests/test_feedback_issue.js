const assert = require('node:assert/strict');

const feedback = require('../app/feedback.issue.js');

const {
  ISSUE_TYPES,
  TARGET_OWNER,
  TARGET_REPO,
  FEEDBACK_ANIMATION_MS,
  AUTO_PROMPT_STORAGE_KEY,
  getFeedbackMotionStyles,
  normalizeSelectedTypes,
  buildIssueTitle,
  buildIssueBody,
  validateFeedbackForm,
  buildIssueDraftUrl,
  resolveGithubToken,
  classifyIssueError,
  submitIssueWithFallback,
  formatLocalDayKey,
  computeLocalDayDiff,
  isUpstreamDemoHost,
  evaluateAutoPrompt,
  isPageBusyForAutoPrompt,
  markAutoPromptHandled,
  checkAutoFeedbackPrompt,
} = feedback.__test;

function testFeedbackMotionStylesCoverEnterAndExit() {
  const hidden = getFeedbackMotionStyles(false);
  const visible = getFeedbackMotionStyles(true);

  assert.equal(FEEDBACK_ANIMATION_MS, 180);
  assert.equal(hidden.overlay.opacity, '0');
  assert.equal(hidden.panel.opacity, '0');
  assert.match(hidden.panel.transform, /translateY\(12px\)/);
  assert.equal(visible.overlay.opacity, '1');
  assert.equal(visible.panel.opacity, '1');
  assert.equal(visible.panel.transform, 'translateY(0) scale(1)');
}

function buildValidForm(overrides = {}) {
  return {
    types: ['体验问题', '功能新增'],
    title: '侧栏切换后计数不同步',
    content: '切换标签后，当前日期的计数没有立即刷新。',
    confirmPublic: true,
    ...overrides,
  };
}

function testNormalizeSelectedTypesKeepsCanonicalOrder() {
  assert.deepEqual(
    normalizeSelectedTypes(['其他', '功能新增', '功能新增', '体验问题', '无效项']),
    ['功能新增', '体验问题', '其他'],
  );
  assert.deepEqual(normalizeSelectedTypes(new Set(['BUG反馈', '论文 / 会议数据'])), [
    'BUG反馈',
    '论文 / 会议数据',
  ]);
  assert.deepEqual(ISSUE_TYPES.length, 5);
}

function testBuildIssueTitleUsesStrictPrefixFormat() {
  assert.equal(
    buildIssueTitle(['体验问题', '功能新增'], '  [其他]  侧栏宽度在窄屏下异常  '),
    '[功能新增|体验问题] 侧栏宽度在窄屏下异常',
  );
  assert.equal(buildIssueTitle([], '没有类型'), '');
}

function testBuildIssueBodyStaysMinimal() {
  assert.equal(
    buildIssueBody('\n第一行\r\n第二行\n'),
    '第一行\n第二行',
  );
}

function testValidateFeedbackFormRequiresTypeAndConfirmation() {
  const invalid = validateFeedbackForm(buildValidForm({
    types: [],
    confirmPublic: false,
  }));

  assert.equal(invalid.valid, false);
  assert.equal(invalid.errors.types, '请至少选择一个反馈类型。');
  assert.equal(invalid.errors.confirmPublic, '请先确认将公开提交。');

  const valid = validateFeedbackForm(buildValidForm());
  assert.equal(valid.valid, true);
  assert.equal(valid.formattedTitle, '[功能新增|体验问题] 侧栏切换后计数不同步');
  assert.equal(valid.body, '切换标签后，当前日期的计数没有立即刷新。');
}

function testBuildIssueDraftUrlTargetsFixedRepo() {
  const url = new URL(buildIssueDraftUrl({
    title: '[功能新增|体验问题] 标题',
    body: '正文内容',
  }));

  assert.equal(url.origin, 'https://github.com');
  assert.equal(url.pathname, `/${TARGET_OWNER}/${TARGET_REPO}/issues/new`);
  assert.equal(url.searchParams.get('title'), '[功能新增|体验问题] 标题');
  assert.equal(url.searchParams.get('body'), '正文内容');
}

function testResolveGithubTokenPrefersDecodedSecretPrivate() {
  const token = resolveGithubToken({
    decoded_secret_private: {
      github: {
        token: 'secret-token',
      },
    },
    SubscriptionsGithubToken: {
      loadGithubToken() {
        return { token: 'fallback-token' };
      },
    },
  });

  assert.equal(token, 'secret-token');
}

function testClassifyIssueError() {
  assert.equal(classifyIssueError({ status: 401 }), 'auth');
  assert.equal(classifyIssueError({ status: 403 }), 'auth');
  assert.equal(classifyIssueError({ status: 404 }), 'auth');
  assert.equal(classifyIssueError({ status: 422 }), 'validation');
  assert.equal(classifyIssueError({ status: 500 }), 'unknown');
}

async function testSubmitIssueUsesApiWhenTokenAvailable() {
  const calls = [];
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        decoded_secret_private: {
          github: {
            token: 'secret-token',
          },
        },
      },
      fetchImpl: async (url, init) => {
        calls.push({ url, init });
        return {
          ok: true,
          json: async () => ({
            number: 12,
            html_url: 'https://github.com/ziwenhahaha/daily-paper-reader/issues/12',
          }),
        };
      },
      openDraft: false,
    },
  );

  assert.equal(result.mode, 'api');
  assert.equal(result.issueNumber, 12);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.github.com/repos/ziwenhahaha/daily-paper-reader/issues');
  assert.equal(calls[0].init.headers.Authorization, 'token secret-token');

  const payload = JSON.parse(calls[0].init.body);
  assert.deepEqual(payload, {
    title: '[功能新增|体验问题] 侧栏切换后计数不同步',
    body: '切换标签后，当前日期的计数没有立即刷新。',
  });
}

async function testSubmitIssueFallsBackToDraftWhenNoToken() {
  let openedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        open(url) {
          openedUrl = url;
          return {};
        },
      },
    },
  );

  assert.equal(result.mode, 'draft');
  assert.match(result.message, /未检测到可用 GitHub Token/);
  assert.equal(openedUrl, result.draftUrl);

  const url = new URL(openedUrl);
  assert.equal(url.pathname, `/${TARGET_OWNER}/${TARGET_REPO}/issues/new`);
  assert.equal(url.searchParams.get('body'), '切换标签后，当前日期的计数没有立即刷新。');
}

async function testBlockedDraftDoesNotNavigateCurrentPage() {
  let assignedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        open() {
          return null;
        },
        location: {
          assign(url) {
            assignedUrl = url;
          },
        },
      },
    },
  );

  assert.equal(result.mode, 'draft');
  assert.equal(result.opened, false);
  assert.equal(assignedUrl, '');
  assert.match(result.message, /再次点击提交按钮/);
}

async function testSubmitIssueFallsBackGracefullyOnAuthFailure() {
  let openedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        SubscriptionsGithubToken: {
          loadGithubToken() {
            return { token: 'stored-token' };
          },
        },
        open(url) {
          openedUrl = url;
          return {};
        },
      },
      fetchImpl: async () => ({
        ok: false,
        status: 403,
        json: async () => ({
          message: 'Resource not accessible by personal access token',
        }),
      }),
    },
  );

  assert.equal(result.mode, 'draft');
  assert.equal(result.errorKind, 'auth');
  assert.match(result.message, /缺少仓库或 Issues 权限/);
  assert.equal(openedUrl, result.draftUrl);
}

function makeMemoryStorage({ throwOnSet = false } = {}) {
  const map = new Map();
  return {
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      if (throwOnSet) throw new Error('QuotaExceededError');
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

function testAutoPromptSkipsGuestLockedAndUpstreamHost() {
  const now = new Date(2026, 10, 24, 14, 0, 0).getTime();
  assert.equal(isUpstreamDemoHost('ziwenhahaha.github.io'), true);
  assert.equal(isUpstreamDemoHost('alice.github.io'), false);

  assert.equal(
    evaluateAutoPrompt({ accessMode: 'guest', hostname: 'alice.github.io', nowMs: now }).reason,
    'not_full_mode',
  );
  assert.equal(
    evaluateAutoPrompt({ accessMode: 'locked', hostname: 'alice.github.io', nowMs: now }).reason,
    'not_full_mode',
  );
  assert.equal(
    evaluateAutoPrompt({ accessMode: 'full', hostname: 'ziwenhahaha.github.io', nowMs: now }).reason,
    'upstream_demo_host',
  );
}

function testAutoPromptTriggersOnceOnSecondDayAndRespectsMidnightBuffer() {
  const storage = makeMemoryStorage();
  const openedCalls = [];
  const openFn = (opts) => {
    openedCalls.push(opts);
    return { id: 'dpr-feedback-overlay' };
  };
  const quietDoc = {
    visibilityState: 'visible',
    getElementById: () => null,
    querySelectorAll: () => [],
    activeElement: null,
  };
  const baseRoot = {
    document: quietDoc,
    localStorage: storage,
    DPR_ACCESS_MODE: 'full',
    location: { hostname: 'alice.github.io' },
  };

  // Day 1 23:30: record first use, do NOT prompt
  const day1Late = new Date(2026, 10, 24, 23, 30, 0).getTime();
  const r1 = checkAutoFeedbackPrompt({ root: baseRoot, nowMs: day1Late, openFn });
  assert.equal(r1.action, 'record_first_use');
  assert.equal(r1.opened, false);
  assert.equal(openedCalls.length, 0);
  const saved = JSON.parse(storage.getItem(AUTO_PROMPT_STORAGE_KEY));
  assert.equal(saved.firstUsedDay, formatLocalDayKey(day1Late));

  // Day 1 23:55: same day, still wait
  const day1Later = new Date(2026, 10, 24, 23, 55, 0).getTime();
  const rSame = checkAutoFeedbackPrompt({ root: baseRoot, nowMs: day1Later, openFn });
  assert.equal(rSame.action, 'wait');
  assert.equal(rSame.reason, 'same_day');
  assert.equal(openedCalls.length, 0);

  // Day 2 00:15 (only 45 min after first use across midnight): wait so setup isn't interrupted
  const day2Midnight = new Date(2026, 10, 25, 0, 15, 0).getTime();
  const rMidnight = checkAutoFeedbackPrompt({ root: baseRoot, nowMs: day2Midnight, openFn });
  assert.equal(rMidnight.action, 'wait');
  assert.equal(rMidnight.reason, 'too_soon_after_first_use');
  assert.equal(openedCalls.length, 0);

  // Day 2 09:00: next morning (>4h elapsed) -> prompt ONCE
  const day2Morning = new Date(2026, 10, 25, 9, 0, 0).getTime();
  const r2 = checkAutoFeedbackPrompt({ root: baseRoot, nowMs: day2Morning, openFn });
  assert.equal(r2.action, 'prompt');
  assert.equal(r2.opened, true);
  assert.deepEqual(openedCalls, [{ source: 'auto' }]);

  // Day 2 afternoon & Day 3+: already prompted, NEVER prompt again
  const day3 = new Date(2026, 10, 26, 10, 0, 0).getTime();
  const r3 = checkAutoFeedbackPrompt({ root: baseRoot, nowMs: day3, openFn });
  assert.equal(r3.action, 'skip');
  assert.equal(r3.reason, 'already_handled');
  assert.equal(r3.opened, false);
  assert.equal(openedCalls.length, 1);
  assert.equal(computeLocalDayDiff('2026-11-24', '2026-11-26'), 2);
}

function testAutoPromptSuppressedAfterManualOpenAndDefersWhenBusy() {
  const storage = makeMemoryStorage();
  const day1 = new Date(2026, 10, 24, 10, 0, 0).getTime();
  const day2 = new Date(2026, 10, 25, 10, 0, 0).getTime();
  const fakeRoot = {
    document: {
      visibilityState: 'visible',
      getElementById: () => null,
      querySelectorAll: () => [],
      activeElement: null,
    },
    localStorage: storage,
    DPR_ACCESS_MODE: 'full',
    location: { hostname: 'bob.github.io' },
  };

  // Manual open on Day 1 suppresses Day 2 auto prompt
  markAutoPromptHandled('manualOpenedAt', fakeRoot, day1);
  const afterManual = checkAutoFeedbackPrompt({
    root: fakeRoot,
    nowMs: day2,
    openFn: () => { throw new Error('must not auto-open after manual open'); },
  });
  assert.equal(afterManual.action, 'skip');
  assert.equal(afterManual.reason, 'already_handled');

  // Busy page defers without consuming the one-time prompt
  const storage2 = makeMemoryStorage();
  const busyRoot = {
    document: {
      visibilityState: 'visible',
      getElementById: (id) => (id === 'arxiv-search-overlay'
        ? { hidden: false, style: { display: 'flex' } }
        : null),
      querySelectorAll: () => [],
      activeElement: null,
    },
    localStorage: storage2,
    DPR_ACCESS_MODE: 'full',
    location: { hostname: 'bob.github.io' },
  };
  assert.equal(isPageBusyForAutoPrompt(busyRoot), true);
  checkAutoFeedbackPrompt({ root: busyRoot, nowMs: day1, openFn: () => ({}) });
  const deferred = checkAutoFeedbackPrompt({ root: busyRoot, nowMs: day2, openFn: () => ({}) });
  assert.equal(deferred.action, 'defer');
  assert.equal(deferred.reason, 'page_busy');
  assert.equal(JSON.parse(storage2.getItem(AUTO_PROMPT_STORAGE_KEY)).promptedAt, null);

  // Storage failure fails closed (never nags repeatedly)
  const readonlyStorage = makeMemoryStorage({ throwOnSet: true });
  const readonlyResult = checkAutoFeedbackPrompt({
    root: {
      ...fakeRoot,
      localStorage: {
        getItem: () => JSON.stringify({ firstUsedDay: '2026-11-24', firstUsedAt: day1 }),
        setItem: readonlyStorage.setItem,
      },
    },
    nowMs: day2,
    openFn: () => { throw new Error('must not open if persistence fails'); },
  });
  assert.equal(readonlyResult.action, 'skip');
  assert.equal(readonlyResult.reason, 'storage_unavailable');
}

async function run() {
  testFeedbackMotionStylesCoverEnterAndExit();
  testNormalizeSelectedTypesKeepsCanonicalOrder();
  testBuildIssueTitleUsesStrictPrefixFormat();
  testBuildIssueBodyStaysMinimal();
  testValidateFeedbackFormRequiresTypeAndConfirmation();
  testBuildIssueDraftUrlTargetsFixedRepo();
  testResolveGithubTokenPrefersDecodedSecretPrivate();
  testClassifyIssueError();
  testAutoPromptSkipsGuestLockedAndUpstreamHost();
  testAutoPromptTriggersOnceOnSecondDayAndRespectsMidnightBuffer();
  testAutoPromptSuppressedAfterManualOpenAndDefersWhenBusy();
  await testSubmitIssueUsesApiWhenTokenAvailable();
  await testSubmitIssueFallsBackToDraftWhenNoToken();
  await testBlockedDraftDoesNotNavigateCurrentPage();
  await testSubmitIssueFallsBackGracefullyOnAuthFailure();
}

run().then(() => {
  console.log('test_feedback_issue.js passed');
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
