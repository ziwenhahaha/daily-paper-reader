// 全局密钥会话管理：负责首次进入时的密码解锁 / 游客模式
(function () {
  const STORAGE_KEY_MODE = 'dpr_secret_access_mode_v1'; // 已不再使用，仅保留兼容
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
      console.warn('[SECRET] 未能读取静态 secret.private：', e);
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
      console.error('[SECRET] 读取本地 secret.private 失败：', e);
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
      console.error('[SECRET] 保存本地 secret.private 失败：', e);
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
      throw new Error((data && data.error) || `写入本地 secret.private 失败：HTTP ${res.status}`);
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

  // 简单的密码强度校验：至少 8 位，包含数字、小写字母、大写字母和特殊符号
  function validatePassword(pwd) {
    if (!pwd || pwd.length < 8) {
      return '密码至少需要 8 位字符。';
    }
    if (!/[0-9]/.test(pwd)) {
      return '密码必须包含数字。';
    }
    if (!/[a-z]/.test(pwd)) {
      return '密码必须包含小写字母。';
    }
    if (!/[A-Z]/.test(pwd)) {
      return '密码必须包含大写字母。';
    }
    if (!/[^A-Za-z0-9]/.test(pwd)) {
      return '密码必须包含至少一个特殊符号（如 !@# 等）。';
    }
    return '';
  }

  // 旧版模式标记已废弃，仅用于清理兼容
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
      label: '公益 Rerank（zwwen.online）',
      provider: 'public_zwwen',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: 'https://zwwen.online/rerank',
      requiresApiKey: false,
      testApiKey: '26932a86d772001af60cbd9d2c162bfda3a90e094f797f3d6806f6077478b27a',
      note: '默认推荐；使用 zwwen.online 公益 rerank 服务。',
    },
    {
      value: 'local-qwen3-0.6b',
      label: '本地 Qwen3-Reranker-0.6B',
      provider: 'local',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: '',
      requiresApiKey: false,
      note: '无需 reranker API Key，GitHub Actions 在 CPU 上加载本地模型。',
    },
    {
      value: 'siliconflow-qwen3-0.6b',
      label: '硅基流动 Qwen3-Reranker-0.6B',
      provider: 'siliconflow',
      model: 'Qwen/Qwen3-Reranker-0.6B',
      baseUrl: 'https://api.siliconflow.cn/v1/rerank',
      requiresApiKey: true,
      note: '速度快、成本低；需要硅基流动 API Key。',
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
      throw new Error('请先填写完整的模型配置。');
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
          throw new Error('模型配置缺少 apiKey、baseUrl 或 model。');
        }
        if (statusEl) {
          statusEl.textContent = `正在测试模型 ${i + 1}/${entries.length}：${model} ...`;
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
            `${model} 请求失败：HTTP ${resp.status} ${resp.statusText}${text ? ` - ${text.slice(0, 160)}` : ''}`,
          );
        }
        const data = await resp.json().catch(() => null);
        const text = extractChatResponseText(data);
        if (!normalizeText(text)) {
          throw new Error(`${model} 返回为空，请检查模型兼容性。`);
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

  // 使用 GitHub Token 推断目标仓库 owner/repo（与订阅面板保持一致的推断规则）
  async function detectGithubRepoFromToken(token) {
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        Authorization: `token ${token}`,
        Accept: 'application/vnd.github.v3+json',
      },
    });
    if (!userRes.ok) {
      throw new Error('无法使用当前 GitHub Token 获取用户信息。');
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
            `Token 用户 ${login} 与站点所有者 ${repoMeta.owner} 不一致`,
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
      throw new Error('无法推断目标仓库，请检查当前访问域名或配置。');
    }

    return { owner: repoOwner, repo: repoName };
  }

  // 将总结模型 / workflow 所需的大模型配置写入 GitHub Secrets
  // 可选 progress 回调用于在 UI 中展示上传进度：progress(currentIndex, total, secretName)
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
      // 等待 libsodium-wrappers 就绪（通过 CDN 注入全局 sodium）
      if (!window.sodium || !window.sodium.ready) {
        if (
          window.sodium &&
          typeof window.sodium.ready === 'object' &&
          typeof window.sodium.ready.then === 'function'
        ) {
          await window.sodium.ready;
        } else {
          throw new Error(
            '浏览器未正确加载 libsodium-wrappers，无法写入 GitHub Secrets。',
          );
        }
      }
      const sodium = window.sodium;
      if (!sodium) {
        throw new Error('浏览器缺少 libsodium 支持，无法写入 GitHub Secrets。');
      }

      const { owner, repo } = await detectGithubRepoFromToken(token);

      // 获取仓库 Public Key
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
          `获取仓库 Public Key 失败（HTTP ${pkRes.status}），请确认 Token 是否具备 repo 权限。`,
        );
      }
      const pkData = await pkRes.json();
      const publicKey = pkData.key;
      const keyId = pkData.key_id;
      if (!publicKey || !keyId) {
        throw new Error('Public Key 数据不完整，无法写入 Secrets。');
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
        throw new Error('总结模型配置不完整，无法写入 GitHub Secrets。');
      }
      if (!rerankerProfile || !rerankerProvider || !rerankerModel) {
        throw new Error('Reranker 配置不完整，无法写入 GitHub Secrets。');
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
            `写入 GitHub Secret ${name} 失败：HTTP ${res.status} ${res.statusText} - ${txt}`,
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
            // 忽略进度回调中的异常
          }
        }
        await putSecret(item.name, encryptValue(item.value));
      }

      return true;
    } catch (e) {
      console.error('[SECRET] 保存 GitHub Secrets 失败：', e);
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

  // 将生成好的 secret.private 提交到当前 GitHub 仓库根目录
  async function saveSecretPrivateToGithubRepo(token, payload) {
    try {
      const { owner, repo } = await detectGithubRepoFromToken(token);
      const filePath = 'secret.private';

      // 先尝试获取现有文件，拿到 sha（如果不存在则忽略 404）
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
            `读取远程 secret.private 失败：HTTP ${getRes.status} ${getRes.statusText} - ${txt}`,
          );
        }
      } catch (e) {
        console.error('[SECRET] 预读远程 secret.private 失败：', e);
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
          `提交 secret.private 到仓库失败：HTTP ${putRes.status} ${putRes.statusText} - ${txt}`,
        );
      }

      return true;
    } catch (e) {
      console.error('[SECRET] 保存 secret.private 到 GitHub 仓库失败：', e);
      return false;
    }
  }

  async function deriveAesGcmKey(password, saltBytes, usages) {
    const enc = new TextEncoder();
    const cryptoObj = (typeof window !== 'undefined' && (window.crypto || window.msCrypto)) || null;
    if (!cryptoObj || !cryptoObj.subtle) {
      throw new Error(
        '当前环境不支持 Web Crypto AES-GCM。请通过 https 或 http://localhost 使用现代浏览器（Chrome/Edge/Firefox）打开本页面后重试。',
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

  // 约定 secret.private 的结构为：
  // {
  //   "version": 1,
  //   "salt": "<base64>",
  //   "iv": "<base64>",
  //   "ciphertext": "<base64>"
  // }
  // 明文为 JSON 字符串，包含 LLM API Key 等配置信息。
  async function decryptSecret(password, payload) {
    if (!payload || typeof payload !== 'object') {
      throw new Error('密文格式不正确');
    }
    const saltB64 = payload.salt;
    const ivB64 = payload.iv;
    const cipherB64 = payload.ciphertext;
    if (!saltB64 || !ivB64 || !cipherB64) {
      throw new Error('缺少必须字段（salt/iv/ciphertext）');
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
      throw new Error('解密成功但内容不是有效 JSON');
    }
    return obj;
  }

  // 创建新的 secret.private：以明文配置对象 + 密码生成加密文件结构
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

  // 初始化模式：已有 secret.private -> 解锁 / 游客；无 secret.private -> 首次配置向导
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

    // 已有 secret.private 时的解锁界面渲染逻辑
    const renderUnlockUI = () => {
      setStep2Modal(false);
      modal.innerHTML = `
        <h2 style="margin-top:0;">🔐 解锁密钥</h2>
        <p style="font-size:13px; color:#555; margin-bottom:8px;">
          检测到已存在密钥文件 <code>secret.private</code>。请输入解锁密码，
          或选择以游客身份访问（仅支持阅读论文，无法使用后台大模型能力）。
        </p>
        <label for="secret-gate-password" style="font-size:13px; color:#333; display:block; margin-bottom:4px;">
          解锁密码（至少 8 位，包含数字、小写字母、大写字母和特殊符号）：
        </label>
        <input
          id="secret-gate-password"
          type="password"
          autocomplete="off"
          style="width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:6px; font-size:13px;"
        />
        <div id="secret-gate-error" style="min-height:18px; font-size:12px; color:#999; margin-bottom:8px;">
          密码仅在本地用于解密，不会上传到服务器。
        </div>
        <div class="secret-gate-actions">
          <button id="secret-gate-guest" type="button" class="secret-gate-btn secondary">
            以游客身份访问
          </button>
          <button id="secret-gate-unlock" type="button" class="secret-gate-btn primary">
            解锁密钥
          </button>
        </div>
      `;

      const pwdInput = document.getElementById('secret-gate-password');
      const errorEl = document.getElementById('secret-gate-error');
      const guestBtn = document.getElementById('secret-gate-guest');
      const unlockBtn = document.getElementById('secret-gate-unlock');

      if (!pwdInput || !guestBtn || !unlockBtn) return;

      // 游客模式：不解密，不加载密钥，仅浏览 & 阅读
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
          errorEl.textContent = '正在解锁密钥，请稍候...';
          errorEl.style.color = '#666';
        }
        unlockBtn.disabled = true;
        guestBtn.disabled = true;
        try {
          const staticPayload = await fetchStaticSecretPayload();
          if (!staticPayload) {
            throw new Error('获取 secret.private 失败');
          }
          const payload = await loadLocalSecretPayloadPreferred(staticPayload);
          const secret = await decryptSecret(pwd, payload);
          // 将解密后的配置保存在内存中，不落盘，同时记住密码以便下次自动解锁
          window.decoded_secret_private = secret;
          savePassword(pwd);
          setMode('full');
          hide();
        } catch (e) {
          console.error(e);
          if (errorEl) {
            errorEl.textContent =
              '解锁失败，请检查密码是否正确，或稍后重试。';
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

    // 初始化向导：第 2 步（仅保留 DeepSeek API）
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
          ? 'DeepSeek V4 Flash · 默认推荐'
          : model === 'deepseek-v4-pro'
            ? 'DeepSeek V4 Pro · 高性能模型'
            : model,
      }));

      modal.innerHTML = `
        <h2 style="margin-top:0;">🛡️ 新配置指引 · 第二步</h2>
        <div class="secret-setup-step2-grid" style="font-size:13px;">
          <div class="secret-setup-step2-col">
            <div class="secret-setup-step2-block">
              <div class="secret-setup-step2-title">GitHub Token（必填）</div>
              <p class="secret-setup-step2-note">
                需要使用 <code>Classic PAT</code>，并同时具备 <code>repo</code>、<code>workflow</code> 和 <code>gist</code> 权限。
              </p>
              <div class="secret-setup-input-row">
                <input
                  id="secret-setup-github-token"
                  type="password"
                  autocomplete="off"
                  placeholder="用于读写 config.yaml 与触发 workflow 的 GitHub PAT"
                  style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                />
                <button id="secret-setup-github-verify" type="button" class="secret-gate-btn secondary">
                  验证
                </button>
              </div>
              <div id="secret-setup-github-status" style="min-height:18px; font-size:12px; color:#999;">
                需要使用 <code>Classic PAT</code>，并同时具备 <code>repo</code>、<code>workflow</code> 和 <code>gist</code> 权限。
              </div>
            </div>

            <div id="secret-setup-deepseek-section" class="secret-setup-step2-block">
              <div class="secret-setup-step2-title">DeepSeek API（必填）</div>
              <p class="secret-setup-step2-note">
                DeepSeek 用于 query enrich、LLM refine、总结与聊天；Reranker 可在右侧单独选择。
              </p>
              <div class="secret-setup-input-row multi-actions">
                <input
                  id="secret-setup-deepseek"
                  type="password"
                  autocomplete="off"
                  placeholder="DeepSeek API Key，例如：sk-xxxx"
                  style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                />
                <button id="secret-setup-deepseek-test" type="button" class="secret-gate-btn secondary">
                  测试
                </button>
                <button id="secret-setup-deepseek-verify" type="button" class="secret-gate-btn secondary" style="display:none;">
                  验证
                </button>
              </div>
              <div id="secret-setup-deepseek-status" style="min-height:18px; font-size:12px; color:#999; margin-bottom:8px;">
                将通过一次 <code>hello world</code> 请求检查 DeepSeek 配置可用性。
              </div>

              <div style="font-weight:500; margin-bottom:4px; display:flex; align-items:center; gap:4px;">
                用于工作流总结 / 过滤的大模型
                <span class="secret-model-tip">!
                  <span class="secret-model-tip-popup">
                    当前只保留 DeepSeek 官方 API。<br/>
                    Reranker API Key 与 DeepSeek 分开配置。
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
                Step 3 使用 Qwen3 reranker 对候选论文重排。请选择本地模型或远端服务。
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
                    placeholder="Rerank Base URL，例如 https://api.siliconflow.cn/v1/rerank"
                    style="width:100%; box-sizing:border-box; padding:6px 8px; font-size:13px;"
                  />
                </div>
                <button id="secret-setup-reranker-test" type="button" class="secret-gate-btn secondary secret-setup-step2-actions">
                  测试 Reranker
                </button>
                <div id="secret-setup-reranker-test-status" style="min-height:18px; font-size:12px; color:#999; margin-top:6px;">
                  将发送一次最小 rerank 请求验证 API Key、Base URL 与模型是否可用。
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
          所有密钥信息将加密写入 GitHub Secrets（用于 GitHub Actions），并同步生成本地 <code>secret.private</code> 备份，原文不会直接存入仓库。
        </div>
        <div class="secret-gate-actions">
          <button id="secret-setup-back" type="button" class="secret-gate-btn secondary">
            上一步
          </button>
          <button id="secret-setup-close" type="button" class="secret-gate-btn secondary">
            关闭
          </button>
          <button id="secret-setup-generate" type="button" class="secret-gate-btn primary">
            保存配置
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
            : '公益 Reranker 无需 API Key';
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
        rerankerStatusEl.textContent = `${profile.note} 模型：${profile.model}`;
      };
      const syncProviderSections = () => {
        deepseekSection.style.display = 'block';
      };

      const resetGithubStatus = () => {
        githubOk = false;
        githubStatusEl.innerHTML = '需要使用 <code>Classic PAT</code>，并同时具备 <code>repo</code>、<code>workflow</code> 和 <code>gist</code> 权限。';
        githubStatusEl.style.color = '#999';
      };

      const resetDeepSeekStatus = () => {
        deepseekOk = false;
        deepseekStatusEl.innerHTML =
          '将通过一次 <code>hello world</code> 请求检查 DeepSeek 配置可用性。';
        deepseekStatusEl.style.color = '#999';
      };
      const resetCustomStatus = () => {
        customStatusEl.innerHTML =
          '将依次用已填写聊天模型发送 <code>hello world</code>，检查接口与模型是否可用。';
        customStatusEl.style.color = '#999';
      };
      const resetRerankerTestStatus = () => {
        const profile = selectedRerankerProfile();
        rerankerTestStatusEl.textContent = rerankerRequiresApiKey(profile)
          ? '将发送一次最小 rerank 请求验证 API Key、Base URL 与模型是否可用。'
          : '将发送一次最小 rerank 请求验证 Base URL 与模型是否可用。';
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
          throw new Error(`选择 ${profile.label} 时需要填写 Reranker API Key。`);
        }
        if (profile.provider !== 'local' && !baseUrl) {
          throw new Error(`请选择 ${profile.label} 时需要填写 Rerank Base URL。`);
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
          throw new Error('请先输入 DeepSeek API Key。');
        }
        if (!model) {
          throw new Error('请选择用于工作流总结的大模型。');
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
          throw new Error('请先填写 DeepSeek API Key 并选择模型。');
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
        githubStatusEl.textContent = '已载入当前加密配置；如更换 GitHub Token，保存前请重新验证。';
        githubStatusEl.style.color = '#666';
      }
      if (initialApiKey) {
        deepseekStatusEl.textContent = '已载入当前 DeepSeek 配置；如更换 API Key 或模型，建议点击测试按钮。';
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
          rerankerTestStatusEl.textContent = '当前选择为本地 reranker，无需远端测试。';
          rerankerTestStatusEl.style.color = '#666';
          return;
        }
        const endpoint = buildRerankEndpoint(draft.baseUrl);
        if (!endpoint) {
          rerankerTestStatusEl.textContent = '❌ 请填写 Rerank Base URL。';
          rerankerTestStatusEl.style.color = '#c00';
          return;
        }
        rerankerTestBtn.disabled = true;
        rerankerTestStatusEl.textContent = '正在测试远端 Reranker...';
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
            throw new Error('响应缺少 results 字段。');
          }
          rerankerTestStatusEl.textContent = `✅ Reranker 可用：返回 ${data.results.length} 条结果。`;
          rerankerTestStatusEl.style.color = '#28a745';
        } catch (e) {
          rerankerTestStatusEl.textContent = `❌ 测试失败：${e.message || e}`;
          rerankerTestStatusEl.style.color = '#c00';
        } finally {
          rerankerTestBtn.disabled = false;
        }
      });
      providerInputs.forEach((input) => {
        input.addEventListener('change', () => {
          syncProviderSections();
          setErrorText(
            'DeepSeek 密钥将加密写入 GitHub Secrets（用于 GitHub Actions），并同步生成本地 secret.private 备份。',
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
          githubStatusEl.textContent = '请先输入 GitHub Token。';
          githubStatusEl.style.color = '#c00';
          githubOk = false;
          return;
        }
        githubVerifyBtn.disabled = true;
        githubStatusEl.textContent = '正在验证 GitHub Token...';
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
              `Token 权限不足，缺少：${missing.join(', ')}。请在 GitHub 中重新生成 PAT。`,
            );
          }
          const userData = await res.json().catch(() => ({}));
          const login = userData.login || '';
          let repoInfo = '';
          const repoMeta = await readRepoOwnerJson();
          if (repoMeta) {
            if (login && repoMeta.owner && login.toLowerCase() !== repoMeta.owner.toLowerCase()) {
              throw new Error(
                `Token 用户 ${login} 与站点所有者 ${repoMeta.owner} 不一致，请使用站点所有者的 Token。`,
              );
            }
            repoInfo = `<br>仓库：${repoMeta.owner}/${repoMeta.repo}`;
          }
          githubStatusEl.innerHTML = `✅ 验证成功：用户 ${login}，权限：${scopeList.join(', ')}${repoInfo}<br>Gist 分享：已开启。`;
          githubStatusEl.style.color = '#28a745';
          githubOk = true;
        } catch (e) {
          githubStatusEl.textContent = `❌ 验证失败：${e.message || e}`;
          githubStatusEl.style.color = '#c00';
          githubOk = false;
        } finally {
          githubVerifyBtn.disabled = false;
        }
      });

      deepseekVerifyBtn.addEventListener('click', async () => {
        const key = normalizeText(deepseekInput.value);
        if (!key) {
          deepseekStatusEl.textContent = '请先输入 DeepSeek API Key。';
          deepseekStatusEl.style.color = '#c00';
          deepseekOk = false;
          return;
        }
        deepseekVerifyBtn.disabled = true;
        deepseekStatusEl.textContent = '正在测试 DeepSeek 配置...';
        deepseekStatusEl.style.color = '#666';
        try {
          const models = await pingChatModels(buildPingEntries(), deepseekStatusEl);
          deepseekStatusEl.textContent = `✅ 配置可用：${models.join(', ')}`;
          deepseekStatusEl.style.color = '#28a745';
          deepseekOk = true;
        } catch (e) {
          deepseekStatusEl.textContent = `❌ 验证失败：${e.message || e}`;
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
          deepseekStatusEl.textContent = `✅ 配置可用：${models.join(', ')}`;
          deepseekStatusEl.style.color = '#28a745';
          deepseekOk = true;
        } catch (e) {
          deepseekStatusEl.textContent = `❌ 测试失败：${e.message || e}`;
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
          setErrorText('请先填写并通过验证 GitHub Token。', '#c00');
          return;
        }

        let providerDraft = null;
        try {
          providerDraft = collectProviderDraft();
        } catch (e) {
          setErrorText(e.message || '当前模型配置不完整。', '#c00');
          return;
        }

        if (providerDraft.providerType === 'deepseek' && !deepseekOk) {
          setErrorText('请先点击“测试当前配置”，确认 DeepSeek 配置可用。', '#c00');
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
          setErrorText(localOnly ? '正在生成本地加密配置...' : '正在准备写入 GitHub Secrets...', '#666');
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
                setErrorText(`(${current}/${total}) 正在上传 GitHub Secret：${secretName}...`, '#666');
              },
            );
            if (!secretsOk) {
              setErrorText(
                '❌ 写入 GitHub Secrets 失败，请检查网络、Token 权限（需 Classic PAT + repo/workflow/gist）或稍后重试。',
                '#c00',
              );
              return;
            }
          }

          setErrorText(localOnly ? '正在保存到浏览器本地...' : 'GitHub Secrets 上传完成，正在生成加密配置 secret.private...', '#666');
          const payload = await createEncryptedSecret(password, plainConfig);
          window.decoded_secret_private = plainConfig;
          setMode('full');

          if (localOnly) {
            try {
              await saveLocalSecretPayloadToDisk(payload, plainConfig);
            } catch (e) {
              console.error(e);
              setErrorText('❌ 保存到本地 secret.private 失败，请确认本地后端已启动。', '#c00');
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

            setErrorText('正在将 secret.private 推送到 GitHub 仓库根目录...', '#666');
            const commitOk = await saveSecretPrivateToGithubRepo(githubToken, payload);
            if (!commitOk) {
              setErrorText(
                '⚠️ 已生成本地 secret.private，但自动推送到 GitHub 仓库失败，请稍后手动提交或检查 Token/网络。',
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
            // 若后台订阅面板唤起失败，则静默忽略，不影响主流程
          }
        } catch (e) {
          console.error(e);
          setErrorText(
            '生成 secret.private 失败，请稍后重试或检查浏览器兼容性。',
            '#c00',
          );
        } finally {
          genBtn.disabled = false;
        }
      });
    };

    // 初始化向导：第 1 步（设置密码）
    const renderInitStep1 = () => {
      setStep2Modal(false);
      modal.innerHTML = `
        <h2 style="margin-top:0;">🛡️ 新配置指引 · 第一步</h2>
        <p style="font-size:13px; color:#555; margin-bottom:8px;">
          检测到当前仓库尚未创建 <code>secret.private</code> 文件。
          请先设置一个用于加密本地配置的密码，该密码将用于解锁大模型密钥等敏感信息。
        </p>
        <label for="secret-setup-password" style="font-size:13px; color:#333; display:block; margin-bottom:4px;">
          设置解锁密码：
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
          placeholder="再次输入密码确认"
          style="width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:6px; font-size:13px;"
        />
        <div id="secret-setup-error" style="min-height:18px; font-size:12px; color:#666; margin-bottom:8px;">
          密码至少 8 位，且必须包含数字、小写字母、大写字母和特殊符号。密码仅保存在浏览器本地，用于解锁密钥。
        </div>
        <div class="secret-gate-actions">
          <button id="secret-setup-guest" type="button" class="secret-gate-btn secondary">
            以游客身份访问
          </button>
          <button id="secret-setup-next" type="button" class="secret-gate-btn primary">
            下一步
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
            errorEl.textContent = '两次输入的密码不一致，请重新确认。';
            errorEl.style.color = '#c00';
          }
          return;
        }

        // 正式进入第 2 步
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

    // 统一渲染两种模式的 UI（仅使用新的两步初始化向导 / 解锁界面）
    // 同时在此处挂钩后台管理面板的“密钥配置”按钮入口，利用当前闭包中的 renderInitStep1/renderInitStep2
    try {
      window.DPRSecretSetup = window.DPRSecretSetup || {};
      window.DPRSecretSetup.openStep2 = function () {
        const savedPwd = loadSavedPassword();
        openSecretOverlay(overlay);
        // 确保浮层可见
        if (hasSecretFile && !savedPwd) {
          // 已有 secret.private 但浏览器没有保存密码时，必须先解锁，不能回到初始化向导。
          renderUnlockUI();
        } else if (!savedPwd) {
          // 没有 secret.private 且没有保存密码：从第 1 步开始完整向导。
          renderInitStep1();
        } else {
          // 已保存密码：直接进入第 2 步配置向导
          renderInitStep2(savedPwd);
        }
      };
    } catch {
      // 忽略挂钩失败，后台按钮会走自身的降级提示
    }

    if (hasSecretFile) {
      // 已有 secret.private：展示“解锁 / 游客”界面
      renderUnlockUI();
    } else {
      // 不存在 secret.private：进入初始化两步向导
      renderInitStep1();
    }
  }

  function init() {
    const overlay = document.getElementById('secret-gate-overlay');
    const registerGuestOnlySecretSetup = () => {
      window.DPRSecretSetup = window.DPRSecretSetup || {};
      window.DPRSecretSetup.openStep2 = function () {
        enforceGuestMode(document.getElementById('secret-gate-overlay'));
        alert('当前域名已启用游客模式，不支持解锁密码与密钥配置。');
      };
    };

    // 默认视为锁定状态，直到用户选择“解锁 / 游客”
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
      // 初始化早期兜底入口失败时，后续 setupOverlay 仍会尝试注册正式入口。
    }

    // 检查是否已经存在 secret.private（用于区分“解锁”与“初始化”）
    (async () => {
      try {
        const staticPayload = await fetchStaticSecretPayload();
        let hasSecret = Boolean(staticPayload);
        const localPayload = await loadLocalSecretPayloadPreferred(staticPayload);
        hasSecret = hasSecret || Boolean(localPayload);

        window.DPR_ACCESS_MODE = 'locked';

        if (hasSecret) {
          // 已存在 secret.private：若浏览器保存了密码，先尝试自动解锁；
          // 成功则直接进入页面；失败或无密码则展示解锁/游客界面。
          const savedPwd = loadSavedPassword();
          if (savedPwd) {
            try {
              const payload = localPayload || staticPayload || await fetchStaticSecretPayload();
              if (!payload) {
                throw new Error('获取 secret.private 失败');
              }
              const secret = await decryptSecret(savedPwd, payload);
              window.decoded_secret_private = secret;
              // 这里不在 setupOverlay 作用域内，直接标记全局访问模式为 full 并广播事件
              try {
                setAccessMode('full', { mode: 'full' });
              } catch {
                // ignore
              }
              // 自动解锁成功时，仍然初始化一次 overlay，以便后台“密钥配置”按钮可以直接打开第二步向导
              // 注意：此时不移除 hidden 类，浮层保持隐藏，仅注册 DPRSecretSetup.openStep2 等入口
              try {
                setupOverlay(true);
              } catch {
                // ignore
              }
              closeSecretOverlay(overlay);
              return;
            } catch (e) {
              console.error(
                '[SECRET] 自动解锁失败，将回退到手动输入密码界面：',
                e,
              );
              clearPassword();
            }
          }
          // 没有保存的密码或自动解锁失败：展示解锁/游客界面
          setupOverlay(true);
          openSecretOverlay(overlay);
        } else {
          // 不存在 secret.private：始终展示初始化向导
          setupOverlay(false);
          openSecretOverlay(overlay);
        }
      } catch {
        // 请求失败时按“文件不存在”处理：始终进入初始化向导
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
