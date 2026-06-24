/**
 * DPR Read State Sync — 阅读状态同步到 Supabase
 *
 * 认证用户（有 GitHub Token）的阅读记录存到 Supabase user_read_state 表，
 * 游客/未认证仍用 localStorage 回退。
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
   * 初始化：传入 Supabase 连接信息和 GitHub 用户名
   * 从 Supabase 拉取该用户的全部阅读记录
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
   * 标记论文阅读状态
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
   * 删除阅读标记
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
   * 获取某篇论文的阅读状态
   */
  function getStatus(paperId) {
    return _cache[paperId] || null;
  }

  /**
   * 获取全部已读状态（返回对象 { paper_id: status }）
   */
  function getAll() {
    return Object.assign({}, _cache);
  }

  /**
   * 计算一组论文 ID 中的未读数
   */
  function countUnread(paperIds) {
    var count = 0;
    for (var i = 0; i < paperIds.length; i++) {
      if (!_cache[paperIds[i]]) count++;
    }
    return count;
  }

  /**
   * 是否已初始化（认证用户模式）
   */
  function isActive() {
    return _initialized && !!_username;
  }

  /**
   * 从 localStorage 迁移已有的阅读记录到 Supabase（一次性）
   */
  function migrateFromLocalStorage(localState) {
    if (!_initialized || !_username || !localState) return;
    var entries = Object.keys(localState);
    if (!entries.length) return;

    // 合并到缓存
    entries.forEach(function (paperId) {
      if (!_cache[paperId]) {
        _cache[paperId] = localState[paperId];
      }
    });

    // 批量 upsert
    var rows = entries.map(function (paperId) {
      return {
        github_username: _username,
        paper_id: paperId,
        status: localState[paperId] || 'read',
        read_at: new Date().toISOString(),
      };
    });

    // 分批 upsert（每批 50 条）
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
