(function (root, factory) {
  const api = factory(root || globalThis);
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRFeedback = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  const ISSUE_TYPES = Object.freeze([
    '功能新增',
    'BUG反馈',
    '体验问题',
    '论文 / 会议数据',
    '其他',
  ]);
  const TARGET_OWNER = 'ziwenhahaha';
  const TARGET_REPO = 'daily-paper-reader';
  const FEEDBACK_ANIMATION_MS = 180;
  const AUTO_PROMPT_STORAGE_KEY = 'dpr_feedback_day2_prompt_v1';
  const AUTO_PROMPT_MIN_ELAPSED_MS = 4 * 60 * 60 * 1000;
  const AUTO_PROMPT_DELAY_MS = 2500;
  const UPSTREAM_HOST_TOKEN = 'ziwenhahaha';

  const getFeedbackMotionStyles = (isVisible) => ({
    overlay: {
      opacity: isVisible ? '1' : '0',
    },
    panel: {
      opacity: isVisible ? '1' : '0',
      transform: isVisible
        ? 'translateY(0) scale(1)'
        : 'translateY(12px) scale(0.98)',
    },
  });

  const state = {
    overlay: null,
    refs: null,
    bodyOverflow: '',
    attemptedSubmit: false,
    submitting: false,
    submitted: false,
    submittedLabel: '',
    pendingDraftUrl: '',
    restoreFocus: null,
    keydownHandler: null,
    openFrame: null,
    closingTimer: null,
    isClosing: false,
    autoPromptTimer: null,
    autoPromptBound: false,
  };

  const formatLocalDayKey = (timestampMs) => {
    const date = new Date(Number(timestampMs));
    if (Number.isNaN(date.getTime())) return '';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const parseDayKeyToUtcMs = (dayKey) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dayKey || '').trim());
    if (!match) return NaN;
    return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  };

  const computeLocalDayDiff = (fromDayKey, toDayKey) => {
    const fromMs = parseDayKeyToUtcMs(fromDayKey);
    const toMs = parseDayKeyToUtcMs(toDayKey);
    if (!Number.isFinite(fromMs) || !Number.isFinite(toMs)) return NaN;
    return Math.round((toMs - fromMs) / 86400000);
  };

  const isUpstreamDemoHost = (hostname) => String(hostname || '').toLowerCase().includes(UPSTREAM_HOST_TOKEN);

  const toPositiveTimestamp = (value) => {
    if (value == null || value === '') return null;
    const num = Number(value);
    return Number.isFinite(num) && num > 0 ? num : null;
  };

  const normalizeAutoPromptRecord = (raw) => {
    if (!raw || typeof raw !== 'object') return null;
    const firstUsedDay = typeof raw.firstUsedDay === 'string' && parseDayKeyToUtcMs(raw.firstUsedDay) ? raw.firstUsedDay : '';
    const firstUsedAt = toPositiveTimestamp(raw.firstUsedAt);
    const promptedAt = toPositiveTimestamp(raw.promptedAt);
    const manualOpenedAt = toPositiveTimestamp(raw.manualOpenedAt);
    const submittedAt = toPositiveTimestamp(raw.submittedAt);
    if (!firstUsedDay && !firstUsedAt && !promptedAt && !manualOpenedAt && !submittedAt) return null;
    return {
      firstUsedDay,
      firstUsedAt,
      promptedAt,
      manualOpenedAt,
      submittedAt,
    };
  };

  const readAutoPromptRecord = (storage) => {
    if (!storage || typeof storage.getItem !== 'function') return null;
    try {
      const raw = storage.getItem(AUTO_PROMPT_STORAGE_KEY);
      if (!raw) return null;
      return normalizeAutoPromptRecord(JSON.parse(raw));
    } catch {
      return null;
    }
  };

  const writeAutoPromptRecord = (storage, record) => {
    if (!storage || typeof storage.setItem !== 'function') return false;
    try {
      storage.setItem(AUTO_PROMPT_STORAGE_KEY, JSON.stringify(record));
      return true;
    } catch {
      return false;
    }
  };

  const evaluateAutoPrompt = ({
    accessMode = '',
    hostname = '',
    nowMs = Date.now(),
    record = null,
    minElapsedMs = AUTO_PROMPT_MIN_ELAPSED_MS,
  } = {}) => {
    if (String(accessMode || '').toLowerCase() !== 'full') {
      return { action: 'skip', reason: 'not_full_mode' };
    }
    if (isUpstreamDemoHost(hostname)) {
      return { action: 'skip', reason: 'upstream_demo_host' };
    }

    const normalized = normalizeAutoPromptRecord(record);
    if (normalized && (normalized.promptedAt || normalized.manualOpenedAt || normalized.submittedAt)) {
      return { action: 'skip', reason: 'already_handled' };
    }

    const todayKey = formatLocalDayKey(nowMs);
    if (!todayKey) {
      return { action: 'skip', reason: 'invalid_time' };
    }

    if (!normalized || !normalized.firstUsedDay || !Number.isFinite(normalized.firstUsedAt)) {
      return {
        action: 'record_first_use',
        reason: 'first_day_recorded',
        nextRecord: {
          firstUsedDay: todayKey,
          firstUsedAt: nowMs,
          promptedAt: null,
          manualOpenedAt: null,
          submittedAt: null,
        },
      };
    }

    const dayDiff = computeLocalDayDiff(normalized.firstUsedDay, todayKey);
    const elapsedMs = nowMs - normalized.firstUsedAt;
    if (!Number.isFinite(dayDiff) || dayDiff < 1) {
      return { action: 'wait', reason: 'same_day', dayDiff, elapsedMs };
    }
    if (dayDiff === 1 && elapsedMs < minElapsedMs) {
      return { action: 'wait', reason: 'too_soon_after_first_use', dayDiff, elapsedMs };
    }

    return {
      action: 'prompt',
      reason: 'second_day_reached',
      dayDiff,
      elapsedMs,
      nextRecord: {
        ...normalized,
        promptedAt: nowMs,
      },
    };
  };

  const isElementVisible = (el, scopeRoot) => {
    if (!el || el.hidden) return false;
    try {
      const style = scopeRoot && typeof scopeRoot.getComputedStyle === 'function'
        ? scopeRoot.getComputedStyle(el)
        : el.style;
      if (style && (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0')) {
        return false;
      }
      if (typeof el.getBoundingClientRect === 'function') {
        const rect = el.getBoundingClientRect();
        if (rect && rect.width === 0 && rect.height === 0) return false;
      }
    } catch {
      // fall through
    }
    return true;
  };

  const isPageBusyForAutoPrompt = (scopeRoot) => {
    const safeRoot = scopeRoot || root || {};
    const doc = safeRoot.document;
    if (!doc) return true;
    if (doc.visibilityState && doc.visibilityState !== 'visible') return true;
    if (state.overlay) return true;

    const secretOverlay = typeof doc.getElementById === 'function'
      ? doc.getElementById('secret-gate-overlay')
      : null;
    if (secretOverlay) {
      const hiddenByClass = secretOverlay.classList
        && typeof secretOverlay.classList.contains === 'function'
        && secretOverlay.classList.contains('secret-gate-hidden');
      const shownByClass = secretOverlay.classList
        && typeof secretOverlay.classList.contains === 'function'
        && secretOverlay.classList.contains('show');
      if (shownByClass || (!hiddenByClass && isElementVisible(secretOverlay, safeRoot))) {
        return true;
      }
    }

    const adminOverlay = typeof doc.getElementById === 'function'
      ? doc.getElementById('arxiv-search-overlay')
      : null;
    if (adminOverlay && isElementVisible(adminOverlay, safeRoot)) {
      return true;
    }

    if (typeof doc.querySelectorAll === 'function') {
      const modals = doc.querySelectorAll('[aria-modal="true"]');
      for (let i = 0; i < modals.length; i += 1) {
        if (isElementVisible(modals[i], safeRoot)) return true;
      }
    }

    const active = doc.activeElement;
    if (active) {
      const tag = String(active.tagName || '').toUpperCase();
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || active.isContentEditable) {
        return true;
      }
    }

    return false;
  };

  const markAutoPromptHandled = (fieldName, scopeRoot, nowMs = Date.now()) => {
    const safeRoot = scopeRoot || root || {};
    const storage = safeRoot.localStorage;
    if (!storage) return false;
    const existing = readAutoPromptRecord(storage) || {
      firstUsedDay: formatLocalDayKey(nowMs),
      firstUsedAt: nowMs,
      promptedAt: null,
      manualOpenedAt: null,
      submittedAt: null,
    };
    const next = {
      ...existing,
      [fieldName]: existing[fieldName] || nowMs,
    };
    return writeAutoPromptRecord(storage, next);
  };

  const normalizeText = (value) => String(value == null ? '' : value).replace(/\r\n/g, '\n').trim();

  const normalizeInlineText = (value) => normalizeText(value).replace(/\s+/g, ' ');

  const normalizeSelectedTypes = (values) => {
    const rawValues = Array.isArray(values)
      ? values
      : values && typeof values[Symbol.iterator] === 'function'
        ? Array.from(values)
        : values == null
          ? []
          : [values];
    const selected = new Set(rawValues.map((item) => String(item || '').trim()).filter(Boolean));
    return ISSUE_TYPES.filter((item) => selected.has(item));
  };

  const stripExistingTypePrefix = (title) => normalizeInlineText(title).replace(/^\[[^\]]*\]\s*/u, '');

  const buildIssueTitle = (types, rawTitle) => {
    const normalizedTypes = normalizeSelectedTypes(types);
    const cleanTitle = stripExistingTypePrefix(rawTitle);
    if (!normalizedTypes.length || !cleanTitle) return '';
    return `[${normalizedTypes.join('|')}] ${cleanTitle}`;
  };

  const buildIssueBody = (content) => normalizeText(content);

  const validateFeedbackForm = (form) => {
    const normalizedTypes = normalizeSelectedTypes(form && form.types);
    const plainTitle = stripExistingTypePrefix(form && form.title);
    const body = buildIssueBody(form && form.content);
    const confirmPublic = Boolean(form && form.confirmPublic);
    const errors = {};

    if (!normalizedTypes.length) {
      errors.types = '请至少选择一个反馈类型。';
    }
    if (!plainTitle) {
      errors.title = '请填写标题。';
    }
    if (!body) {
      errors.content = '请填写反馈内容。';
    }
    if (!confirmPublic) {
      errors.confirmPublic = '请先确认将公开提交。';
    }

    const formattedTitle = buildIssueTitle(normalizedTypes, plainTitle);
    return {
      valid: Object.keys(errors).length === 0,
      errors,
      types: normalizedTypes,
      plainTitle,
      formattedTitle,
      body,
      confirmPublic,
    };
  };

  const buildIssueDraftUrl = ({ title, body, owner = TARGET_OWNER, repo = TARGET_REPO } = {}) => {
    const params = new URLSearchParams();
    params.set('title', normalizeInlineText(title));
    params.set('body', buildIssueBody(body));
    return `https://github.com/${owner}/${repo}/issues/new?${params.toString()}`;
  };

  const readTokenFromStoredData = (tokenData) => {
    if (!tokenData) return '';
    if (typeof tokenData === 'string') return String(tokenData).trim();
    return String((tokenData && tokenData.token) || '').trim();
  };

  const resolveGithubToken = (scopeRoot) => {
    const safeRoot = scopeRoot || root || {};
    const secret = safeRoot.decoded_secret_private || {};
    if (secret.github && secret.github.token) {
      return String(secret.github.token || '').trim();
    }
    const tokenLoader = safeRoot.SubscriptionsGithubToken
      && typeof safeRoot.SubscriptionsGithubToken.loadGithubToken === 'function'
      ? safeRoot.SubscriptionsGithubToken.loadGithubToken
      : null;
    if (!tokenLoader) return '';
    return readTokenFromStoredData(tokenLoader.call(safeRoot.SubscriptionsGithubToken));
  };

  const classifyIssueError = (error) => {
    const status = Number(error && error.status);
    if (status === 401 || status === 403 || status === 404) return 'auth';
    if (status === 422) return 'validation';
    return 'unknown';
  };

  const parseGitHubErrorPayload = async (response) => {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      try {
        const text = await response.text();
        if (text) payload = { message: text };
      } catch {
        payload = null;
      }
    }
    const message = payload && typeof payload.message === 'string'
      ? payload.message
      : `GitHub API 请求失败（HTTP ${response.status}）`;
    return {
      status: response.status,
      message,
      payload,
    };
  };

  const createIssueViaApi = async ({ token, title, body, fetchImpl }) => {
    const response = await fetchImpl(
      `https://api.github.com/repos/${TARGET_OWNER}/${TARGET_REPO}/issues`,
      {
        method: 'POST',
        headers: {
          Authorization: `token ${token}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          body,
        }),
      },
    );

    if (!response.ok) {
      throw await parseGitHubErrorPayload(response);
    }

    const payload = await response.json().catch(() => ({}));
    return {
      number: payload.number || null,
      htmlUrl: payload.html_url || '',
      payload,
    };
  };

  const openDraftIssuePage = (scopeRoot, url) => {
    if (!url) return false;
    const safeRoot = scopeRoot || root || {};
    try {
      if (typeof safeRoot.open === 'function') {
        const opened = safeRoot.open(url, '_blank', 'noopener');
        if (opened) return true;
      }
    } catch {
      // ignore
    }
    return false;
  };

  const submitIssueWithFallback = async (form, options = {}) => {
    const validation = validateFeedbackForm(form);
    if (!validation.valid) {
      return {
        ok: false,
        mode: 'invalid',
        validation,
        message: Object.values(validation.errors)[0] || '表单校验失败。',
      };
    }

    const safeRoot = options.root || root || {};
    const fetchImpl = options.fetchImpl || (typeof safeRoot.fetch === 'function' ? safeRoot.fetch.bind(safeRoot) : null);
    const token = Object.prototype.hasOwnProperty.call(options, 'token')
      ? String(options.token || '').trim()
      : resolveGithubToken(safeRoot);
    const draftUrl = buildIssueDraftUrl({
      title: validation.formattedTitle,
      body: validation.body,
    });

    if (!token) {
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        message: opened
          ? '未检测到可用 GitHub Token，已为你打开预填好的公开 Issue 页面。'
          : '浏览器未能打开 GitHub，请再次点击提交按钮继续。',
      };
    }

    if (!fetchImpl) {
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        errorKind: 'unknown',
        message: opened
          ? '当前环境无法直接调用 GitHub API，已为你打开预填好的公开 Issue 页面。'
          : '当前环境无法直接调用 GitHub API，请再次点击提交按钮继续。',
      };
    }

    try {
      const created = await createIssueViaApi({
        token,
        title: validation.formattedTitle,
        body: validation.body,
        fetchImpl,
      });
      return {
        ok: true,
        mode: 'api',
        opened: false,
        validation,
        draftUrl,
        issueNumber: created.number,
        htmlUrl: created.htmlUrl,
        message: created.number
          ? `已公开提交到 GitHub Issues：#${created.number}`
          : '已公开提交到 GitHub Issues。',
      };
    } catch (error) {
      const errorKind = classifyIssueError(error);
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      let message = '自动创建 issue 失败，已为你打开预填好的公开 issue 页面。';
      if (errorKind === 'auth') {
        message = opened
          ? 'GitHub Token 可能缺少仓库或 Issues 权限，已打开预填好的公开 Issue 页面。'
          : 'GitHub Token 可能缺少仓库或 Issues 权限，请再次点击提交按钮继续。';
      } else if (errorKind === 'validation') {
        message = opened
          ? 'GitHub API 拒绝了当前内容，已打开预填好的公开 Issue 页面。'
          : 'GitHub API 拒绝了当前内容，请再次点击提交按钮继续。';
      } else if (!opened) {
        message = '自动创建 Issue 失败，请再次点击提交按钮继续。';
      }
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        errorKind,
        error,
        message,
      };
    }
  };

  const hasDom = () => Boolean(root && root.document && typeof root.document.createElement === 'function');

  const applyStyles = (node, styles) => {
    Object.keys(styles).forEach((key) => {
      node.style[key] = styles[key];
    });
  };

  const prefersReducedMotion = () => Boolean(
    root
      && typeof root.matchMedia === 'function'
      && root.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  const applyFeedbackMotionStyles = (overlay, panel, isVisible) => {
    if (!overlay || !panel) return;
    const styles = getFeedbackMotionStyles(isVisible);
    applyStyles(overlay, styles.overlay);
    applyStyles(panel, styles.panel);
  };

  const clearScheduledOpen = () => {
    if (state.openFrame == null) return;
    if (root && typeof root.cancelAnimationFrame === 'function') {
      root.cancelAnimationFrame(state.openFrame);
    } else {
      root.clearTimeout(state.openFrame);
    }
    state.openFrame = null;
  };

  const clearClosingTimer = () => {
    if (state.closingTimer == null) return;
    root.clearTimeout(state.closingTimer);
    state.closingTimer = null;
  };

  const setStatus = (text, tone) => {
    if (!state.refs || !state.refs.status) return;
    const colorMap = {
      error: '#b42318',
      success: '#067647',
      info: '#344054',
    };
    state.refs.status.textContent = text || '';
    state.refs.status.style.color = colorMap[tone] || colorMap.info;
  };

  const collectFormData = () => {
    const refs = state.refs;
    if (!refs) {
      return {
        types: [],
        title: '',
        content: '',
        confirmPublic: false,
      };
    }
    return {
      types: refs.typeInputs.filter((input) => input.checked).map((input) => input.value),
      title: refs.titleInput.value,
      content: refs.contentInput.value,
      confirmPublic: refs.confirmInput.checked,
    };
  };

  const renderValidationState = () => {
    if (!state.refs) return;
    const validation = validateFeedbackForm(collectFormData());
    const refs = state.refs;
    const canSubmit = (validation.valid || Boolean(state.pendingDraftUrl))
      && !state.submitting
      && !state.submitted;

    refs.submitButton.disabled = !canSubmit;
    refs.submitButton.style.opacity = canSubmit ? '1' : '0.55';
    refs.submitButton.style.cursor = canSubmit ? 'pointer' : 'not-allowed';

    if (refs.titlePreview) {
      refs.titlePreview.textContent = validation.formattedTitle
        ? `Issue 标题：${validation.formattedTitle}`
        : 'Issue 标题将在选择类型并填写标题后生成。';
    }

    if (state.submitted) return validation;

    if (!state.attemptedSubmit) {
      setStatus('公开提交前请确认类型、标题、内容，并勾选公开确认。', 'info');
      return validation;
    }

    if (!validation.valid) {
      const firstError = validation.errors.types
        || validation.errors.title
        || validation.errors.content
        || validation.errors.confirmPublic
        || '表单校验失败。';
      setStatus(firstError, 'error');
      return validation;
    }

    if (!state.submitting) {
      setStatus('确认后将公开提交到 GitHub Issues。', 'info');
    }
    return validation;
  };

  const updateButtonBusyState = () => {
    if (!state.refs) return;
    if (state.submitting) {
      state.refs.submitButton.textContent = '提交中...';
    } else if (state.submitted) {
      state.refs.submitButton.textContent = state.submittedLabel || '已提交';
    } else if (state.pendingDraftUrl) {
      state.refs.submitButton.textContent = '在 GitHub 打开';
    } else {
      state.refs.submitButton.textContent = '公开提交反馈';
    }
    renderValidationState();
  };

  const finishClose = (snapshot) => {
    if (snapshot.overlay && snapshot.overlay.parentNode) {
      snapshot.overlay.parentNode.removeChild(snapshot.overlay);
    }
    if (state.overlay !== snapshot.overlay) return;

    state.overlay = null;
    state.refs = null;
    state.attemptedSubmit = false;
    state.submitting = false;
    state.submitted = false;
    state.submittedLabel = '';
    state.pendingDraftUrl = '';
    state.restoreFocus = null;
    state.keydownHandler = null;
    state.openFrame = null;
    state.closingTimer = null;
    state.isClosing = false;
    state.bodyOverflow = '';
    if (hasDom() && root.document && root.document.body) {
      root.document.body.style.overflow = snapshot.bodyOverflow || '';
    }
    if (snapshot.shouldRestoreFocus
      && snapshot.restoreFocus
      && typeof snapshot.restoreFocus.focus === 'function') {
      snapshot.restoreFocus.focus();
    }
  };

  const close = (options = {}) => {
    if (!state.overlay) return;
    const immediate = Boolean(options && options.immediate);
    const snapshot = {
      overlay: state.overlay,
      restoreFocus: state.restoreFocus,
      bodyOverflow: state.bodyOverflow,
      shouldRestoreFocus: !(options && options.restoreFocus === false),
    };

    if (state.keydownHandler && hasDom()) {
      root.document.removeEventListener('keydown', state.keydownHandler);
    }
    state.keydownHandler = null;
    clearScheduledOpen();

    if (state.isClosing && !immediate) return;
    clearClosingTimer();

    if (immediate || prefersReducedMotion()) {
      finishClose(snapshot);
      return;
    }

    state.isClosing = true;
    state.overlay.style.pointerEvents = 'none';
    state.overlay.setAttribute('aria-hidden', 'true');
    applyFeedbackMotionStyles(state.overlay, state.refs && state.refs.panel, false);
    state.closingTimer = root.setTimeout(() => {
      state.closingTimer = null;
      finishClose(snapshot);
    }, FEEDBACK_ANIMATION_MS);
  };

  const handleSubmit = async () => {
    if (!state.refs || state.submitting) return;
    if (state.pendingDraftUrl) {
      const opened = openDraftIssuePage(root, state.pendingDraftUrl);
      if (opened) {
        state.pendingDraftUrl = '';
        state.submitted = true;
        state.submittedLabel = '已打开 GitHub';
        markAutoPromptHandled('submittedAt', root);
        setStatus('已打开预填好的公开 Issue 页面，请在 GitHub 完成提交。', 'success');
      } else {
        setStatus('浏览器阻止了新窗口，请允许本站打开弹窗后重试。', 'error');
      }
      updateButtonBusyState();
      return;
    }
    state.attemptedSubmit = true;
    const validation = renderValidationState();
    if (!validation.valid) return;

    state.submitting = true;
    updateButtonBusyState();
    setStatus('正在提交公开 issue...', 'info');

    try {
      const result = await submitIssueWithFallback(collectFormData(), { root });
      if (result.mode === 'api') {
        state.submitted = true;
        state.submittedLabel = '提交成功';
        markAutoPromptHandled('submittedAt', root);
        setStatus(result.message, 'success');
      } else {
        if (result.opened) {
          state.submitted = true;
          state.submittedLabel = '已打开 GitHub';
          markAutoPromptHandled('submittedAt', root);
        } else if (result.draftUrl) {
          state.pendingDraftUrl = result.draftUrl;
        }
        setStatus(result.message, result.errorKind ? 'error' : 'info');
      }
    } finally {
      state.submitting = false;
      updateButtonBusyState();
    }
  };

  const createTypeCheckbox = (documentRef, typeLabel) => {
    const label = documentRef.createElement('label');
    label.className = 'dpr-feedback-type-option';
    applyStyles(label, {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '6px 10px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      background: '#f8fafc',
      color: '#101828',
      fontSize: '13px',
      lineHeight: '18px',
      cursor: 'pointer',
      userSelect: 'none',
    });

    const input = documentRef.createElement('input');
    input.type = 'checkbox';
    input.name = 'dpr-feedback-types';
    input.value = typeLabel;
    input.style.margin = '0';
    input.addEventListener('change', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const text = documentRef.createElement('span');
    text.textContent = typeLabel;

    label.appendChild(input);
    label.appendChild(text);
    return { label, input };
  };

  const buildModal = (options = {}) => {
    if (!hasDom()) return null;
    const documentRef = root.document;
    const isAutoPrompt = Boolean(options && options.isAutoPrompt);

    const overlay = documentRef.createElement('div');
    overlay.id = 'dpr-feedback-overlay';
    overlay.className = 'dpr-feedback-overlay';
    overlay.setAttribute('role', 'presentation');
    applyStyles(overlay, {
      position: 'fixed',
      inset: '0',
      zIndex: '9999',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '16px',
      background: 'rgba(15, 23, 42, 0.52)',
      boxSizing: 'border-box',
      opacity: '0',
      transition: `opacity ${FEEDBACK_ANIMATION_MS}ms ease`,
      willChange: 'opacity',
    });
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) {
        close();
      }
    });

    const panel = documentRef.createElement('section');
    panel.id = 'dpr-feedback-panel';
    panel.className = 'dpr-feedback-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'dpr-feedback-heading');
    applyStyles(panel, {
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      width: 'min(640px, 100%)',
      maxHeight: 'calc(100vh - 32px)',
      overflowY: 'auto',
      overflowX: 'hidden',
      padding: '22px 24px 20px',
      borderRadius: '12px',
      background: '#ffffff',
      boxShadow: '0 24px 72px rgba(15, 23, 42, 0.22)',
      boxSizing: 'border-box',
      color: '#101828',
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      opacity: '0',
      transform: 'translateY(12px) scale(0.98)',
      transformOrigin: 'center center',
      transition: `opacity ${FEEDBACK_ANIMATION_MS}ms ease, transform ${FEEDBACK_ANIMATION_MS}ms cubic-bezier(0.2, 0, 0, 1)`,
      willChange: 'opacity, transform',
    });

    const closeButton = documentRef.createElement('button');
    closeButton.id = 'dpr-feedback-close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', '关闭');
    closeButton.textContent = '×';
    applyStyles(closeButton, {
      position: 'absolute',
      top: '12px',
      right: '12px',
      width: '34px',
      height: '34px',
      border: '0',
      borderRadius: '999px',
      background: 'transparent',
      color: '#344054',
      fontSize: '22px',
      lineHeight: '34px',
      cursor: 'pointer',
    });
    closeButton.addEventListener('click', close);

    const title = documentRef.createElement('h2');
    title.id = 'dpr-feedback-heading';
    title.textContent = '公开反馈';
    applyStyles(title, {
      margin: '0 36px 4px 0',
      fontSize: '20px',
      lineHeight: '28px',
      fontWeight: '700',
    });

    const intro = documentRef.createElement('p');
    intro.textContent = '提交后会公开发布到 GitHub Issues，请不要填写隐私或敏感信息。';
    applyStyles(intro, {
      margin: '0 0 12px',
      color: '#475467',
      fontSize: '13px',
      lineHeight: '20px',
    });

    let autoBanner = null;
    if (isAutoPrompt) {
      autoBanner = documentRef.createElement('div');
      autoBanner.id = 'dpr-feedback-auto-banner';
      autoBanner.textContent = '使用已经第二天啦 👋 如果有任何体验建议、Bug 或想补充的会议/功能，欢迎随手告诉我们。本提示仅自动弹出这一次，不想填写直接关闭即可。';
      applyStyles(autoBanner, {
        margin: '0 0 12px',
        padding: '8px 12px',
        borderRadius: '8px',
        border: '1px solid #bbf7d0',
        background: '#f0fdf4',
        color: '#166534',
        fontSize: '12.5px',
        lineHeight: '19px',
      });
    }

    const typeTitle = documentRef.createElement('div');
    typeTitle.id = 'dpr-feedback-types-label';
    typeTitle.textContent = '反馈类型';
    applyStyles(typeTitle, {
      margin: '0 0 6px',
      fontSize: '13px',
      lineHeight: '18px',
      fontWeight: '600',
    });

    const typeWrap = documentRef.createElement('div');
    typeWrap.setAttribute('role', 'group');
    typeWrap.setAttribute('aria-labelledby', 'dpr-feedback-types-label');
    applyStyles(typeWrap, {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      marginBottom: '12px',
    });

    const typeInputs = ISSUE_TYPES.map((item) => createTypeCheckbox(documentRef, item));
    typeInputs.forEach(({ label }) => typeWrap.appendChild(label));

    const titleLabel = documentRef.createElement('label');
    titleLabel.htmlFor = 'dpr-feedback-title-input';
    titleLabel.textContent = '标题';
    applyStyles(titleLabel, {
      display: 'block',
      margin: '0 0 6px',
      fontSize: '13px',
      lineHeight: '18px',
      fontWeight: '600',
    });

    const titleInput = documentRef.createElement('input');
    titleInput.id = 'dpr-feedback-title-input';
    titleInput.type = 'text';
    titleInput.placeholder = '例如：会议标签切换后计数不刷新';
    applyStyles(titleInput, {
      width: '100%',
      padding: '9px 12px',
      margin: '0 0 6px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      fontSize: '13.5px',
      lineHeight: '20px',
      boxSizing: 'border-box',
    });
    titleInput.addEventListener('input', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const titlePreview = documentRef.createElement('div');
    titlePreview.id = 'dpr-feedback-title-preview';
    applyStyles(titlePreview, {
      margin: '0 0 12px',
      color: '#667085',
      fontSize: '12px',
      lineHeight: '16px',
      overflowWrap: 'anywhere',
    });

    const contentLabel = documentRef.createElement('label');
    contentLabel.htmlFor = 'dpr-feedback-content-input';
    contentLabel.textContent = '内容';
    applyStyles(contentLabel, {
      display: 'block',
      margin: '0 0 6px',
      fontSize: '13px',
      lineHeight: '18px',
      fontWeight: '600',
    });

    const contentInput = documentRef.createElement('textarea');
    contentInput.id = 'dpr-feedback-content-input';
    contentInput.placeholder = '请直接写问题、现象、建议或缺失的数据。';
    applyStyles(contentInput, {
      width: '100%',
      height: '120px',
      minHeight: '96px',
      flex: '0 1 auto',
      padding: '10px 12px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      resize: 'none',
      fontSize: '13.5px',
      lineHeight: '20px',
      boxSizing: 'border-box',
    });
    contentInput.addEventListener('input', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const confirmRow = documentRef.createElement('label');
    applyStyles(confirmRow, {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '8px',
      marginTop: '12px',
      color: '#101828',
      fontSize: '13px',
      lineHeight: '20px',
      cursor: 'pointer',
    });

    const confirmInput = documentRef.createElement('input');
    confirmInput.id = 'dpr-feedback-public-confirm';
    confirmInput.type = 'checkbox';
    confirmInput.style.margin = '3px 0 0';
    confirmInput.addEventListener('change', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const confirmText = documentRef.createElement('span');
    confirmText.textContent = '我已知晓这会公开提交到 GitHub Issues，任何人都可能看到。';

    confirmRow.appendChild(confirmInput);
    confirmRow.appendChild(confirmText);

    const status = documentRef.createElement('div');
    status.id = 'dpr-feedback-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    applyStyles(status, {
      minHeight: '18px',
      marginTop: '10px',
      fontSize: '13px',
      lineHeight: '18px',
      color: '#344054',
    });

    const submitButton = documentRef.createElement('button');
    submitButton.id = 'dpr-feedback-submit';
    submitButton.type = 'button';
    submitButton.textContent = '公开提交反馈';
    applyStyles(submitButton, {
      width: isAutoPrompt ? 'auto' : '100%',
      flex: isAutoPrompt ? '1 1 auto' : '',
      marginTop: isAutoPrompt ? '0' : '12px',
      padding: '10px 16px',
      border: '0',
      borderRadius: '8px',
      background: '#1d4ed8',
      color: '#ffffff',
      fontSize: '14px',
      lineHeight: '20px',
      fontWeight: '600',
      cursor: 'pointer',
    });
    submitButton.addEventListener('click', handleSubmit);

    let actionFooter = submitButton;
    if (isAutoPrompt) {
      const actionRow = documentRef.createElement('div');
      actionRow.id = 'dpr-feedback-actions';
      applyStyles(actionRow, {
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        marginTop: '12px',
      });

      const dismissButton = documentRef.createElement('button');
      dismissButton.id = 'dpr-feedback-dismiss';
      dismissButton.type = 'button';
      dismissButton.textContent = '暂不反馈';
      applyStyles(dismissButton, {
        flex: '0 0 auto',
        padding: '10px 18px',
        border: '1px solid #d0d5dd',
        borderRadius: '8px',
        background: '#ffffff',
        color: '#344054',
        fontSize: '14px',
        lineHeight: '20px',
        fontWeight: '600',
        cursor: 'pointer',
      });
      dismissButton.addEventListener('click', () => close());

      actionRow.appendChild(dismissButton);
      actionRow.appendChild(submitButton);
      actionFooter = actionRow;
    }

    panel.appendChild(closeButton);
    panel.appendChild(title);
    panel.appendChild(intro);
    if (autoBanner) {
      panel.appendChild(autoBanner);
    }
    panel.appendChild(typeTitle);
    panel.appendChild(typeWrap);
    panel.appendChild(titleLabel);
    panel.appendChild(titleInput);
    panel.appendChild(titlePreview);
    panel.appendChild(contentLabel);
    panel.appendChild(contentInput);
    panel.appendChild(confirmRow);
    panel.appendChild(status);
    panel.appendChild(actionFooter);
    overlay.appendChild(panel);

    return {
      overlay,
      refs: {
        panel,
        closeButton,
        typeInputs: typeInputs.map((item) => item.input),
        titleInput,
        titlePreview,
        contentInput,
        confirmInput,
        status,
        submitButton,
      },
    };
  };

  const open = (prefill = {}) => {
    if (!hasDom()) return null;
    clearAutoPromptTimer();
    const isAutoPrompt = Boolean(prefill && prefill.source === 'auto');
    if (!isAutoPrompt) {
      markAutoPromptHandled('manualOpenedAt', root);
    }
    close({ immediate: true, restoreFocus: false });

    const built = buildModal({ isAutoPrompt });
    if (!built) return null;

    state.overlay = built.overlay;
    state.refs = built.refs;
    state.attemptedSubmit = false;
    state.submitting = false;
    state.submitted = false;
    state.submittedLabel = '';
    state.pendingDraftUrl = '';
    state.isClosing = false;
    state.restoreFocus = root.document.activeElement || null;
    state.bodyOverflow = root.document.body ? root.document.body.style.overflow || '' : '';

    state.keydownHandler = (event) => {
      if (event && event.key === 'Escape' && !state.submitting) close();
    };
    root.document.addEventListener('keydown', state.keydownHandler);

    if (root.document.body) {
      root.document.body.appendChild(state.overlay);
      root.document.body.style.overflow = 'hidden';
    }

    const reveal = () => {
      state.openFrame = null;
      if (state.overlay !== built.overlay || state.isClosing) return;
      applyFeedbackMotionStyles(built.overlay, built.refs.panel, true);
    };
    if (prefersReducedMotion()) {
      reveal();
    } else if (typeof root.requestAnimationFrame === 'function') {
      built.overlay.getBoundingClientRect();
      state.openFrame = root.requestAnimationFrame(reveal);
    } else {
      state.openFrame = root.setTimeout(reveal, 0);
    }

    const types = normalizeSelectedTypes(prefill.types);
    state.refs.typeInputs.forEach((input) => {
      input.checked = types.includes(input.value);
    });
    state.refs.titleInput.value = normalizeInlineText(prefill.title || '');
    state.refs.contentInput.value = normalizeText(prefill.content || '');
    state.refs.confirmInput.checked = Boolean(prefill.confirmPublic);

    renderValidationState();
    const focusTarget = isAutoPrompt ? state.refs.closeButton : state.refs.titleInput;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      focusTarget.focus();
    }
    return state.overlay;
  };

  const clearAutoPromptTimer = () => {
    if (state.autoPromptTimer == null) return;
    if (root && typeof root.clearTimeout === 'function') {
      root.clearTimeout(state.autoPromptTimer);
    }
    state.autoPromptTimer = null;
  };

  const checkAutoFeedbackPrompt = (options = {}) => {
    const safeRoot = options.root || root || {};
    const storage = options.storage || safeRoot.localStorage;
    const nowMs = Number.isFinite(Number(options.nowMs)) ? Number(options.nowMs) : Date.now();
    const accessMode = Object.prototype.hasOwnProperty.call(options, 'accessMode')
      ? options.accessMode
      : safeRoot.DPR_ACCESS_MODE;
    const hostname = Object.prototype.hasOwnProperty.call(options, 'hostname')
      ? options.hostname
      : (safeRoot.location && safeRoot.location.hostname) || '';
    const record = readAutoPromptRecord(storage);
    const decision = evaluateAutoPrompt({
      accessMode,
      hostname,
      nowMs,
      record,
      minElapsedMs: options.minElapsedMs,
    });

    if (decision.action === 'record_first_use') {
      const saved = writeAutoPromptRecord(storage, decision.nextRecord);
      return { ...decision, saved, opened: false };
    }

    if (decision.action !== 'prompt') {
      return { ...decision, opened: false };
    }

    if (options.bypassBusyCheck !== true && isPageBusyForAutoPrompt(safeRoot)) {
      return { action: 'defer', reason: 'page_busy', opened: false };
    }

    // 必须先成功落盘“已弹出”标记，避免在隐私模式/禁用存储环境下重复打扰用户。
    if (!writeAutoPromptRecord(storage, decision.nextRecord)) {
      return { action: 'skip', reason: 'storage_unavailable', opened: false };
    }

    const openFn = typeof options.openFn === 'function' ? options.openFn : open;
    const overlay = openFn({ source: 'auto' });
    return { ...decision, opened: Boolean(overlay) };
  };

  const scheduleAutoFeedbackPrompt = (delayMs = AUTO_PROMPT_DELAY_MS) => {
    if (!hasDom()) return;
    const safeRoot = root || {};
    const accessMode = safeRoot.DPR_ACCESS_MODE;
    const hostname = (safeRoot.location && safeRoot.location.hostname) || '';
    const storage = safeRoot.localStorage;
    const decision = evaluateAutoPrompt({
      accessMode,
      hostname,
      nowMs: Date.now(),
      record: readAutoPromptRecord(storage),
    });

    if (decision.action === 'record_first_use') {
      writeAutoPromptRecord(storage, decision.nextRecord);
      return;
    }
    if (decision.action !== 'prompt') {
      clearAutoPromptTimer();
      return;
    }
    if (safeRoot.document && safeRoot.document.visibilityState && safeRoot.document.visibilityState !== 'visible') {
      return;
    }

    clearAutoPromptTimer();
    const waitMs = Math.max(0, Number(delayMs) || 0);
    state.autoPromptTimer = safeRoot.setTimeout(() => {
      state.autoPromptTimer = null;
      checkAutoFeedbackPrompt({ root: safeRoot });
    }, waitMs);
  };

  const initAutoPromptListeners = () => {
    if (!hasDom() || state.autoPromptBound) return;
    state.autoPromptBound = true;
    const doc = root.document;
    if (typeof doc.addEventListener === 'function') {
      doc.addEventListener('dpr-access-mode-changed', () => {
        scheduleAutoFeedbackPrompt(AUTO_PROMPT_DELAY_MS);
      });
      doc.addEventListener('visibilitychange', () => {
        if (!doc.visibilityState || doc.visibilityState === 'visible') {
          scheduleAutoFeedbackPrompt(AUTO_PROMPT_DELAY_MS);
        }
      });
    }
    scheduleAutoFeedbackPrompt(AUTO_PROMPT_DELAY_MS);
  };

  return {
    open,
    close,
    checkAutoFeedbackPrompt,
    scheduleAutoFeedbackPrompt,
    __test: {
      ISSUE_TYPES,
      TARGET_OWNER,
      TARGET_REPO,
      FEEDBACK_ANIMATION_MS,
      AUTO_PROMPT_STORAGE_KEY,
      AUTO_PROMPT_MIN_ELAPSED_MS,
      AUTO_PROMPT_DELAY_MS,
      getFeedbackMotionStyles,
      normalizeText,
      normalizeInlineText,
      normalizeSelectedTypes,
      stripExistingTypePrefix,
      buildIssueTitle,
      buildIssueBody,
      validateFeedbackForm,
      buildIssueDraftUrl,
      readTokenFromStoredData,
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
      initAutoPromptListeners,
    },
  };
});

if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('dpr-open-feedback', function () {
    if (window.DPRFeedback && typeof window.DPRFeedback.open === 'function') {
      window.DPRFeedback.open();
    }
  });
  if (window.DPRFeedback && window.DPRFeedback.__test && typeof window.DPRFeedback.__test.initAutoPromptListeners === 'function') {
    window.DPRFeedback.__test.initAutoPromptListeners();
  }
}
