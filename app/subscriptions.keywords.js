// Subscription keyword management module
// Responsibilities: render the keyword list, add/remove keywords

window.SubscriptionsKeywords = (function () {
  let keywordsListEl = null;
  let keywordInput = null;
  let keywordAliasInput = null;
  let addBtn = null;
  let msgEl = null;
  let reloadAll = null;

  // Simple HTML escaping to prevent XSS
  const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  // Validate keyword syntax to avoid producing config that YAML cannot parse
  const validateKeywordSyntax = (keyword) => {
    const raw = (keyword || '').trim();
    if (!raw) {
      return { valid: false, message: 'The keyword cannot be empty' };
    }
    return { valid: true, message: '' };
  };

  const render = (items) => {
    if (!keywordsListEl) return;
    if (!items || !items.length) {
      keywordsListEl.innerHTML =
        '<div style="color:#999;">No keyword subscriptions yet; add one below.</div>';
      return;
    }
    keywordsListEl.innerHTML = '';
    items.forEach((item) => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.justifyContent = 'space-between';
      row.style.marginBottom = '2px';
      const tag = item.tag || item.alias || '';
      row.innerHTML = `
        <span>${
          tag
            ? '<span class="tag-label tag-green">' +
              escapeHtml(tag) +
              '</span>'
            : ''
        }${escapeHtml(item.keyword || '')}</span>
        <button data-id="${
          item.id
        }" class="arxiv-keyword-del" style="border:none;background:none;color:#c00;font-size:11px;cursor:pointer;">Delete</button>
      `;
      keywordsListEl.appendChild(row);
    });

    keywordsListEl.querySelectorAll('.arxiv-keyword-del').forEach((btn) => {
      if (btn._bound) return;
      btn._bound = true;
      btn.addEventListener('click', async () => {
        const idStr = btn.getAttribute('data-id');
        if (idStr == null) return;
        const index = parseInt(idStr, 10);
        if (Number.isNaN(index)) return;
        try {
          if (
            !window.SubscriptionsManager ||
            !window.SubscriptionsManager.updateDraftConfig
          ) {
            throw new Error('Missing local draft update capability');
          }
          window.SubscriptionsManager.updateDraftConfig((cfg) => {
            const next = cfg || {};
            if (!next.subscriptions) next.subscriptions = {};
            const subs = next.subscriptions;
            const list = Array.isArray(subs.keywords)
              ? subs.keywords.slice()
              : [];
            if (index >= 0 && index < list.length) {
              list.splice(index, 1);
            }
            subs.keywords = list;
            next.subscriptions = subs;
            return next;
          });
          if (typeof reloadAll === 'function') reloadAll();
        } catch (err) {
          console.error(err);
          if (msgEl) {
            msgEl.textContent = 'Failed to delete the keyword, please try again later';
            msgEl.style.color = '#c00';
          }
        }
      });
    });
  };

  const addKeyword = async () => {
    if (!keywordInput || !keywordAliasInput) return;
    const keyword = (keywordInput.value || '').trim();
    const tag = (keywordAliasInput.value || '').trim();
    if (!keyword) {
      if (msgEl) {
        msgEl.textContent = 'The keyword cannot be empty';
        msgEl.style.color = '#c00';
      }
      return;
    }

    // Keyword syntax validation
    const { valid, message } = validateKeywordSyntax(keyword);
    if (!valid) {
      if (msgEl) {
        msgEl.textContent = message || 'Invalid keyword format';
        msgEl.style.color = '#c00';
      }
      return;
    }

    if (!tag) {
      if (msgEl) {
        msgEl.textContent = 'A tag is required';
        msgEl.style.color = '#c00';
      }
      return;
    }

    try {
      if (
        !window.SubscriptionsManager ||
        !window.SubscriptionsManager.updateDraftConfig
      ) {
        throw new Error('Missing local draft update capability');
      }
      window.SubscriptionsManager.updateDraftConfig((cfg) => {
        const next = cfg || {};
        if (!next.subscriptions) next.subscriptions = {};
        const subs = next.subscriptions;
        const list = Array.isArray(subs.keywords) ? subs.keywords.slice() : [];
        list.push({ keyword, tag });
        subs.keywords = list;
        next.subscriptions = subs;
        return next;
      });

      if (msgEl) {
        msgEl.textContent = 'The keyword was added to the local draft; click Save to sync it to the cloud.';
        msgEl.style.color = '#666';
      }
      keywordInput.value = '';
      keywordAliasInput.value = '';
      if (typeof reloadAll === 'function') reloadAll();
    } catch (e) {
      console.error(e);
      if (msgEl) {
        msgEl.textContent = 'Failed to add the keyword, please try again later';
        msgEl.style.color = '#c00';
      }
    }
  };

  const attach = (context) => {
    keywordsListEl = context.keywordsListEl || null;
    keywordInput = context.keywordInput || null;
    keywordAliasInput = context.keywordAliasInput || null;
    addBtn = context.keywordAddBtn || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    // Render a placeholder on first mount so the list area is not blank when the panel first opens
    if (keywordsListEl && !keywordsListEl._initialized) {
      keywordsListEl._initialized = true;
      render([]);
    }

    if (keywordInput && !keywordInput._advancedPlaceholderSet) {
      keywordInput._advancedPlaceholderSet = true;
      keywordInput.placeholder = 'Enter a keyword';
    }

    if (addBtn && !addBtn._bound) {
      addBtn._bound = true;
      addBtn.addEventListener('click', addKeyword);
    }
    if (keywordAliasInput && !keywordAliasInput._bound) {
      keywordAliasInput._bound = true;
      keywordAliasInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          addKeyword();
        }
      });
    }
  };

  return {
    attach,
    render,
  };
})();
