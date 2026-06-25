// GitHub Token subscription configuration module
// Responsibilities: store Token locally, validate permissions, update button and info panel state

window.SubscriptionsGithubToken = (function () {
  const LOCAL_CONFIG_STORAGE_KEY = 'dpr_local_config_yaml_v1';

  const isLocalDebugHost = () => {
    const host = String((window.location && window.location.hostname) || '').toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  };

  const getLocalApiUrl = (path) => {
    const base = String(window.DPR_LOCAL_API_BASE || '').trim().replace(/\/$/, '');
    if (base) return `${base}${path}`;
    const protocol = String((window.location && window.location.protocol) || 'http:');
    const hostname = String((window.location && window.location.hostname) || '127.0.0.1');
    return `${protocol}//${hostname}:8567${path}`;
  };

  const loadLocalConfigOverride = () => {
    if (!isLocalDebugHost()) return null;
    try {
      if (!window.localStorage) return null;
      const raw = window.localStorage.getItem(LOCAL_CONFIG_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed.config === 'object' ? parsed : null;
    } catch (e) {
      console.error('Failed to load local config override:', e);
      return null;
    }
  };

  const saveLocalConfigOverride = (configObject, commitMessage) => {
    if (!isLocalDebugHost()) return null;
    const payload = {
      config: configObject || {},
      source: 'localStorage',
      message: commitMessage || 'local dashboard config save',
      savedAt: new Date().toISOString(),
    };
    try {
      if (!window.localStorage) {
        throw new Error('localStorage is not supported in this browser.');
      }
      window.localStorage.setItem(LOCAL_CONFIG_STORAGE_KEY, JSON.stringify(payload));
      return payload;
    } catch (e) {
      console.error('Failed to save local config override:', e);
      throw e;
    }
  };

  const loadLocalConfigFromDisk = async () => {
    if (!isLocalDebugHost()) return null;
    const res = await fetch(getLocalApiUrl('/api/local/config'), { cache: 'no-store' });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`Failed to read local config.yaml: HTTP ${res.status}${text ? ` - ${text}` : ''}`);
    }
    const data = await res.json().catch(() => ({}));
    if (!data || data.ok === false) {
      throw new Error((data && data.error) || 'Failed to read local config.yaml.');
    }
    const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
    if (!yaml || typeof yaml.load !== 'function') {
      throw new Error('Missing YAML parser (js-yaml). Cannot parse config.yaml.');
    }
    const cfg = yaml.load(data.content || '') || {};
    return {
      config: cfg,
      sha: null,
      source: data.path || 'local-disk',
      localOnly: true,
      savedAt: data.savedAt || '',
    };
  };

  const saveLocalConfigToDisk = async (configObject, commitMessage) => {
    if (!isLocalDebugHost()) return null;
    const safeConfig = configObject || {};
    const res = await fetch(getLocalApiUrl('/api/local/config'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config: safeConfig,
        message: commitMessage || 'local dashboard config save',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw new Error((data && data.error) || `Failed to write local config.yaml: HTTP ${res.status}`);
    }
    saveLocalConfigOverride(safeConfig, commitMessage);
    return {
      config: safeConfig,
      source: data.path || 'local-disk',
      localOnly: true,
      savedAt: data.savedAt || new Date().toISOString(),
    };
  };

  // Load GitHub Token data from local storage
  const loadGithubToken = () => {
    try {
      const tokenData = localStorage.getItem('github_token_data');
      if (tokenData) {
        const data = JSON.parse(tokenData);
        return data;
      }
    } catch (e) {
      console.error('Failed to load GitHub token:', e);
    }
    return null;
  };

  // Save GitHub Token data to local storage
  const saveGithubToken = (data) => {
    try {
      localStorage.setItem('github_token_data', JSON.stringify(data));
    } catch (e) {
      console.error('Failed to save GitHub token:', e);
    }
  };

  // Clear GitHub Token data
  const clearGithubToken = () => {
    try {
      localStorage.removeItem('github_token_data');
    } catch (e) {
      console.error('Failed to clear GitHub token:', e);
    }
  };

  const readConfigYamlForRepo = async () => {
    const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
    if (!yaml || typeof yaml.load !== 'function') {
      return null;
    }
    const candidates = ['config.yaml', 'docs/config.yaml', '../config.yaml', '/config.yaml'];
    for (const url of candidates) {
      try {
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) continue;
        const text = await res.text();
        const cfg = yaml.load(text || '') || {};
        const githubCfg = (cfg && cfg.github) || {};
        if (githubCfg && typeof githubCfg === 'object') {
          const owner = String(githubCfg.owner || '').trim();
          const repo = String(githubCfg.repo || '').trim();
          if (owner || repo) {
            return { owner, repo };
          }
        }
      } catch {
        // ignore
      }
    }
    return null;
  };

  const readRepoOwnerJson = async () => {
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
  };

  // Verify GitHub Token and check permissions
  const verifyGithubToken = async (token, options = {}) => {
    const { requireWorkflow = true } = options;
    try {
      // 1. Fetch user information
      const userRes = await fetch('https://api.github.com/user', {
        headers: {
          Authorization: `token ${token}`,
          Accept: 'application/vnd.github.v3+json',
        },
      });

      if (!userRes.ok) {
        throw new Error('Token is invalid or has expired');
      }

      const userData = await userRes.json();

      // 2. Check permissions via the X-OAuth-Scopes response header
      const scopes = userRes.headers.get('X-OAuth-Scopes');
      const scopeList = scopes ? scopes.split(',').map((s) => s.trim()) : [];

      const requiredScopes = requireWorkflow ? ['repo', 'workflow', 'gist'] : ['repo', 'gist'];
      const missingScopes = requiredScopes.filter(
        (scope) => !scopeList.includes(scope),
      );

      if (missingScopes.length > 0) {
        // Insufficient permissions: return a failure result with the existing scope list for a more informative UI
        return {
          valid: false,
          error: `Token has insufficient permissions: missing ${missingScopes.join(
            ', ',
          )}. Please use a Classic Personal Access Token with the required permissions listed above.`,
          scopes: scopeList,
          login: userData.login,
        };
      }

      // 3. Resolve repository information for the current site
      // Priority: .repo-owner.json > *.github.io URL pattern > config.yaml > userData.login fallback
      const currentUrl = window.location.href;
      const urlObj = new URL(currentUrl);
      const host = urlObj.hostname || '';

      let repoOwner = '';
      let repoName = '';

      if (host === 'localhost' || host === '127.0.0.1') {
        repoOwner = userData.login || '';
        repoName = 'daily-paper-reader';
      } else {
        const repoMeta = await readRepoOwnerJson();
        if (repoMeta) {
          repoOwner = repoMeta.owner;
          repoName = repoMeta.repo;
          if (userData.login && repoMeta.owner && userData.login.toLowerCase() !== repoMeta.owner.toLowerCase()) {
            throw new Error(
              `Token user ${userData.login} does not match the site owner ${repoMeta.owner}`,
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
            const parsedRepo = await readConfigYamlForRepo();
            if (parsedRepo) {
              repoOwner = parsedRepo.owner || repoOwner;
              repoName = parsedRepo.repo || repoName;
            }
            if (!repoOwner) {
              repoOwner = userData.login || '';
            }
          }
        }
      }

      // 4. If repository information is available, verify that the Token has access to it
      if (repoOwner && repoName) {
        const repoRes = await fetch(
          `https://api.github.com/repos/${repoOwner}/${repoName}`,
          {
            headers: {
              Authorization: `token ${token}`,
              Accept: 'application/vnd.github.v3+json',
            },
          },
        );

        if (!repoRes.ok) {
          throw new Error(
            `Cannot access repository ${repoOwner}/${repoName}. Please verify the Token permissions.`,
          );
        }

        const repoData = await repoRes.json();

        if (!repoData.permissions || !repoData.permissions.push) {
          throw new Error(
            `No write access to repository ${repoOwner}/${repoName}`,
          );
        }
      }

      return {
        valid: true,
        login: userData.login,
        name: userData.name,
        repo:
          repoOwner && repoName
            ? `${repoOwner}/${repoName}`
            : 'No repository detected',
        scopes: scopeList,
      };
    } catch (error) {
      return {
        valid: false,
        error: error.message,
      };
    }
  };

  // Prefer retrieving the GitHub Token from the secret configuration (decoded_secret_private after decrypting secret.private);
  // fall back to the legacy locally stored Token if not present.
  const getTokenForConfig = () => {
    const secret = window.decoded_secret_private || {};
    if (secret.github && secret.github.token) {
      return String(secret.github.token || '').trim();
    }
    const tokenData = loadGithubToken();
    if (tokenData && tokenData.token) {
      return String(tokenData.token || '').trim();
    }
    return null;
  };

  // Infer repository owner/name from the Token (reuses verifyGithubToken logic)
  const resolveRepoInfoFromToken = async (token, requireWorkflow = true) => {
    const result = await verifyGithubToken(token, { requireWorkflow });
    if (!result.valid) {
      throw new Error(
        `GitHub Token verification failed: ${result.error || 'unknown reason'}`,
      );
    }
    if (!result.repo || !result.repo.includes('/')) {
      throw new Error('Could not determine a valid repository from the GitHub Token');
    }
    const parts = result.repo.split('/');
    const owner = parts[0];
    const repo = parts[1];
    return { owner, repo, token };
  };

  // Read config.yaml via the GitHub API (to obtain the latest sha before saving)
  const loadConfigFromGithub = async () => {
    const token = getTokenForConfig();
    if (!token) {
      throw new Error('No valid GitHub Token configured. Please complete the setup guide on the home page first.');
    }
    const info = await resolveRepoInfoFromToken(token, false);
    const res = await fetch(
      `https://api.github.com/repos/${info.owner}/${info.repo}/contents/config.yaml`,
      {
        headers: {
          Authorization: `token ${info.token}`,
          Accept: 'application/vnd.github.v3+json',
        },
      },
    );
    if (!res.ok) {
      throw new Error('Could not read config.yaml. Please verify the file exists and the Token has the required permissions.');
    }
    const data = await res.json();
    const rawBase64 = (data.content || '').replace(/\n/g, '');
    // Decode base64 with UTF-8 to avoid mojibake with non-ASCII characters
    let content = '';
    try {
      const binary = atob(rawBase64);
      // Older browser compatibility: prefer TextDecoder, fall back to escape/decodeURIComponent
      if (window.TextDecoder) {
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {
          bytes[i] = binary.charCodeAt(i);
        }
        content = new TextDecoder('utf-8').decode(bytes);
      } else {
        // eslint-disable-next-line no-escape
        content = decodeURIComponent(escape(binary));
      }
    } catch (e) {
      console.error('Failed to decode config.yaml content from GitHub:', e);
      content = '';
    }
    const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
    if (!yaml || typeof yaml.load !== 'function') {
      throw new Error('Missing YAML parser (js-yaml). Cannot parse config.yaml.');
    }
    const cfg = yaml.load(content) || {};
    return { config: cfg, sha: data.sha };
  };

  // Read config.yaml from the current site using a relative path (no GitHub Token required; for display only)
  // Note: GitHub Pages URLs follow https://<user>.github.io/<repo>/, so /config.yaml would resolve to the domain root — use relative paths instead.
  const loadConfig = async () => {
    try {
      if (isLocalDebugHost()) {
        try {
          return await loadLocalConfigFromDisk();
        } catch (diskError) {
          console.warn('Failed to read config.yaml from local disk, falling back to localStorage:', diskError);
          const localOverride = loadLocalConfigOverride();
          if (localOverride) {
            return {
              config: localOverride.config || {},
              sha: null,
              source: 'localStorage',
              localOnly: true,
              savedAt: localOverride.savedAt || '',
            };
          }
        }
      }

      const candidates = [
        'config.yaml',
        'docs/config.yaml',
        '../config.yaml',
      ];

      let lastError = null;
      for (const url of candidates) {
        try {
          const res = await fetch(url, { cache: 'no-store' });
          if (!res.ok) {
            lastError = new Error(`Could not read ${url} (HTTP ${res.status})`);
            continue;
          }
          const text = await res.text();
          const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
          if (!yaml || typeof yaml.load !== 'function') {
            throw new Error('Missing YAML parser (js-yaml). Cannot parse config.yaml.');
          }
          const cfg = yaml.load(text || '') || {};
          return { config: cfg, sha: null, source: url };
        } catch (e) {
          lastError = e;
        }
      }
      throw lastError || new Error('Could not read config.yaml (unknown reason)');
    } catch (e) {
      console.error('Failed to read config.yaml from site:', e);
      throw e;
    }
  };

  // Update config.yaml: accepts an updater(config) callback that returns the new config object
  const updateConfig = async (updater, commitMessage = 'chore: update config.yaml from dashboard') => {
    if (isLocalDebugHost()) {
      const { config: current } = await loadConfig();
      const next = typeof updater === 'function' ? updater({ ...(current || {}) }) || current : current;
      return saveLocalConfigToDisk(next, commitMessage);
    }

    const token = getTokenForConfig();
    if (!token) {
      throw new Error('No valid GitHub Token configured. Please complete the setup guide on the home page first.');
    }
    const info = await resolveRepoInfoFromToken(token, false);
    const { config: current, sha } = await loadConfigFromGithub();
    const next = typeof updater === 'function' ? updater({ ...(current || {}) }) || current : current;
    const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
    if (!yaml || typeof yaml.dump !== 'function') {
      throw new Error('Missing YAML serializer (js-yaml). Cannot write config.yaml.');
    }
    const newContent = yaml.dump(next, { lineWidth: 120 });
    const body = {
      message: commitMessage,
      content: btoa(unescape(encodeURIComponent(newContent))),
      sha,
    };
    const res = await fetch(
      `https://api.github.com/repos/${info.owner}/${info.repo}/contents/config.yaml`,
      {
        method: 'PUT',
        headers: {
          Authorization: `token ${info.token}`,
          Accept: 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      },
    );
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(
        `Failed to write config.yaml: ${res.status} ${res.statusText} - ${text}`,
      );
    }
    return res.json();
  };

  // Save the given config object to the remote config.yaml (used by the “Save” button)
  const saveConfig = async (configObject, commitMessage = 'chore: save dashboard config from panel') => {
    if (isLocalDebugHost()) {
      return saveLocalConfigToDisk(configObject || {}, commitMessage);
    }

    const token = getTokenForConfig();
    if (!token) {
      throw new Error('No valid GitHub Token configured. Please complete the setup guide on the home page first.');
    }
    const info = await resolveRepoInfoFromToken(token, false);
    // Fetch the current file sha only
    const { sha } = await loadConfigFromGithub();
    const yaml = window.jsyaml || window.jsYaml || window.jsYAML;
    if (!yaml || typeof yaml.dump !== 'function') {
      throw new Error('Missing YAML serializer (js-yaml). Cannot write config.yaml.');
    }
    const safeConfig = configObject || {};
    const newContent = yaml.dump(safeConfig, { lineWidth: 120 });
    const body = {
      message: commitMessage,
      content: btoa(unescape(encodeURIComponent(newContent))),
      sha,
    };
    const res = await fetch(
      `https://api.github.com/repos/${info.owner}/${info.repo}/contents/config.yaml`,
      {
        method: 'PUT',
        headers: {
          Authorization: `token ${info.token}`,
          Accept: 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      },
    );
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(
        `Failed to write config.yaml: ${res.status} ${res.statusText} - ${text}`,
      );
    }
    return res.json();
  };

    const init = (dom) => {
      const {
        githubAuthBtn, // may be null — kept for backward compatibility only
        githubTokenSection,
      githubTokenInput,
      githubTokenToggleBtn,
      githubTokenVerifyBtn,
      githubTokenClearBtn,
      githubTokenMessage,
      githubTokenInfo,
      githubUserName,
      githubRepoName,
    } = dom;

    // Shared: render the “verification successful” message
    const renderSuccessMessage = (data) => {
      if (!githubTokenMessage) return;
      const scopes = Array.isArray(data.scopes) ? data.scopes : [];
      githubTokenMessage.innerHTML = `
        <div style="color:#28a745; font-size:12px; line-height:1.6;">
          <strong>✅ Verification successful!</strong><br>
          User: ${data.login || ''}<br>
          Repository: ${data.repo || ''}<br>
          Permissions: ${scopes.join(', ')}<br>
          Gist sharing: enabled
        </div>
      `;
    };

    // Update the login button state (backward-compatible; silently skips if no button is present)
    const updateAuthButtonStatus = () => {
      if (!githubAuthBtn) return;
      const tokenData = loadGithubToken();
      if (tokenData && tokenData.token && tokenData.verified) {
        githubAuthBtn.textContent = 'Signed in';
        githubAuthBtn.style.background = '#28a745';
        githubAuthBtn.style.color = 'white';
      } else {
        githubAuthBtn.textContent = 'Not signed in';
        githubAuthBtn.style.background = '#6c757d';
        githubAuthBtn.style.color = 'white';
      }
    };

    // Show Token information
    const showTokenInfo = (userData) => {
      if (githubTokenInfo && githubUserName && githubRepoName) {
        githubUserName.textContent = userData.login || 'Unknown';
        githubRepoName.textContent = userData.repo || 'Unknown';
        githubTokenInfo.style.display = 'block';
      }
    };

    // Hide Token information
    const hideTokenInfo = () => {
      if (githubTokenInfo) {
        githubTokenInfo.style.display = 'none';
      }
    };

    // Login button click handler — legacy logic (no button is rendered currently; kept for compatibility)
    if (githubAuthBtn && !githubAuthBtn._bound) {
      githubAuthBtn._bound = true;
      githubAuthBtn.addEventListener('click', () => {
        if (githubTokenSection.style.display === 'none') {
          githubTokenSection.style.display = 'block';

          const tokenData = loadGithubToken();
          if (tokenData && tokenData.verified) {
            if (githubTokenInput) {
              githubTokenInput.value = tokenData.token || '';
            }
            renderSuccessMessage(tokenData);
            showTokenInfo(tokenData);
          }
        } else {
          githubTokenSection.style.display = 'none';
        }
      });
    }

    // Toggle Token visibility
    if (githubTokenToggleBtn && !githubTokenToggleBtn._bound) {
      githubTokenToggleBtn._bound = true;
      githubTokenToggleBtn.addEventListener('click', () => {
        if (githubTokenInput.type === 'password') {
          githubTokenInput.type = 'text';
          githubTokenToggleBtn.textContent = '🙈';
        } else {
          githubTokenInput.type = 'password';
          githubTokenToggleBtn.textContent = '👁️';
        }
      });
    }

    // Verify and save Token
    if (githubTokenVerifyBtn && !githubTokenVerifyBtn._bound) {
      githubTokenVerifyBtn._bound = true;
      githubTokenVerifyBtn.addEventListener('click', async () => {
        const token = githubTokenInput.value.trim();

        if (!token) {
          githubTokenMessage.innerHTML =
            '<span style="color:#dc3545;">❌ Please enter a GitHub Token</span>';
          return;
        }

        githubTokenVerifyBtn.disabled = true;
        githubTokenVerifyBtn.textContent = 'Verifying...';
        githubTokenMessage.innerHTML =
          '<span style="color:#666;">Verifying Token...</span>';
        hideTokenInfo();

        const result = await verifyGithubToken(token);

        if (result.valid) {
          const tokenData = {
            token: token,
            verified: true,
            login: result.login,
            name: result.name,
            repo: result.repo,
            scopes: result.scopes,
            savedAt: new Date().toISOString(),
          };

          saveGithubToken(tokenData);

          renderSuccessMessage(tokenData);

          showTokenInfo(tokenData);
          updateAuthButtonStatus();
          githubTokenInput.value = '';
        } else {
          const userText =
            result.login && typeof result.login === 'string'
              ? `User: ${result.login}<br>`
              : '';
          const scopesText =
            result.scopes && result.scopes.length
              ? `Current permissions: ${result.scopes.join(', ')}<br>`
              : 'Current permissions: (none)<br>';
          const gistHint = 'This tool requires a Classic Personal Access Token with repo, workflow, and gist permissions.<br>';
          githubTokenMessage.innerHTML = `
            <div style="font-size:12px; line-height:1.6;">
              ${userText}${scopesText}${gistHint}
              <span style="color:#dc3545;">❌ ${result.error}</span>
            </div>
          `;
          hideTokenInfo();

          // On verification failure, change the top button state to a red "Verification failed" indicator
          if (githubAuthBtn) {
            githubAuthBtn.textContent = 'Verification failed';
            githubAuthBtn.style.background = '#dc3545';
            githubAuthBtn.style.color = 'white';
          }

          // Also clear the locally saved Token so the UI does not show “Signed in” after a page refresh
          clearGithubToken();
        }

        githubTokenVerifyBtn.disabled = false;
        githubTokenVerifyBtn.textContent = 'Verify & Save';
      });
    }

    // Clear Token
    if (githubTokenClearBtn && !githubTokenClearBtn._bound) {
      githubTokenClearBtn._bound = true;
      githubTokenClearBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear the saved GitHub Token?')) {
          clearGithubToken();
          githubTokenInput.value = '';
          githubTokenMessage.innerHTML =
            '<span style="color:#666;">Token cleared</span>';
          hideTokenInfo();
          updateAuthButtonStatus();
        }
      });
    }

    updateAuthButtonStatus();
  };

  return {
    init,
    loadGithubToken,
    loadLocalConfigOverride,
    loadConfig,
    updateConfig,
    saveConfig,
    isLocalDebugHost,
  };
})();
