/**
 * DPR Sidebar v2 — 自建侧边栏，替代 docsify 内置 sidebar
 *
 * 数据源：docs/_sidebar.md（仍由 src/6.generate_docs.py 和 src/conference_sidebar.py 维护）
 * 解析：直接读取条目 <a data-sidebar-item="..."> 上的 JSON payload
 *
 * UI：
 *   - 顶部工具条：[全部 / 未读] segmented control + 搜索框（debounce 200ms）
 *   - 主体：会议论文 + 日报两个一级面板，面板内第三级目录默认收起
 *   - 阅读状态接入 window.DPRReadStateSync（Supabase）或 localStorage 回退
 *   - hashchange → syncActive() 高亮 + 滚动居中
 */
(function () {
  'use strict';

  // ---------- 常量 ----------
  var SIDEBAR_URL = 'docs/_sidebar.md';
  var READ_STORAGE_KEY = 'dpr_read_papers_v1';
  var REFRESH_AFTER_HIDDEN_MS = 5 * 60 * 1000;
  var SEARCH_DEBOUNCE_MS = 200;
  var FILTER_KEY = 'dpr_sidebar_filter_v2';
  var COLLAPSE_KEY = 'dpr_sidebar_collapse_v4';
  var WIDTH_KEY = 'dpr_sidebar_width_v2';
  var LEGACY_DEFAULT_SIDEBAR_WIDTH = 373;
  var DEFAULT_SIDEBAR_WIDTH = 298;
  var MIN_SIDEBAR_WIDTH = 240;
  var MAX_SIDEBAR_WIDTH = 520;
  var OVERLAY_SIDEBAR_QUERY = '(max-width: 1023px)';
  var MARK_STATUSES = [
    { key: 'good', label: '1', title: '标记 1：重点 / 好' },
    { key: 'blue', label: '2', title: '标记 2：蓝色' },
    { key: 'orange', label: '3', title: '标记 3：紫色' },
    { key: 'bad', label: '4', title: '标记 4：暂不看 / 差' },
  ];

  // ---------- 工具 ----------
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function safeAttr(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
  function safeText(value) {
    var d = document.createElement('div');
    d.textContent = String(value == null ? '' : value);
    return d.innerHTML;
  }
  function debounce(fn, wait) {
    var t = null;
    return function () {
      var args = arguments;
      var ctx = this;
      window.clearTimeout(t);
      t = window.setTimeout(function () {
        fn.apply(ctx, args);
      }, wait);
    };
  }
  function decodeHtmlEntities(s) {
    var d = document.createElement('div');
    d.innerHTML = String(s == null ? '' : s);
    return d.textContent || '';
  }
  function parseScore(raw) {
    var n = parseFloat(raw);
    if (!isFinite(n)) return null;
    return n;
  }
  function starHtmlFromScore(score) {
    var s = parseScore(score);
    if (s == null) return '';
    var filled = Math.max(0, Math.min(5, Math.round(s / 2)));
    var stars = '';
    for (var i = 0; i < 5; i++) {
      stars += i < filled ? '★' : '☆';
    }
    return '<span class="dpr-sidebar-paper-stars" data-score="' + safeAttr(s.toFixed(1)) + '">' + stars + '</span>';
  }
  function tagsHtml(tags) {
    if (!Array.isArray(tags) || !tags.length) return '';
    return tags
      .map(function (t) {
        if (!t || typeof t !== 'object') return '';
        var kind = String(t.kind || 'query');
        var label = String(t.label || '');
        if (!label) return '';
        return '<span class="dpr-sidebar-paper-tag dpr-sidebar-paper-tag-' + safeAttr(kind) + '">' + safeText(label) + '</span>';
      })
      .join('');
  }
  function pad2(n) {
    var v = Number(n);
    return v < 10 ? '0' + v : String(v);
  }
  function normalizeDailyDateKey(value) {
    var s = String(value || '').trim();
    if (!s) return '';
    var compactRange = s.match(/^(\d{8})\s*-\s*(\d{8})$/);
    if (compactRange) return compactRange[1] + '-' + compactRange[2];
    var labelRange = s.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*(?:~|至|到|—|–|-)\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    if (labelRange) {
      return labelRange[1] + pad2(labelRange[2]) + pad2(labelRange[3]) + '-' +
        labelRange[4] + pad2(labelRange[5]) + pad2(labelRange[6]);
    }
    var compact = s.match(/^(\d{8})$/);
    if (compact) return compact[1];
    var label = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
    if (label) return label[1] + pad2(label[2]) + pad2(label[3]);
    return '';
  }
  function isDailyRangeKey(dateKey) {
    return /^\d{8}-\d{8}$/.test(String(dateKey || ''));
  }
  function isDailySingleDateKey(dateKey) {
    return /^\d{8}$/.test(String(dateKey || ''));
  }
  function dailyRangeEndDateKey(dateKey) {
    var s = String(dateKey || '');
    return isDailyRangeKey(s) ? s.slice(9, 17) : '';
  }
  function dailyCalendarAnchorDateKey(dateKey) {
    var normalized = normalizeDailyDateKey(dateKey) || String(dateKey || '');
    if (isDailySingleDateKey(normalized)) return normalized;
    if (isDailyRangeKey(normalized)) return dailyRangeEndDateKey(normalized);
    return '';
  }
  function formatCompactDateLabel(yyyymmdd) {
    var s = String(yyyymmdd || '');
    if (/^\d{8}$/.test(s)) {
      return s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8);
    }
    return s;
  }
  function formatDateLabel(value) {
    var normalized = normalizeDailyDateKey(value);
    if (isDailyRangeKey(normalized)) {
      return formatCompactDateLabel(normalized.slice(0, 8)) + ' ~ ' + formatCompactDateLabel(normalized.slice(9, 17));
    }
    if (isDailySingleDateKey(normalized)) return formatCompactDateLabel(normalized);
    return String(value || '');
  }
  function monthKeyFromDateKey(dateKey) {
    var anchor = dailyCalendarAnchorDateKey(dateKey);
    return anchor ? anchor.slice(0, 6) : '';
  }
  function normalizeMonthKey(monthKey) {
    var s = String(monthKey || '');
    if (!/^\d{6}$/.test(s)) return '';
    var month = Number(s.slice(4, 6));
    return month >= 1 && month <= 12 ? s : '';
  }
  function formatMonthLabel(monthKey) {
    var s = normalizeMonthKey(monthKey);
    if (!s) return '';
    return s.slice(0, 4) + '年' + Number(s.slice(4, 6)) + '月';
  }
  function shiftMonthKey(monthKey, delta) {
    var s = normalizeMonthKey(monthKey);
    if (!s) return '';
    var date = new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(4, 6)) - 1 + Number(delta || 0), 1));
    return String(date.getUTCFullYear()) + pad2(date.getUTCMonth() + 1);
  }
  function daysInMonth(monthKey) {
    var s = normalizeMonthKey(monthKey);
    if (!s) return 0;
    return new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(4, 6)), 0)).getUTCDate();
  }
  function monthStartOffsetMondayFirst(monthKey) {
    var s = normalizeMonthKey(monthKey);
    if (!s) return 0;
    var weekday = new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(4, 6)) - 1, 1)).getUTCDay();
    return (weekday + 6) % 7;
  }
  function dateKeyFromMonthDay(monthKey, dayNumber) {
    var s = normalizeMonthKey(monthKey);
    if (!s) return '';
    return s + pad2(dayNumber);
  }
  function dailyDateKeyFromHref(href) {
    var s = String(href || '');
    var range = s.match(/#?\/(\d{8}-\d{8})(?:\/|$)/);
    if (range) return range[1];
    var daily = s.match(/#?\/(\d{6})\/(\d{2})(?:\/|$)/);
    if (daily) return daily[1] + daily[2];
    return '';
  }
  function paperIdFromHref(href) {
    var s = String(href || '');
    s = s.replace(/^#\//, '').replace(/^\/+/, '');
    if (!s) return '';
    return s;
  }
  function normalizeRouteHref(href) {
    var h = String(href || '').trim();
    if (!h) return '';
    var idx = h.indexOf('?');
    if (idx >= 0) h = h.slice(0, idx);
    if (h.startsWith('#/')) return h;
    if (h.startsWith('#')) return '#/' + h.slice(1).replace(/^\//, '');
    return '#/' + h.replace(/^\//, '');
  }
  function dayReportHrefFromKey(dateKey, explicitHref) {
    var explicit = normalizeRouteHref(explicitHref || '');
    if (explicit && !/^#\/javascript:/i.test(explicit)) return explicit;
    var key = String(dateKey || '').trim();
    if (/^\d{8}$/.test(key)) {
      return '#/' + key.slice(0, 6) + '/' + key.slice(6, 8) + '/README';
    }
    if (/^\d{8}-\d{8}$/.test(key)) {
      return '#/' + key + '/README';
    }
    return '';
  }
  function collectPaperHrefsFromModel(model) {
    var out = [];
    var m = model || state.model || {};
    (m.daily || []).forEach(function (day) {
      (day.papers || []).forEach(function (paper) {
        if (paper && paper.href) out.push(normalizeRouteHref(paper.href));
      });
    });
    (m.conferences || []).forEach(function (conf) {
      (conf.topics || []).forEach(function (topic) {
        (topic.papers || []).forEach(function (paper) {
          if (paper && paper.href) out.push(normalizeRouteHref(paper.href));
        });
      });
    });
    return out.filter(Boolean);
  }
  function collectReportHrefsFromModel(model) {
    var out = [];
    var m = model || state.model || {};
    (m.daily || []).forEach(function (day) {
      var href = day && (day.reportHref || dayReportHrefFromKey(day.dateKey));
      if (href) out.push(normalizeRouteHref(href));
    });
    return out.filter(Boolean);
  }
  function findCurrentPaperHrefFromModel(model, href) {
    var current = normalizeRouteHref(href || currentRouteHref());
    return collectPaperHrefsFromModel(model).indexOf(current) >= 0 ? current : '';
  }
  function findCurrentReportHrefFromModel(model, href) {
    var current = normalizeRouteHref(href || currentRouteHref());
    return collectReportHrefsFromModel(model).indexOf(current) >= 0 ? current : '';
  }
  function normalizeReadStatus(value) {
    if (value === true || value === 'read') return 'read';
    if (value === 'good' || value === 'bad' || value === 'blue' || value === 'orange') return value;
    return '';
  }
  function statusForMarkIndex(value) {
    var n = String(value == null ? '' : value).trim();
    if (n === '1') return 'good';
    if (n === '2') return 'blue';
    if (n === '3') return 'orange';
    if (n === '4') return 'bad';
    return '';
  }
  function shouldAutoMarkRead(status) {
    return !normalizeReadStatus(status);
  }
  function rememberPendingPaperHref(href) {
    var normalized = normalizeRouteHref(href || '');
    state.pendingPaperHref = normalized || '';
    return state.pendingPaperHref;
  }
  function resolveCurrentPaperHrefForRender(model, viewState) {
    var requested = viewState && viewState.currentPaperHref || state.pendingPaperHref || currentRouteHref();
    return findCurrentPaperHrefFromModel(model, requested);
  }
  function clampSidebarWidth(width) {
    var n = parseInt(width, 10);
    if (!isFinite(n)) n = DEFAULT_SIDEBAR_WIDTH;
    return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, n));
  }
  function timestampFromDateLike(value) {
    if (typeof value === 'number' && isFinite(value)) return value;
    var s = String(value == null ? '' : value).trim();
    if (!s) return 0;
    var normalized = normalizeDailyDateKey(s);
    if (isDailyRangeKey(normalized)) return timestampFromDateLike(dailyRangeEndDateKey(normalized));
    if (isDailySingleDateKey(normalized)) s = normalized;
    var compact = s.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (compact) return Date.UTC(Number(compact[1]), Number(compact[2]) - 1, Number(compact[3]));
    var yearOnly = s.match(/^(\d{4})$/);
    if (yearOnly) return Date.UTC(Number(yearOnly[1]), 11, 31, 23, 59, 59);
    var parsed = Date.parse(s);
    return isFinite(parsed) ? parsed : 0;
  }
  function timestampFromRoute(href) {
    var s = String(href || '');
    var daily = s.match(/#?\/(\d{6})\/(\d{2})\//);
    if (daily) return timestampFromDateLike(daily[1] + daily[2]);
    return 0;
  }
  function timestampFromYearText(value) {
    var years = String(value || '').match(/\b(19|20)\d{2}\b/g);
    if (!years || !years.length) return 0;
    var newest = Math.max.apply(null, years.map(function (year) { return Number(year); }));
    return timestampFromDateLike(String(newest));
  }
  function conferenceSortTimestamp(conf) {
    if (!conf) return 0;
    return timestampFromYearText([conf.years, conf.label, conf.name].join(' '));
  }
  function paperSortTimestamp(paper, fallback) {
    var p = paper || {};
    var fields = [
      p.published,
      p.publishedAt,
      p.published_at,
      p.date,
      p.updated,
      p.updatedAt,
      p.submitted,
      p.created_at,
      fallback,
    ];
    for (var i = 0; i < fields.length; i++) {
      var ts = timestampFromDateLike(fields[i]);
      if (ts) return ts;
    }
    return timestampFromRoute(p.href);
  }
  function sortByTimestampDesc(items, getTimestamp) {
    return (items || []).map(function (item, index) {
      return { item: item, index: index, timestamp: getTimestamp(item) || 0 };
    }).sort(function (a, b) {
      if (b.timestamp !== a.timestamp) return b.timestamp - a.timestamp;
      return a.index - b.index;
    }).map(function (record) {
      return record.item;
    });
  }
  function sortPapersByTimeDesc(papers, fallback) {
    return sortByTimestampDesc(papers, function (paper) {
      return paperSortTimestamp(paper, fallback);
    });
  }
  function rerenderOptionsForReadStateEvent() {
    return {
      syncActive: true,
      centerActive: false,
      autoMark: false,
      preserveScroll: true,
    };
  }
  function rerenderOptionsForAxisInteraction(panelKey) {
    return {
      syncActive: false,
      scrollPanel: panelKey || '',
    };
  }
  function rerenderOptionsForPanelToggle(panelKey) {
    return {
      syncActive: false,
      scrollPanel: panelKey || '',
      dispatchUpdated: false,
    };
  }
  function rerenderOptionsForAxisControlClick() {
    return {
      syncActive: false,
      centerActive: false,
      autoMark: false,
      preserveScroll: true,
      dispatchUpdated: false,
    };
  }
  function rerenderOptionsForStatusClick() {
    return {
      updateInPlace: true,
      syncActive: false,
      centerActive: false,
      autoMark: false,
      preserveScroll: true,
      dispatchUpdated: false,
    };
  }
  function syncActiveOptionsForInitialLoad() {
    return {
      center: true,
      autoMark: false,
    };
  }

  // ---------- 阅读状态（包一层，方便切换 Supabase / localStorage） ----------
  var ReadState = {
    getAll: function () {
      if (window.DPRReadStateSync && window.DPRReadStateSync.isActive && window.DPRReadStateSync.isActive()) {
        return window.DPRReadStateSync.getAll() || {};
      }
      try {
        var raw = window.localStorage && window.localStorage.getItem(READ_STORAGE_KEY);
        if (!raw) return {};
        var obj = JSON.parse(raw);
        if (!obj || typeof obj !== 'object') return {};
        var normalized = {};
        Object.keys(obj).forEach(function (key) {
          var status = normalizeReadStatus(obj[key]);
          if (status) normalized[key] = status;
        });
        return normalized;
      } catch (e) {
        return {};
      }
    },
    saveAll: function (map) {
      try {
        window.localStorage && window.localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(map || {}));
      } catch (e) {}
    },
    mark: function (paperId, status) {
      if (!paperId) return '';
      var st = normalizeReadStatus(status) || 'read';
      var map = this.getAll();
      map[paperId] = st;
      this.saveAll(map);
      if (window.DPRReadStateSync && window.DPRReadStateSync.isActive && window.DPRReadStateSync.isActive()) {
        window.DPRReadStateSync.markRead(paperId, st);
      }
      return st;
    },
    clear: function (paperId) {
      if (!paperId) return;
      var map = this.getAll();
      delete map[paperId];
      this.saveAll(map);
      if (window.DPRReadStateSync && window.DPRReadStateSync.isActive && window.DPRReadStateSync.isActive()) {
        window.DPRReadStateSync.clearRead(paperId);
      }
    },
    isRead: function (paperId) {
      if (!paperId) return false;
      return !!normalizeReadStatus(this.getAll()[paperId]);
    },
  };

  function dispatchReadStateChanged(paperId, status) {
    if (!document || typeof document.dispatchEvent !== 'function') return;
    try {
      document.dispatchEvent(new CustomEvent('dpr-paper-read-state-changed', {
        detail: { paperId: paperId, status: status || null },
      }));
    } catch (e) {
      try {
        var event = document.createEvent('CustomEvent');
        event.initCustomEvent('dpr-paper-read-state-changed', false, false, {
          paperId: paperId,
          status: status || null,
        });
        document.dispatchEvent(event);
      } catch (ignored) {}
    }
  }

  function markPaperStatus(paperId, status, options) {
    var st = ReadState.mark(paperId, status);
    if (!st) return '';
    if (!options || options.notify !== false) dispatchReadStateChanged(paperId, st);
    return st;
  }

  // ---------- 数据解析 ----------
  // 把 docs/_sidebar.md 文本解析成 model
  // 结构：
  //   - 行 "* Daily Papers" 进入日报分组
  //   - 行 "  * <YYYY-MM-DD>  <!--dpr-date:YYYYMMDD-->" 是日期标题
  //   - 行 "    * 精读区 / 速读区" 是 section
  //   - 行 "      * <a class=dpr-sidebar-item-link href=#/.. data-sidebar-item={...}>..." 是论文
  //   - 行 "* Conference Papers" 进入会议分组
  //   - 行 "  * <CONF YYYY...>  <!--dpr-conference:xxx-->" 是会议块
  //   - 行 "    * <topic-label>  <!--dpr-conference-topic:...-->" 是 topic
  //   - 同样 "      * <a ...>" 是论文
  function parseSidebar(text) {
    var lines = String(text || '').split(/\r?\n/);
    var model = {
      home: null,
      tutorial: null,
      daily: [],
      conferences: [],
    };

    var i = 0;
    function parseTopLink(line) {
      // 顶层链接 line: "* <a ... href="#/" >首页</a>"
      var m = line.match(/href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
      if (!m) return null;
      var hashMatch = line.match(/data-dpr-hash="([^"]+)"/);
      return { href: hashMatch ? hashMatch[1] : m[1], label: stripTags(m[2]) };
    }
    function stripTags(html) {
      var d = document.createElement('div');
      d.innerHTML = String(html || '');
      return (d.textContent || '').trim();
    }
    function parsePaperLine(line) {
      var m = line.match(/<a\b([^>]*)>([\s\S]*?)<\/a>/);
      if (!m) return null;
      var attrStr = m[1];
      var title = stripTags(m[2]);
      var hrefMatch = attrStr.match(/href="([^"]+)"/);
      var href = hrefMatch ? hrefMatch[1] : '';
      if (!href || !/^#\//.test(href)) return null;
      var payloadMatch = attrStr.match(/data-sidebar-item="([^"]*)"/);
      var payload = null;
      if (payloadMatch && payloadMatch[1]) {
        try {
          payload = JSON.parse(decodeHtmlEntities(payloadMatch[1]));
        } catch (e) {
          payload = null;
        }
      }
      var paperId = paperIdFromHref(href);
      var node = {
        id: paperId,
        href: href,
        title: (payload && payload.title) || title || paperId,
        link: (payload && payload.link) || '',
        score: payload && payload.score,
        evidence: (payload && payload.evidence) || '',
        published: payload && (payload.published || payload.published_at || payload.publishedAt || payload.date || payload.updated || payload.updated_at || payload.submitted || payload.created_at) || '',
        tags: (payload && Array.isArray(payload.tags) ? payload.tags : []),
        selectionSource: payload && payload.selection_source,
      };
      return node;
    }

    while (i < lines.length) {
      var line = lines[i];
      var trimmed = line.replace(/\s+$/, '');
      if (!trimmed) { i += 1; continue; }

      // 顶层入口（首页/教程）
      if (/^\*\s+<a\b/.test(trimmed) && i < 3) {
        var top = parseTopLink(trimmed);
        if (top) {
          if (!model.home && (top.href === '#/' || /\/$/.test(top.href))) {
            model.home = top;
          } else if (!model.tutorial) {
            model.tutorial = top;
          }
        }
        i += 1;
        continue;
      }

      if (/^\*\s*Daily Papers/.test(trimmed)) {
        i += 1;
        while (i < lines.length && !/^\*\s/.test(lines[i])) {
          var dayLine = lines[i];
          var markerMatch = dayLine.match(/<!--dpr-date:([^>]+?)-->/);
          if (/^\s{2}\*\s/.test(dayLine) && !/^\s{4}/.test(dayLine)) {
            var dayLink = parseTopLink(dayLine);
            var rawLabel = dayLine.replace(/^\s{2}\*\s+/, '').replace(/<!--.*?-->/g, '').trim();
            var dateKey = normalizeDailyDateKey(markerMatch ? markerMatch[1] : rawLabel) ||
              dailyDateKeyFromHref(dayLink && dayLink.href) ||
              rawLabel;
            var day = {
              dateKey: dateKey,
              dateLabel: (dayLink && dayLink.label) || rawLabel || formatDateLabel(dateKey),
              reportHref: dayReportHrefFromKey(dateKey, dayLink && dayLink.href),
              papers: [],
            };
            i += 1;
            var currentSection = 'deep';
            // 收到下一行不是当前 day 的子节点（缩进 >=4）则跳出
            while (i < lines.length) {
              var inner = lines[i];
              if (/^\*\s/.test(inner) || /^\s{0,3}\*\s/.test(inner)) break;
              if (!inner.trim()) { i += 1; continue; }
              // section heading 4-space "* 精读区/速读区"
              if (/^\s{4}\*\s+精读区/.test(inner)) {
                currentSection = 'deep';
                i += 1;
                continue;
              }
              if (/^\s{4}\*\s+速读区/.test(inner)) {
                currentSection = 'quick';
                i += 1;
                continue;
              }
              // paper at 6-space indent (生产格式：分 section)
              if (/^\s{6}\*\s+<a/.test(inner)) {
                var paper = parsePaperLine(inner);
                if (paper) {
                  paper.section = currentSection;
                  day.papers.push(paper);
                }
                i += 1;
                continue;
              }
              // paper at 4-space indent (无 section 简化格式)
              if (/^\s{4}\*\s+<a/.test(inner)) {
                var paper2 = parsePaperLine(inner);
                if (paper2) {
                  paper2.section = currentSection;
                  day.papers.push(paper2);
                }
                i += 1;
                continue;
              }
              i += 1;
            }
            model.daily.push(day);
            continue;
          }
          i += 1;
        }
        continue;
      }

      if (/^\*\s*Conference Papers/.test(trimmed)) {
        i += 1;
        while (i < lines.length && !/^\*\s/.test(lines[i])) {
          var confLine = lines[i];
          var confMarker = confLine.match(/<!--dpr-conference:(.+?)-([0-9]{4}(?:-[0-9]{4})*)-->/);
          if (/^\s{2}\*\s/.test(confLine) && !/^\s{4}/.test(confLine)) {
            var confLabel = confLine.replace(/^\s{2}\*\s+/, '').replace(/<!--.*?-->/g, '').trim();
            var confBlock = {
              name: confMarker ? confMarker[1] : confLabel,
              years: confMarker ? confMarker[2] : '',
              label: confLabel,
              topics: [],
            };
            i += 1;
            var topic = null;
            while (i < lines.length) {
              var tLine = lines[i];
              if (/^\*\s/.test(tLine) || /^\s{0,3}\*\s/.test(tLine)) break;
              if (!tLine.trim()) { i += 1; continue; }
              // topic heading 4-space "* <label>" 但不是 paper 链接
              if (/^\s{4}\*\s+(?!<a)/.test(tLine)) {
                var topicLabel = tLine.replace(/^\s{4}\*\s+/, '').replace(/<!--.*?-->/g, '').trim();
                topic = { label: topicLabel || 'General', papers: [] };
                confBlock.topics.push(topic);
                i += 1;
                continue;
              }
              // paper at 6-space indent
              if (/^\s{6}\*\s+<a/.test(tLine)) {
                if (!topic) {
                  topic = { label: 'General', papers: [] };
                  confBlock.topics.push(topic);
                }
                var p = parsePaperLine(tLine);
                if (p) {
                  p.section = 'conference';
                  topic.papers.push(p);
                }
                i += 1;
                continue;
              }
              // paper at 4-space indent (无 topic)
              if (/^\s{4}\*\s+<a/.test(tLine)) {
                if (!topic) {
                  topic = { label: 'General', papers: [] };
                  confBlock.topics.push(topic);
                }
                var pp = parsePaperLine(tLine);
                if (pp) {
                  pp.section = 'conference';
                  topic.papers.push(pp);
                }
                i += 1;
                continue;
              }
              i += 1;
            }
            model.conferences.push(confBlock);
            continue;
          }
          i += 1;
        }
        continue;
      }

      i += 1;
    }

    model.daily.forEach(function (day) {
      day.papers = sortPapersByTimeDesc(day.papers || [], day.dateKey);
    });
    model.conferences.forEach(function (conf) {
      (conf.topics || []).forEach(function (topic) {
        topic.papers = sortPapersByTimeDesc(topic.papers || [], conferenceSortTimestamp(conf));
      });
    });
    model.conferences = sortByTimestampDesc(model.conferences, conferenceSortTimestamp);
    // 日报按日期倒序；区间日报按结束日期归位，保证最近的区间报告不会从日历里“消失”。
    model.daily.sort(function (a, b) {
      var at = timestampFromDateLike(a && a.dateKey);
      var bt = timestampFromDateLike(b && b.dateKey);
      if (bt !== at) return bt - at;
      return String(b.dateKey).localeCompare(String(a.dateKey));
    });

    return model;
  }

  function conferenceKey(conf) {
    if (!conf) return '';
    var name = String(conf.name || '').trim();
    var years = String(conf.years || '').trim();
    if (name && years) return name + '-' + years;
    return String(conf.label || name || years || '').trim();
  }

  function paperTagLabels(paper) {
    var out = [];
    (paper && paper.tags || []).forEach(function (tag) {
      var label = tag && String(tag.label || '').trim();
      if (label && out.indexOf(label) === -1) out.push(label);
    });
    return out.length ? out : ['未标注'];
  }

  function addTab(tabs, seen, key, label) {
    if (!key || seen[key]) return;
    seen[key] = { key: key, label: label || key, count: 0, unreadCount: 0 };
    tabs.push(seen[key]);
  }

  function flattenDailyPapers(model) {
    var records = [];
    (model && model.daily || []).forEach(function (day) {
      (day.papers || []).forEach(function (paper) {
        records.push({
          dateKey: day.dateKey,
          dateLabel: day.dateLabel || formatDateLabel(day.dateKey),
          paper: paper,
        });
      });
    });
    return records;
  }

  function flattenConferencePapers(model) {
    var records = [];
    (model && model.conferences || []).forEach(function (conf) {
      var confKey = conferenceKey(conf);
      (conf.topics || []).forEach(function (topic) {
        (topic.papers || []).forEach(function (paper) {
          records.push({
            confKey: confKey,
            confLabel: conf.label || confKey,
            topicLabel: topic.label || 'General',
            paper: paper,
          });
        });
      });
    });
    return records;
  }

  function paperSearchText(paper) {
    return [
      paper && paper.title || '',
      paper && paper.evidence || '',
      (paper && paper.tags || []).map(function (t) { return (t && t.label) || ''; }).join(' '),
    ].join(' ').toLowerCase();
  }

  function paperReadStatus(paper, readMap) {
    var id = paperIdentity(paper);
    return normalizeReadStatus(id && readMap && readMap[id]);
  }
  function paperIdentity(paper) {
    return (paper && paper.id) || paperIdFromHref(paper && paper.href) || '';
  }

  function normalizePaperIdSet(value) {
    if (value instanceof Set) return value;
    if (Array.isArray(value)) return new Set(value.filter(Boolean));
    return null;
  }

  function collectUnreadPaperIdsForSnapshot(model, readMap) {
    var ids = new Set();
    flattenDailyPapers(model).forEach(function (record) {
      var id = paperIdentity(record.paper);
      if (id && !paperReadStatus(record.paper, readMap || {})) ids.add(id);
    });
    flattenConferencePapers(model).forEach(function (record) {
      var id = paperIdentity(record.paper);
      if (id && !paperReadStatus(record.paper, readMap || {})) ids.add(id);
    });
    return ids;
  }

  function ensureUnreadSessionPaperIds(model, readMap) {
    if (!state.unreadResultPaperIds) {
      state.unreadResultPaperIds = collectUnreadPaperIdsForSnapshot(model, readMap || {});
    }
    return state.unreadResultPaperIds;
  }

  function resolveResultOptions(options) {
    var opts = options || {};
    var currentPaperId = opts.currentPaperId || paperIdFromHref(opts.currentPaperHref || '');
    return {
      keyword: String(opts.keyword || '').trim().toLowerCase(),
      readMap: opts.readMap || {},
      unreadOnly: !!opts.unreadOnly,
      currentPaperId: currentPaperId || '',
      unreadResultPaperIds: normalizePaperIdSet(opts.unreadResultPaperIds),
    };
  }

  function paperMatchesResult(paper, options) {
    var opts = resolveResultOptions(options);
    var id = paperIdentity(paper);
    if (opts.keyword && paperSearchText(paper).indexOf(opts.keyword) === -1) return false;
    if (opts.unreadOnly && opts.unreadResultPaperIds) return id && opts.unreadResultPaperIds.has(id);
    if (opts.unreadOnly && paperReadStatus(paper, opts.readMap) && paperIdentity(paper) !== opts.currentPaperId) return false;
    return true;
  }

  function filterModelForPaperResults(model, options) {
    var opts = resolveResultOptions(options);
    if (!opts.keyword && !opts.unreadOnly) return model || { home: null, tutorial: null, daily: [], conferences: [] };
    var source = model || {};
    var filtered = {
      home: source.home || null,
      tutorial: source.tutorial || null,
      daily: [],
      conferences: [],
    };
    (source.daily || []).forEach(function (day) {
      var papers = (day.papers || []).filter(function (paper) {
        return paperMatchesResult(paper, opts);
      });
      if (!papers.length) return;
      var nextDay = {};
      Object.keys(day || {}).forEach(function (key) {
        nextDay[key] = day[key];
      });
      nextDay.papers = papers;
      filtered.daily.push(nextDay);
    });
    (source.conferences || []).forEach(function (conf) {
      var topics = [];
      (conf.topics || []).forEach(function (topic) {
        var papers = (topic.papers || []).filter(function (paper) {
          return paperMatchesResult(paper, opts);
        });
        if (!papers.length) return;
        var nextTopic = {};
        Object.keys(topic || {}).forEach(function (key) {
          nextTopic[key] = topic[key];
        });
        nextTopic.papers = papers;
        topics.push(nextTopic);
      });
      if (!topics.length) return;
      var nextConf = {};
      Object.keys(conf || {}).forEach(function (key) {
        nextConf[key] = conf[key];
      });
      nextConf.topics = topics;
      filtered.conferences.push(nextConf);
    });
    return filtered;
  }

  function modelForUnreadNormalFilter(model, readMap) {
    var keyword = String(state.search || '').trim();
    if (state.filter !== 'unread' || keyword) return model;
    var currentPaperHref = resolveCurrentPaperHrefForRender(model, {
      currentPaperHref: state.pendingPaperHref || currentRouteHref(),
    });
    return filterModelForPaperResults(model, {
      readMap: readMap || {},
      unreadOnly: true,
      currentPaperId: currentPaperHref ? paperIdFromHref(currentPaperHref) : '',
      unreadResultPaperIds: state.unreadResultPaperIds,
    });
  }

  function resultTabLabel(options) {
    var opts = resolveResultOptions(options);
    if (opts.keyword && opts.unreadOnly) return '未读搜索';
    if (opts.keyword) return '搜索结果';
    if (opts.unreadOnly) return '未读';
    return '全部';
  }

  function buildResultView(groups, options) {
    var opts = resolveResultOptions(options);
    var total = 0;
    var unread = 0;
    groups.forEach(function (group) {
      total += (group.papers || []).length;
      group.unreadCount = countUnreadPapers(group.papers || [], opts.readMap);
      unread += group.unreadCount;
    });
    return {
      activeKey: '__results__',
      resultMode: true,
      tabs: [{ key: '__results__', label: resultTabLabel(opts), count: total, unreadCount: unread }],
      groups: groups,
      totalCount: total,
    };
  }

  function buildDailyResultView(model, options) {
    var opts = resolveResultOptions(options);
    var groups = [];
    (model && model.daily || []).forEach(function (day) {
      var papers = (day.papers || []).filter(function (paper) {
        return paperMatchesResult(paper, opts);
      });
      if (!papers.length) return;
      groups.push({
        key: day.dateKey,
        label: day.dateLabel || formatDateLabel(day.dateKey),
        papers: papers,
      });
    });
    return buildResultView(groups, opts);
  }

  function buildConferenceResultView(model, options) {
    var opts = resolveResultOptions(options);
    var groups = [];
    (model && model.conferences || []).forEach(function (conf) {
      var confKey = conferenceKey(conf);
      (conf.topics || []).forEach(function (topic) {
        var papers = (topic.papers || []).filter(function (paper) {
          return paperMatchesResult(paper, opts);
        });
        if (!papers.length) return;
        groups.push({
          key: confKey + ':' + (topic.label || 'General'),
          label: (conf.label || confKey) + ' / ' + (topic.label || 'General'),
          papers: papers,
        });
      });
    });
    return buildResultView(groups, opts);
  }

  function countUnreadPapers(papers, readMap) {
    var unread = 0;
    (papers || []).forEach(function (paper) {
      if (!paperReadStatus(paper, readMap || {})) unread += 1;
    });
    return unread;
  }

  function countPapersInView(view) {
    var total = 0;
    (view && view.groups || []).forEach(function (group) {
      total += (group.papers || []).length;
    });
    return total;
  }

  function countUnreadInView(view, readMap) {
    var unread = 0;
    (view && view.groups || []).forEach(function (group) {
      unread += countUnreadPapers(group.papers || [], readMap || {});
    });
    return unread;
  }

  function computeModelReadSummary(model, readMap) {
    var dailyPapers = flattenDailyPapers(model).map(function (record) { return record.paper; });
    var conferencePapers = flattenConferencePapers(model).map(function (record) { return record.paper; });
    var allPapers = dailyPapers.concat(conferencePapers);
    var map = readMap || {};
    return {
      total: {
        papers: allPapers.length,
        unread: countUnreadPapers(allPapers, map),
      },
      daily: {
        papers: dailyPapers.length,
        unread: countUnreadPapers(dailyPapers, map),
      },
      conference: {
        papers: conferencePapers.length,
        unread: countUnreadPapers(conferencePapers, map),
      },
    };
  }

  function findDailyRecordByHref(model, href) {
    var target = normalizeRouteHref(href);
    var records = flattenDailyPapers(model);
    for (var i = 0; i < records.length; i++) {
      if (normalizeRouteHref(records[i].paper && records[i].paper.href) === target) return records[i];
    }
    return null;
  }

  function findConferenceRecordByHref(model, href) {
    var target = normalizeRouteHref(href);
    var records = flattenConferencePapers(model);
    for (var i = 0; i < records.length; i++) {
      if (normalizeRouteHref(records[i].paper && records[i].paper.href) === target) return records[i];
    }
    return null;
  }

  function syncAxisStateToHref(href) {
    var daily = findDailyRecordByHref(state.model, href);
    if (daily) {
      state.expandedGroups.daily = true;
      state.activeDailyDate = daily.dateKey;
      state.activeDailyMonth = monthKeyFromDateKey(daily.dateKey) || state.activeDailyMonth;
      var dailyTags = paperTagLabels(daily.paper);
      if (!state.activeDailyTag || state.activeDailyTag === '__all__' || dailyTags.indexOf(state.activeDailyTag) === -1) {
        state.activeDailyTag = '__all__';
      }
      return 'daily';
    }
    var conf = findConferenceRecordByHref(state.model, href);
    if (conf) {
      state.expandedGroups.conference = true;
      state.activeConference = conf.confKey;
      var confTags = paperTagLabels(conf.paper);
      if (confTags.indexOf(state.activeConferenceTag) === -1) state.activeConferenceTag = confTags[0] || '';
      return 'conference';
    }
    return '';
  }

  function buildDailyCalendarView(model, activeDateKey, activeMonthKey, readMap) {
    var map = readMap || {};
    var byDate = {};
    var dateKeys = [];
    (model && model.daily || []).forEach(function (day) {
      var anchor = day && dailyCalendarAnchorDateKey(day.dateKey);
      if (!anchor) return;
      if (!byDate[anchor]) {
        byDate[anchor] = { records: [], papers: [] };
        dateKeys.push(anchor);
      }
      byDate[anchor].records.push(day);
      byDate[anchor].papers = byDate[anchor].papers.concat(day.papers || []);
    });
    var fallbackActive = dateKeys[0] || '';
    var requestedActive = dailyCalendarAnchorDateKey(activeDateKey);
    var active = requestedActive && byDate[requestedActive] ? requestedActive : fallbackActive;
    var month = normalizeMonthKey(activeMonthKey) || monthKeyFromDateKey(active) || monthKeyFromDateKey(fallbackActive);
    var days = [];
    var weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    if (!month) {
      return {
        monthKey: '',
        monthLabel: '',
        activeDateKey: active || '',
        prevMonthKey: '',
        nextMonthKey: '',
        weekdays: weekdays,
        days: days,
      };
    }
    for (var blank = 0; blank < monthStartOffsetMondayFirst(month); blank += 1) {
      days.push({ blank: true, key: 'blank-' + blank });
    }
    for (var dayNumber = 1; dayNumber <= daysInMonth(month); dayNumber += 1) {
      var dateKey = dateKeyFromMonthDay(month, dayNumber);
      var day = byDate[dateKey] || null;
      var papers = day ? (day.papers || []) : [];
      var unread = countUnreadPapers(papers, map);
      days.push({
        blank: false,
        dateKey: dateKey,
        label: day && day.records && day.records.length > 1
          ? formatDateLabel(dateKey) + '（含区间日报）'
          : (day && day.records && day.records[0] && day.records[0].dateLabel || formatDateLabel(dateKey)),
        dayNumber: dayNumber,
        totalCount: papers.length,
        unreadCount: unread,
        hasPapers: papers.length > 0,
        isActive: dateKey === active,
      });
    }
    return {
      monthKey: month,
      monthLabel: formatMonthLabel(month),
      activeDateKey: active || '',
      prevMonthKey: shiftMonthKey(month, -1),
      nextMonthKey: shiftMonthKey(month, 1),
      weekdays: weekdays,
      days: days,
    };
  }

  function buildDailyDateView(model, activeKey, readMap, activeMonthKey) {
    var map = readMap || {};
    var requestedMonth = normalizeMonthKey(activeMonthKey);
    var tabs = [];
    var seen = {};
    (model && model.daily || []).forEach(function (day) {
      addTab(tabs, seen, day.dateKey, day.dateLabel || formatDateLabel(day.dateKey));
      seen[day.dateKey].count = (day.papers || []).length;
      seen[day.dateKey].unreadCount = countUnreadPapers(day.papers || [], map);
    });
    var active = '';
    if (activeKey && seen[activeKey] && (!requestedMonth || monthKeyFromDateKey(activeKey) === requestedMonth)) {
      active = activeKey;
    }
    if (!active && requestedMonth) {
      for (var tabIndex = 0; tabIndex < tabs.length; tabIndex += 1) {
        if (monthKeyFromDateKey(tabs[tabIndex].key) === requestedMonth) {
          active = tabs[tabIndex].key;
          break;
        }
      }
    }
    if (!active) active = activeKey && seen[activeKey] ? activeKey : (tabs[0] && tabs[0].key) || '';
    var groups = [];
    (model && model.daily || []).forEach(function (day) {
      if (day.dateKey !== active) return;
      groups.push({
        key: day.dateKey,
        label: day.dateLabel || formatDateLabel(day.dateKey),
        papers: day.papers || [],
        unreadCount: countUnreadPapers(day.papers || [], map),
      });
    });
    return {
      activeKey: active,
      tabs: tabs,
      groups: groups,
      calendar: buildDailyCalendarView(model, active, activeMonthKey, map),
    };
  }

  function buildDailyTagView(model, activeKey, readMap) {
    var map = readMap || {};
    var records = flattenDailyPapers(model);
    var tabs = [];
    var seen = {};
    records.forEach(function (record) {
      paperTagLabels(record.paper).forEach(function (tag) {
        addTab(tabs, seen, tag, tag);
        seen[tag].count += 1;
        if (!paperReadStatus(record.paper, map)) seen[tag].unreadCount += 1;
      });
    });
    var active = activeKey && seen[activeKey] ? activeKey : (tabs[0] && tabs[0].key) || '';
    var byDate = {};
    var order = [];
    records.forEach(function (record) {
      if (paperTagLabels(record.paper).indexOf(active) === -1) return;
      if (!byDate[record.dateKey]) {
        byDate[record.dateKey] = {
          key: record.dateKey,
          label: record.dateLabel,
          papers: [],
          unreadCount: 0,
        };
        order.push(record.dateKey);
      }
      byDate[record.dateKey].papers.push(record.paper);
      if (!paperReadStatus(record.paper, map)) byDate[record.dateKey].unreadCount += 1;
    });
    return { activeKey: active, tabs: tabs, groups: order.map(function (key) { return byDate[key]; }) };
  }

  function filterDailyModelByTag(model, tagKey) {
    if (!tagKey || tagKey === '__all__') return model || { home: null, tutorial: null, daily: [], conferences: [] };
    var source = model || {};
    var filtered = {
      home: source.home || null,
      tutorial: source.tutorial || null,
      daily: [],
      conferences: source.conferences || [],
    };
    (source.daily || []).forEach(function (day) {
      var papers = (day.papers || []).filter(function (paper) {
        return paperTagLabels(paper).indexOf(tagKey) !== -1;
      });
      if (!papers.length) return;
      var nextDay = {};
      Object.keys(day || {}).forEach(function (key) {
        nextDay[key] = day[key];
      });
      nextDay.papers = papers;
      filtered.daily.push(nextDay);
    });
    return filtered;
  }

  function buildDailyCalendarTagView(model, activeDateKey, activeTagKey, readMap, activeMonthKey) {
    var map = readMap || {};
    var allKey = '__all__';
    var dateView = buildDailyDateView(model, activeDateKey, map, activeMonthKey);
    var activeDate = dailyCalendarAnchorDateKey(dateView.activeKey) || dateView.activeKey || '';
    var activeRecords = [];
    (model && model.daily || []).forEach(function (day) {
      if (day && dailyCalendarAnchorDateKey(day.dateKey) === activeDate) {
        activeRecords.push(day);
      }
    });
    var papers = [];
    activeRecords.forEach(function (day) {
      papers = papers.concat(day.papers || []);
    });
    var tabs = [];
    var seen = {};
    addTab(tabs, seen, allKey, '全部');
    seen[allKey].count = papers.length;
    seen[allKey].unreadCount = countUnreadPapers(papers, map);
    papers.forEach(function (paper) {
      paperTagLabels(paper).forEach(function (tag) {
        addTab(tabs, seen, tag, tag);
        seen[tag].count += 1;
        if (!paperReadStatus(paper, map)) seen[tag].unreadCount += 1;
      });
    });
    var activeTag = activeTagKey && seen[activeTagKey] ? activeTagKey : allKey;
    var groups = [];
    activeRecords.forEach(function (day) {
      var filtered = activeTag
        ? (day.papers || []).filter(function (paper) {
          if (activeTag === allKey) return true;
          return paperTagLabels(paper).indexOf(activeTag) !== -1;
        })
        : (day.papers || []);
      if (!filtered.length) return;
      var label = day && (day.dateLabel || formatDateLabel(day.dateKey)) || formatDateLabel(activeDate);
      if (activeTag && activeTag !== allKey) label += ' / ' + activeTag;
      groups.push({
        key: day.dateKey + ':' + (activeTag || 'all'),
        label: label,
        papers: filtered,
        unreadCount: countUnreadPapers(filtered, map),
      });
    });
    var calendarModel = filterDailyModelByTag(model, activeTag);
    return {
      activeKey: activeTag,
      activeDateKey: activeDate,
      tabs: tabs,
      groups: activeDate ? groups : [],
      calendar: buildDailyCalendarView(calendarModel, activeDate, activeMonthKey, map),
    };
  }

  function buildConferenceConfView(model, activeKey, readMap) {
    var map = readMap || {};
    var tabs = [];
    var seen = {};
    (model && model.conferences || []).forEach(function (conf) {
      var key = conferenceKey(conf);
      addTab(tabs, seen, key, conf.label || key);
      var count = 0;
      var unread = 0;
      (conf.topics || []).forEach(function (topic) {
        count += (topic.papers || []).length;
        unread += countUnreadPapers(topic.papers || [], map);
      });
      seen[key].count = count;
      seen[key].unreadCount = unread;
    });
    var active = activeKey && seen[activeKey] ? activeKey : (tabs[0] && tabs[0].key) || '';
    var groups = [];
    (model && model.conferences || []).forEach(function (conf) {
      if (conferenceKey(conf) !== active) return;
      (conf.topics || []).forEach(function (topic) {
        groups.push({
          key: active + ':' + (topic.label || 'General'),
          label: topic.label || 'General',
          papers: topic.papers || [],
          unreadCount: countUnreadPapers(topic.papers || [], map),
        });
      });
    });
    return { activeKey: active, tabs: tabs, groups: groups };
  }

  function buildConferenceTagView(model, activeKey, readMap) {
    var map = readMap || {};
    var records = flattenConferencePapers(model);
    var tabs = [];
    var seen = {};
    records.forEach(function (record) {
      paperTagLabels(record.paper).forEach(function (tag) {
        addTab(tabs, seen, tag, tag);
        seen[tag].count += 1;
        if (!paperReadStatus(record.paper, map)) seen[tag].unreadCount += 1;
      });
    });
    var active = activeKey && seen[activeKey] ? activeKey : (tabs[0] && tabs[0].key) || '';
    var groups = [];
    var byGroup = {};
    records.forEach(function (record) {
      if (paperTagLabels(record.paper).indexOf(active) === -1) return;
      var key = record.confKey + ':' + record.topicLabel;
      if (!byGroup[key]) {
        byGroup[key] = {
          key: key,
          label: record.confLabel + ' / ' + record.topicLabel,
          papers: [],
          unreadCount: 0,
        };
        groups.push(byGroup[key]);
      }
      byGroup[key].papers.push(record.paper);
      if (!paperReadStatus(record.paper, map)) byGroup[key].unreadCount += 1;
    });
    return { activeKey: active, tabs: tabs, groups: groups };
  }

  function axisSectionStateKey(group, mode, sectionKey) {
    return [group || '', mode || '', sectionKey || ''].join(':');
  }

  function normalizeSet(value) {
    if (value instanceof Set) return value;
    if (Array.isArray(value)) return new Set(value);
    return new Set();
  }
  function defaultExpandedGroups() {
    return { conference: true, daily: true };
  }
  function normalizeExpandedGroups(groups) {
    if (!groups || typeof groups !== 'object') return defaultExpandedGroups();
    return {
      conference: groups.conference !== false,
      daily: groups.daily !== false,
    };
  }
  function collapseAxisSectionsForGroup(group) {
    if (!state.expandedAxisSections) state.expandedAxisSections = new Set();
    var prefix = String(group || '') + ':';
    Array.from(state.expandedAxisSections).forEach(function (key) {
      if (String(key).indexOf(prefix) === 0) state.expandedAxisSections.delete(key);
    });
  }

  // ---------- 状态 ----------
  var state = {
    model: { home: null, tutorial: null, daily: [], conferences: [] },
    rootEl: null,
    bodyEl: null,
    searchInput: null,
    unreadCountEl: null,
    filter: 'all', // 'all' | 'unread'
    search: '',
    unreadResultPaperIds: null,
    pendingPaperHref: '',
    lastFetchAt: 0,
    expandedGroups: defaultExpandedGroups(),
    expandedAxisSections: new Set(),
    dailyViewMode: 'date',
    dailyCalendarPlacement: 'top',
    conferenceViewMode: 'conf',
    activeDailyDate: '',
    activeDailyMonth: '',
    activeDailyTag: '',
    activeConference: '',
    activeConferenceTag: '',
    sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    sidebarCollapsed: false,
    titleOverflowFrame: 0,
  };

  function loadPersistedFilter() {
    try {
      var v = window.localStorage && window.localStorage.getItem(FILTER_KEY);
      return v === 'unread' ? 'unread' : 'all';
    } catch (e) {
      return 'all';
    }
  }
  function persistFilter() {
    try {
      window.localStorage && window.localStorage.setItem(FILTER_KEY, state.filter);
    } catch (e) {}
  }
  function loadPersistedCollapse() {
    try {
      var raw = window.localStorage && window.localStorage.getItem(COLLAPSE_KEY);
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || typeof obj !== 'object') return null;
      return {
        expandedGroups: normalizeExpandedGroups(obj.groups),
        expandedAxisSections: Array.isArray(obj.sections) ? new Set(obj.sections) : new Set(),
      };
    } catch (e) {
      return null;
    }
  }
  function persistCollapse() {
    try {
      var payload = {
        groups: state.expandedGroups || defaultExpandedGroups(),
        sections: state.expandedAxisSections ? Array.from(state.expandedAxisSections) : [],
      };
      window.localStorage && window.localStorage.setItem(COLLAPSE_KEY, JSON.stringify(payload));
    } catch (e) {}
  }
  function loadPersistedSidebarWidth() {
    try {
      var raw = window.localStorage && window.localStorage.getItem(WIDTH_KEY);
      if (parseInt(raw, 10) === LEGACY_DEFAULT_SIDEBAR_WIDTH) return DEFAULT_SIDEBAR_WIDTH;
      return clampSidebarWidth(raw || DEFAULT_SIDEBAR_WIDTH);
    } catch (e) {
      return DEFAULT_SIDEBAR_WIDTH;
    }
  }
  function applySidebarWidth(width) {
    var nextWidth = clampSidebarWidth(width);
    state.sidebarWidth = nextWidth;
    if (document.documentElement && document.documentElement.style) {
      document.documentElement.style.setProperty('--dpr-sidebar-width', nextWidth + 'px');
    }
    schedulePaperTitleOverflowMarks();
    return nextWidth;
  }
  function persistSidebarWidth(width) {
    try {
      window.localStorage && window.localStorage.setItem(WIDTH_KEY, String(clampSidebarWidth(width)));
    } catch (e) {}
  }

  // ---------- 路由 / active ----------
  function currentRouteHref() {
    return normalizeRouteHref(window.location.hash || '#/');
  }
  function findActivePaper() {
    var href = currentRouteHref();
    return href || '';
  }

  // ---------- 渲染 ----------
  function ensureRoot() {
    var existing = $('#dpr-sidebar-v2');
    if (existing) {
      document.body.classList.add('dpr-sidebar-v2');
      return existing;
    }
    var aside = document.createElement('aside');
    aside.id = 'dpr-sidebar-v2';
    aside.className = 'dpr-sidebar';
    document.body.appendChild(aside);
    document.body.classList.add('dpr-sidebar-v2');
    return aside;
  }

  // docsify 主题会把渲染到 <nav> 上的 .app-nav 当成顶部导航栏，
  // 进而触发 `.app-nav li ul{position:absolute;...}` 等下拉菜单规则，
  // 会破坏侧边栏内 ul/li 的正常流式布局。挂载后剥离这两类名。
  function stripAppNav(node) {
    if (!node || !node.classList) return;
    node.classList.remove('app-nav', 'no-badge');
  }

  function renderQuickLink(className, href, icon, label) {
    return (
      '<a class="dpr-sidebar-quick ' + safeAttr(className) + '" href="' + safeAttr(href) + '">' +
      '<span class="dpr-sidebar-quick-label"><span class="dpr-sidebar-quick-icon" aria-hidden="true">' +
      safeText(icon) +
      '</span>' +
      safeText(label) +
      '</span></a>'
    );
  }

  function renderSidebarFooterControls(collapsed) {
    var collapseLabel = collapsed ? '展开侧边栏' : '收起侧边栏';
    return (
      '<div class="dpr-sidebar-footer">' +
      '  <button type="button" class="dpr-sidebar-footer-btn dpr-sidebar-collapse-btn" data-sidebar-collapse aria-label="' +
      safeAttr(collapseLabel) + '" title="' + safeAttr(collapseLabel) + '">☰</button>' +
      '  <button type="button" class="dpr-sidebar-footer-btn dpr-sidebar-settings-btn" data-sidebar-settings aria-label="打开设置" title="打开设置">⚙️</button>' +
      '</div>'
    );
  }

  function dispatchNamedEvent(name) {
    try {
      document.dispatchEvent(new CustomEvent(name));
    } catch (e) {
      try {
        var event = document.createEvent('CustomEvent');
        event.initCustomEvent(name, false, false, null);
        document.dispatchEvent(event);
      } catch (ignored) {}
    }
  }

  function openSettingsPanel() {
    dispatchNamedEvent('ensure-arxiv-ui');
    window.setTimeout(function () {
      dispatchNamedEvent('load-arxiv-subscriptions');

      var overlay = document.getElementById('arxiv-search-overlay');
      if (overlay) {
        overlay.style.display = 'flex';
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            overlay.classList.add('show');
          });
        });
      }
    }, 100);
  }

  function renderShell(root) {
    var homeHref = (state.model.home && state.model.home.href) || '#/';
    var tutorialHref = (state.model.tutorial && state.model.tutorial.href) || '#/tutorial/README';
    var homeLabel = (state.model.home && state.model.home.label) || '首页';
    var tutorialLabel = (state.model.tutorial && state.model.tutorial.label) || '使用教程';
    var filterAllActive = state.filter === 'all' ? 'is-active' : '';
    var filterUnreadActive = state.filter === 'unread' ? 'is-active' : '';
    root.innerHTML =
      '<button type="button" class="dpr-sidebar-mobile-toggle" aria-label="切换侧边栏">' +
      '<span></span><span></span><span></span></button>' +
      '<header class="dpr-sidebar-header">' +
      renderQuickLink('dpr-sidebar-quick-home', homeHref, '🏠', homeLabel) +
      renderQuickLink('dpr-sidebar-quick-tutorial', tutorialHref, '📖', tutorialLabel) +
      '</header>' +
      '<div class="dpr-sidebar-toolbar">' +
      '  <div class="dpr-sidebar-search-wrap">' +
      '    <span class="dpr-sidebar-search-icon" aria-hidden="true">🔍</span>' +
      '    <input type="search" class="dpr-sidebar-search" placeholder="搜索标题 / 摘要 / 标签" autocomplete="off" spellcheck="false" />' +
      '  </div>' +
      '  <div class="dpr-sidebar-filter" role="tablist">' +
      '    <button type="button" class="dpr-sidebar-filter-btn ' + filterAllActive + '" data-filter="all">全部</button>' +
      '    <button type="button" class="dpr-sidebar-filter-btn ' + filterUnreadActive + '" data-filter="unread">未读 <span class="dpr-sidebar-unread-count" data-count="0">0</span></button>' +
      '  </div>' +
      '</div>' +
      '<nav class="dpr-sidebar-body" aria-label="论文导航"></nav>' +
      renderSidebarFooterControls(state.sidebarCollapsed) +
      '<div class="dpr-sidebar-resizer" role="separator" aria-orientation="vertical" title="拖动调整侧栏宽度"></div>';
    state.bodyEl = $('.dpr-sidebar-body', root);
    state.searchInput = $('.dpr-sidebar-search', root);
    state.unreadCountEl = $('.dpr-sidebar-unread-count', root);
    if (state.searchInput) state.searchInput.value = state.search || '';
    // 渲染后立刻剥离 docsify 注入的 .app-nav / .no-badge（防下拉菜单定位）
    stripAppNav(state.bodyEl);
  }

  function resolveViewState(viewState) {
    var vs = viewState || state;
    return {
      expandedGroups: normalizeExpandedGroups(vs.expandedGroups),
      dailyViewMode: vs.dailyViewMode === 'tag' ? 'tag' : 'date',
      dailyCalendarPlacement: vs.dailyCalendarPlacement === 'bottom' ? 'bottom' : 'top',
      conferenceViewMode: vs.conferenceViewMode === 'tag' ? 'tag' : 'conf',
      activeDailyDate: vs.activeDailyDate || '',
      activeDailyMonth: normalizeMonthKey(vs.activeDailyMonth) || '',
      activeDailyTag: vs.activeDailyTag || '',
      activeConference: vs.activeConference || '',
      activeConferenceTag: vs.activeConferenceTag || '',
      search: String(vs.search || ''),
      filter: vs.filter === 'unread' ? 'unread' : 'all',
      readMap: vs.readMap || {},
      expandedAxisSections: normalizeSet(vs.expandedAxisSections),
      currentPaperHref: normalizeRouteHref(vs.currentPaperHref || ''),
      unreadResultPaperIds: normalizePaperIdSet(vs.unreadResultPaperIds),
    };
  }

  function buildAxisViewForMode(model, group, mode, viewState, readMap) {
    var vs = resolveViewState(viewState);
    var map = readMap || vs.readMap || {};
    var axisMode = mode || '';
    var keyword = vs.search.trim();
    var resultMode = axisMode === 'results' || !!keyword;
    var normalUnreadFilterMode = vs.filter === 'unread' && !keyword && axisMode !== 'results';
    var currentPaperHref = resolveCurrentPaperHrefForRender(model, vs);
    var resultOptions = {
      keyword: keyword,
      readMap: map,
      unreadOnly: vs.filter === 'unread',
      currentPaperId: currentPaperHref ? paperIdFromHref(currentPaperHref) : '',
      unreadResultPaperIds: vs.unreadResultPaperIds,
    };
    var viewModel = normalUnreadFilterMode ? filterModelForPaperResults(model, resultOptions) : model;
    if (group === 'conference') {
      if (resultMode) return buildConferenceResultView(model, resultOptions);
      return axisMode === 'tag'
        ? buildConferenceTagView(viewModel, vs.activeConferenceTag, map)
        : buildConferenceConfView(viewModel, vs.activeConference, map);
    }
    if (resultMode) return buildDailyResultView(model, resultOptions);
    return buildDailyCalendarTagView(viewModel, vs.activeDailyDate, vs.activeDailyTag, map, vs.activeDailyMonth);
  }

  function renderBodyHtml(model, viewState) {
    var html = [];
    var vs = resolveViewState(viewState);
    var unreadOnly = vs.filter === 'unread';
    var keyword = vs.search.trim();
    var resultMode = !!keyword;
    var normalUnreadFilterMode = unreadOnly && !keyword;
    var currentPaperHref = resolveCurrentPaperHrefForRender(model, vs);
    var resultOptions = {
      keyword: keyword,
      readMap: vs.readMap,
      unreadOnly: unreadOnly,
      currentPaperId: currentPaperHref ? paperIdFromHref(currentPaperHref) : '',
      unreadResultPaperIds: vs.unreadResultPaperIds,
    };
    var viewModel = normalUnreadFilterMode ? filterModelForPaperResults(model, resultOptions) : model;
    var renderedGroups = 0;
    if (viewModel && viewModel.conferences && viewModel.conferences.length) {
      var conferenceView = resultMode
        ? buildConferenceResultView(model, resultOptions)
        : (vs.conferenceViewMode === 'tag'
          ? buildConferenceTagView(viewModel, vs.activeConferenceTag, vs.readMap)
          : buildConferenceConfView(viewModel, vs.activeConference, vs.readMap));
      var conferenceTotal = countPapersInView(conferenceView);
      var conferenceUnread = countUnreadInView(conferenceView, vs.readMap);
      if (!resultMode || conferenceTotal > 0) {
        renderedGroups += 1;
        html.push(renderAxisGroup({
          group: 'conference',
          title: '会议论文',
          icon: '🏛️',
          mode: vs.conferenceViewMode,
          expanded: vs.expandedGroups.conference !== false,
          view: conferenceView,
          toggleLabel: vs.conferenceViewMode === 'tag' ? '按会议' : '按标签',
          totalCount: conferenceTotal,
          unreadCount: conferenceUnread,
          expandedAxisSections: vs.expandedAxisSections,
          readMap: vs.readMap,
          currentPaperId: resultOptions.currentPaperId,
        }));
      }
    }
    if (viewModel && viewModel.daily && viewModel.daily.length) {
      var dailyView = resultMode
        ? buildDailyResultView(model, resultOptions)
        : buildDailyCalendarTagView(viewModel, vs.activeDailyDate, vs.activeDailyTag, vs.readMap, vs.activeDailyMonth);
      var dailyTotal = countPapersInView(dailyView);
      var dailyUnread = countUnreadInView(dailyView, vs.readMap);
      if (!resultMode || dailyTotal > 0) {
        renderedGroups += 1;
        html.push(renderAxisGroup({
          group: 'daily',
          title: '日报',
          icon: '📅',
          mode: resultMode ? vs.dailyViewMode : 'tag',
          dailyCalendarPlacement: vs.dailyCalendarPlacement,
          expanded: vs.expandedGroups.daily !== false,
          view: dailyView,
          toggleLabel: vs.dailyCalendarPlacement === 'top' ? '标签上置' : '日历上置',
          totalCount: dailyTotal,
          unreadCount: dailyUnread,
          expandedAxisSections: vs.expandedAxisSections,
          readMap: vs.readMap,
          currentPaperId: resultOptions.currentPaperId,
        }));
      }
    }
    if ((resultMode || normalUnreadFilterMode) && renderedGroups === 0) {
      html.push('<div class="dpr-sidebar-empty">没有匹配的论文</div>');
    }
    return html.join('');
  }

  function renderBody() {
    var readMap = ReadState.getAll();
    var viewState = {
      expandedGroups: state.expandedGroups,
      dailyViewMode: state.dailyViewMode,
      dailyCalendarPlacement: state.dailyCalendarPlacement,
      conferenceViewMode: state.conferenceViewMode,
      activeDailyDate: state.activeDailyDate,
      activeDailyMonth: state.activeDailyMonth,
      activeDailyTag: state.activeDailyTag,
      activeConference: state.activeConference,
      activeConferenceTag: state.activeConferenceTag,
      search: state.search,
      filter: state.filter,
      readMap: readMap,
      unreadResultPaperIds: state.filter === 'unread' ? ensureUnreadSessionPaperIds(state.model, readMap) : state.unreadResultPaperIds,
      expandedAxisSections: state.expandedAxisSections,
    };
    state.bodyEl.innerHTML = renderBodyHtml(state.model, viewState);
    schedulePaperTitleOverflowMarks(state.bodyEl);
    syncResolvedAxisState();
  }

  function updatePaperTitleOverflowMarks(root) {
    var scope = root || state.bodyEl;
    if (!scope || !scope.querySelectorAll) return;
    var papers = scope.matches && scope.matches('.dpr-sidebar-paper')
      ? [scope]
      : $$('.dpr-sidebar-paper', scope);
    papers.forEach(function (li) {
      var title = $('.dpr-sidebar-paper-title', li);
      if (!title || !li.classList) return;
      var overflow = (title.scrollWidth || 0) > ((title.clientWidth || 0) + 1);
      li.classList.toggle('is-title-overflowing', overflow);
    });
  }

  function schedulePaperTitleOverflowMarks(root) {
    var scope = root || state.bodyEl;
    if (!scope) return;
    if (!window.requestAnimationFrame) {
      updatePaperTitleOverflowMarks(scope);
      return;
    }
    if (state.titleOverflowFrame) {
      window.cancelAnimationFrame && window.cancelAnimationFrame(state.titleOverflowFrame);
    }
    state.titleOverflowFrame = window.requestAnimationFrame(function () {
      state.titleOverflowFrame = 0;
      updatePaperTitleOverflowMarks(scope);
    });
  }

  function updateAxisTabUnreadMarks(readMap) {
    if (!state.bodyEl) return;
    $$('.dpr-sidebar-axis-row', state.bodyEl).forEach(function (row) {
      var group = row.getAttribute('data-axis-group') || '';
      var mode = row.getAttribute('data-axis-mode') || '';
      var view = buildAxisViewForMode(state.model, group, mode, state, readMap || {});
      var tabsByKey = {};
      (view.tabs || []).forEach(function (tab) {
        tabsByKey[tab.key] = tab;
      });
      $$('.dpr-sidebar-axis-tab', row).forEach(function (tabEl) {
        var key = tabEl.getAttribute('data-axis-key') || '';
        var tab = tabsByKey[key];
        if (!tab) return;
        var unread = typeof tab.unreadCount === 'number' ? tab.unreadCount : tab.count;
        var total = typeof tab.count === 'number' ? tab.count : 0;
        var unreadEl = $('.dpr-sidebar-axis-tab-unread', tabEl);
        var totalEl = $('.dpr-sidebar-axis-tab-total', tabEl);
        tabEl.setAttribute('data-unread', unread > 0 ? '1' : '0');
        if (unreadEl) unreadEl.textContent = String(unread);
        if (totalEl) totalEl.textContent = String(total);
      });
    });
  }

  function updateDailyCalendarUnreadMarks(readMap) {
    if (!state.bodyEl) return;
    var map = readMap || {};
    var calendarModel = modelForUnreadNormalFilter(state.model, map);
    var view = buildDailyCalendarTagView(calendarModel, state.activeDailyDate, state.activeDailyTag, map, state.activeDailyMonth);
    var daysByKey = {};
    (view.calendar && view.calendar.days || []).forEach(function (day) {
      if (day && day.dateKey) daysByKey[day.dateKey] = day;
    });
    $$('.dpr-sidebar-calendar-day[data-calendar-date]', state.bodyEl).forEach(function (dayEl) {
      var key = dayEl.getAttribute('data-calendar-date') || '';
      var day = daysByKey[key];
      if (!day) return;
      var unread = typeof day.unreadCount === 'number' ? day.unreadCount : 0;
      var total = typeof day.totalCount === 'number' ? day.totalCount : 0;
      dayEl.setAttribute('data-unread', unread > 0 ? '1' : '0');
      dayEl.classList.toggle('has-unread', unread > 0);
      dayEl.classList.toggle('is-active', key === view.activeDateKey);
      var unreadEl = $('.dpr-sidebar-calendar-day-unread', dayEl);
      var totalEl = $('.dpr-sidebar-calendar-day-total', dayEl);
      if (unreadEl) unreadEl.textContent = String(unread);
      if (totalEl) totalEl.textContent = String(total);
    });
  }

  function resolveDailyAxisSectionStateKey(model, viewState, readMap) {
    var vs = resolveViewState(viewState || state);
    var map = readMap || vs.readMap || {};
    var axisModel = modelForUnreadNormalFilter(model, map);
    var dailyView = buildDailyCalendarTagView(axisModel, vs.activeDailyDate, vs.activeDailyTag, map, vs.activeDailyMonth);
    var preferredDateKey = String(vs.activeDailyDate || '');
    var group = null;
    (dailyView.groups || []).some(function (item) {
      if (preferredDateKey && String(item.key || '').indexOf(preferredDateKey + ':') === 0) {
        group = item;
        return true;
      }
      return false;
    });
    if (!group) group = dailyView.groups && dailyView.groups[0];
    return group ? axisSectionStateKey('daily', 'tag', group.key) : '';
  }

  function expandCurrentDailyAxisSection(readMap) {
    if (!state.expandedAxisSections) state.expandedAxisSections = new Set();
    collapseAxisSectionsForGroup('daily');
    var sectionKey = resolveDailyAxisSectionStateKey(state.model, state, readMap || ReadState.getAll());
    if (sectionKey) state.expandedAxisSections.add(sectionKey);
  }

  function syncResolvedAxisState() {
    var readMap = ReadState.getAll();
    var axisModel = modelForUnreadNormalFilter(state.model, readMap);
    var dailyView = buildDailyCalendarTagView(axisModel, state.activeDailyDate, state.activeDailyTag, readMap, state.activeDailyMonth);
    var confView = buildConferenceConfView(axisModel, state.activeConference, readMap);
    var confTag = buildConferenceTagView(axisModel, state.activeConferenceTag, readMap);
    state.activeDailyDate = dailyView.activeDateKey || '';
    state.activeDailyMonth = dailyView.calendar && dailyView.calendar.monthKey || monthKeyFromDateKey(dailyView.activeDateKey) || '';
    state.activeDailyTag = dailyView.activeKey;
    state.activeConference = confView.activeKey;
    state.activeConferenceTag = confTag.activeKey;
  }

  function renderAxisGroup(opts) {
    var html = [];
    var groupClass = opts.group === 'conference' ? 'dpr-sidebar-group-conference' : 'dpr-sidebar-group-daily';
    var expandedClass = opts.expanded ? ' is-expanded' : '';
    var resultClass = opts.view && opts.view.resultMode ? ' is-result-mode' : '';
    var axisMode = opts.view && opts.view.resultMode ? 'results' : opts.mode;
    var isDailyNormal = opts.group === 'daily' && !(opts.view && opts.view.resultMode);
    var hasHeaderAxisToggle = !(opts.view && opts.view.resultMode) && (opts.group === 'daily' || opts.group === 'conference');
    var calendarPlacement = opts.dailyCalendarPlacement === 'bottom' ? 'bottom' : 'top';
    var totalCount = typeof opts.totalCount === 'number' ? opts.totalCount : countPapersInView(opts.view);
    var unreadCount = typeof opts.unreadCount === 'number' ? opts.unreadCount : 0;
    html.push('<section class="dpr-sidebar-group dpr-sidebar-panel ' + groupClass + expandedClass + resultClass + '" data-panel="' + safeAttr(opts.group) + '">');
    if (hasHeaderAxisToggle) {
      html.push('  <div class="dpr-sidebar-panel-header dpr-sidebar-panel-header-has-axis dpr-sidebar-panel-header-' + safeAttr(opts.group) + '">');
      html.push('    <button type="button" class="dpr-sidebar-panel-toggle" data-panel-toggle="' + safeAttr(opts.group) + '" aria-expanded="' + (opts.expanded ? 'true' : 'false') + '">');
      html.push('      <span class="dpr-sidebar-day-arrow" aria-hidden="true">▸</span>');
      html.push('      <span class="dpr-sidebar-panel-title">' + safeText(opts.icon + ' ' + opts.title) + '</span>');
      html.push('    </button>');
      html.push('    <button type="button" class="dpr-sidebar-axis-toggle dpr-sidebar-header-axis-toggle" data-axis-toggle="' + safeAttr(opts.group) + '" title="' + safeAttr(opts.toggleLabel) + '">⇄</button>');
      html.push('    <span class="dpr-sidebar-day-counts"><span class="dpr-sidebar-day-unread">' + unreadCount + '</span>/<span class="dpr-sidebar-day-total">' + totalCount + '</span></span>');
      html.push('  </div>');
    } else {
      html.push('  <button type="button" class="dpr-sidebar-panel-header" data-panel-toggle="' + safeAttr(opts.group) + '" aria-expanded="' + (opts.expanded ? 'true' : 'false') + '">');
      html.push('    <span class="dpr-sidebar-day-arrow" aria-hidden="true">▸</span>');
      html.push('    <span class="dpr-sidebar-panel-title">' + safeText(opts.icon + ' ' + opts.title) + '</span>');
      html.push('    <span class="dpr-sidebar-day-counts"><span class="dpr-sidebar-day-unread">' + unreadCount + '</span>/<span class="dpr-sidebar-day-total">' + totalCount + '</span></span>');
      html.push('  </button>');
    }
    html.push('  <div class="dpr-sidebar-panel-content">');
    if (isDailyNormal) {
      if (calendarPlacement === 'top') {
        html.push(renderDailyCalendar(opts.view && opts.view.calendar, calendarPlacement));
        html.push(renderAxisTabs('daily', 'tag', opts.view, opts.toggleLabel, { hideToggle: true, rowClass: 'dpr-sidebar-daily-tabs-row' }));
      } else {
        html.push(renderAxisTabs('daily', 'tag', opts.view, opts.toggleLabel, { hideToggle: true, rowClass: 'dpr-sidebar-daily-tabs-row' }));
        html.push(renderDailyCalendar(opts.view && opts.view.calendar, calendarPlacement));
      }
    } else if (hasHeaderAxisToggle) {
      html.push(renderAxisTabs(opts.group, opts.mode, opts.view, opts.toggleLabel, { hideToggle: true }));
    } else {
      html.push(renderAxisTabs(opts.group, opts.mode, opts.view, opts.toggleLabel));
    }
    html.push(renderAxisContent(opts.group, axisMode, opts.view, opts.expandedAxisSections, opts.readMap, opts.currentPaperId));
    html.push('  </div>');
    html.push('</section>');
    return html.join('');
  }

  function renderAxisTabs(group, mode, view, toggleLabel, options) {
    var opts = options || {};
    var html = [];
    var resultMode = !!(view && view.resultMode);
    var axisMode = resultMode ? 'results' : mode;
    var disabled = resultMode ? ' disabled aria-disabled="true"' : '';
    var rowClass = resultMode ? ' dpr-sidebar-axis-row-results' : '';
    if (opts.rowClass) rowClass += ' ' + opts.rowClass;
    html.push('<div class="dpr-sidebar-axis-row' + rowClass + '" data-axis-group="' + safeAttr(group) + '" data-axis-mode="' + safeAttr(axisMode) + '">');
    if (!opts.hideToggle) {
      html.push('  <button type="button" class="dpr-sidebar-axis-toggle" data-axis-toggle="' + safeAttr(group) + '" title="' + safeAttr(toggleLabel) + '"' + disabled + '>⇄</button>');
    }
    html.push('  <div class="dpr-sidebar-axis-tabs" role="tablist">');
    (view.tabs || []).forEach(function (tab) {
      var active = tab.key === view.activeKey ? ' is-active' : '';
      var unread = typeof tab.unreadCount === 'number' ? tab.unreadCount : tab.count;
      var unreadFlag = unread > 0 ? '1' : '0';
      html.push('    <button type="button" class="dpr-sidebar-axis-tab' + active + '" data-axis-tab="' + safeAttr(group) + '" data-axis-key="' + safeAttr(tab.key) + '" data-unread="' + unreadFlag + '" title="' + safeAttr(tab.label) + '">');
      html.push('      <span class="dpr-sidebar-axis-tab-label">' + safeText(tab.label) + '</span>');
      html.push('      <span class="dpr-sidebar-axis-tab-count"><span class="dpr-sidebar-axis-tab-unread">' + safeText(unread) + '</span>/<span class="dpr-sidebar-axis-tab-total">' + safeText(tab.count) + '</span></span>');
      html.push('    </button>');
    });
    html.push('  </div>');
    html.push('</div>');
    return html.join('');
  }

  function renderDailyCalendar(calendar, placement) {
    var view = calendar || {};
    var html = [];
    html.push('<div class="dpr-sidebar-calendar is-' + safeAttr(placement || 'top') + '" data-daily-calendar data-calendar-month="' + safeAttr(view.monthKey || '') + '">');
    html.push('  <div class="dpr-sidebar-calendar-header">');
    html.push('    <button type="button" class="dpr-sidebar-calendar-nav" data-calendar-nav="' + safeAttr(view.prevMonthKey || '') + '" aria-label="上个月">‹</button>');
    html.push('    <span class="dpr-sidebar-calendar-title">' + safeText(view.monthLabel || '') + '</span>');
    html.push('    <button type="button" class="dpr-sidebar-calendar-nav" data-calendar-nav="' + safeAttr(view.nextMonthKey || '') + '" aria-label="下个月">›</button>');
    html.push('  </div>');
    html.push('  <div class="dpr-sidebar-calendar-weekdays" aria-hidden="true">');
    (view.weekdays || []).forEach(function (label) {
      html.push('    <span>' + safeText(label) + '</span>');
    });
    html.push('  </div>');
    html.push('  <div class="dpr-sidebar-calendar-grid">');
    (view.days || []).forEach(function (day) {
      if (!day || day.blank) {
        html.push('    <span class="dpr-sidebar-calendar-blank" aria-hidden="true"></span>');
        return;
      }
      var activeClass = day.isActive ? ' is-active' : '';
      var paperClass = day.hasPapers ? ' has-papers' : ' is-empty';
      var unreadClass = day.unreadCount > 0 ? ' has-unread' : '';
      var disabled = day.hasPapers ? '' : ' disabled aria-disabled="true"';
      var unreadFlag = day.unreadCount > 0 ? '1' : '0';
      html.push('    <button type="button" class="dpr-sidebar-calendar-day' + activeClass + paperClass + unreadClass + '" data-calendar-date="' + safeAttr(day.dateKey) + '" data-unread="' + unreadFlag + '" title="' + safeAttr(day.label) + '"' + disabled + '>');
      html.push('      <span class="dpr-sidebar-calendar-day-number">' + safeText(day.dayNumber) + '</span>');
      html.push('      <span class="dpr-sidebar-calendar-day-counts"><span class="dpr-sidebar-calendar-day-total">' + safeText(day.totalCount) + '</span><span class="dpr-sidebar-calendar-day-unread">' + safeText(day.unreadCount) + '</span></span>');
      html.push('    </button>');
    });
    html.push('  </div>');
    html.push('</div>');
    return html.join('');
  }

  function renderAxisContent(group, mode, view, expandedAxisSections, readMap, currentPaperId) {
    var html = [];
    var expanded = normalizeSet(expandedAxisSections);
    html.push('<div class="dpr-sidebar-axis-content" data-axis-content="' + safeAttr(group) + '">');
    (view.groups || []).forEach(function (item) {
      var sectionClass = group === 'conference'
        ? ' dpr-sidebar-axis-section-conference'
        : ' dpr-sidebar-axis-section-daily';
      var stateKey = axisSectionStateKey(group, mode, item.key);
      var isExpanded = expanded.has(stateKey);
      var expandedClass = isExpanded ? ' is-expanded' : '';
      var activeSectionClass = (currentPaperId && (item.papers || []).some(function (paper) {
        return paperIdentity(paper) === currentPaperId;
      })) ? ' has-active-paper' : '';
      var unread = typeof item.unreadCount === 'number' ? item.unreadCount : (item.papers || []).length;
      var unreadFlag = unread > 0 ? '1' : '0';
      html.push('<section class="dpr-sidebar-axis-section' + sectionClass + expandedClass + activeSectionClass + '" data-axis-section="' + safeAttr(item.key) + '" data-axis-section-key="' + safeAttr(stateKey) + '">');
      html.push('  <button type="button" class="dpr-sidebar-axis-section-header" data-axis-section-toggle="' + safeAttr(stateKey) + '" aria-expanded="' + (isExpanded ? 'true' : 'false') + '" data-unread="' + unreadFlag + '">');
      html.push('    <span class="dpr-sidebar-day-arrow" aria-hidden="true">▸</span>');
      html.push('    <span class="dpr-sidebar-axis-section-label">' + safeText(item.label) + ' <span class="dpr-sidebar-day-counts"><span class="dpr-sidebar-day-unread">' + safeText(unread) + '</span>/<span class="dpr-sidebar-day-total">' + safeText((item.papers || []).length) + '</span></span></span>');
      html.push('  </button>');
      html.push('  <ul class="dpr-sidebar-axis-papers">');
      (item.papers || []).forEach(function (paper) {
        html.push(renderPaper(paper, readMap, currentPaperId));
      });
      html.push('  </ul>');
      html.push('</section>');
    });
    html.push('</div>');
    return html.join('');
  }

  function renderPaper(p, readMap, currentPaperId) {
    var sectionClass = p.section ? ' dpr-sidebar-paper-' + p.section : '';
    var paperId = p.id || '';
    var status = paperReadStatus(p, readMap || {});
    var activeClass = currentPaperId && paperIdentity(p) === currentPaperId ? ' is-active' : '';
    var dataAttrs = [
      'data-paper-id="' + safeAttr(paperId) + '"',
      'data-href="' + safeAttr(p.href) + '"',
      'data-section="' + safeAttr(p.section || '') + '"',
      'data-search="' + safeAttr(paperSearchText(p)) + '"',
      'data-read="' + (status ? '1' : '0') + '"',
      'data-read-status="' + safeAttr(status) + '"',
    ].join(' ');
    var stars = starHtmlFromScore(p.score);
    var tagBits = tagsHtml(p.tags);
    var evidence = p.evidence
      ? '<div class="dpr-sidebar-paper-evidence">' + safeText(p.evidence) + '</div>'
      : '';
    var actions = MARK_STATUSES.map(function (item) {
      return (
        '<button type="button" class="dpr-sidebar-paper-status-btn dpr-sidebar-paper-status-' + safeAttr(item.key) + (item.key === status ? ' is-active' : '') + '" ' +
        'data-paper-id="' + safeAttr(paperId) + '" data-paper-status="' + safeAttr(item.key) + '" title="' + safeAttr(item.title) + '">' +
        safeText(item.label) +
        '</button>'
      );
    }).join('');
    return (
      '<li class="dpr-sidebar-paper' + sectionClass + activeClass + '" ' + dataAttrs + '>' +
      '  <div class="dpr-sidebar-paper-main">' +
      '    <a class="dpr-sidebar-paper-link" href="' + safeAttr(p.href) + '">' +
      '      <span class="dpr-sidebar-paper-title">' + safeText(p.title) + '</span>' +
      evidence +
      '      <span class="dpr-sidebar-paper-meta">' + stars + (tagBits ? '<span class="dpr-sidebar-paper-tags">' + tagBits + '</span>' : '') + '</span>' +
      '    </a>' +
      '    <div class="dpr-sidebar-paper-actions" aria-label="论文标记">' + actions + '</div>' +
      '  </div>' +
      '</li>'
    );
  }

  // ---------- 状态同步 ----------
  function updateReadStateMarks() {
    if (!state.bodyEl) return;
    var readMap = ReadState.getAll();
    var summary = computeModelReadSummary(state.model, readMap);
    $$('.dpr-sidebar-paper', state.bodyEl).forEach(function (li) {
      var id = li.getAttribute('data-paper-id');
      var status = normalizeReadStatus(id && readMap[id]);
      li.setAttribute('data-read', status ? '1' : '0');
      li.setAttribute('data-read-status', status);
      $$('.dpr-sidebar-paper-status-btn', li).forEach(function (btn) {
        btn.classList.toggle('is-active', btn.getAttribute('data-paper-status') === status);
      });
    });
    $$('.dpr-sidebar-panel', state.bodyEl).forEach(function (panel) {
      var header = $('.dpr-sidebar-panel-header', panel);
      var totalEl = header && $('.dpr-sidebar-day-total', header);
      var unreadEl = header && $('.dpr-sidebar-day-unread', header);
      var papers = $$('.dpr-sidebar-paper', panel);
      var unread = 0;
      papers.forEach(function (li) {
        if (li.getAttribute('data-read') === '0') unread += 1;
      });
      var counts = { papers: papers.length, unread: unread };
      if (totalEl) totalEl.textContent = String(counts.papers);
      if (unreadEl) unreadEl.textContent = String(counts.unread);
      if (counts.unread === 0) {
        panel.classList.add('is-all-read');
      } else {
        panel.classList.remove('is-all-read');
      }
    });
    // 竖向分组的计数只描述当前结果/当前轴切片。
    $$('.dpr-sidebar-axis-section', state.bodyEl).forEach(function (group) {
      var papers = $$('.dpr-sidebar-paper', group);
      var unread = 0;
      papers.forEach(function (li) {
        if (li.getAttribute('data-read') === '0') unread += 1;
      });
      var totalEl = $('.dpr-sidebar-day-total', group);
      var unreadEl = $('.dpr-sidebar-day-unread', group);
      var header = $('.dpr-sidebar-axis-section-header', group);
      if (totalEl) totalEl.textContent = String(papers.length);
      if (unreadEl) unreadEl.textContent = String(unread);
      if (header) header.setAttribute('data-unread', unread > 0 ? '1' : '0');
      if (unread === 0) {
        group.classList.add('is-all-read');
      } else {
        group.classList.remove('is-all-read');
      }
    });
    updateAxisTabUnreadMarks(readMap);
    updateDailyCalendarUnreadMarks(readMap);
    if (state.unreadCountEl) {
      state.unreadCountEl.textContent = String(summary.total.unread);
      state.unreadCountEl.setAttribute('data-count', String(summary.total.unread));
    }
  }

  function applyFilterAndSearch() {
    if (!state.rootEl) return;
    state.rootEl.classList.toggle('is-filter-unread', state.filter === 'unread');
  }

  function syncActive(options) {
    var opts = options || {};
    var shouldCenter = opts.center !== false;
    var shouldAutoMark = opts.autoMark !== false;
    if (!state.bodyEl) return;
    stripAppNav(state.bodyEl); // docsify 可能再次注入 .app-nav（每次路由）
    var href = findActivePaper();
    if (state.pendingPaperHref && normalizeRouteHref(href) === state.pendingPaperHref) {
      state.pendingPaperHref = '';
    }
    $$('.dpr-sidebar-paper.is-active', state.bodyEl).forEach(function (li) {
      li.classList.remove('is-active');
    });
    $$('.dpr-sidebar-axis-section.has-active-paper', state.bodyEl).forEach(function (section) {
      section.classList.remove('has-active-paper');
    });
    if (!href) return;
    var li = state.bodyEl.querySelector(
      '.dpr-sidebar-paper[data-href="' + cssEscape(href) + '"]'
    );
    if (!li && syncAxisStateToHref(href)) {
      renderBody();
      updateReadStateMarks();
      applyFilterAndSearch();
      li = state.bodyEl.querySelector(
        '.dpr-sidebar-paper[data-href="' + cssEscape(href) + '"]'
      );
    }
    if (!li) return;
    li.classList.add('is-active');
    var activeSection = li.closest && li.closest('.dpr-sidebar-axis-section');
    if (activeSection) activeSection.classList.add('has-active-paper');
    var currentPaperHref = findCurrentPaperHrefFromModel(state.model, href);
    var currentPaperId = currentPaperHref ? paperIdFromHref(currentPaperHref) : '';
    var readMap = ReadState.getAll();
    if (shouldAutoMark && currentPaperId && shouldAutoMarkRead(readMap[currentPaperId])) {
      markPaperStatus(currentPaperId, 'read', { notify: false });
      rerenderSidebarBody({ syncActive: true, centerActive: shouldCenter, autoMark: false });
      return;
    }
    // 居中滚动
    if (shouldCenter) centerOn(li);
  }

  function cssEscape(s) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(s);
    return String(s).replace(/["\\#.]/g, '\\$&');
  }

  function centerOn(li) {
    if (!state.bodyEl || !li) return;
    var bodyRect = state.bodyEl.getBoundingClientRect();
    var liRect = li.getBoundingClientRect();
    var current = state.bodyEl.scrollTop;
    var targetTop = current + (liRect.top - bodyRect.top) - bodyRect.height / 2 + liRect.height / 2;
    state.bodyEl.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
  }

  function scrollPanelIntoView(panelKey) {
    if (!state.bodyEl || !panelKey) return;
    var panel = state.bodyEl.querySelector(
      '.dpr-sidebar-panel[data-panel="' + cssEscape(panelKey) + '"]'
    );
    if (!panel || !panel.getBoundingClientRect) return;
    var bodyRect = state.bodyEl.getBoundingClientRect();
    var panelRect = panel.getBoundingClientRect();
    if (panelRect.top < bodyRect.top || panelRect.top > bodyRect.bottom - 40) {
      var target = state.bodyEl.scrollTop + (panelRect.top - bodyRect.top) - 6;
      state.bodyEl.scrollTop = Math.max(0, target);
    }
  }

  function dispatchSidebarUpdated() {
    if (!document || typeof document.dispatchEvent !== 'function') return;
    var detail = {
      paperHrefs: collectPaperHrefsFromModel(state.model),
      reportHrefs: collectReportHrefsFromModel(state.model),
      currentPaperHref: findCurrentPaperHrefFromModel(state.model),
      currentReportHref: findCurrentReportHrefFromModel(state.model),
    };
    try {
      document.dispatchEvent(new CustomEvent('dpr-sidebar-updated', { detail: detail }));
    } catch (e) {
      try {
        var event = document.createEvent('CustomEvent');
        event.initCustomEvent('dpr-sidebar-updated', false, false, detail);
        document.dispatchEvent(event);
      } catch (ignored) {}
    }
  }

  function rerenderSidebarBody(options) {
    if (!state.bodyEl) return;
    var opts = options || {};
    var previousScrollTop = state.bodyEl.scrollTop || 0;
    renderBody();
    updateReadStateMarks();
    applyFilterAndSearch();
    if (opts.syncActive) {
      syncActive({
        center: opts.centerActive !== false,
        autoMark: opts.autoMark !== false,
      });
    }
    if (opts.preserveScroll) {
      state.bodyEl.scrollTop = previousScrollTop;
    } else if (opts.scrollPanel) {
      scrollPanelIntoView(opts.scrollPanel);
    }
    if (opts.dispatchUpdated !== false) {
      dispatchSidebarUpdated();
    }
  }

  function toggleMobile(open) {
    var root = state.rootEl || $('#dpr-sidebar-v2');
    if (!root || !root.classList) return false;
    if (typeof open === 'boolean') {
      root.classList.toggle('is-open', open);
    } else {
      root.classList.toggle('is-open');
    }
    return root.classList.contains('is-open');
  }

  function isOverlaySidebarViewport() {
    return !!(window.matchMedia && window.matchMedia(OVERLAY_SIDEBAR_QUERY).matches);
  }

  function updateCollapseButtonLabel(root) {
    var btn = root && $('.dpr-sidebar-collapse-btn', root);
    if (!btn) return;
    var label = state.sidebarCollapsed ? '展开侧边栏' : '收起侧边栏';
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
  }

  function applySidebarCollapsed(collapsed) {
    var root = state.rootEl || $('#dpr-sidebar-v2');
    state.sidebarCollapsed = !!collapsed;
    if (root && root.classList) {
      root.classList.toggle('is-collapsed', state.sidebarCollapsed);
    }
    if (document.body && document.body.classList) {
      document.body.classList.toggle('dpr-sidebar-v2-collapsed', state.sidebarCollapsed);
    }
    updateCollapseButtonLabel(root);
    return state.sidebarCollapsed;
  }

  function toggleSidebarCollapsed() {
    return applySidebarCollapsed(!state.sidebarCollapsed);
  }

  function syncResponsiveSidebarMode() {
    var root = state.rootEl || $('#dpr-sidebar-v2');
    if (!root || !root.classList) return state.sidebarCollapsed;
    if (isOverlaySidebarViewport()) {
      state.sidebarCollapsed = false;
      root.classList.remove('is-collapsed');
      if (document.body && document.body.classList) {
        document.body.classList.remove('dpr-sidebar-v2-collapsed');
      }
      updateCollapseButtonLabel(root);
      return false;
    }
    root.classList.remove('is-open');
    if (document.body && document.body.classList) {
      document.body.classList.toggle('dpr-sidebar-v2-collapsed', state.sidebarCollapsed);
    }
    root.classList.toggle('is-collapsed', state.sidebarCollapsed);
    updateCollapseButtonLabel(root);
    return state.sidebarCollapsed;
  }

  // ---------- 事件 ----------
  function bindEvents(root) {
    // 工具栏：筛选
    root.addEventListener('click', function (e) {
      var fbtn = e.target.closest('.dpr-sidebar-filter-btn');
      if (fbtn) {
        var f = fbtn.getAttribute('data-filter') || 'all';
        state.filter = f === 'unread' ? 'unread' : 'all';
        $$('.dpr-sidebar-filter-btn', root).forEach(function (b) {
          b.classList.toggle('is-active', b.getAttribute('data-filter') === state.filter);
        });
        persistFilter();
        rerenderSidebarBody({ syncActive: false });
        return;
      }
      // 移动端切换
      var mobile = e.target.closest('.dpr-sidebar-mobile-toggle');
      if (mobile) {
        root.classList.toggle('is-open');
        return;
      }
      var collapseBtn = e.target.closest('.dpr-sidebar-collapse-btn');
      if (collapseBtn) {
        e.preventDefault();
        if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
          toggleMobile(false);
        } else {
          toggleSidebarCollapsed();
        }
        return;
      }
      var settingsBtn = e.target.closest('.dpr-sidebar-settings-btn');
      if (settingsBtn) {
        e.preventDefault();
        openSettingsPanel();
        return;
      }
      var axisToggle = e.target.closest('.dpr-sidebar-axis-toggle');
      if (axisToggle) {
        var axisGroup = axisToggle.getAttribute('data-axis-toggle');
        if (axisGroup === 'daily') {
          state.dailyViewMode = 'date';
          state.dailyCalendarPlacement = state.dailyCalendarPlacement === 'bottom' ? 'top' : 'bottom';
        } else if (axisGroup === 'conference') {
          state.conferenceViewMode = state.conferenceViewMode === 'tag' ? 'conf' : 'tag';
        }
        collapseAxisSectionsForGroup(axisGroup);
        persistCollapse();
        rerenderSidebarBody(rerenderOptionsForAxisControlClick());
        return;
      }
      var panelHeader = e.target.closest('[data-panel-toggle]');
      if (panelHeader) {
        var panel = panelHeader.getAttribute('data-panel-toggle');
        if (!state.expandedGroups) state.expandedGroups = defaultExpandedGroups();
        state.expandedGroups[panel] = !state.expandedGroups[panel];
        persistCollapse();
        rerenderSidebarBody(rerenderOptionsForPanelToggle(panel));
        return;
      }
      var calendarNav = e.target.closest('.dpr-sidebar-calendar-nav');
      if (calendarNav) {
        var navMonth = normalizeMonthKey(calendarNav.getAttribute('data-calendar-nav') || '');
        if (navMonth) {
          state.dailyViewMode = 'date';
          state.activeDailyMonth = navMonth;
          rerenderSidebarBody(rerenderOptionsForAxisControlClick());
        }
        return;
      }
      var calendarDay = e.target.closest('.dpr-sidebar-calendar-day[data-calendar-date]');
      if (calendarDay) {
        if (calendarDay.disabled || calendarDay.getAttribute('aria-disabled') === 'true') return;
        var calendarDate = calendarDay.getAttribute('data-calendar-date') || '';
        if (calendarDate) {
          state.dailyViewMode = 'date';
          state.activeDailyDate = calendarDate;
          state.activeDailyMonth = monthKeyFromDateKey(calendarDate) || state.activeDailyMonth;
          expandCurrentDailyAxisSection(ReadState.getAll());
          persistCollapse();
          rerenderSidebarBody(rerenderOptionsForAxisControlClick());
        }
        return;
      }
      var axisTab = e.target.closest('.dpr-sidebar-axis-tab');
      if (axisTab) {
        var tabGroup = axisTab.getAttribute('data-axis-tab');
        var tabKey = axisTab.getAttribute('data-axis-key') || '';
        if (tabGroup === 'daily') {
          var dailyAxisRow = axisTab.closest('.dpr-sidebar-axis-row');
          var dailyAxisMode = dailyAxisRow && dailyAxisRow.getAttribute('data-axis-mode') || '';
          if (dailyAxisMode === 'tag') state.activeDailyTag = tabKey;
          else {
            state.activeDailyDate = tabKey;
            state.activeDailyMonth = monthKeyFromDateKey(tabKey) || state.activeDailyMonth;
          }
          expandCurrentDailyAxisSection(ReadState.getAll());
          persistCollapse();
        } else if (tabGroup === 'conference') {
          if (state.conferenceViewMode === 'tag') state.activeConferenceTag = tabKey;
          else state.activeConference = tabKey;
        }
        rerenderSidebarBody(rerenderOptionsForAxisControlClick());
        return;
      }
      var statusButton = e.target.closest('.dpr-sidebar-paper-status-btn');
      if (statusButton) {
        e.preventDefault();
        e.stopPropagation();
        var statusPaperId = statusButton.getAttribute('data-paper-id') || '';
        var nextStatus = normalizeReadStatus(statusButton.getAttribute('data-paper-status'));
        if (statusPaperId && nextStatus) {
          var readMap = ReadState.getAll();
          var currentStatus = normalizeReadStatus(readMap[statusPaperId]);
          markPaperStatus(statusPaperId, currentStatus === nextStatus ? 'read' : nextStatus, { notify: false });
          var updateOptions = rerenderOptionsForStatusClick();
          if (updateOptions.updateInPlace) {
            updateReadStateMarks();
            applyFilterAndSearch();
            schedulePaperTitleOverflowMarks(statusButton.closest('.dpr-sidebar-paper'));
          } else {
            rerenderSidebarBody(updateOptions);
          }
        }
        return;
      }
      var sectionToggle = e.target.closest('.dpr-sidebar-axis-section-header');
      if (sectionToggle) {
        var sectionKey = sectionToggle.getAttribute('data-axis-section-toggle') || '';
        var section = sectionToggle.closest('.dpr-sidebar-axis-section');
        if (!state.expandedAxisSections) state.expandedAxisSections = new Set();
        var openSection;
        if (state.expandedAxisSections.has(sectionKey)) {
          state.expandedAxisSections.delete(sectionKey);
          openSection = false;
        } else {
          state.expandedAxisSections.add(sectionKey);
          openSection = true;
        }
        if (section) section.classList.toggle('is-expanded', openSection);
        sectionToggle.setAttribute('aria-expanded', openSection ? 'true' : 'false');
        persistCollapse();
        return;
      }
      // 论文点击：移动端自动关闭抽屉
      var paperLink = e.target.closest('.dpr-sidebar-paper-link');
      if (paperLink) {
        rememberPendingPaperHref(paperLink.getAttribute('href') || '');
        if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
          root.classList.remove('is-open');
        }
      }
      // 顶部 Home / Tutorial：移动端自动收起
      var quick = e.target.closest('.dpr-sidebar-quick');
      if (quick) {
        if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
          root.classList.remove('is-open');
        }
      }
    });

    root.addEventListener('mouseover', function (e) {
      var paper = e.target.closest('.dpr-sidebar-paper');
      if (!paper) return;
      schedulePaperTitleOverflowMarks(paper);
    });

    root.addEventListener('focusin', function (e) {
      var paper = e.target.closest('.dpr-sidebar-paper');
      if (!paper) return;
      schedulePaperTitleOverflowMarks(paper);
    });

    root.addEventListener('mousedown', function (e) {
      var handle = e.target.closest('.dpr-sidebar-resizer');
      if (!handle) return;
      e.preventDefault();
      var startX = e.clientX;
      var startWidth = state.sidebarWidth || loadPersistedSidebarWidth();
      root.classList.add('is-resizing');
      document.body.classList.add('dpr-sidebar-resizing');
      document.body.classList.add('sidebar-resizing');
      function onMove(moveEvent) {
        var delta = moveEvent.clientX - startX;
        applySidebarWidth(startWidth + delta);
      }
      function onUp() {
        persistSidebarWidth(state.sidebarWidth);
        root.classList.remove('is-resizing');
        document.body.classList.remove('dpr-sidebar-resizing');
        document.body.classList.remove('sidebar-resizing');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    state.searchInput.addEventListener('input', debounce(function () {
      state.search = state.searchInput.value || '';
      rerenderSidebarBody({ syncActive: false });
    }, SEARCH_DEBOUNCE_MS));

    window.addEventListener('hashchange', function () { syncActive(); });
    window.addEventListener('resize', syncResponsiveSidebarMode);
    document.addEventListener('dpr-paper-read-state-changed', function () {
      rerenderSidebarBody(rerenderOptionsForReadStateEvent());
    });

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState !== 'visible') return;
      if (!state.lastFetchAt) return;
      if (Date.now() - state.lastFetchAt < REFRESH_AFTER_HIDDEN_MS) return;
      loadAndRender();
    });
  }

  // ---------- 启动 ----------
  function determineInitialExpansion() {
    // 一级面板默认展开；面板内第三级目录默认收起，用户展开后再尊重本地状态。
    var persisted = loadPersistedCollapse();
    if (persisted) {
      state.expandedGroups = persisted.expandedGroups || defaultExpandedGroups();
      state.expandedAxisSections = persisted.expandedAxisSections || new Set();
    } else {
      state.expandedGroups = defaultExpandedGroups();
      state.expandedAxisSections = new Set();
    }
    var href = findActivePaper();
    if (href) syncAxisStateToHref(href);
    syncResolvedAxisState();
  }

  function loadAndRender() {
    return fetch(SIDEBAR_URL, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('sidebar HTTP ' + r.status);
        return r.text();
      })
      .then(function (text) {
        state.model = parseSidebar(text);
        state.lastFetchAt = Date.now();
        determineInitialExpansion();
        if (!state.rootEl) {
          state.rootEl = ensureRoot();
        }
        applySidebarWidth(state.sidebarWidth || loadPersistedSidebarWidth());
        renderShell(state.rootEl);
        syncResponsiveSidebarMode();
        if (!state._eventsBound) {
          bindEvents(state.rootEl);
          state._eventsBound = true;
        } else {
          // shell 元素被替换了，重新绑搜索框 input 事件
          rebindSearchInput();
        }
        renderBody();
        updateReadStateMarks();
        applyFilterAndSearch();
        syncActive(syncActiveOptionsForInitialLoad());
        dispatchSidebarUpdated();
      })
      .catch(function (err) {
        console.error('[DPR Sidebar] 加载失败:', err);
        if (state.rootEl && state.bodyEl) {
          state.bodyEl.innerHTML = '<div class="dpr-sidebar-error">侧边栏加载失败</div>';
        }
      });
  }

  function rebindSearchInput() {
    if (!state.searchInput) return;
    state.searchInput.addEventListener('input', debounce(function () {
      state.search = state.searchInput.value || '';
      rerenderSidebarBody({ syncActive: false });
    }, SEARCH_DEBOUNCE_MS));
  }

  function start() {
    state.filter = loadPersistedFilter();
    state.rootEl = ensureRoot();
    applySidebarWidth(loadPersistedSidebarWidth());
    state.rootEl.innerHTML = '<div class="dpr-sidebar-loading">加载中…</div>';
    loadAndRender();
  }

  var DPRSidebarApi = {
    refresh: function () { return loadAndRender(); },
    syncActive: syncActive,
    notifyReadStateChanged: function () { rerenderSidebarBody(rerenderOptionsForReadStateEvent()); },
    getReadState: function () { return ReadState.getAll(); },
    getPaperHrefs: function () { return collectPaperHrefsFromModel(state.model); },
    getReportHrefs: function () { return collectReportHrefsFromModel(state.model); },
    getCurrentHref: function () { return currentRouteHref(); },
    getCurrentPaperHref: function () { return findCurrentPaperHrefFromModel(state.model); },
    getCurrentReportHref: function () { return findCurrentReportHrefFromModel(state.model); },
    openMobile: function () { return toggleMobile(true); },
    closeMobile: function () { return toggleMobile(false); },
    toggleMobile: function () { return toggleMobile(); },
    toggleCollapsed: function () { return toggleSidebarCollapsed(); },
    setCollapsed: function (collapsed) { return applySidebarCollapsed(collapsed); },
    syncResponsiveSidebarMode: syncResponsiveSidebarMode,
    openSettingsPanel: openSettingsPanel,
  };

  // 让正文页（评分按钮）和 docsify 插件能消费侧栏状态。
  window.DPRSidebar = DPRSidebarApi;
  window.DPROpenSettingsPanel = openSettingsPanel;

  if (typeof module === 'object' && module.exports) {
    module.exports = {
      api: DPRSidebarApi,
      __test: {
        parseSidebar: parseSidebar,
        collectPaperHrefsFromModel: collectPaperHrefsFromModel,
        collectReportHrefsFromModel: collectReportHrefsFromModel,
        findCurrentPaperHrefFromModel: findCurrentPaperHrefFromModel,
        findCurrentReportHrefFromModel: findCurrentReportHrefFromModel,
        collectUnreadPaperIdsForSnapshot: collectUnreadPaperIdsForSnapshot,
        ensureUnreadSessionPaperIds: ensureUnreadSessionPaperIds,
        buildDailyDateView: buildDailyDateView,
        buildDailyCalendarView: buildDailyCalendarView,
        buildDailyTagView: buildDailyTagView,
        buildDailyCalendarTagView: buildDailyCalendarTagView,
        buildDailyResultView: buildDailyResultView,
        resolveDailyAxisSectionStateKey: resolveDailyAxisSectionStateKey,
        buildConferenceConfView: buildConferenceConfView,
        buildConferenceTagView: buildConferenceTagView,
        buildConferenceResultView: buildConferenceResultView,
        buildAxisViewForMode: buildAxisViewForMode,
        computeModelReadSummary: computeModelReadSummary,
        axisSectionStateKey: axisSectionStateKey,
        renderBodyHtml: renderBodyHtml,
        normalizeReadStatus: normalizeReadStatus,
        statusForMarkIndex: statusForMarkIndex,
        shouldAutoMarkRead: shouldAutoMarkRead,
        clampSidebarWidth: clampSidebarWidth,
        loadPersistedSidebarWidth: loadPersistedSidebarWidth,
        rerenderOptionsForReadStateEvent: rerenderOptionsForReadStateEvent,
        rerenderOptionsForAxisInteraction: rerenderOptionsForAxisInteraction,
        rerenderOptionsForPanelToggle: rerenderOptionsForPanelToggle,
        rerenderOptionsForAxisControlClick: rerenderOptionsForAxisControlClick,
        rerenderOptionsForStatusClick: rerenderOptionsForStatusClick,
        syncActiveOptionsForInitialLoad: syncActiveOptionsForInitialLoad,
        rememberPendingPaperHref: rememberPendingPaperHref,
        resolveCurrentPaperHrefForRender: resolveCurrentPaperHrefForRender,
        updatePaperTitleOverflowMarks: updatePaperTitleOverflowMarks,
        renderQuickLink: renderQuickLink,
        renderSidebarFooterControls: renderSidebarFooterControls,
        applySidebarCollapsed: applySidebarCollapsed,
        toggleSidebarCollapsed: toggleSidebarCollapsed,
        syncResponsiveSidebarMode: syncResponsiveSidebarMode,
        openSettingsPanel: openSettingsPanel,
      },
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
