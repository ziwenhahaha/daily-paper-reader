// Smart subscription management module (formerly Zotero)
// Responsibilities: render the smart subscription list (query + tags), add/remove subscriptions

window.SubscriptionsZotero = (function () {
  let zoteroListEl = null;
  let zoteroIdInput = null;
  let zoteroAliasInput = null;
  let zoteroAddBtn = null;
  let msgEl = null;
  let reloadAll = null;

  const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  const render = (items) => {
    if (!zoteroListEl) return;
    if (!items || !items.length) {
      zoteroListEl.innerHTML =
        '<div style="color:#999;">No smart subscriptions yet; add one below.</div>';
      return;
    }
    zoteroListEl.innerHTML = '';
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
            ? '<span class="tag-label tag-blue">' +
              escapeHtml(tag) +
              '</span>'
            : ''
        }${escapeHtml(item.zotero_id || '')}</span>
        <button data-id="${
          item.id
        }" class="zotero-del-btn" style="border:none;background:none;color:#c00;font-size:11px;cursor:pointer;">Delete</button>
      `;
      zoteroListEl.appendChild(row);
    });

    zoteroListEl.querySelectorAll('.zotero-del-btn').forEach((btn) => {
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
            const list = Array.isArray(subs.llm_queries)
              ? subs.llm_queries.slice()
              : [];
            if (index >= 0 && index < list.length) {
              list.splice(index, 1);
            }
            subs.llm_queries = list;
            next.subscriptions = subs;
            return next;
          });
          if (typeof reloadAll === 'function') reloadAll();
        } catch (err) {
          console.error(err);
        }
      });
    });
  };

  const addZotero = async () => {
    if (!zoteroIdInput || !zoteroAliasInput) return;

    const query = (zoteroIdInput.value || '').trim();
    const tag = (zoteroAliasInput.value || '').trim();
    if (!query) {
      if (msgEl) {
        msgEl.textContent = 'The query cannot be empty';
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
        const list = Array.isArray(subs.llm_queries)
          ? subs.llm_queries.slice()
          : [];
        list.push({
          query,
          tag,
        });
        subs.llm_queries = list;
        next.subscriptions = subs;
        return next;
      });

      if (msgEl) {
        msgEl.textContent = 'The smart subscription was added to the local draft; click Save to sync it to the cloud.';
        msgEl.style.color = '#666';
      }
      zoteroIdInput.value = '';
      zoteroAliasInput.value = '';
      if (typeof reloadAll === 'function') reloadAll();
    } catch (e) {
      console.error(e);
      if (msgEl) {
        msgEl.textContent = 'Failed to add the smart subscription, please try again later';
        msgEl.style.color = '#c00';
      }
    }
  };

  const attach = (context) => {
    zoteroListEl = context.zoteroListEl || null;
    zoteroIdInput = context.zoteroIdInput || null;
    zoteroAliasInput = context.zoteroAliasInput || null;
    zoteroAddBtn = context.zoteroAddBtn || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    // Render a placeholder on first mount so the list area is not blank when the panel first opens
    if (zoteroListEl && !zoteroListEl._initialized) {
      zoteroListEl._initialized = true;
      render([]);
    }

    if (zoteroAddBtn && !zoteroAddBtn._bound) {
      zoteroAddBtn._bound = true;
      zoteroAddBtn.addEventListener('click', addZotero);
    }

    if (zoteroAliasInput && !zoteroAliasInput._bound) {
      zoteroAliasInput._bound = true;
      zoteroAliasInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          addZotero();
        }
      });
    }
  };

  return {
    attach,
    render,
  };
})();
