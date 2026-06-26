/**
 * DPR Read State Sync — sync read state to Supabase
 *
 * Authenticated users (with a GitHub Token) store read records in the Supabase user_read_state table,
 * guests/unauthenticated users fall back to localStorage.
 */
(function () {
  'use strict';

  var TABLE = 'user_read_state';
  var _supabaseUrl = '';
  var _anonKey = '';
  var _username = '';
  var _cache = {}; // { paper_id: status }
  var _initialized = false;
  var _syncing = false;

  function getRestUrl() {
    return _supabaseUrl.replace(/\/$/, '') + '/rest/v1/' + TABLE;
  }

  function headers(extra) {
    var h = {
      apikey: _anonKey,
      Authorization: 'Bearer ' + _anonKey,
      'Content-Type': 'application/json',
      Prefer: 'return=minimal',
    };
    if (extra) Object.assign(h, extra);
    return h;
  }

  /**
   * Initialize: pass in Supabase connection info and the GitHub username
   * Pull all of this user's read records from Supabase
   */
  function init(supabaseUrl, anonKey, githubUsername) {
    if (!supabaseUrl || !anonKey || !githubUsername) return Promise.resolve();
    _supabaseUrl = supabaseUrl;
    _anonKey = anonKey;
    _username = githubUsername;

    return fetch(
      getRestUrl() + '?github_username=eq.' + encodeURIComponent(_username) + '&select=paper_id,status',
      { headers: headers() }
    )
      .then(function (resp) {
        if (!resp.ok) throw new Error('read_state fetch ' + resp.status);
        return resp.json();
      })
      .then(function (rows) {
        _cache = {};
        (rows || []).forEach(function (row) {
          if (row.paper_id) _cache[row.paper_id] = row.status || 'read';
        });
        _initialized = true;
      })
      .catch(function (err) {
        console.warn('[DPR ReadState] init failed:', err);
        _initialized = false;
      });
  }

  /**
   * Mark a paper's read state
   */
  function markRead(paperId, status) {
    if (!paperId) return;
    var st = status || 'read';
    _cache[paperId] = st;

    if (!_initialized || !_username) return;

    // upsert to Supabase
    var body = JSON.stringify({
      github_username: _username,
      paper_id: paperId,
      status: st,
      read_at: new Date().toISOString(),
    });

    fetch(getRestUrl() + '?on_conflict=github_username,paper_id', {
      method: 'POST',
      headers: headers({ Prefer: 'resolution=merge-duplicates,return=minimal' }),
      body: body,
    }).catch(function (err) {
      console.warn('[DPR ReadState] upsert failed:', err);
    });
  }

  /**
   * Remove a read mark
   */
  function clearRead(paperId) {
    if (!paperId) return;
    delete _cache[paperId];

    if (!_initialized || !_username) return;

    fetch(
      getRestUrl() + '?github_username=eq.' + encodeURIComponent(_username) + '&paper_id=eq.' + encodeURIComponent(paperId),
      { method: 'DELETE', headers: headers() }
    ).catch(function (err) {
      console.warn('[DPR ReadState] delete failed:', err);
    });
  }

  /**
   * Get the read state of a paper
   */
  function getStatus(paperId) {
    return _cache[paperId] || null;
  }

  /**
   * Get all read states (returns an object { paper_id: status })
   */
  function getAll() {
    return Object.assign({}, _cache);
  }

  /**
   * Count unread papers among a set of paper IDs
   */
  function countUnread(paperIds) {
    var count = 0;
    for (var i = 0; i < paperIds.length; i++) {
      if (!_cache[paperIds[i]]) count++;
    }
    return count;
  }

  /**
   * Whether it is initialized (authenticated-user mode)
   */
  function isActive() {
    return _initialized && !!_username;
  }

  /**
   * Migrate existing read records from localStorage to Supabase (one-time)
   */
  function migrateFromLocalStorage(localState) {
    if (!_initialized || !_username || !localState) return;
    var entries = Object.keys(localState);
    if (!entries.length) return;

    // Merge into the cache
    entries.forEach(function (paperId) {
      if (!_cache[paperId]) {
        _cache[paperId] = localState[paperId];
      }
    });

    // Bulk upsert
    var rows = entries.map(function (paperId) {
      return {
        github_username: _username,
        paper_id: paperId,
        status: localState[paperId] || 'read',
        read_at: new Date().toISOString(),
      };
    });

    // Upsert in batches (50 per batch)
    var batchSize = 50;
    for (var i = 0; i < rows.length; i += batchSize) {
      var batch = rows.slice(i, i + batchSize);
      fetch(getRestUrl() + '?on_conflict=github_username,paper_id', {
        method: 'POST',
        headers: headers({ Prefer: 'resolution=merge-duplicates,return=minimal' }),
        body: JSON.stringify(batch),
      }).catch(function () {});
    }
  }

  window.DPRReadStateSync = {
    init: init,
    markRead: markRead,
    clearRead: clearRead,
    getStatus: getStatus,
    getAll: getAll,
    countUnread: countUnread,
    isActive: isActive,
    migrateFromLocalStorage: migrateFromLocalStorage,
  };
})();
