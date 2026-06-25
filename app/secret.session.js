// Global secret/session manager: handles the unlock screen and guest mode on first entry
(function () {
  const STORAGE_KEY_MODE = 'dpr_secret_access_mode_v1'; // Deprecated; retained for compatibility only
  const STORAGE_KEY_PASS = 'dpr_secret_password_v1';
  const STORAGE_KEY_LOCAL_SECRET = 'dpr_local_secret_private_v1';
  const SECRET_FILE_URL = 'secret.private';
  const SECRET_OVERLAY_ANIMATION_MS = 280;
  const FORCE_GUEST_DOMAIN_TOKEN = 'ziwenhahaha';
  let secretOverlayHideTimer = null;
  const isForceGuestDomain = (host) => {
    const normalized = String(host || '').toLowerCase();
    return normalized.includes(FORCE_GUEST_DOMAIN_TOKEN);
  };
  const FORCE_GUEST_MODE = isForceGuestDomain(window && window.location && window.location.hostname);
  const isLocalDebugHost = () => {
    const host = String((window.location && window.location.hostname) || '').toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  };

  const getCurrentDirectoryUrl = () => {
    const loc = window.location || {};
    const origin = String(loc.origin || '');
    const pathname = String(loc.pathname || '/');
    if (!origin) return '';
    const dirPath = pathname.endsWith('/')
      ? pathname
      : pathname.includes('.')
        ? pathname.replace(/\/[^/]*$/, '/')
        : `${pathname}/`;
    return `${origin}${dirPath}`;
  };

  const getStaticSecretFileUrl = () => {
    const currentDir = getCurrentDirectoryUrl();
    return currentDir ? new URL(SECRET_FILE_URL, currentDir).href : SECRET_FILE_URL;
  };

  async function fetchStaticSecretPayload() {
    const url = getStaticSecretFileUrl();
    try {
      const resp = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
      });
      if (!resp || !resp.ok) {
        throw new Error(`HTTP ${resp ? resp.status : 0} ${url}`);
      }
      return await resp.json();
    } catch (e) {
      console.warn('[SECRET] Failed to read static secret.private:', e);
    }
    return null;
  }

  const getLocalApiUrl = (path) => {
    const base = String(window.DPR_LOCAL_API_BASE || '').trim().replace(/\/$/, '');
    if (base) return `${base}${path}`;
    const protocol = String((window.location && window.location.protocol) || 'http:');
    const hostname = String((window.location && window.location.hostname) || '127.0.0.1');
    return `${protocol}//${hostname}:8567${path}`;
  };

  function loadLocalSecretPayload() {
    if (!isLocalDebugHost()) return null;
    try {
      if (!window.localStorage) return null;
      const raw = window.localStorage.getItem(STORAGE_KEY_LOCAL_SECRET);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && parsed.payload ? parsed.payload : parsed;
    } catch (e) {
      console.error('[SECRET] Failed to read local secret.private:', e);
      return null;
    }
  }

  function saveLocalSecretPayload(payload) {
    if (!isLocalDebugHost()) return false;
    try {
      if (!window.localStorage) return false;
      window.localStorage.setItem(
        STORAGE_KEY_LOCAL_SECRET,
        JSON.stringify({ payload, savedAt: new Date().toISOString() }),
      );
      return true;
    } catch (e) {
      console.error('[SECRET] Failed to save local secret.private:', e);
      return false;
    }
  }

  async function saveLocalSecretPayloadToDisk(payload, secretPlain) {
    if (!isLocalDebugHost()) return false;
    const body = { payload };
    if (secretPlain && typeof secretPlain === 'object') {
      body.secret = secretPlain;
    }
    const res = await fetch(getLocalApiUrl('/api/local/secret'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw new Error((data && data.error) || `Failed to write local secret.private: HTTP ${res.status}`);
    }
    saveLocalSecretPayload(payload);
    return true;
  }

  async function loadLocalSecretPayloadPreferred(staticPayload) {
    if (staticPayload) return staticPayload;
    if (!isLocalDebugHost()) return null;
    return loadLocalSecretPayload();
  }

  const setAccessMode = (mode, detail) => {
    window.DPR_ACCESS_MODE = mode;
    try {
      const ev = new CustomEvent('dpr-access-mode-changed', {
        detail: detail || { mode },
      });
      document.dispatchEvent(ev);
    } catch {
      // ignore
    }
  };

  const enforceGuestMode = (overlayEl) => {
    setAccessMode('guest', { mode: 'guest', reason: 'domain_force_guest' });
    if (overlayEl) {
      try {
        overlayEl.classList.remove('show');
        overlayEl.classList.add('secret-gate-hidden');
      } catch {
        // ignore
      }
    }
  };

  const openSecretOverlay = (overlayEl) => {
    if (!overlayEl) return;
    try {
      if (typeof window.DPRHideInitialSplash === 'function') {
        window.DPRHideInitialSplash();
      }
    } catch {
      // ignore
    }
    if (secretOverlayHideTimer) {
      clearTimeout(secretOverlayHideTimer);
      secretOverlayHideTimer = null;
    }
    overlayEl.classList.remove('secret-gate-hidden');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        overlayEl.classList.add('show');
      });
    });
  };

  const closeSecretOverlay = (overlayEl) => {
    if (!overlayEl) return;
    overlayEl.classList.remove('show');
    if (secretOverlayHideTimer) {
      clearTimeout(secretOverlayHideTimer);
    }
    secretOverlayHideTimer = setTimeout(() => {
      overlayEl.classList.add('secret-gate-hidden');
      secretOverlayHideTimer = null;
    }, SECRET_OVERLAY_ANIMATION_MS);
  };

  // Simple password strength check: min. 8 characters, must include digits, lowercase, uppercase, and a special character
  function validatePassword(pwd) {
    if (!pwd || pwd.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (!/[0-9]/.test(pwd)) {
      return 'Password must contain at least one digit.';
    }
    if (!/[a-z]/.test(pwd)) {
      return 'Password must contain at least one lowercase letter.';
    }
    if (!/[A-Z]/.test(pwd)) {
      return 'Password must contain at least one uppercase letter.';
    }
    if (!/[^A-Za-z0-9]/.test(pwd)) {
      return 'Password must contain at least one special character (e.g. !@#).';
    }
    return '';
  }

  // Legacy mode flag is deprecated; retained only for cleanup compatibility
  function loadAccessMode() {
    try {
      if (!window.localStorage) return null;
      return window.localStorage.getItem(STORAGE_KEY_MODE);
    } catch {
      return null;
    }
  }

  function loadSavedPassword() {
    try {
      if (!window.localStorage) return '';
      return window.localStorage.getItem(STORAGE_KEY_PASS) || '';
    } catch {
      return '';
    }
  }

  function savePassword(pwd) {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(STORAGE_KEY_PASS, pwd);
    } catch {
      // ignore
    }
  }

  function clearPassword() {
    try {
      if (!window.localStorage) return;
      window.localStorage.removeItem(STORAGE_KEY_PASS);
    } catch {
      // ignore
    }
  }

  const getLLMUtils = () => window.DPRLLMConfigUtils || {};
  const normalizeText = (value) => {
    const utils = getLLMUtils();
    if (typeof utils.normalizeText === 'function') {
      return utils.normalizeText(value);
    }
    return String(value || '').trim();
  };
  const normalizeBaseUrlForStorage = (value) => {
    const utils = getLLMUtils();
    if (typeof utils.normalizeBaseUrlForStorage === 'function') {
      return utils.normalizeBaseUrlForStorage(value);
    }
    return normalizeText(value).replace(/\/chat\/completions$/i, '').replace(/\/+$/g, '');
  };
  const buildChatCompletionsEndpoint = (value) => {
    const utils = getLLMUtils();
    if (typeof utils.buildChatCompletionsEndpoint === 'function') {
      return utils.buildChatCompletionsEndpoint(value);
    }
    const raw = normalizeText(value).replace(/\/+$/g, '');
    if (!raw) return '';
    if (/\/chat\/completions$/i.test(raw)) return raw;
    if (/\/v\d+$/i.test(raw)) return `${raw}/chat/completions`;
    return `${raw}/v1/chat/completions`;
  };
  const sanitizeModelList = (values, maxCount) => {
    const utils = getLLMUtils();
    if (typeof utils.sanitizeModelList === 'function') {
      return utils.sanitizeModelList(values, maxCount);
    }
    const limit = Math.max(Number(maxCount) || 1, 1);
    const rawList = Array.isArray(values) ? values : [values];
    const out = [];
    const seen = new Set();
    rawList.forEach((value) => {
      String(value || '')
        .split(/[\n,]+/)
        .map((item) => normalizeText(item))
        .filter(Boolean)
        .forEach((name) => {
          const key = name.toLowerCase();
          if (!key || seen.has(key) || out.length >= limit) return;
          seen.add(key);
          out.push(name);
        });
    });
    return out;
  };
  const resolveSummaryLLM = (secret) => {
    const utils = getLLMUtils();
    if (typeof utils.resolveSummaryLLM === 'function') {
      return utils.resolveSummaryLLM(secret);
    }
    const safeSecret = secret && typeof secret === 'object' ? secret : {};
    const summarized = safeSecret.summarizedLLM || {};
    const baseUrl = normalizeBaseUrlForStorage(summarized.baseUrl || '');
    const apiKey = normalizeText(summarized.apiKey || '');
    const model = normalizeText(summarized.model || '');
    if (baseUrl && apiKey && model) {
      return { baseUrl, apiKey, model };
    }
    return null;
  };
  const inferProviderType = (secret) => {
    const utils = getLLMUtils();
    if (typeof utils.inferProviderType === 'function') {
      return utils.inferProviderType(secret);
    }
    return 'deepseek';
  };
  const getDefaultDeepSeekBaseUrl = () => {
    const utils = getLLMUtils();
    return normalizeBaseUrlForStorage(utils.DEFAULT_DEEPSEEK_BASE_URL || 'https://api.deepseek.com');
  };
  const getDefaultDeepSeekChatModels = () => {
    const utils = getLLMUtils();
      const defaults = Array.isArray(utils.DEFAULT_DEEPSEEK_CHAT_MODELS)
        ? utils.DEFAULT_DEEPSEEK_CHAT_MODELS
        : [
            'deepseek-v4-flash',
            'deepseek-v4-pro',
          ];
    return sanitizeModelList(defaults, 99);
  };
  const RERANKER_PROFILES = [
    {
      value: 'public-zwwen-rerank',
      label: 'Public Rerank (zwwen.online)',
      provider: 'public_zwwen',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: 'https://zwwen.online/rerank',
      requiresApiKey: false,
      testApiKey: '26932a86d772001af60cbd9d2c162bfda3a90e094f797f3d6806f6077478b27a',
      note: 'Recommended default; uses the zwwen.online public rerank service.',
    },
    {
      value: 'local-qwen3-0.6b',
      label: 'Local Qwen3-Reranker-0.6B',
      provider: 'local',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: '',
      requiresApiKey: false,
      note: 'No Reranker API key required; loads the model locally on CPU in GitHub Actions.',
    },
    {
      value: 'siliconflow-qwen3-0.6b',
      label: 'SiliconFlow Qwen3-Reranker-0.6B',
      provider: 'siliconflow',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: 'https://api.siliconflow.cn/v1/rerank',
      requiresApiKey: true,
      note: 'Fast and cost-effective; requires a SiliconFlow API key.',
    },
  ];
  const DEFAULT_RERANKER_PROFILE =
    RERANKER_PROFILES.find((item) => item.value === 'public-zwwen-rerank') ||
    RERANKER_PROFILES[0];
  const findRerankerProfile = (value) => {
    const normalized = normalizeText(value || '').toLowerCase().replace(/_/g, '-');
    return (
      RERANKER_PROFILES.find((item) => item.value === normalized) ||
      DEFAULT_RERANKER_PROFILE
    );
  };
  const resolveRerankerConfig = (secret) => {
    const safeSecret = secret && typeof secret === 'object' ? secret : {};
    const reranker = safeSecret.rerankerLLM || {};
    const provider = normalizeText(reranker.provider || reranker.type || '');
    const model = normalizeText(reranker.model || '');
    const inferredProfile =
      reranker.profile ||
      '';
    const profile = findRerankerProfile(inferredProfile);
    return {
      profile: profile.value,
      provider: provider || profile.provider,
      model: model || profile.model,
      apiKey: normalizeText(reranker.apiKey || ''),
      baseUrl: normalizeBaseUrlForStorage(reranker.baseUrl || profile.baseUrl || ''),
    };
  };
  const buildConnectivityTestPayload = (baseUrl, model) => {
    const utils = getLLMUtils();
    if (typeof utils.buildConnectivityTestPayload === 'function') {
      return utils.buildConnectivityTestPayload({ baseUrl, model });
    }
    return {
      model: normalizeText(model || ''),
      messages: [
        {
          role: 'system',
          content: 'Reply with exactly: hello world',
        },
        {
          role: 'user',
          content: 'hello world',
        },
      ],
      temperature: 0,
      max_tokens: 256,
    };
  };
  const extractChatResponseText = (data) => {
    const normalizeContentPart = (part) => {
      if (typeof part === 'string') return normalizeText(part);
      if (!part || typeof part !== 'object') return '';
      return normalizeText(part.text || part.content || part.output_text || '');
    };

    const firstChoice = (((data || {}).choices || [])[0] || {});
    const message = firstChoice.message || {};
    const content = message.content;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      return content.map((part) => normalizeContentPart(part)).filter(Boolean).join('\n');
    }
    if (content && typeof content === 'object') {
      return normalizeContentPart(content);
    }

    const reasoningContent = message.reasoning_content || message.thinking;
    if (typeof reasoningContent === 'string' && reasoningContent.trim()) {
      return reasoningContent;
    }

    const outputText = (data || {}).output_text;
    if (typeof outputText === 'string') return outputText;
    if (Array.isArray(outputText)) {
      return outputText.map((part) => normalizeContentPart(part)).filter(Boolean).join('\n');
    }
    return '';
  };

  async function pingChatModels(modelEntries, statusEl) {
    const entries = Array.isArray(modelEntries) ? modelEntries : [];
    if (!entries.length) {
      throw new Error('Please fill in the complete model configuration first.');
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    const results = [];

    try {
      for (let i = 0; i < entries.length; i += 1) {
        const entry = entries[i] || {};
        const model = normalizeText(entry.model || entry.name || '');
        const apiKey = normalizeText(entry.apiKey || '');
        const baseUrl = normalizeBaseUrlForStorage(entry.baseUrl || '');
        const endpoint = buildChatCompletionsEndpoint(baseUrl);

        if (!model || !apiKey || !endpoint) {
          throw new Error('Model configuration is missing apiKey, baseUrl, or model.');
        }
        if (statusEl) {
          statusEl.textContent = `Testing model ${i + 1}/${entries.length}: ${model} ...`;
          statusEl.style.color = '#666';
        }

        const payload = buildConnectivityTestPayload(baseUrl, model);

        const headers = {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          Authorization: `Bearer ${apiKey}`,
        };

        const doFetch = (requestPayload) => fetch(endpoint, {
          method: 'POST',
          headers,
          body: JSON.stringify(requestPayload),
          signal: controller.signal,
        });
        let resp = await doFetch(payload);
        if (!resp.ok && payload.max_completion_tokens != null) {
          const text = await resp.text().catch(() => '');
          if (resp.status === 400 && /max_completion_tokens/i.test(text)) {
            const fallbackPayload = { ...payload };
            delete fallbackPayload.max_completion_tokens;
            resp = await doFetch(fallbackPayload);
          } else {
            resp._dprErrorPreview = text;
          }
        }
        if (!resp.ok) {
          const text = resp._dprErrorPreview || await resp.text().catch(() => '');
          throw new Error(
            `${model} request failed: HTTP ${resp.status} ${resp.statusText}${text ? ` - ${text.slice(0, 160)}` : ''}`,
          );
        }
        const data = await resp.json().catch(() => null);
        const text = extractChatResponseText(data);
        if (!normalizeText(text)) {
          throw new Error(`${model} returned an empty response. Please check model compatibility.`);
        }
        results.push(model);
      }
    } finally {
      clearTimeout(timeout);
    }

    return results;
  }

  async function readRepoOwnerJson() {
    const candidates = ['.repo-owner.json', 'docs/.repo-owner.json', '/.repo-owner.json'];
    for (const url of candidates) {
      try {
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) continue;
        const data = await res.json();
        if (data && data.owner && data.repo) return data;
      } catch { }
    }
    return null;
  }

  // Infer the target repository owner/repo from the GitHub Token (consistent with the subscription panel logic)
  async function detectGithubRepoFromToken(token) {
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        Authorization: `token ${token}`,
        Accept: 'application/vnd.github.v3+json',
      },
    });
    if (!userRes.ok) {
      throw new Error('Unable to fetch user information with the current GitHub Token.');
    }
    const userData = await userRes.json();
    const login = userData.login || '';

    const currentUrl = window.location.href;
    const urlObj = new URL(currentUrl);
    const host = urlObj.hostname || '';

    let repoOwner = '';
    let repoName = '';

    if (host === 'localhost' || host === '127.0.0.1') {
      repoOwner = login;
      repoName = 'daily-paper-reader';
    } else {
      const repoMeta = await readRepoOwnerJson();
      if (repoMeta) {
        repoOwner = repoMeta.owner;
        repoName = repoMeta.repo;
        if (login && repoMeta.owner && login.toLowerCase() !== repoMeta.owner.toLowerCase()) {
          throw new Error(
            `Token user ${login} does not match site owner ${repoMeta.owner}`,
          );
        }
      } else {
        const githubPagesMatch = currentUrl.match(
          /https?:\/\/([^.]+)\.github\.io\/([^\/]+)/,
        );
        if (githubPagesMatch) {
          repoOwner = githubPagesMatch[1];
          repoName = githubPagesMatch[2];
        } else {
          try {
            const candidates = ['config.yaml', 'docs/config.yaml', '../config.yaml', '/config.yaml'];
            for (const cfgUrl of candidates) {
              try {
                const res = await fetch(cfgUrl, { cache: 'no-store' });
                if (!res.ok) continue;
                const text = await res.text();
                const yaml =
                  window.jsyaml || window.jsYaml || window.jsYAML || window.jsYml;
                if (yaml && typeof yaml.load === 'function') {
                  const cfg = yaml.load(text) || {};
                  const githubCfg = (cfg && cfg.github) || {};
                  if (githubCfg && typeof githubCfg === 'object') {
                    if (githubCfg.owner) repoOwner = String(githubCfg.owner);
                    if (githubCfg.repo) repoName = String(githubCfg.repo);
                    if (repoOwner || repoName) break;
                  }
                }
              } catch { }
            }
          } catch { }

          if (!repoOwner) {
            repoOwner = login;
          }
        }
      }
    }

    if (!repoOwner || !repoName) {
      throw new Error('Unable to infer the target repository. Please check the current domain or configuration.');
    }

    return { owner: repoOwner, repo: repoName };
  }

  // Write the summarization model / workflow LLM configuration into GitHub Secrets
  // Optional progress callback for showing upload progress in the UI: progress(currentIndex, total, secretName)
  async function saveSummarizeSecretsToGithub(token, options, progress) {
    try {
      if (!window.sodium && typeof window.DPRLoadAssets === 'function') {
        await window.DPRLoadAssets([
          {
            type: 'script',
            path: 'app/vendor/libsodium/0.7.10/dist/modules/libsodium.js',
          },
          {
            type: 'script',
            path: 'app/vendor/libsodium-wrappers/0.7.9/dist/modules/libsodium-wrappers.js',
          },
        ]);
      }
      // Wait for libsodium-wrappers to be ready (injected globally via CDN)
      if (!window.sodium || !window.sodium.ready) {
        if (
          window.sodium &&
          typeof window.sodium.ready === 'object' &&
          typeof window.sodium.ready.then === 'function'
        ) {
          await window.sodium.ready;
        } else {
          throw new Error(
            'libsodium-wrappers failed to load in the browser. Cannot write GitHub Secrets.',
          );
        }
      }
      const sodium = window.sodium;
      if (!sodium) {
        throw new Error('libsodium is not available in this browser. Cannot write GitHub Secrets.');
      }

      const { owner, repo } = await detectGithubRepoFromToken(token);

      // Fetch the repository Public Key
      const pkRes = await fetch(
        `https://api.github.com/repos/${owner}/${repo}/actions/secrets/public-key`,
        {
          headers: {
            Authorization: `token ${token}`,
            Accept: 'application/vnd.github.v3+json',
          },
        },
      );
      if (!pkRes.ok) {
        throw new Error(
          `Failed to fetch repository Public Key (HTTP ${pkRes.status}). Please verify that the Token has the required repo scope.`,
        );
      }
      const pkData = await pkRes.json();
      const publicKey = pkData.key;
      const keyId = pkData.key_id;
      if (!publicKey || !keyId) {
        throw new Error('Public Key data is incomplete. Cannot write Secrets.');
      }

      const encryptValue = (value) => {
        const binkey = sodium.from_base64(
          publicKey,
          sodium.base64_variants.ORIGINAL,
        );
        const binsec = sodium.from_string(value);
        const encBytes = sodium.crypto_box_seal(binsec, binkey);
        return sodium.to_base64(encBytes, sodium.base64_variants.ORIGINAL);
      };

      const safeOptions = options && typeof options === 'object' ? options : {};
      const summarizedApiKey = normalizeText(safeOptions.summarizedApiKey || '');
      const summarizedBaseUrl = normalizeBaseUrlForStorage(safeOptions.summarizedBaseUrl || '');
      const summarizedModel = normalizeText(safeOptions.summarizedModel || '');
      const filterModel = normalizeText(safeOptions.filterModel || summarizedModel);
      const rewriteModel = normalizeText(safeOptions.rewriteModel || summarizedModel);
      const skipRerank = !!safeOptions.skipRerank;
      const localRerankModel = normalizeText(
        safeOptions.localRerankModel || 'Qwen/Qwen3-Reranker-0.6B',
      );
      const rerankerProfile = normalizeText(
        safeOptions.rerankerProfile || DEFAULT_RERANKER_PROFILE.value,
      );
      const rerankerProvider = normalizeText(
        safeOptions.rerankerProvider || DEFAULT_RERANKER_PROFILE.provider,
      );
      const rerankerModel = normalizeText(
        safeOptions.rerankerModel ||
          (rerankerProvider === 'local' ? localRerankModel : DEFAULT_RERANKER_PROFILE.model),
      );
      const rerankerApiKey = normalizeText(safeOptions.rerankerApiKey || '');
      const rerankerBaseUrl = normalizeBaseUrlForStorage(safeOptions.rerankerBaseUrl || '');

      if (!summarizedApiKey || !summarizedBaseUrl || !summarizedModel) {
        throw new Error('Summarization model configuration is incomplete. Cannot write GitHub Secrets.');
      }
      if (!rerankerProfile || !rerankerProvider || !rerankerModel) {
        throw new Error('Reranker configuration is incomplete. Cannot write GitHub Secrets.');
      }

      const secretNameSummKey = 'Summarized_LLM_API_KEY';
      const secretNameSummUrl = 'Summarized_LLM_BASE_URL';
      const secretNameSummModel = 'Summarized_LLM_MODEL';
      const secretNameSummaryApiKey = 'SUMMARY_API_KEY';
      const secretNameSummaryBaseUrl = 'SUMMARY_BASE_URL';
      const secretNameSummaryModel = 'SUMMARY_MODEL';
      const secretNameDeepSeekKey = 'DEEPSEEK_API_KEY';
      const secretNameDeepSeekBase = 'DEEPSEEK_BASE_URL';
      const secretNameDeepSeekModel = 'DEEPSEEK_MODEL';
      const secretNameLlmPrimaryBase = 'LLM_PRIMARY_BASE_URL';
      const secretNameSkipRerank = 'DPR_SKIP_RERANK';
      const secretNameLocalRerankModel = 'LOCAL_RERANK_MODEL';
      const secretNameRerankProfile = 'RERANK_PROFILE';
      const secretNameRerankProvider = 'RERANK_PROVIDER';
      const secretNameRerankModel = 'RERANK_MODEL';
      const secretNameRerankApiKey = 'RERANK_API_KEY';
      const secretNameRerankBaseUrl = 'RERANK_API_BASE_URL';
      const secretNameSiliconFlowKey = 'SILICONFLOW_API_KEY';
      const secretNameSiliconFlowUrl = 'SILICONFLOW_RERANK_URL';
      const secretNameSiliconFlowInterval = 'SILICONFLOW_RERANK_MIN_INTERVAL_SECONDS';

      const putSecret = async (name, encrypted) => {
        const body = {
          encrypted_value: encrypted,
          key_id: keyId,
        };
        const res = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/actions/secrets/${encodeURIComponent(
            name,
          )}`,
          {
            method: 'PUT',
            headers: {
              Authorization: `token ${token}`,
              Accept: 'application/vnd.github.v3+json',
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
          },
        );
        if (!res.ok) {
          const txt = await res.text().catch(() => '');
          throw new Error(
            `Failed to write GitHub Secret ${name}: HTTP ${res.status} ${res.statusText} - ${txt}`,
          );
        }
      };

      const secrets = [
        { name: secretNameSummKey, value: summarizedApiKey },
        { name: secretNameSummUrl, value: summarizedBaseUrl },
        { name: secretNameSummModel, value: summarizedModel },
        { name: secretNameSummaryApiKey, value: summarizedApiKey },
        { name: secretNameSummaryBaseUrl, value: summarizedBaseUrl },
        { name: secretNameSummaryModel, value: summarizedModel },
        { name: secretNameDeepSeekKey, value: summarizedApiKey },
        { name: secretNameDeepSeekBase, value: summarizedBaseUrl },
        { name: secretNameDeepSeekModel, value: summarizedModel },
        { name: secretNameLlmPrimaryBase, value: summarizedBaseUrl },
        { name: secretNameSkipRerank, value: skipRerank ? 'true' : 'false' },
        { name: secretNameLocalRerankModel, value: localRerankModel },
        { name: secretNameRerankProfile, value: rerankerProfile },
        { name: secretNameRerankProvider, value: rerankerProvider },
        { name: secretNameRerankModel, value: rerankerModel },
      ];
      if (rerankerProvider !== 'local') {
        if (rerankerApiKey) {
          secrets.push({ name: secretNameRerankApiKey, value: rerankerApiKey });
        }
        if (rerankerBaseUrl) {
          secrets.push({ name: secretNameRerankBaseUrl, value: rerankerBaseUrl });
        }
      }
      if (rerankerProvider === 'siliconflow') {
        if (rerankerApiKey) {
          secrets.push({ name: secretNameSiliconFlowKey, value: rerankerApiKey });
        }
        secrets.push({
          name: secretNameSiliconFlowUrl,
          value: rerankerBaseUrl || 'https://api.siliconflow.cn/v1/rerank',
        });
        secrets.push({ name: secretNameSiliconFlowInterval, value: '8' });
      }
      if (!skipRerank && rerankerProvider !== 'local' && rerankerApiKey && rerankerBaseUrl && rerankerModel) {
        secrets.push(
          { name: secretNameRerankApiKey, value: rerankerApiKey },
          { name: secretNameRerankBaseUrl, value: rerankerBaseUrl },
          { name: secretNameRerankModel, value: rerankerModel },
        );
      }

      for (let i = 0; i < secrets.length; i += 1) {
        const item = secrets[i];
        if (typeof progress === 'function') {
          try {
            progress(i + 1, secrets.length, item.name);
          } catch {
            // Ignore exceptions in the progress callback
          }
        }
        await putSecret(item.name, encryptValue(item.value));
      }

      return true;
    } catch (e) {
      console.error('[SECRET] Failed to save GitHub Secrets:', e);
      return false;
    }
  }

  function base64ToBytes(b64) {
    const bin = atob(b64);
    const len = bin.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
      bytes[i] = bin.charCodeAt(i);
    }
    return bytes;
  }

  // Commit the generated secret.private to the root of the current GitHub repository
  async function saveSecretPrivateToGithubRepo(token, payload) {
    try {
      const { owner, repo } = await detectGithubRepoFromToken(token);
      const filePath = 'secret.private';

      // Try to fetch the existing file to retrieve its sha (ignore 404 if it does not exist)
      let existingSha = null;
      try {
        const getRes = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(
            filePath,
          )}`,
          {
            headers: {
              Authorization: `token ${token}`,
              Accept: 'application/vnd.github.v3+json',
            },
          },
        );
        if (getRes.ok) {
          const info = await getRes.json().catch(() => null);
          if (info && info.sha) {
            existingSha = info.sha;
          }
        } else if (getRes.status !== 404) {
          const txt = await getRes.text().catch(() => '');
          throw new Error(
            `Failed to read remote secret.private: HTTP ${getRes.status} ${getRes.statusText} - ${txt}`,
          );
        }
      } catch (e) {
        console.error('[SECRET] Pre-read of remote secret.private failed:', e);
        throw e;
      }

      const contentJson =
        typeof payload === 'string'
          ? payload
          : JSON.stringify(payload, null, 2);
      const contentB64 = btoa(unescape(encodeURIComponent(contentJson)));
      const body = {
        message: existingSha
          ? 'chore: update secret.private via web setup'
          : 'chore: init secret.private via web setup',
        content: contentB64,
      };
      if (existingSha) {
        body.sha = existingSha;
      }

      const putRes = await fetch(
        `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(
          filePath,
        )}`,
        {
          method: 'PUT',
          headers: {
            Authorization: `token ${token}`,
            Accept: 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        },
      );
      if (!putRes.ok) {
        const txt = await putRes.text().catch(() => '');
        throw new Error(
          `Failed to commit secret.private to the repository: HTTP ${putRes.status} ${putRes.statusText} - ${txt}`,
        );
      }

      return true;
    } catch (e) {
      console.error('[SECRET] Failed to save secret.private to the GitHub repository:', e);
      return false;
    }
  }

  async function deriveAesGcmKey(password, saltBytes, usages) {
    const enc = new TextEncoder();
    const cryptoObj = (typeof window !== 'undefined' && (window.crypto || window.msCrypto)) || null;
    if (!cryptoObj || !cryptoObj.subtle) {
      throw new Error(
        'Web Crypto AES-GCM is not supported in this environment. Please open this page over https or http://localhost using a modern browser (Chrome/Edge/Firefox) and try again.',
      );
    }
    const baseKey = await cryptoObj.subtle.importKey(
      'raw',
      enc.encode(password),
      'PBKDF2',
      false,
      ['deriveKey'],
    );
    return cryptoObj.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: saltBytes,
        iterations: 120000,
        hash: 'SHA-256',
      },
      baseKey,
      { name: 'AES-GCM', length: 256 },
      false,
      usages,
    );
  }

  // Expected structure of secret.private:
  // {
  //   "version": 1,
  //   "salt": "<base64>",
  //   "iv": "<base64>",
  //   "ciphertext": "<base64>"
  // }
  // The plaintext is a JSON string containing the LLM API key and other configuration.
  async function decryptSecret(password, payload) {
    if (!payload || typeof payload !== 'object') {
      throw new Error('Invalid ciphertext format');
    }
    const saltB64 = payload.salt;
    const ivB64 = payload.iv;
    const cipherB64 = payload.ciphertext;
    if (!saltB64 || !ivB64 || !cipherB64) {
      throw new Error('Missing required fields (salt/iv/ciphertext)');
    }

    const saltBytes = base64ToBytes(saltB64);
    const ivBytes = base64ToBytes(ivB64);
    const cipherBytes = base64ToBytes(cipherB64);

    const key = await deriveAesGcmKey(password, saltBytes, ['decrypt']);
    const plainBuf = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: ivBytes,
      },
      key,
      cipherBytes,
    );
    const dec = new TextDecoder();
    const text = dec.decode(plainBuf);
    let obj = null;
    try {
      obj = JSON.parse(text);
    } catch {
      throw new Error('Decryption succeeded but the content is not valid JSON');
    }
    return obj;
  }

  // Create a new secret.private: generate an encrypted file structure from a plaintext config object and password
  async function createEncryptedSecret(password, plainConfig) {
    const enc = new TextEncoder();
    const saltBytes = crypto.getRandomValues(new Uint8Array(16));
    const ivBytes = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveAesGcmKey(password, saltBytes, ['encrypt']);

    const plainText = JSON.stringify(plainConfig || {}, null, 2);
    const cipherBuf = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: ivBytes,
      },
      key,
      enc.encode(plainText),
    );

    const toB64 = (bytes) => {
      let bin = '';
      const view = new Uint8Array(bytes);
      for (let i = 0; i < view.length; i += 1) {
        bin += String.fromCharCode(view[i]);
      }
      return btoa(bin);
    };

    return {
      version: 1,
      salt: toB64(saltBytes),
      iv: toB64(ivBytes),
      ciphertext: toB64(cipherBuf),
    };
  }

  // Initialization mode: existing secret.private -> unlock / guest; no secret.private -> first-time setup wizard
  function setupOverlay(hasSecretFile) {
    const overlay = document.getElementById('secret-gate-overlay');
    const modal = document.getElementById('secret-gate-modal');
    if (!overlay || !modal) {
      return;
    }

    const setMode = (mode) => {
      if (FORCE_GUEST_MODE && mode !== 'guest') {
        enforceGuestMode(overlay);
        return;
      }
      setAccessMode(mode);
    };

    const hide = () => {
      closeSecretOverlay(overlay);
    };
    const setStep2Modal = (enabled) => {
      modal.classList.toggle('secret-gate-modal-step2', !!enabled);
    };

    if (overlay && !overlay._secretBound) {
      overlay._secretBound = true;
      overlay.addEventListener('mousedown', (e) => {
        if (e.target === overlay) {
          hide();
        }
      });
    }

    // Render the unlock UI when a secret.private file already exists
    const renderUnlockUI = () => {
      setStep2Modal(false);
      modal.innerHTML = `
        <h2 style="margin-top:0;">🔐 Unlock Credentials</h2>
        <p style="font-size:13px; color:#555; margin-bottom:8px;">
          A credentials file (<code>secret.private</code>) has been detected. Please enter your unlock password,
          or continue as a guest (read-only access to papers; AI features unavailable).
        </p>
        <label for="secret-gate-password" style="font-size:13px; color:#333; display:block; margin-bottom:4px;">
          Unlock password (min. 8 chars, must include digits, uppercase, lowercase, and a special character):
        </label>
        <input
          id="secret-gate-password"
          type="password"
          autocomplete="off"
          style="width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:6px; font-size:13px;"
        />
        <div id="secret-gate-error" style="min-height:18px; font-size:12px; color:#999; margin-bottom:8px;">
          Your password is used locally for decryption only and is never sent to any server.
        </div>
        <div class="secret-gate-actions">
          <button id="secret-gate-guest" type="button" class="secret-gate-btn secondary">
            Continue as guest
          </button>
          <button id="secret-gate-unlock" type="button" class="secret-gate-btn primary">
            Unlock Credentials
          </button>
        </div>
      `;

      const pwdInput = document.getElementById('secret-gate-password');
      const errorEl = document.getElementById('secret-gate-error');
      const guestBtn = document.getElementById('secret-gate-guest');
      const unlockBtn = document.getElementById('secret-gate-unlock');

      if (!pwdInput || !guestBtn || !unlockBtn) return;

      // Guest mode: no decryption, no key loading — browse and read only
      guestBtn.addEventListener('click', () => {
        setMode('guest');
        hide();
      });

      unlockBtn.addEventListener('click', async () => {
        const pwd = (pwdInput.value || '').trim();
        const msg = validatePassword(pwd);
        if (msg) {
          if (errorEl) {
            errorEl.textContent = msg;
            errorEl.style.color = '#c00';
          }
          return;
        }
        if (errorEl) {
          errorEl.textContent = 'Unlocking credentials, please wait...';
          errorEl.style.color = '#666';
        }
        unlockBtn.disabled = true;
        guestBtn.disabled = true;
        try {
          const staticPayload = await fetchStaticSecretPayload();
          if (!staticPayload) {
            throw new Error('Failed to fetch secret.private');
          }
          const payload = await loadLocalSecretPayloadPreferred(staticPayload);
          const secret = await decryptSecret(pwd, payload);
          // Keep the decrypted config in memory only (not persisted to disk); save the password for future auto-unlock
          window.decoded_secret_private = secret;
          savePassword(pwd);
          setMode('full');
          hide();
        } catch (e) {
          console.error(e);
          if (errorEl) {
            errorEl.textContent =
              'Unlock failed. Please check your password and try again.';
            errorEl.style.color = '#c00';
          }
        } finally {
          unlockBtn.disabled = false;
          guestBtn.disabled = false;
        }
      });

      setTimeout(() => {
        try {
          pwdInput.focus();
        } catch {
          // ignore
        }
      }, 100);
    };

    // Setup wizard: Step 2 (DeepSeek API only)
    const renderInitStep2 = (password) => {
      setStep2Modal(true);
      const currentSecret =
        window.decoded_secret_private && typeof window.decoded_secret_private === 'object'
          ? window.decoded_secret_private
          : {};
      const currentSummaryLLM = resolveSummaryLLM(currentSecret) || {};
      const currentChatEntry =
        Array.isArray(currentSecret.chatLLMs) && currentSecret.chatLLMs.length
          ? currentSecret.chatLLMs[0] || {}
          : {};
      const currentReranker = resolveRerankerConfig(currentSecret);

      const initialGithubToken = normalizeText(
        currentSecret.github && currentSecret.github.token,
      );
      const initialApiKey = normalizeText(currentSummaryLLM.apiKey || '');
      const initialDeepSeekModel =
        normalizeText(currentSummaryLLM.model || '') || 'deepseek-v4-flash';
      const deepseekSummaryModels = getDefaultDeepSeekChatModels().map((model) => ({
        value: model,
        label: model === 'deepseek-v4-flash'
          ? 'DeepSeek V4 Flash · Recommended default'
          : model === 'deepseek-v4-pro'
            ? 'DeepSeek V4 Pro · High-performance model'
            : model,
      }));

      modal.innerHTML = `
        <h2 style="margin-top:0;">🛡️ Setup Wizard · Step 2</h2>
        <div class="secret-setup-step2-grid" style="font-size:13px;">
          <div class="secret-setup-step2-col">
            <div class="secret-setup-step2-block">
              <div class="secret-setup-step2-title">GitHub Token (required)</div>
              <p class="secret-setup-step2-note">
                A <code>Classic PAT</code> is required with <code>repo</code>, <code>workflow</code>, and <code>gist</code> scopes.
              </p>
              <div class="secret-setup-input-row">
                <input
                  id="secret-setup-github-token"
                  type="password"
                  autocomplete="off"
                  placeholder="GitHub PAT for reading/writing config.yaml and triggering workflows"
                  style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                />
                <button id="secret-setup-github-verify" type="button" class="secret-gate-btn secondary">
                  Verify
                </button>
              </div>
              <div id="secret-setup-github-status" style="min-height:18px; font-size:12px; color:#999;">
                A <code>Classic PAT</code> is required with <code>repo</code>, <code>workflow</code>, and <code>gist</code> scopes.
              </div>
            </div>

            <div id="secret-setup-deepseek-section" class="secret-setup-step2-block">
              <div class="secret-setup-step2-title">DeepSeek API (required)</div>
              <p class="secret-setup-step2-note">
                DeepSeek is used for query enrichment, LLM refining, summarization, and chat. The Reranker can be configured separately on the right.
              </p>
              <div class="secret-setup-input-row multi-actions">
                <input
                  id="secret-setup-deepseek"
                  type="password"
                  autocomplete="off"
                  placeholder="DeepSeek API Key, e.g. sk-xxxx"
                  style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                />
                <button id="secret-setup-deepseek-test" type="button" class="secret-gate-btn secondary">
                  Test
                </button>
                <button id="secret-setup-deepseek-verify" type="button" class="secret-gate-btn secondary" style="display:none;">
                  Verify
                </button>
              </div>
              <div id="secret-setup-deepseek-status" style="min-height:18px; font-size:12px; color:#999; margin-bottom:8px;">
                A <code>hello world</code> request will be sent to verify the DeepSeek configuration.
              </div>

              <div style="font-weight:500; margin-bottom:4px; display:flex; align-items:center; gap:4px;">
                Model for workflow summarization / filtering
                <span class="secret-model-tip">!
                  <span class="secret-model-tip-popup">
                    Only the official DeepSeek API is supported here.<br/>
                    The Reranker API key is configured separately.
                  </span>
                </span>
              </div>
              <div id="secret-setup-deepseek-models" style="font-size:13px;">
                <select id="secret-setup-deepseek-model-select" class="secret-setup-select"></select>
              </div>
            </div>
          </div>

          <div class="secret-setup-step2-col">
            <div class="secret-setup-step2-block">
              <div class="secret-setup-step2-title">Reranker</div>
              <p class="secret-setup-step2-note">
                Step 3 uses the Qwen3 reranker to re-rank candidate papers. Choose between a local model or a remote service.
              </p>
              <select id="secret-setup-reranker-profile" class="secret-setup-select" style="margin-bottom:8px;"></select>
              <div id="secret-setup-reranker-remote-fields" style="display:none;">
                <div class="secret-setup-input-row" style="margin-bottom:6px;">
                  <input
                    id="secret-setup-reranker-api-key"
                    type="password"
                    autocomplete="off"
                    placeholder="Reranker API Key"
                    style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                  />
                </div>
                <div class="secret-setup-input-row" style="margin-bottom:6px;">
                  <input
                    id="secret-setup-reranker-base-url"
                    type="text"
                    autocomplete="off"
                    placeholder="Rerank Base URL, e.g. https://api.siliconflow.cn/v1/rerank"
                    style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                  />
                </div>
                <button id="secret-setup-reranker-test" type="button" class="secret-gate-btn secondary secret-setup-step2-actions">
                  Test Reranker
                </button>
                <div id="secret-setup-reranker-test-status" style="min-height:18px; font-size:12px; color:#999; margin-top:6px;">
                  A minimal rerank request will be sent to verify the Reranker API key, Base URL, and model.
                </div>
              </div>
              <div id="secret-setup-reranker-status" style="font-size:12px; color:#666; line-height:1.6;"></div>
              <input type="radio" name="secret-setup-provider" value="deepseek" checked style="display:none;" />
            </div>

            <div id="secret-setup-custom-section" style="display:none;">
              <input id="secret-setup-custom-api-key" type="hidden" />
              <input id="secret-setup-custom-base-url" type="hidden" />
              <input id="secret-setup-custom-model-1" type="hidden" />
              <input id="secret-setup-custom-model-2" type="hidden" />
              <input id="secret-setup-custom-model-3" type="hidden" />
              <button id="secret-setup-custom-test" type="button" style="display:none;"></button>
              <div id="secret-setup-custom-status" style="display:none;"></div>
            </div>
          </div>
        </div>

        <div id="secret-setup-error" style="min-height:18px; font-size:12px; color:#999; margin-top:10px; margin-bottom:8px;">
          All credentials will be encrypted and written to GitHub Secrets (for GitHub Actions). A local <code>secret.private</code> backup will also be generated. Plaintext values are never stored in the repository.
        </div>
        <div class="secret-gate-actions">
          <button id="secret-setup-back" type="button" class="secret-gate-btn secondary">
            Back
          </button>
          <button id="secret-setup-close" type="button" class="secret-gate-btn secondary">
            Close
          </button>
          <button id="secret-setup-generate" type="button" class="secret-gate-btn primary">
            Save configuration
          </button>
        </div>
      `;

      const githubInput = document.getElementById('secret-setup-github-token');
      const githubVerifyBtn = document.getElementById('secret-setup-github-verify');
      const githubStatusEl = document.getElementById('secret-setup-github-status');
      const providerInputs = Array.from(
        document.querySelectorAll('input[name="secret-setup-provider"]'),
      );
      const deepseekSection = document.getElementById('secret-setup-deepseek-section');
      const deepseekInput = document.getElementById('secret-setup-deepseek');
      const deepseekVerifyBtn = document.getElementById('secret-setup-deepseek-verify');
      const deepseekTestBtn = document.getElementById('secret-setup-deepseek-test');
      const deepseekStatusEl = document.getElementById('secret-setup-deepseek-status');
      const deepseekModelSelect = document.getElementById('secret-setup-deepseek-model-select');
      const customApiKeyInput = document.getElementById('secret-setup-custom-api-key');
      const customBaseUrlInput = document.getElementById('secret-setup-custom-base-url');
      const customModel1Input = document.getElementById('secret-setup-custom-model-1');
      const customModel2Input = document.getElementById('secret-setup-custom-model-2');
      const customModel3Input = document.getElementById('secret-setup-custom-model-3');
      const customTestBtn = document.getElementById('secret-setup-custom-test');
      const customStatusEl = document.getElementById('secret-setup-custom-status');
      const rerankerProfileSelect = document.getElementById('secret-setup-reranker-profile');
      const rerankerRemoteFields = document.getElementById('secret-setup-reranker-remote-fields');
      const rerankerApiKeyInput = document.getElementById('secret-setup-reranker-api-key');
      const rerankerBaseUrlInput = document.getElementById('secret-setup-reranker-base-url');
      const rerankerTestBtn = document.getElementById('secret-setup-reranker-test');
      const rerankerTestStatusEl = document.getElementById('secret-setup-reranker-test-status');
      const rerankerStatusEl = document.getElementById('secret-setup-reranker-status');
      const errorEl = document.getElementById('secret-setup-error');
      const backBtn = document.getElementById('secret-setup-back');
      const closeBtn = document.getElementById('secret-setup-close');
      const genBtn = document.getElementById('secret-setup-generate');

      if (
        !githubInput ||
        !githubVerifyBtn ||
        !githubStatusEl ||
        !providerInputs.length ||
        !deepseekSection ||
        !deepseekInput ||
        !deepseekVerifyBtn ||
        !deepseekTestBtn ||
        !deepseekStatusEl ||
        !deepseekModelSelect ||
        !customApiKeyInput ||
        !customBaseUrlInput ||
        !customModel1Input ||
        !customModel2Input ||
        !customModel3Input ||
        !customTestBtn ||
        !customStatusEl ||
        !rerankerProfileSelect ||
        !rerankerRemoteFields ||
        !rerankerApiKeyInput ||
        !rerankerBaseUrlInput ||
        !rerankerTestBtn ||
        !rerankerTestStatusEl ||
        !rerankerStatusEl ||
        !errorEl ||
        !backBtn ||
        !closeBtn ||
        !genBtn
      ) {
        return;
      }

      deepseekModelSelect.innerHTML = deepseekSummaryModels
        .map((item) => `<option value="${item.value}">${item.label}</option>`)
        .join('');

      githubInput.value = initialGithubToken;
      deepseekInput.value = initialApiKey;

      providerInputs.forEach((input) => {
        input.checked = input.value === 'deepseek';
      });
      deepseekModelSelect.value = initialDeepSeekModel || 'deepseek-v4-flash';
      if (!deepseekModelSelect.value) {
        deepseekModelSelect.value = 'deepseek-v4-flash';
      }
      rerankerProfileSelect.innerHTML = RERANKER_PROFILES
        .map(
          (item) =>
            `<option value="${item.value}">${item.label}</option>`,
        )
        .join('');
      rerankerProfileSelect.value = currentReranker.profile || DEFAULT_RERANKER_PROFILE.value;
      if (!rerankerProfileSelect.value) {
        rerankerProfileSelect.value = DEFAULT_RERANKER_PROFILE.value;
      }
      rerankerApiKeyInput.value = currentReranker.apiKey || '';
      rerankerBaseUrlInput.value = currentReranker.baseUrl || '';

      let githubOk = !!initialGithubToken;
      let deepseekOk = !!initialApiKey;

      const setErrorText = (text, color) => {
        if (!errorEl) return;
        errorEl.textContent = text;
        errorEl.style.color = color || '#999';
      };

      const selectedDeepSeekModel = () => {
        return normalizeText(deepseekModelSelect.value || '');
      };
      const selectedRerankerProfile = () => {
        return findRerankerProfile(rerankerProfileSelect.value);
      };
      const rerankerRequiresApiKey = (profile) => {
        return profile.provider !== 'local' && profile.requiresApiKey !== false;
      };
      const syncRerankerFields = () => {
        const profile = selectedRerankerProfile();
        const isRemote = profile.provider !== 'local';
        const requiresApiKey = rerankerRequiresApiKey(profile);
        const previousProfile = findRerankerProfile(
          rerankerBaseUrlInput.getAttribute('data-reranker-profile') || '',
        );
        const currentBaseUrl = normalizeText(rerankerBaseUrlInput.value || '');
        rerankerRemoteFields.style.display = isRemote ? 'block' : 'none';
        if (isRemote) {
          rerankerApiKeyInput.closest('.secret-setup-input-row').style.display = requiresApiKey ? 'block' : 'none';
          rerankerApiKeyInput.disabled = !requiresApiKey;
          rerankerApiKeyInput.placeholder = requiresApiKey
            ? 'Reranker API Key'
            : 'No API key required for the public Reranker';
          if (!requiresApiKey) {
            rerankerApiKeyInput.value = '';
          }
        } else {
          rerankerApiKeyInput.closest('.secret-setup-input-row').style.display = 'none';
          rerankerApiKeyInput.disabled = true;
          rerankerApiKeyInput.value = '';
        }
        if (
          isRemote &&
          (!currentBaseUrl || currentBaseUrl === previousProfile.baseUrl)
        ) {
          rerankerBaseUrlInput.value = profile.baseUrl || '';
        }
        if (!isRemote) {
          rerankerBaseUrlInput.value = '';
        }
        rerankerBaseUrlInput.setAttribute('data-reranker-profile', profile.value);
        rerankerStatusEl.textContent = `${profile.note} Model: ${profile.model}`;
      };
      const syncProviderSections = () => {
        deepseekSection.style.display = 'block';
      };

      const resetGithubStatus = () => {
        githubOk = false;
        githubStatusEl.innerHTML = 'A <code>Classic PAT</code> is required with <code>repo</code>, <code>workflow</code>, and <code>gist</code> scopes.';
        githubStatusEl.style.color = '#999';
      };

      const resetDeepSeekStatus = () => {
        deepseekOk = false;
        deepseekStatusEl.innerHTML =
          'A <code>hello world</code> request will be sent to verify the DeepSeek configuration.';
        deepseekStatusEl.style.color = '#999';
      };
      const resetCustomStatus = () => {
        customStatusEl.innerHTML =
          'A <code>hello world</code> request will be sent for each configured chat model to verify the endpoint and model availability.';
        customStatusEl.style.color = '#999';
      };
      const resetRerankerTestStatus = () => {
        const profile = selectedRerankerProfile();
        rerankerTestStatusEl.textContent = rerankerRequiresApiKey(profile)
          ? 'A minimal rerank request will be sent to verify the Reranker API key, Base URL, and model.'
          : 'A minimal rerank request will be sent to verify the Reranker Base URL and model.';
        rerankerTestStatusEl.style.color = '#999';
      };
      const buildRerankerDraft = (fallbackApiKey, fallbackBaseUrl) => {
        const profile = selectedRerankerProfile();
        const typedApiKey = normalizeText(rerankerApiKeyInput.value || '');
        const typedBaseUrl = normalizeBaseUrlForStorage(
          rerankerBaseUrlInput.value || profile.baseUrl || '',
        );
        const apiKey = typedApiKey;
        const baseUrl = typedBaseUrl;
        const requiresApiKey = rerankerRequiresApiKey(profile);

        if (requiresApiKey && !apiKey) {
          throw new Error(`A Reranker API key is required when using ${profile.label}.`);
        }
        if (profile.provider !== 'local' && !baseUrl) {
          throw new Error(`A Rerank Base URL is required when using ${profile.label}.`);
        }

        return {
          profile: profile.value,
          type: profile.provider,
          provider: profile.provider,
          model: profile.model,
          apiKey: requiresApiKey ? apiKey : '',
          testApiKey: profile.testApiKey || '',
          baseUrl: profile.provider === 'local' ? '' : baseUrl,
        };
      };
      const buildRerankEndpoint = (baseUrl) => {
        const raw = normalizeBaseUrlForStorage(baseUrl || '');
        if (!raw) return '';
        if (/\/rerank$/i.test(raw)) return raw;
        if (/\/v\d+$/i.test(raw)) return `${raw}/rerank`;
        return `${raw}/v1/rerank`;
      };

      const collectProviderDraft = () => {
        const apiKey = normalizeText(deepseekInput.value);
        const model = selectedDeepSeekModel();
        if (!apiKey) {
          throw new Error('Please enter a DeepSeek API key first.');
        }
        if (!model) {
          throw new Error('Please select a model for workflow summarization.');
        }
        const reranker = buildRerankerDraft(apiKey, getDefaultDeepSeekBaseUrl());
        return {
          providerType: 'deepseek',
          summaryApiKey: apiKey,
          summaryBaseUrl: getDefaultDeepSeekBaseUrl(),
          summaryModel: model,
          chatModels: getDefaultDeepSeekChatModels(),
          skipRerank: false,
          reranker: {
            ...reranker,
          },
        };
      };

      const buildPingEntries = () => {
        const apiKey = normalizeText(deepseekInput.value);
        const model = selectedDeepSeekModel();
        if (!apiKey || !model) {
          throw new Error('Please enter a DeepSeek API key and select a model first.');
        }
        return [
          {
            apiKey,
            baseUrl: getDefaultDeepSeekBaseUrl(),
            model,
          },
        ];
      };

      const bindResetOnInput = (elements, resetFn) => {
        elements.forEach((el) => {
          if (!el) return;
          el.addEventListener('input', resetFn);
          el.addEventListener('change', resetFn);
        });
      };

      if (initialGithubToken) {
        githubStatusEl.textContent = 'Loaded from current encrypted configuration. If you change the GitHub Token, please re-verify before saving.';
        githubStatusEl.style.color = '#666';
      }
      if (initialApiKey) {
        deepseekStatusEl.textContent = 'Loaded from current DeepSeek configuration. If you change the API key or model, it is recommended to click the Test button.';
        deepseekStatusEl.style.color = '#666';
      }

      syncProviderSections();
      syncRerankerFields();
      resetRerankerTestStatus();

      bindResetOnInput([githubInput], resetGithubStatus);
      bindResetOnInput([deepseekInput, deepseekModelSelect], resetDeepSeekStatus);
      bindResetOnInput(
        [customApiKeyInput, customBaseUrlInput, customModel1Input, customModel2Input, customModel3Input],
        resetCustomStatus,
      );
      bindResetOnInput([rerankerApiKeyInput, rerankerBaseUrlInput], resetRerankerTestStatus);
      rerankerProfileSelect.addEventListener('change', syncRerankerFields);
      rerankerProfileSelect.addEventListener('change', resetRerankerTestStatus);
      rerankerTestBtn.addEventListener('click', async () => {
        let draft = null;
        try {
          draft = buildRerankerDraft('', '');
        } catch (e) {
          rerankerTestStatusEl.textContent = `❌ ${e.message || e}`;
          rerankerTestStatusEl.style.color = '#c00';
          return;
        }
        if (draft.provider === 'local') {
          rerankerTestStatusEl.textContent = 'Local reranker selected; no remote test needed.';
          rerankerTestStatusEl.style.color = '#666';
          return;
        }
        const endpoint = buildRerankEndpoint(draft.baseUrl);
        if (!endpoint) {
          rerankerTestStatusEl.textContent = '❌ Please enter the Rerank Base URL.';
          rerankerTestStatusEl.style.color = '#c00';
          return;
        }
        rerankerTestBtn.disabled = true;
        rerankerTestStatusEl.textContent = 'Testing remote Reranker...';
        rerankerTestStatusEl.style.color = '#666';
        try {
          const headers = {
            'Content-Type': 'application/json',
          };
          const authApiKey = draft.apiKey || draft.testApiKey || '';
          if (authApiKey) {
            headers.Authorization = `Bearer ${authApiKey}`;
          }
          const res = await fetch(endpoint, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              model: draft.model,
              query: 'Which paper is about neural machine translation?',
              documents: [
                'Attention Is All You Need introduces the Transformer architecture for sequence modeling.',
                'A recipe for sourdough bread with flour and water.',
              ],
              top_n: 1,
              return_documents: false,
            }),
          });
          if (!res.ok) {
            const text = await res.text().catch(() => '');
            throw new Error(`HTTP ${res.status} ${res.statusText}${text ? ` - ${text.slice(0, 180)}` : ''}`);
          }
          const data = await res.json().catch(() => null);
          if (!data || !Array.isArray(data.results)) {
            throw new Error('Response is missing the results field.');
          }
          rerankerTestStatusEl.textContent = `✅ Reranker is available: ${data.results.length} result(s) returned.`;
          rerankerTestStatusEl.style.color = '#28a745';
        } catch (e) {
          rerankerTestStatusEl.textContent = `❌ Test failed: ${e.message || e}`;
          rerankerTestStatusEl.style.color = '#c00';
        } finally {
          rerankerTestBtn.disabled = false;
        }
      });
      providerInputs.forEach((input) => {
        input.addEventListener('change', () => {
          syncProviderSections();
          setErrorText(
            'DeepSeek credentials will be encrypted and written to GitHub Secrets (for GitHub Actions). A local secret.private backup will also be generated.',
            '#999',
          );
        });
      });

      backBtn.addEventListener('click', () => {
        renderInitStep1();
      });

      closeBtn.addEventListener('click', () => {
        hide();
      });

      githubVerifyBtn.addEventListener('click', async () => {
        const token = normalizeText(githubInput.value);
        if (!token) {
          githubStatusEl.textContent = 'Please enter a GitHub Token first.';
          githubStatusEl.style.color = '#c00';
          githubOk = false;
          return;
        }
        githubVerifyBtn.disabled = true;
        githubStatusEl.textContent = 'Verifying GitHub Token...';
        githubStatusEl.style.color = '#666';
        try {
          const res = await fetch('https://api.github.com/user', {
            headers: {
              Authorization: `token ${token}`,
              Accept: 'application/vnd.github.v3+json',
            },
          });
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
          }
          const scopesHeader = res.headers.get('X-OAuth-Scopes') || '';
          const scopeList = scopesHeader
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
          const requiredScopes = ['repo', 'workflow', 'gist'];
          const missing = requiredScopes.filter((scope) => !scopeList.includes(scope));
          if (missing.length) {
            throw new Error(
              `Insufficient Token permissions; missing scopes: ${missing.join(', ')}. Please regenerate the PAT in GitHub.`,
            );
          }
          const userData = await res.json().catch(() => ({}));
          const login = userData.login || '';
          let repoInfo = '';
          const repoMeta = await readRepoOwnerJson();
          if (repoMeta) {
            if (login && repoMeta.owner && login.toLowerCase() !== repoMeta.owner.toLowerCase()) {
              throw new Error(
                `Token user ${login} does not match site owner ${repoMeta.owner}. Please use the site owner's Token.`,
              );
            }
            repoInfo = `<br>Repository: ${repoMeta.owner}/${repoMeta.repo}`;
          }
          githubStatusEl.innerHTML = `✅ Verification successful: user ${login}, scopes: ${scopeList.join(', ')}${repoInfo}<br>Gist sharing: enabled.`;
          githubStatusEl.style.color = '#28a745';
          githubOk = true;
        } catch (e) {
          githubStatusEl.textContent = `❌ Verification failed: ${e.message || e}`;
          githubStatusEl.style.color = '#c00';
          githubOk = false;
        } finally {
          githubVerifyBtn.disabled = false;
        }
      });

      deepseekVerifyBtn.addEventListener('click', async () => {
        const key = normalizeText(deepseekInput.value);
        if (!key) {
          deepseekStatusEl.textContent = 'Please enter a DeepSeek API key first.';
          deepseekStatusEl.style.color = '#c00';
          deepseekOk = false;
          return;
        }
        deepseekVerifyBtn.disabled = true;
        deepseekStatusEl.textContent = 'Testing DeepSeek configuration...';
        deepseekStatusEl.style.color = '#666';
        try {
          const models = await pingChatModels(buildPingEntries(), deepseekStatusEl);
          deepseekStatusEl.textContent = `✅ Configuration is working: ${models.join(', ')}`;
          deepseekStatusEl.style.color = '#28a745';
          deepseekOk = true;
        } catch (e) {
          deepseekStatusEl.textContent = `❌ Verification failed: ${e.message || e}`;
          deepseekStatusEl.style.color = '#c00';
          deepseekOk = false;
        } finally {
          deepseekVerifyBtn.disabled = false;
        }
      });

      deepseekTestBtn.addEventListener('click', async () => {
        deepseekTestBtn.disabled = true;
        deepseekVerifyBtn.disabled = true;
        try {
          const models = await pingChatModels(buildPingEntries(), deepseekStatusEl);
          deepseekStatusEl.textContent = `✅ Configuration is working: ${models.join(', ')}`;
          deepseekStatusEl.style.color = '#28a745';
          deepseekOk = true;
        } catch (e) {
          deepseekStatusEl.textContent = `❌ Test failed: ${e.message || e}`;
          deepseekStatusEl.style.color = '#c00';
          deepseekOk = false;
        } finally {
          deepseekTestBtn.disabled = false;
          deepseekVerifyBtn.disabled = false;
        }
      });

      genBtn.addEventListener('click', async () => {
        const githubToken = normalizeText(githubInput.value);
        const localOnly = isLocalDebugHost();
        if (!localOnly && (!githubToken || !githubOk)) {
          setErrorText('Please enter and verify your GitHub Token first.', '#c00');
          return;
        }

        let providerDraft = null;
        try {
          providerDraft = collectProviderDraft();
        } catch (e) {
          setErrorText(e.message || 'The current model configuration is incomplete.', '#c00');
          return;
        }

        if (providerDraft.providerType === 'deepseek' && !deepseekOk) {
          setErrorText('Please click “Test” first to confirm that the DeepSeek configuration is working.', '#c00');
          return;
        }

        const nowIso = new Date().toISOString();
        const plainConfig = {
          createdAt: currentSecret.createdAt || nowIso,
          updatedAt: nowIso,
          github: {
            token: githubToken,
          },
          llmProvider: {
            type: providerDraft.providerType,
            skipRerank: providerDraft.skipRerank,
          },
          summarizedLLM: {
            apiKey: providerDraft.summaryApiKey,
            baseUrl: providerDraft.summaryBaseUrl,
            model: providerDraft.summaryModel,
          },
          rerankerLLM: providerDraft.reranker
            ? {
                profile: providerDraft.reranker.profile || DEFAULT_RERANKER_PROFILE.value,
                provider: providerDraft.reranker.provider || providerDraft.reranker.type || DEFAULT_RERANKER_PROFILE.provider,
                type: providerDraft.reranker.type || providerDraft.reranker.provider || DEFAULT_RERANKER_PROFILE.provider,
                apiKey: providerDraft.reranker.apiKey,
                baseUrl: providerDraft.reranker.baseUrl,
                model: providerDraft.reranker.model,
              }
            : {
                enabled: false,
              },
          chatLLMs: [
            {
              apiKey: providerDraft.summaryApiKey,
              baseUrl: providerDraft.summaryBaseUrl,
              models: providerDraft.chatModels,
            },
          ],
        };

        try {
          setErrorText(localOnly ? 'Generating local encrypted configuration...' : 'Preparing to write GitHub Secrets...', '#666');
          genBtn.disabled = true;

          if (!localOnly) {
            const secretsOk = await saveSummarizeSecretsToGithub(
              githubToken,
              {
                providerType: providerDraft.providerType,
                summarizedApiKey: providerDraft.summaryApiKey,
                summarizedBaseUrl: providerDraft.summaryBaseUrl,
                summarizedModel: providerDraft.summaryModel,
                filterModel: providerDraft.filterModel,
                rewriteModel: providerDraft.rewriteModel,
                skipRerank: providerDraft.skipRerank,
                localRerankModel: 'Qwen/Qwen3-Reranker-0.6B',
                rerankerProfile: providerDraft.reranker && providerDraft.reranker.profile,
                rerankerProvider: providerDraft.reranker && providerDraft.reranker.provider,
                rerankerModel: providerDraft.reranker && providerDraft.reranker.model,
                rerankerApiKey: providerDraft.reranker && providerDraft.reranker.apiKey,
                rerankerBaseUrl: providerDraft.reranker && providerDraft.reranker.baseUrl,
              },
              (current, total, secretName) => {
                setErrorText(`(${current}/${total}) Uploading GitHub Secret: ${secretName}...`, '#666');
              },
            );
            if (!secretsOk) {
              setErrorText(
                '❌ Failed to write GitHub Secrets. Please check your network connection, Token permissions (Classic PAT with repo/workflow/gist scopes required), and try again.',
                '#c00',
              );
              return;
            }
          }

          setErrorText(localOnly ? 'Saving to local browser storage...' : 'GitHub Secrets upload complete. Generating encrypted configuration (secret.private)...', '#666');
          const payload = await createEncryptedSecret(password, plainConfig);
          window.decoded_secret_private = plainConfig;
          setMode('full');

          if (localOnly) {
            try {
              await saveLocalSecretPayloadToDisk(payload, plainConfig);
            } catch (e) {
              console.error(e);
              setErrorText('❌ Failed to save local secret.private. Please make sure the local backend server is running.', '#c00');
              return;
            }
          } else {
            const blob = new Blob([JSON.stringify(payload, null, 2)], {
              type: 'application/json',
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'secret.private';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }, 0);

            setErrorText('Pushing secret.private to the GitHub repository root...', '#666');
            const commitOk = await saveSecretPrivateToGithubRepo(githubToken, payload);
            if (!commitOk) {
              setErrorText(
                '⚠️ Local secret.private has been generated, but the automatic push to the GitHub repository failed. Please commit it manually or check your Token and network connection.',
                '#c00',
              );
            }
          }

          hide();

          try {
            if (window.SubscriptionsManager && window.SubscriptionsManager.openOverlay) {
              window.SubscriptionsManager.openOverlay();
            } else {
              var ensureEvent = new CustomEvent('ensure-arxiv-ui');
              document.dispatchEvent(ensureEvent);
              setTimeout(function () {
                var loadEvent = new CustomEvent('load-arxiv-subscriptions');
                document.dispatchEvent(loadEvent);
                var overlay = document.getElementById('arxiv-search-overlay');
                if (overlay) {
                  overlay.style.display = 'flex';
                  requestAnimationFrame(function () {
                    requestAnimationFrame(function () {
                      overlay.classList.add('show');
                    });
                  });
                }
              }, 120);
            }
          } catch {
            // If the subscription panel fails to open, silently ignore it — the main flow is unaffected
          }
        } catch (e) {
          console.error(e);
          setErrorText(
            'Failed to generate secret.private. Please try again or check your browser compatibility.',
            '#c00',
          );
        } finally {
          genBtn.disabled = false;
        }
      });
    };

    // Setup wizard: Step 1 (set password)
    const renderInitStep1 = () => {
      setStep2Modal(false);
      modal.innerHTML = `
        <h2 style="margin-top:0;">🛡️ Setup Wizard · Step 1</h2>
        <p style="font-size:13px; color:#555; margin-bottom:8px;">
          No credentials file (<code>secret.private</code>) found for this repository.
          Please set a password to encrypt your configuration — it will be used to unlock API keys and other sensitive settings.
        </p>
        <label for="secret-setup-password" style="font-size:13px; color:#333; display:block; margin-bottom:4px;">
          Set your unlock password:
        </label>
        <input
          id="secret-setup-password"
          type="password"
          autocomplete="off"
          style="width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:4px; font-size:13px;"
        />
        <input
          id="secret-setup-password-confirm"
          type="password"
          autocomplete="off"
          placeholder="Confirm password"
          style="width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:6px; font-size:13px;"
        />
        <div id="secret-setup-error" style="min-height:18px; font-size:12px; color:#666; margin-bottom:8px;">
          Password must be at least 8 characters and include digits, uppercase, lowercase, and a special character. Your password is stored locally in the browser and used only for decryption.
        </div>
        <div class="secret-gate-actions">
          <button id="secret-setup-guest" type="button" class="secret-gate-btn secondary">
            Continue as guest
          </button>
          <button id="secret-setup-next" type="button" class="secret-gate-btn primary">
            Next
          </button>
        </div>
      `;

      const pwdInput = document.getElementById('secret-setup-password');
      const pwdConfirmInput = document.getElementById(
        'secret-setup-password-confirm',
      );
      const errorEl = document.getElementById('secret-setup-error');
      const guestBtn = document.getElementById('secret-setup-guest');
      const nextBtn = document.getElementById('secret-setup-next');

      if (!pwdInput || !pwdConfirmInput || !guestBtn || !nextBtn) return;

      guestBtn.addEventListener('click', () => {
        setMode('guest');
        hide();
      });

      nextBtn.addEventListener('click', () => {
        const pwd = (pwdInput.value || '').trim();
        const pwd2 = (pwdConfirmInput.value || '').trim();
        const msg = validatePassword(pwd);
        if (msg) {
          if (errorEl) {
            errorEl.textContent = msg;
            errorEl.style.color = '#c00';
          }
          return;
        }
        if (pwd !== pwd2) {
          if (errorEl) {
            errorEl.textContent = 'Passwords do not match. Please try again.';
            errorEl.style.color = '#c00';
          }
          return;
        }

        // Proceed to Step 2
        renderInitStep2(pwd);
      });

      setTimeout(() => {
        try {
          pwdInput.focus();
        } catch {
          // ignore
        }
      }, 100);
    };

    // Render the unified UI for both modes (new two-step setup wizard / unlock screen)
    // Also register the “Credentials Setup” button entry point for the admin panel, using the current closure's renderInitStep1/renderInitStep2
    try {
      window.DPRSecretSetup = window.DPRSecretSetup || {};
      window.DPRSecretSetup.openStep2 = function () {
        const savedPwd = loadSavedPassword();
        openSecretOverlay(overlay);
        // Ensure the overlay is visible
        if (hasSecretFile && !savedPwd) {
          // secret.private exists but no saved password in the browser: must unlock first; cannot go back to the setup wizard.
          renderUnlockUI();
        } else if (!savedPwd) {
          // No secret.private and no saved password: start the full wizard from Step 1.
          renderInitStep1();
        } else {
          // Password is saved: go directly to Step 2 of the configuration wizard
          renderInitStep2(savedPwd);
        }
      };
    } catch {
      // Ignore registration failure; the admin button will fall back to its own degraded message
    }

    if (hasSecretFile) {
      // secret.private exists: show the unlock / guest interface
      renderUnlockUI();
    } else {
      // No secret.private: enter the two-step initialization wizard
      renderInitStep1();
    }
  }

  function init() {
    const overlay = document.getElementById('secret-gate-overlay');
    const registerGuestOnlySecretSetup = () => {
      window.DPRSecretSetup = window.DPRSecretSetup || {};
      window.DPRSecretSetup.openStep2 = function () {
        enforceGuestMode(document.getElementById('secret-gate-overlay'));
        alert('Guest mode is enforced on this domain. Password unlock and credentials configuration are not available.');
      };
    };

    // Default to locked state until the user selects “Unlock” or “Continue as guest”
    window.DPR_ACCESS_MODE = FORCE_GUEST_MODE ? 'guest' : 'locked';

    if (FORCE_GUEST_MODE) {
      setAccessMode('guest', { mode: 'guest', reason: 'domain_force_guest' });
      registerGuestOnlySecretSetup();
      enforceGuestMode(overlay);
      return;
    }

    if (!overlay) return;
    try {
      window.DPRSecretSetup = window.DPRSecretSetup || {};
      const earlyOpenStep2 = function () {
        setupOverlay(true);
        openSecretOverlay(overlay);
        const formalOpenStep2 = window.DPRSecretSetup && window.DPRSecretSetup.openStep2;
        if (typeof formalOpenStep2 === 'function' && formalOpenStep2 !== earlyOpenStep2) {
          formalOpenStep2();
        }
      };
      window.DPRSecretSetup.openStep2 = earlyOpenStep2;
    } catch {
      // If the early fallback entry fails, setupOverlay will still attempt to register the formal entry later.
    }

    // Check whether secret.private already exists (to distinguish “unlock” from “initialize”)
    (async () => {
      try {
        const staticPayload = await fetchStaticSecretPayload();
        let hasSecret = Boolean(staticPayload);
        const localPayload = await loadLocalSecretPayloadPreferred(staticPayload);
        hasSecret = hasSecret || Boolean(localPayload);

        window.DPR_ACCESS_MODE = 'locked';

        if (hasSecret) {
          // secret.private exists: if a password is saved in the browser, attempt auto-unlock;
          // on success, enter the page directly; on failure or no saved password, show the unlock/guest UI.
          const savedPwd = loadSavedPassword();
          if (savedPwd) {
            try {
              const payload = localPayload || staticPayload || await fetchStaticSecretPayload();
              if (!payload) {
                throw new Error('Failed to fetch secret.private');
              }
              const secret = await decryptSecret(savedPwd, payload);
              window.decoded_secret_private = secret;
              // Not inside setupOverlay scope here; directly set the global access mode to full and broadcast the event
              try {
                setAccessMode('full', { mode: 'full' });
              } catch {
                // ignore
              }
              // Even on successful auto-unlock, initialize the overlay once so the admin “Credentials Setup” button can open Step 2 directly
              // Note: the hidden class is NOT removed here; the overlay remains hidden, only DPRSecretSetup.openStep2 etc. are registered
              try {
                setupOverlay(true);
              } catch {
                // ignore
              }
              closeSecretOverlay(overlay);
              return;
            } catch (e) {
              console.error(
                '[SECRET] Auto-unlock failed; falling back to the manual password entry screen:',
                e,
              );
              clearPassword();
            }
          }
          // No saved password or auto-unlock failed: show the unlock/guest UI
          setupOverlay(true);
          openSecretOverlay(overlay);
        } else {
          // No secret.private: always show the initialization wizard
          setupOverlay(false);
          openSecretOverlay(overlay);
        }
      } catch {
        // On request failure, treat it as “file not found”: always enter the initialization wizard
        window.DPR_ACCESS_MODE = 'locked';
        setupOverlay(false);
        openSecretOverlay(overlay);
      }
    })();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
