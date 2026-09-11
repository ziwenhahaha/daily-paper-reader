const assert = require('node:assert/strict');
const fs = require('node:fs');

function decodeEntities(value) {
  return String(value || '')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function setupBrowserStub(hash) {
  global.window = {
    location: { hash: hash || '#/' },
    localStorage: {
      getItem: () => null,
      setItem: () => {},
    },
    addEventListener: () => {},
    setTimeout,
    clearTimeout,
    matchMedia: () => ({ matches: false }),
    CSS: {
      escape: (value) => String(value),
    },
  };
  global.document = {
    readyState: 'loading',
    addEventListener: () => {},
    dispatchEvent: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    createEvent: () => ({
      initCustomEvent(name) {
        this.type = name;
      },
    }),
    createElement: () => {
      let text = '';
      return {
        set innerHTML(value) {
          text = decodeEntities(value).replace(/<[^>]*>/g, '');
        },
        get innerHTML() {
          return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        },
        get textContent() {
          return text;
        },
        set textContent(value) {
          text = String(value == null ? '' : value);
        },
      };
    },
    body: {
      appendChild: () => {},
      classList: { add: () => {} },
    },
    documentElement: {
      style: { setProperty: () => {} },
    },
  };
}

function loadSidebarForTest(hash) {
  setupBrowserStub(hash);
  delete require.cache[require.resolve('../app/dpr-sidebar.js')];
  return require('../app/dpr-sidebar.js');
}

// 公布日期必须有明确精度和出处；旧入库/更新时间不能冒充发表时间。
{
  const api = loadSidebarForTest().__test;
  const model = { daily: [], conferences: [
    { name: 'ICML', years: '2025', label: 'ICML 2025', topics: [{ label: 'ATSP', papers: [
      { id: 'b', title: 'Beta', score: 8, published: '2025-01-01', updated: '2099-12-31' },
      { id: 'a', title: 'Alpha', score: 9 },
    ] }] },
    { name: 'ACL', years: '2025', label: 'ACL 2025', topics: [] },
  ] };
  api.applyConferencePublicationDates(model, { items: [
    { conference: 'ICML', year: 2025, publication_date: '2025-07-21', publication_date_precision: 'day', publication_date_source: 'https://official.test/icml', publication_date_kind: 'proceedings' },
    { conference: 'ACL', year: 2025, publication_date: '2025-08', publication_date_precision: 'month', publication_date_source: 'https://official.test/acl', publication_date_kind: 'proceedings' },
  ] });
  assert.deepEqual(model.conferences.map(c => c.name), ['ACL', 'ICML']);
  assert.deepEqual(model.conferences[1].topics[0].papers.map(p => p.id), ['a', 'b']);
  assert.equal(api.publicationDateLabel(model.conferences[1].topics[0].papers[0]), '2025-07-21 · 论文集公布');
  const old = { conferences: [{ name: 'SOSP', years: '2026', topics: [{ papers: [{ id: 'x', published: '2026-01-01', updated: '2099-01-01' }] }] }] };
  api.applyConferencePublicationDates(old, {});
  assert.equal(api.publicationDateLabel(old.conferences[0].topics[0].papers[0]), '2026 · 具体日期待确认');
  const rows = [
    { id: 'z', title: 'Zeta', score: 10, published: '2099-12-31', updated: '2099-12-31' },
    { id: 'a', title: 'Alpha', score: 6, publication_date: '2025-11-03', publication_date_precision: 'day', publication_date_source: 'Official proceedings', publication_date_kind: 'proceedings' },
    { id: 'c', title: 'Charlie', score: 9, publication_date: '2025-11-03', publication_date_precision: 'day', publication_date_source: 'Official proceedings', publication_date_kind: 'proceedings' },
    { id: 'b', title: 'Beta', score: 9, publication_date: '2025-11-03', publication_date_precision: 'day', publication_date_source: 'Official proceedings', publication_date_kind: 'proceedings' },
    { id: 'invalid', title: 'Invalid', score: 1, publication_date: '2025-02-30', publication_date_precision: 'day', publication_date_source: 'Official proceedings', publication_date_kind: 'proceedings' },
  ];
  const papers = { daily: [], conferences: [{ name: 'TEST', years: '2025', label: 'TEST 2025', topics: [{ label: 'ATSP', papers: rows }] }] };
  rows.forEach(row => { row.section = 'conference'; row.href = '#/conference/test-2025/' + row.id; });
  api.applyConferencePublicationDates(papers, {});
  assert.deepEqual(papers.conferences[0].topics[0].papers.map(p => p.id), ['b', 'c', 'a', 'z', 'invalid']);
  assert.equal(rows[4].publication_date_precision, 'year');
  const html = api.renderBodyHtml(papers, { conferenceViewMode: 'conf', readMap: {} });
  assert.ok(html.includes('2025-11-03 · 论文集公布'));
  assert.ok(html.includes('2025 · 具体日期待确认'));
  assert.ok(html.includes('aria-label="论文标记"'));
  const mixed = { conferences: [{ name: 'ICML', years: '2024-2025', topics: [{ papers: [
    { id: 'old', href: '#/conference/icml-2024/old' },
    { id: 'new', href: '#/conference/icml-2025/new' },
  ] }] }] };
  api.applyConferencePublicationDates(mixed, { items: [
    { conference: 'ICML', year: 2025, publication_date: '2025-10-06', publication_date_precision: 'day', publication_date_source: 'https://official.test', publication_date_kind: 'proceedings' },
  ] });
  assert.deepEqual(mixed.conferences[0].topics[0].papers.map(p => p.publication_date), ['2025-10-06', '2024']);
  const mergedRoutes = { conferences: [{ name: 'ICML', years: '2024-2025', topics: [{ papers: [
    { id: 'explicit', href: '#/conference/icml-2024-2025/explicit', publication_date: '2025', publication_date_precision: 'year' },
    { id: 'unknown', href: '#/conference/icml-2024-2025/unknown' },
    { id: 'no-route', href: '#/conference/icml/no-route' },
  ] }] }] };
  api.applyConferencePublicationDates(mergedRoutes, {});
  const mergedPapers = Object.fromEntries(mergedRoutes.conferences[0].topics[0].papers.map(p => [p.id, p]));
  assert.equal(mergedPapers.explicit.publication_date, '2025');
  assert.equal(mergedPapers.unknown.publication_date_precision, 'unknown');
  assert.equal(mergedPapers['no-route'].publication_date_precision, 'unknown');
  api.applyConferencePublicationDates(mergedRoutes, { items: [
    { conference: 'ICML', year: 2025, publication_date: '2025-10-06', publication_date_precision: 'day', publication_date_source: 'https://official.test', publication_date_kind: 'proceedings' },
  ] });
  assert.equal(mergedPapers.explicit.publication_date, '2025-10-06');
  assert.equal(mergedPapers.unknown.publication_date_precision, 'unknown');
  assert.equal(api.publicationDateLabel({ publication_date: '2026-09', publication_date_precision: 'month', publication_date_kind: 'accepted_notice' }), '2026-09 · 录用预告');
}

{
  const api = loadSidebarForTest().__test;
  const guides = api.parseStarterPackIndex({ version: 1, packs: [
    { run_id: '20260911-abcdef123456', tag: 'ATSP', status: 'complete', paper_count: 12, href: 'https://evil.test' },
    { run_id: '../unsafe', tag: 'bad', status: 'complete' },
    { run_id: '20260911-abcdef123456', tag: 'duplicate' },
    { run_id: '20260910-111111111111', tag: '<SR>', status: 'needs_resume' },
  ] });
  assert.equal(guides.length, 2);
  assert.equal(guides[0].href, '#/starter-pack/20260911-abcdef123456/README');
  const model = { daily: [], conferences: [], starterPacks: guides };
  for (const state of [{}, { filter: 'unread' }, { search: 'unmatched' }]) {
    const html = api.renderBodyHtml(model, state);
    assert.ok(html.includes('专题回溯'));
    assert.ok(html.includes('入门导读'));
    assert.ok(html.includes('待续跑'));
    assert.ok(html.includes('&lt;SR&gt;'));
    assert.ok(html.includes(guides[0].href));
    assert.ok(!html.includes('evil.test'));
    assert.ok(!html.includes('target="_blank"'));
    assert.ok(!html.includes('data-paper-id='));
  }
  assert.equal(api.collectPaperHrefsFromModel(model).length, 0);
  assert.ok(api.collectReportHrefsFromModel(model).includes(guides[0].href));
  assert.deepEqual(api.parseStarterPackIndex({}), []);
  assert.ok(!api.renderBodyHtml({ daily: [], conferences: [] }, {}).includes('入门导读'));
}

function cssRule(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp('(^|\\n)\\s*' + escaped + '\\s*\\{').exec(css);
  const index = match ? match.index + match[1].length : -1;
  assert.notEqual(index, -1, selector + ' CSS rule should exist');
  const start = css.indexOf('{', index);
  const end = css.indexOf('}', start);
  assert.ok(start >= 0 && end > start, selector + ' CSS rule should be complete');
  return css.slice(start + 1, end);
}

function panelHeaderCounts(html, panel) {
  const start = html.indexOf('dpr-sidebar-panel-header-' + panel);
  assert.ok(start >= 0, panel + ' panel header should exist');
  const end = html.indexOf('<div class="dpr-sidebar-panel-content">', start);
  assert.ok(end > start, panel + ' panel content should follow header');
  const header = html.slice(start, end);
  const unread = /dpr-sidebar-day-unread">([^<]+)/.exec(header);
  const total = /dpr-sidebar-day-total">([^<]+)/.exec(header);
  return {
    unread: unread ? Number(unread[1]) : NaN,
    total: total ? Number(total[1]) : NaN,
  };
}

function createClassList(initial = []) {
  const values = new Set(initial);
  return {
    add: (...items) => items.forEach((item) => values.add(item)),
    remove: (...items) => items.forEach((item) => values.delete(item)),
    contains: (item) => values.has(item),
    toggle(item, force) {
      if (typeof force === 'boolean') {
        if (force) values.add(item);
        else values.delete(item);
        return force;
      }
      if (values.has(item)) {
        values.delete(item);
        return false;
      }
      values.add(item);
      return true;
    },
    toString: () => Array.from(values).join(' '),
  };
}

const sampleSidebar = `
* <a class="dpr-sidebar-root-link" href="#/">首页</a>
* <a class="dpr-sidebar-root-link" href="#/tutorial/README">使用教程</a>

* Conference Papers
  * NEURIPS 2024 <!--dpr-conference:neurips-2024-->
    * rl <!--dpr-conference-topic:neurips-2024:query-rl-->
      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/conference/neurips-2024/paper-c" data-sidebar-item="{&quot;title&quot;:&quot;Paper C&quot;,&quot;score&quot;:&quot;9.0&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;rl&quot;}]}">Fallback C</a>
  * ICLR 2025 <!--dpr-conference:iclr-2025-->
    * symbolic <!--dpr-conference-topic:iclr-2025:query-symbolic-->
      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/conference/iclr-2025/paper-e" data-sidebar-item="{&quot;title&quot;:&quot;Paper E&quot;,&quot;score&quot;:&quot;8.0&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;symbolic&quot;}]}">Fallback E</a>

* Daily Papers
  * 2026-06-24 <!--dpr-date:20260624-->
    * 精读区
      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/202606/24/paper-a" data-sidebar-item="{&quot;title&quot;:&quot;Paper A&quot;,&quot;score&quot;:&quot;10.0&quot;,&quot;evidence&quot;:&quot;中文解释 A&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;rl&quot;}]}">Fallback A</a>
    * 速读区
      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/202606/24/paper-b" data-sidebar-item="{&quot;title&quot;:&quot;Paper B&quot;,&quot;score&quot;:&quot;8.0&quot;}">Fallback B</a>
  * 2026-06-23 <!--dpr-date:20260623-->
    * 精读区
      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/202606/23/paper-d" data-sidebar-item="{&quot;title&quot;:&quot;Paper D&quot;,&quot;score&quot;:&quot;9.0&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;rl&quot;}]}">Fallback D</a>
`;

const unorderedSidebar = `
* <a class="dpr-sidebar-root-link" href="#/">首页</a>

* Conference Papers
  * NEURIPS 2024 <!--dpr-conference:neurips-2024-->
    * rl
      * <a class="dpr-sidebar-item-link" href="#/conference/neurips-2024/conf-old" data-sidebar-item="{&quot;title&quot;:&quot;Conf Old&quot;,&quot;published&quot;:&quot;2024-04-01&quot;}">Conf Old</a>
      * <a class="dpr-sidebar-item-link" href="#/conference/neurips-2024/conf-new" data-sidebar-item="{&quot;title&quot;:&quot;Conf New&quot;,&quot;published&quot;:&quot;2024-09-01&quot;}">Conf New</a>
  * ICLR 2025 <!--dpr-conference:iclr-2025-->
    * rl
      * <a class="dpr-sidebar-item-link" href="#/conference/iclr-2025/conf-2025" data-sidebar-item="{&quot;title&quot;:&quot;Conf 2025&quot;}">Conf 2025</a>

* Daily Papers
  * 2026-06-23 <!--dpr-date:20260623-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/202606/23/old" data-sidebar-item="{&quot;title&quot;:&quot;Old Daily&quot;,&quot;published&quot;:&quot;2026-06-23T02:00:00Z&quot;}">Old Daily</a>
  * 2026-06-25 <!--dpr-date:20260625-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/202606/25/new" data-sidebar-item="{&quot;title&quot;:&quot;New Daily&quot;,&quot;published&quot;:&quot;2026-06-25T02:00:00Z&quot;}">New Daily</a>
`;

const rangeDailySidebar = `
* Daily Papers
  * 2026-07-06 <!--dpr-date:20260706-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/202607/06/today" data-sidebar-item="{&quot;title&quot;:&quot;Today Paper&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;data&quot;}]}">Today Paper</a>
  * 2026-06-27 ~ 2026-07-06 <!--dpr-date:20260627-20260706-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/20260627-20260706/range-data" data-sidebar-item="{&quot;title&quot;:&quot;Range Data Paper&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;data&quot;}]}">Range Data Paper</a>
    * 速读区
      * <a class="dpr-sidebar-item-link" href="#/20260627-20260706/range-robot" data-sidebar-item="{&quot;title&quot;:&quot;Range Robot Paper&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;robot&quot;}]}">Range Robot Paper</a>
  * 2017-06-12
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/201706/12/attention" data-sidebar-item="{&quot;title&quot;:&quot;Attention Paper&quot;}">Attention Paper</a>
`;

// 区间日报的结束日「没有」同日单日报，复刻线上真实形态：
// 日历会把区间挂到锚定日 20260827，而该 key 不存在于 model.daily 的原始 key 集合中。
const orphanRangeDailySidebar = `
* Daily Papers
  * 2026-08-28 <!--dpr-date:20260828-->
    * 速读区
      * <a class="dpr-sidebar-item-link" href="#/202608/28/fresh" data-sidebar-item="{&quot;title&quot;:&quot;Fresh Paper&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;eeg&quot;}]}">Fresh Paper</a>
  * 2026-07-29 ~ 2026-08-27 <!--dpr-date:20260729-20260827-->
    * 速读区
      * <a class="dpr-sidebar-item-link" href="#/20260729-20260827/range-one" data-sidebar-item="{&quot;title&quot;:&quot;Range One&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;eeg&quot;}]}">Range One</a>
      * <a class="dpr-sidebar-item-link" href="#/20260729-20260827/range-two" data-sidebar-item="{&quot;title&quot;:&quot;Range Two&quot;,&quot;tags&quot;:[{&quot;kind&quot;:&quot;query&quot;,&quot;label&quot;:&quot;speech&quot;}]}">Range Two</a>
`;

function testSidebarNavigationContract() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-b?from=test');
  const tools = sidebar.__test;
  assert.ok(tools, 'dpr-sidebar.js should export test helpers');
  assert.equal(typeof tools.parseSidebar, 'function');

  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(model.tutorial.label, '教程', '旧版运行态文案也应归一化为两个字');
  assert.deepEqual(tools.collectPaperHrefsFromModel(model), [
    '#/202606/24/paper-a',
    '#/202606/24/paper-b',
    '#/202606/23/paper-d',
    '#/conference/iclr-2025/paper-e',
    '#/conference/neurips-2024/paper-c',
  ]);
  assert.deepEqual(tools.collectReportHrefsFromModel(model), [
    '#/202606/24/README',
    '#/202606/23/README',
  ]);
  assert.equal(
    tools.findCurrentPaperHrefFromModel(model, '#/202606/24/paper-b?from=test'),
    '#/202606/24/paper-b',
  );
  assert.equal(
    tools.findCurrentReportHrefFromModel(model, '#/202606/24/README'),
    '#/202606/24/README',
  );
}

function testAxisViewsForDailyAndConference() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.buildDailyDateView, 'function');
  assert.equal(typeof tools.buildDailyTagView, 'function');
  assert.equal(typeof tools.buildConferenceConfView, 'function');
  assert.equal(typeof tools.buildConferenceTagView, 'function');

  const dateView = tools.buildDailyDateView(model, '20260623');
  assert.deepEqual(dateView.tabs.map((tab) => tab.label), ['2026-06-24', '2026-06-23']);
  assert.equal(dateView.activeKey, '20260623');
  assert.deepEqual(dateView.groups.map((group) => group.label), ['2026-06-23']);
  assert.deepEqual(dateView.groups[0].papers.map((paper) => paper.title), ['Paper D']);

  const dailyTagView = tools.buildDailyTagView(model, 'rl');
  assert.deepEqual(dailyTagView.tabs.map((tab) => tab.label), ['rl', '未标注']);
  assert.equal(dailyTagView.activeKey, 'rl');
  assert.deepEqual(dailyTagView.groups.map((group) => group.label), ['2026-06-24', '2026-06-23']);
  assert.deepEqual(dailyTagView.groups.map((group) => group.papers.map((paper) => paper.title)), [
    ['Paper A'],
    ['Paper D'],
  ]);

  const confView = tools.buildConferenceConfView(model, 'iclr-2025');
  assert.deepEqual(confView.tabs.map((tab) => tab.label), ['ICLR 2025', 'NEURIPS 2024']);
  assert.equal(confView.activeKey, 'iclr-2025');
  assert.deepEqual(confView.groups.map((group) => group.label), ['symbolic']);
  assert.deepEqual(confView.groups[0].papers.map((paper) => paper.title), ['Paper E']);

  const confTagView = tools.buildConferenceTagView(model, 'rl');
  assert.deepEqual(confTagView.tabs.map((tab) => tab.label), ['symbolic', 'rl']);
  assert.equal(confTagView.activeKey, 'rl');
  assert.deepEqual(confTagView.groups.map((group) => group.label), ['NEURIPS 2024 / rl']);
  assert.deepEqual(confTagView.groups[0].papers.map((paper) => paper.title), ['Paper C']);
}

function testHyphenatedConferenceMarkerParsing() {
  const sidebar = loadSidebarForTest('#/conference/ieee-sp-2025/paper-s');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(`
* Conference Papers
  * IEEE_SP 2025 <!--dpr-conference:ieee-sp-2025-->
    * security
      * <a class="dpr-sidebar-item-link" href="#/conference/ieee-sp-2025/paper-s" data-sidebar-item="{&quot;title&quot;:&quot;Paper S&quot;}">Paper S</a>
`);
  assert.deepEqual(model.conferences.map((conf) => [conf.name, conf.years]), [['ieee-sp', '2025']]);
  const confView = tools.buildConferenceConfView(model, 'ieee-sp-2025');
  assert.deepEqual(confView.tabs.map((tab) => tab.key), ['ieee-sp-2025']);
}

function testAxisTabsRenderUnreadCounts() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    readMap: {
      '202606/24/paper-a': 'read',
      'conference/neurips-2024/paper-c': 'good',
    },
  });

  assert.ok(html.includes('class="dpr-sidebar-calendar'));
  assert.ok(html.includes('data-calendar-date="20260624" data-unread="1"'));
  assert.ok(html.includes('<span class="dpr-sidebar-calendar-day-total">2</span><span class="dpr-sidebar-calendar-day-unread">1</span>'));
  assert.ok(html.includes('data-axis-tab="daily"'));
  assert.ok(html.includes('data-axis-key="__all__"'));
  assert.ok(html.includes('data-axis-key="rl"'));
  assert.ok(!html.includes('dpr-sidebar-axis-tab-dot'));
  assert.ok(html.includes('data-axis-key="neurips-2024"'));
  assert.ok(html.includes('data-axis-key="neurips-2024" data-unread="0"'));
  assert.ok(html.includes('<span class="dpr-sidebar-axis-tab-unread">0</span>/<span class="dpr-sidebar-axis-tab-total">1</span>'));
  assert.ok(html.includes('data-axis-section-toggle="daily:tag:20260624:__all__" aria-expanded="false" data-unread="1"'));
  assert.ok(!html.includes('dpr-sidebar-axis-section-dot'));
  assert.deepEqual(panelHeaderCounts(html, 'daily'), { unread: 1, total: 2 });
  assert.deepEqual(panelHeaderCounts(html, 'conference'), { unread: 0, total: 1 });

  assert.equal(typeof tools.buildAxisViewForMode, 'function');
  const updatedDateView = tools.buildAxisViewForMode(model, 'daily', 'date', {
    dailyViewMode: 'date',
    activeDailyDate: '20260624',
  }, {
    '202606/24/paper-a': 'read',
    '202606/24/paper-b': 'blue',
  });
  const updatedAllTab = updatedDateView.tabs.find((tab) => tab.key === '__all__');
  assert.equal(updatedDateView.activeDateKey, '20260624');
  assert.equal(updatedDateView.activeKey, '__all__');
  assert.equal(updatedAllTab.unreadCount, 0);
  assert.equal(updatedDateView.groups[0].unreadCount, 0);
  assert.equal(updatedDateView.calendar.days.find((day) => day.dateKey === '20260624').unreadCount, 0);

  const updatedConferenceView = tools.buildAxisViewForMode(model, 'conference', 'conf', {
    conferenceViewMode: 'conf',
    activeConference: 'neurips-2024',
  }, {
    'conference/neurips-2024/paper-c': 'good',
  });
  const updatedConferenceTab = updatedConferenceView.tabs.find((tab) => tab.key === 'neurips-2024');
  assert.equal(updatedConferenceTab.unreadCount, 0);
  assert.equal(updatedConferenceView.groups[0].unreadCount, 0);
}

function testDailyCalendarViewUsesMonthGridAndActiveDateOnly() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.buildDailyCalendarView, 'function');

  const calendar = tools.buildDailyCalendarView(model, '20260624', '202606', {
    '202606/24/paper-a': 'read',
  });

  assert.equal(calendar.monthKey, '202606');
  assert.equal(calendar.monthLabel, '2026年6月');
  assert.equal(calendar.activeDateKey, '20260624');
  assert.equal(calendar.prevMonthKey, '202605');
  assert.equal(calendar.nextMonthKey, '202607');
  assert.deepEqual(calendar.weekdays, ['一', '二', '三', '四', '五', '六', '日']);

  const activeDay = calendar.days.find((day) => day.dateKey === '20260624');
  assert.ok(activeDay, 'calendar should include active daily date');
  assert.equal(activeDay.dayNumber, 24);
  assert.equal(activeDay.totalCount, 2);
  assert.equal(activeDay.unreadCount, 1);
  assert.equal(activeDay.isActive, true);
  assert.equal(activeDay.hasPapers, true);

  const emptyDay = calendar.days.find((day) => day.dateKey === '20260622');
  assert.ok(emptyDay, 'calendar should include empty dates in the current month');
  assert.equal(emptyDay.totalCount, 0);
  assert.equal(emptyDay.unreadCount, 0);
  assert.equal(emptyDay.hasPapers, false);

  const monthSelectedView = tools.buildDailyDateView(model, '20990101', {}, '202606');
  assert.equal(monthSelectedView.activeKey, '20260624');
  assert.deepEqual(monthSelectedView.groups.map((group) => group.label), ['2026-06-24']);

  const mixedMonthModel = tools.parseSidebar(`
* Daily Papers
  * 2026-07-01 <!--dpr-date:20260701-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/202607/01/july" data-sidebar-item="{&quot;title&quot;:&quot;July Paper&quot;}">July Paper</a>
  * 2026-06-24 <!--dpr-date:20260624-->
    * 精读区
      * <a class="dpr-sidebar-item-link" href="#/202606/24/june" data-sidebar-item="{&quot;title&quot;:&quot;June Paper&quot;}">June Paper</a>
`);
  const navMonthView = tools.buildDailyDateView(mixedMonthModel, '20260701', {}, '202606');
  assert.equal(navMonthView.activeKey, '20260624');
  assert.deepEqual(navMonthView.groups[0].papers.map((paper) => paper.title), ['June Paper']);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: false, daily: true },
    dailyViewMode: 'date',
    activeDailyDate: '20260624',
    activeDailyMonth: '202606',
    readMap: {
      '202606/24/paper-a': 'read',
    },
  });

  assert.ok(html.includes('data-calendar-month="202606"'));
  assert.ok(html.includes('data-calendar-nav="202605"'));
  assert.ok(html.includes('data-calendar-nav="202607"'));
  assert.ok(html.includes('data-calendar-date="20260624" data-unread="1"'));
  assert.ok(html.includes('data-calendar-date="20260623" data-unread="1"'));
  assert.ok(html.includes('Paper A'));
  assert.ok(html.includes('Paper B'));
  assert.ok(!html.includes('Paper D'), 'inactive daily dates should not render their paper rows');
}

function testDailyCalendarTagViewFiltersActiveDateByKeyword() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.buildDailyCalendarTagView, 'function');

  const allView = tools.buildDailyCalendarTagView(model, '20260624', '__all__', {}, '202606');
  assert.equal(allView.activeDateKey, '20260624');
  assert.equal(allView.activeKey, '__all__');
  assert.deepEqual(allView.tabs.map((tab) => tab.key), ['__all__', 'rl', '未标注']);
  assert.deepEqual(allView.groups[0].papers.map((paper) => paper.title), ['Paper A', 'Paper B']);

  const tagView = tools.buildDailyCalendarTagView(model, '20260624', 'rl', {}, '202606');
  assert.equal(tagView.activeDateKey, '20260624');
  assert.equal(tagView.activeKey, 'rl');
  assert.deepEqual(tagView.groups[0].papers.map((paper) => paper.title), ['Paper A']);
  assert.equal(tagView.calendar.days.find((day) => day.dateKey === '20260624').totalCount, 1);
  assert.equal(tagView.calendar.days.find((day) => day.dateKey === '20260623').totalCount, 1);

  const fallbackView = tools.buildDailyCalendarTagView(model, '20260624', 'missing-tag', {}, '202606');
  assert.equal(fallbackView.activeKey, '__all__');
  assert.deepEqual(fallbackView.groups[0].papers.map((paper) => paper.title), ['Paper A', 'Paper B']);
}

function testDailyRangeReportsStayReachableFromCalendarEndDate() {
  const sidebar = loadSidebarForTest('#/20260627-20260706/range-data');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(rangeDailySidebar);

  assert.deepEqual(model.daily.map((day) => day.dateKey), [
    '20260706',
    '20260627-20260706',
    '20170612',
  ]);
  assert.deepEqual(tools.collectReportHrefsFromModel(model), [
    '#/202607/06/README',
    '#/20260627-20260706/README',
    '#/201706/12/README',
  ]);

  const view = tools.buildDailyCalendarTagView(model, '', '__all__', {}, '');
  assert.equal(view.activeDateKey, '20260706');
  assert.deepEqual(view.groups.map((group) => [group.key, group.label, group.papers.length]), [
    ['20260706:__all__', '2026-07-06', 1],
    ['20260627-20260706:__all__', '2026-06-27 ~ 2026-07-06', 2],
  ]);
  const activeCalendarDay = view.calendar.days.find((day) => day.dateKey === '20260706');
  assert.equal(activeCalendarDay.totalCount, 3);
  assert.equal(activeCalendarDay.unreadCount, 3);
  assert.equal(activeCalendarDay.isActive, true);

  const tagView = tools.buildDailyCalendarTagView(model, '20260706', 'data', {}, '202607');
  assert.deepEqual(tagView.groups.map((group) => [group.key, group.papers.map((paper) => paper.title)]), [
    ['20260706:data', ['Today Paper']],
    ['20260627-20260706:data', ['Range Data Paper']],
  ]);
  assert.equal(tagView.calendar.days.find((day) => day.dateKey === '20260706').totalCount, 2);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: false, daily: true },
    dailyViewMode: 'date',
    activeDailyDate: '',
    activeDailyMonth: '',
    readMap: {},
  });
  assert.ok(html.includes('Range Data Paper'));
  assert.ok(html.includes('Range Robot Paper'));
  assert.ok(html.includes('data-axis-section="20260627-20260706:__all__"'));
}

// 回归：区间日报的锚定日（结束日）在当天没有同日单日报时，点击日历格必须能选中该区间。
// 注意 rangeDailySidebar 的区间结束日 20260706 恰好另有一条单日报，会掩盖该缺陷，
// 所以这里必须用「孤立锚定日」的 fixture，且保持单日组排在区间组之前（与线上生成顺序一致）。
function testDailyRangeSelectableFromOrphanCalendarAnchorDay() {
  const sidebar = loadSidebarForTest('#/202608/28/fresh');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(orphanRangeDailySidebar);

  assert.deepEqual(model.daily.map((day) => day.dateKey), [
    '20260828',
    '20260729-20260827',
  ], '单日组必须排在区间组之前，否则该用例会假绿');

  // 日历格按锚定日聚合，27 号格子应带出区间的两篇
  const baseView = tools.buildDailyCalendarTagView(model, '', '__all__', {}, '202608');
  const anchorDay = baseView.calendar.days.find((day) => day.dateKey === '20260827');
  assert.equal(anchorDay.totalCount, 2, '27 号日历格应显示区间日报的篇数');
  assert.equal(anchorDay.hasPapers, true);

  // 点击 27 号格子传回的是锚定日 '20260827'，必须能还原到区间原始 key
  const picked = tools.buildDailyDateView(model, '20260827', {}, '202608');
  assert.equal(picked.activeKey, '20260729-20260827');
  assert.deepEqual(picked.groups.map((group) => group.label), ['2026-07-29 ~ 2026-08-27']);
  assert.deepEqual(picked.groups[0].papers.map((paper) => paper.title), ['Range One', 'Range Two']);

  // 月份为空时走的是另一条兜底分支，同样不能落回最新单日
  const pickedNoMonth = tools.buildDailyDateView(model, '20260827', {}, '');
  assert.equal(pickedNoMonth.activeKey, '20260729-20260827');

  // 完整视图：区间被选中，日历高亮落在锚定日上
  const rangeView = tools.buildDailyCalendarTagView(model, '20260827', '__all__', {}, '202608');
  assert.deepEqual(rangeView.groups.map((group) => [group.key, group.papers.length]), [
    ['20260729-20260827:__all__', 2],
  ]);
  assert.equal(rangeView.calendar.days.find((day) => day.dateKey === '20260827').isActive, true);
  assert.equal(rangeView.calendar.days.find((day) => day.dateKey === '20260828').isActive, false);

  // 普通单日组不能因此回归
  const freshView = tools.buildDailyCalendarTagView(model, '20260828', '__all__', {}, '202608');
  assert.deepEqual(freshView.groups.map((group) => [group.key, group.papers.length]), [
    ['20260828:__all__', 1],
  ]);
  assert.equal(freshView.calendar.days.find((day) => day.dateKey === '20260828').isActive, true);
}

function testDailyCalendarPlacementToggleKeepsControlRowFixedAboveLayers() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const topHtml = tools.renderBodyHtml(model, {
    expandedGroups: { conference: false, daily: true },
    dailyViewMode: 'date',
    dailyCalendarPlacement: 'top',
    activeDailyDate: '20260624',
  });
  const bottomHtml = tools.renderBodyHtml(model, {
    expandedGroups: { conference: false, daily: true },
    dailyViewMode: 'date',
    dailyCalendarPlacement: 'bottom',
    activeDailyDate: '20260624',
  });

  const topToggleIndex = topHtml.indexOf('data-axis-toggle="daily"');
  const topCalendarIndex = topHtml.indexOf('class="dpr-sidebar-calendar');
  const topTabsIndex = topHtml.indexOf('data-axis-tab="daily"');
  const bottomToggleIndex = bottomHtml.indexOf('data-axis-toggle="daily"');
  const bottomCalendarIndex = bottomHtml.indexOf('class="dpr-sidebar-calendar');
  const bottomTabsIndex = bottomHtml.indexOf('data-axis-tab="daily"');
  const dailyHeaderStart = topHtml.indexOf('dpr-sidebar-panel-header-daily');
  const dailyHeaderEnd = topHtml.indexOf('<div class="dpr-sidebar-panel-content">', dailyHeaderStart);
  const dailyHeader = topHtml.slice(dailyHeaderStart, dailyHeaderEnd);

  assert.ok(topToggleIndex < topCalendarIndex);
  assert.ok(topToggleIndex < topTabsIndex);
  assert.ok(bottomToggleIndex < bottomCalendarIndex);
  assert.ok(bottomToggleIndex < bottomTabsIndex);
  assert.ok(topCalendarIndex < topTabsIndex);
  assert.ok(bottomTabsIndex < bottomCalendarIndex);
  assert.ok(topHtml.includes('data-calendar-date="20260624"'));
  assert.ok(bottomHtml.includes('data-calendar-date="20260624"'));
  assert.ok(topHtml.includes('title="标签上置"'));
  assert.ok(bottomHtml.includes('title="日历上置"'));
  assert.ok(dailyHeader.includes('data-panel-toggle="daily"'));
  assert.ok(dailyHeader.includes('data-axis-toggle="daily"'));
  assert.ok(!topHtml.includes('dpr-sidebar-daily-control-row'));
  assert.ok(!bottomHtml.includes('dpr-sidebar-daily-control-row'));
  assert.equal((topHtml.match(/data-axis-toggle="daily"/g) || []).length, 1);
}

function testConferenceAndDailyAxisTogglesRenderBesidePanelTitles() {
  const sidebar = loadSidebarForTest('#/conference/neurips-2024/paper-c');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
  });
  const confHeaderStart = html.indexOf('dpr-sidebar-panel-header-conference');
  const confHeaderEnd = html.indexOf('<div class="dpr-sidebar-panel-content">', confHeaderStart);
  const confHeader = html.slice(confHeaderStart, confHeaderEnd);
  const dailyHeaderStart = html.indexOf('dpr-sidebar-panel-header-daily');
  const dailyHeaderEnd = html.indexOf('<div class="dpr-sidebar-panel-content">', dailyHeaderStart);
  const dailyHeader = html.slice(dailyHeaderStart, dailyHeaderEnd);

  assert.ok(confHeader.includes('data-panel-toggle="conference"'));
  assert.ok(confHeader.includes('data-axis-toggle="conference"'));
  assert.ok(confHeader.indexOf('dpr-sidebar-panel-title') < confHeader.indexOf('data-axis-toggle="conference"'));
  assert.ok(confHeader.indexOf('data-axis-toggle="conference"') < confHeader.indexOf('dpr-sidebar-day-counts'));
  assert.ok(dailyHeader.indexOf('dpr-sidebar-panel-title') < dailyHeader.indexOf('data-axis-toggle="daily"'));
  assert.ok(dailyHeader.indexOf('data-axis-toggle="daily"') < dailyHeader.indexOf('dpr-sidebar-day-counts'));
  assert.equal((html.match(/data-axis-toggle="conference"/g) || []).length, 1);
  assert.equal((html.match(/data-axis-toggle="daily"/g) || []).length, 1);
}

function testDailyCalendarInPlaceRefreshUsesActiveDailyTag() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf('function updateDailyCalendarUnreadMarks(readMap)');
  const end = js.indexOf('function syncResolvedAxisState()', start);
  assert.ok(start > 0 && end > start, 'updateDailyCalendarUnreadMarks should be present');
  const block = js.slice(start, end);

  assert.ok(block.includes('buildDailyPanelView'));
  assert.ok(block.includes("['daily', 'backtrack']"));
  const helper = js.slice(js.indexOf('function buildDailyPanelView'), js.indexOf('function isDailySingleDateKey'));
  assert.ok(helper.includes('buildDailyCalendarTagView'));
  assert.ok(helper.includes("dailyPanelField(group, 'Tag')"));
  assert.ok(block.includes('view.activeDateKey'));
  assert.ok(!block.includes('buildDailyDateView'));
}

function testDailyAxisSectionKeyFollowsActiveDateAndTag() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.resolveDailyAxisSectionStateKey, 'function');

  assert.equal(
    tools.resolveDailyAxisSectionStateKey(model, {
      activeDailyDate: '20260624',
      activeDailyTag: '__all__',
      activeDailyMonth: '202606',
    }, {}),
    'daily:tag:20260624:__all__',
  );
  assert.equal(
    tools.resolveDailyAxisSectionStateKey(model, {
      activeDailyDate: '20260624',
      activeDailyTag: 'rl',
      activeDailyMonth: '202606',
    }, {}),
    'daily:tag:20260624:rl',
  );
}

function testDailyDateAndTagClicksExpandCurrentSectionOnlyForDaily() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const calendarStart = js.indexOf("var calendarDay = e.target.closest('.dpr-sidebar-calendar-day[data-calendar-date]');");
  const calendarEnd = js.indexOf("var axisTab = e.target.closest('.dpr-sidebar-axis-tab');", calendarStart);
  assert.ok(calendarStart > 0 && calendarEnd > calendarStart, 'calendar day handler should be present');
  const calendarBlock = js.slice(calendarStart, calendarEnd);
  assert.ok(calendarBlock.includes('expandCurrentDailyAxisSection('));

  const tabStart = js.indexOf("if (tabGroup === 'daily' || tabGroup === 'backtrack') {");
  const tabEnd = js.indexOf('rerenderSidebarBody(rerenderOptionsForAxisControlClick());', tabStart);
  assert.ok(tabStart > 0 && tabEnd > tabStart, 'axis tab handler should be present');
  const dailyTabBlock = js.slice(tabStart, tabEnd);
  assert.ok(dailyTabBlock.includes('expandCurrentDailyAxisSection('));

  const conferenceBlock = js.slice(js.indexOf("} else if (tabGroup === 'conference')", tabStart), tabEnd);
  assert.ok(!conferenceBlock.includes('expandCurrentDailyAxisSection('));
}

function testPaperEvidenceAndActionButtonsRender() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
  });

  assert.ok(html.includes('中文解释 A'));
  assert.ok(html.includes('class="dpr-sidebar-paper-actions"'));
  assert.ok(!html.includes('dpr-sidebar-paper-unread-dot'));
  assert.ok(html.includes('data-paper-status="good"'));
  assert.ok(html.includes('data-paper-status="blue"'));
  assert.ok(html.includes('data-paper-status="orange"'));
  assert.ok(html.includes('data-paper-status="bad"'));
}

function testPaperMetaOrderKeepsEvidenceBetweenTitleAndStars() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
  });
  const titleIndex = html.indexOf('<span class="dpr-sidebar-paper-title">Paper A</span>');
  const evidenceIndex = html.indexOf('<div class="dpr-sidebar-paper-evidence">中文解释 A</div>');
  const starsIndex = html.indexOf('<span class="dpr-sidebar-paper-stars" data-score="10.0">★★★★★</span>');
  const tagsIndex = html.indexOf('<span class="dpr-sidebar-paper-tags">', starsIndex);

  assert.ok(titleIndex >= 0, 'title should render');
  assert.ok(evidenceIndex > titleIndex, 'Chinese evidence should render after title');
  assert.ok(starsIndex > evidenceIndex, 'stars should render after Chinese evidence');
  assert.ok(tagsIndex > starsIndex, 'tags should stay on the same metadata line after stars');
}

function testQuickLinksCenterTextAndDetachIcon() {
  const sidebar = loadSidebarForTest('#/');
  const tools = sidebar.__test;
  assert.equal(typeof tools.renderQuickLink, 'function');
  assert.equal(typeof tools.renderSidebarHeader, 'function');
  assert.equal(typeof tools.renderFeedbackQuickButton, 'function');

  const html = tools.renderQuickLink('dpr-sidebar-quick-home', '#/', '🏠', '首页');
  assert.ok(html.includes('class="dpr-sidebar-quick dpr-sidebar-quick-home"'));
  assert.ok(html.includes('<span class="dpr-sidebar-quick-label"><span class="dpr-sidebar-quick-icon" aria-hidden="true">🏠</span>首页</span>'));

  const feedbackHtml = tools.renderFeedbackQuickButton();
  assert.ok(feedbackHtml.includes('<button type="button" class="dpr-sidebar-quick dpr-sidebar-feedback-btn"'));
  assert.ok(feedbackHtml.includes('data-sidebar-feedback'));
  assert.ok(feedbackHtml.includes('aria-label="打开反馈"'));
  assert.ok(feedbackHtml.includes('<span class="dpr-sidebar-quick-label"><span class="dpr-sidebar-quick-icon" aria-hidden="true">💬</span>反馈</span>'));

  const headerHtml = tools.renderSidebarHeader('#/', '#/tutorial/README', '首页', '使用教程');
  const homeIndex = headerHtml.indexOf('dpr-sidebar-quick-home');
  const tutorialIndex = headerHtml.indexOf('dpr-sidebar-quick-tutorial');
  const feedbackIndex = headerHtml.indexOf('dpr-sidebar-feedback-btn');
  assert.ok(homeIndex >= 0 && tutorialIndex > homeIndex && feedbackIndex > tutorialIndex);
  assert.ok(headerHtml.includes('aria-hidden="true">📖</span>教程</span>'));

  const sidebarTemplate = fs.readFileSync('docs_init/_sidebar.md', 'utf8').split('\n').slice(0, 3).join('\n');
  assert.ok(sidebarTemplate.includes('data-dpr-hash="#/tutorial/README">教程</a>'));
  assert.ok(!sidebarTemplate.includes('>使用教程</a>'));

  const css = fs.readFileSync('app/app.css', 'utf8');
  const headerRule = cssRule(css, '.dpr-sidebar-header');
  assert.ok(/display:\s*grid/i.test(headerRule));
  assert.ok(/grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/i.test(headerRule));

  const quickRule = cssRule(css, '.dpr-sidebar-quick');
  assert.ok(/position:\s*relative/i.test(quickRule));
  assert.ok(/justify-content:\s*center/i.test(quickRule));
  assert.ok(/min-width:\s*0/i.test(quickRule));
  assert.ok(/width:\s*100%/i.test(quickRule));
  assert.ok(/box-sizing:\s*border-box/i.test(quickRule));
  assert.ok(/cursor:\s*pointer/i.test(quickRule));
  assert.ok(/overflow:\s*visible/i.test(quickRule));

  const labelRule = cssRule(css, '.dpr-sidebar-quick-label');
  assert.ok(/position:\s*relative/i.test(labelRule));
  assert.ok(/display:\s*inline-block/i.test(labelRule));
  assert.ok(/max-width:\s*100%/i.test(labelRule));
  assert.ok(/overflow:\s*visible/i.test(labelRule));
  assert.ok(/white-space:\s*nowrap/i.test(labelRule));
  assert.ok(/text-align:\s*center/i.test(labelRule));

  const iconRule = cssRule(css, '.dpr-sidebar-quick-icon');
  assert.ok(/position:\s*absolute/i.test(iconRule));
  assert.ok(/right:\s*calc\(100%\s*\+\s*4px\)/i.test(iconRule));
  assert.ok(/top:\s*50%/i.test(iconRule));
  assert.ok(/transform:\s*translateY\(-50%\)/i.test(iconRule));

  const feedbackRule = cssRule(css, '.dpr-sidebar-feedback-btn');
  assert.ok(/background:\s*#f0fdf4/i.test(feedbackRule));
  assert.ok(/border-color:\s*#86efac/i.test(feedbackRule));
  assert.ok(/color:\s*#166534/i.test(feedbackRule));
  assert.ok(/box-shadow:\s*inset 0 0 0 1px rgba\(34,\s*197,\s*94,\s*0\.1\)/i.test(feedbackRule));
  assert.ok(/@media \(max-width:\s*420px\)[\s\S]*\.dpr-sidebar-header\s*{[^}]*gap:\s*6px/i.test(css));
  assert.ok(/body\.dpr-dark \.dpr-sidebar-feedback-btn\s*{[^}]*background:\s*#123522/i.test(css));
}

function testFeedbackEntryClickContractAndFallbacks() {
  const sidebar = loadSidebarForTest('#/');
  const tools = sidebar.__test;
  assert.equal(typeof tools.openFeedbackPanel, 'function');

  const originalCustomEvent = global.CustomEvent;
  const dispatched = [];
  const openCalls = [];

  global.CustomEvent = function CustomEvent(name) {
    this.type = name;
  };
  document.dispatchEvent = (event) => {
    dispatched.push(event.type);
    return true;
  };
  document.createEvent = () => ({
    initCustomEvent(name) {
      this.type = name;
    },
  });

  window.DPRFeedback = {
    open() {
      openCalls.push('open');
    },
  };
  assert.equal(tools.openFeedbackPanel(), true);
  assert.deepEqual(openCalls, ['open']);
  assert.deepEqual(dispatched, []);

  delete window.DPRFeedback;
  assert.equal(tools.openFeedbackPanel(), false);
  assert.deepEqual(dispatched, ['dpr-open-feedback']);

  if (typeof originalCustomEvent === 'undefined') delete global.CustomEvent;
  else global.CustomEvent = originalCustomEvent;

  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf("var feedbackBtn = e.target.closest('.dpr-sidebar-feedback-btn');");
  const end = js.indexOf("var axisToggle = e.target.closest('.dpr-sidebar-axis-toggle');", start);
  assert.ok(start > 0 && end > start, 'feedback button click handler should be present');
  const block = js.slice(start, end);
  assert.ok(block.includes('e.preventDefault();'));
  assert.ok(block.includes('openFeedbackPanel();'));
  assert.ok(block.includes('if (isOverlaySidebarViewport()) {'));
  assert.ok(block.includes('toggleMobile(false);'));
}

function testSidebarFooterControlsReplaceRefresh() {
  const sidebar = loadSidebarForTest('#/');
  const tools = sidebar.__test;
  assert.equal(typeof tools.renderSidebarFooterControls, 'function');

  const html = tools.renderSidebarFooterControls(false);
  assert.ok(html.includes('class="dpr-sidebar-footer"'));
  assert.ok(html.includes('class="dpr-sidebar-footer-btn dpr-sidebar-collapse-btn"'));
  assert.ok(html.includes('data-sidebar-collapse'));
  assert.ok(html.includes('aria-label="收起侧边栏"'));
  assert.ok(html.includes('class="dpr-sidebar-footer-btn dpr-sidebar-settings-btn"'));
  assert.ok(html.includes('data-sidebar-settings'));
  assert.ok(html.includes('aria-label="打开设置"'));
  assert.ok(!html.includes('dpr-sidebar-refresh'));
  assert.ok(!html.includes('刷新'));

  const collapsedHtml = tools.renderSidebarFooterControls(true);
  assert.ok(collapsedHtml.includes('aria-label="展开侧边栏"'));
  assert.ok(collapsedHtml.includes('title="展开侧边栏"'));

  const css = fs.readFileSync('app/app.css', 'utf8');
  const bodyRule = cssRule(css, 'body.dpr-sidebar-v2');
  assert.ok(/--dpr-sidebar-collapsed-width:\s*0px/i.test(bodyRule));
  const contentRule = cssRule(css, 'body.dpr-sidebar-v2 .content');
  assert.ok(/left:\s*var\(--dpr-sidebar-width,\s*298px\)\s*!important/i.test(contentRule));
  assert.ok(/transition:\s*left \.24s ease,\s*width \.24s ease/i.test(contentRule));
  const footerRule = cssRule(css, '.dpr-sidebar-footer');
  assert.ok(/display:\s*flex/i.test(footerRule));
  assert.ok(/gap:\s*8px/i.test(footerRule));
  assert.ok(/margin-top:\s*auto/i.test(footerRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(footerRule));

  const footerBtnRule = cssRule(css, '.dpr-sidebar-footer-btn');
  assert.ok(/width:\s*34px/i.test(footerBtnRule));
  assert.ok(/height:\s*34px/i.test(footerBtnRule));
  assert.ok(/display:\s*inline-flex/i.test(footerBtnRule));

  const collapsedRootRule = cssRule(css, '#dpr-sidebar-v2.is-collapsed');
  assert.ok(/width:\s*var\(--dpr-sidebar-collapsed-width\)/i.test(collapsedRootRule));
  assert.ok(/border-right-color:\s*transparent/i.test(collapsedRootRule));
  assert.ok(/border-right-width:\s*0/i.test(collapsedRootRule));
  assert.ok(/overflow:\s*visible/i.test(collapsedRootRule));
  assert.ok(/pointer-events:\s*none/i.test(collapsedRootRule));
  const collapsedContentRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed .content');
  assert.ok(/left:\s*0\s*!important/i.test(collapsedContentRule));
  const collapsedFooterRule = cssRule(css, '#dpr-sidebar-v2.is-collapsed .dpr-sidebar-footer');
  assert.ok(/position:\s*fixed/i.test(collapsedFooterRule));
  assert.ok(/left:\s*12px/i.test(collapsedFooterRule));
  assert.ok(/padding:\s*0/i.test(collapsedFooterRule));
  assert.ok(/border:\s*0/i.test(collapsedFooterRule));
  assert.ok(/border-radius:\s*0/i.test(collapsedFooterRule));
  assert.ok(/box-shadow:\s*none/i.test(collapsedFooterRule));
  assert.ok(/background:\s*transparent/i.test(collapsedFooterRule));
  assert.ok(/pointer-events:\s*auto/i.test(collapsedFooterRule));
  assert.ok(/@media \(max-width:\s*1023px\)/i.test(css));
  assert.ok(/@media \(max-width:\s*1023px\)[\s\S]*body\.dpr-sidebar-v2 \.content\s*{[^}]*left:\s*0\s*!important/i.test(css));
  assert.ok(/@media \(max-width:\s*1023px\)[\s\S]*#dpr-sidebar-v2\s*{[^}]*transform:\s*translateX\(-100%\)/i.test(css));
  assert.ok(/\.dpr-sidebar-refresh/.test(css) === false, 'refresh button CSS should be removed');

  const uiScript = fs.readFileSync('app/ui.layout-and-subscriptions-entry.js', 'utf8');
  assert.ok(/function isDprSidebarV2Active\(\)/.test(uiScript));
  assert.ok(/function shouldUseDprSidebarInternalSettings\(\)/.test(uiScript));
  assert.ok(/window\.matchMedia\('\(min-width:\s*1024px\)'\)\.matches/i.test(uiScript));
  assert.ok(/if\s*\(shouldUseDprSidebarInternalSettings\(\)\)\s*return;/i.test(uiScript));
}

function testCollapsedSidebarRecentersChatSurface() {
  const css = fs.readFileSync('app/app.css', 'utf8');
  const v2InputRule = cssRule(css, 'body.dpr-sidebar-v2 #paper-chat-container .input-area');
  assert.ok(/left:\s*calc\(\s*var\(--dpr-sidebar-width,\s*298px\)\s*\+\s*\(100%\s*-\s*var\(--dpr-sidebar-width,\s*298px\)\)\s*\/\s*2\s*\)/i.test(v2InputRule));
  assert.ok(/max-width:\s*min\(var\(--dpr-paper-content-max-width\),\s*calc\(100%\s*-\s*var\(--dpr-sidebar-width,\s*298px\)\s*-\s*40px\)\)/i.test(v2InputRule));

  const collapsedInputRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed #paper-chat-container .input-area');
  assert.ok(/left:\s*50%/i.test(collapsedInputRule));
  assert.ok(/max-width:\s*min\(var\(--dpr-paper-content-max-width\),\s*calc\(100%\s*-\s*var\(--dpr-paper-content-gap-desktop\)\)\)/i.test(collapsedInputRule));

  const collapsedFooterRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed .chat-footer');
  assert.ok(/left:\s*50%/i.test(collapsedFooterRule));
  assert.ok(/max-width:\s*min\(var\(--dpr-paper-content-max-width\),\s*calc\(100%\s*-\s*var\(--dpr-paper-content-gap-desktop\)\)\)/i.test(collapsedFooterRule));

  const collapsedQuestionRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed #paper-chat-container .chat-questions-panel');
  assert.ok(/left:\s*50%/i.test(collapsedQuestionRule));
  assert.ok(/max-width:\s*min\(var\(--dpr-paper-content-max-width\),\s*calc\(100%\s*-\s*var\(--dpr-paper-content-gap-desktop\)\)\)/i.test(collapsedQuestionRule));

  const collapsedBeforeRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed #paper-chat-container::before');
  const collapsedAfterRule = cssRule(css, 'body.dpr-sidebar-v2.dpr-sidebar-v2-collapsed #paper-chat-container::after');
  assert.ok(/left:\s*0/i.test(collapsedBeforeRule));
  assert.ok(/left:\s*0/i.test(collapsedAfterRule));

  assert.ok(/@media \(max-width:\s*1023px\)[\s\S]*body\.dpr-sidebar-v2 #paper-chat-container \.input-area\s*{[^}]*left:\s*50%/i.test(css));
}

function testResponsiveModeClearsDesktopCollapsedStateOnOverlayViewports() {
  const sidebar = loadSidebarForTest('#/');
  const tools = sidebar.__test;
  assert.equal(typeof tools.syncResponsiveSidebarMode, 'function');

  const rootClassList = createClassList(['is-collapsed']);
  const bodyClassList = createClassList(['dpr-sidebar-v2', 'dpr-sidebar-v2-collapsed']);
  const collapseButton = {
    attrs: {},
    setAttribute(key, value) {
      this.attrs[key] = value;
    },
  };

  document.body.classList = bodyClassList;
  document.querySelector = (selector) => {
    if (selector === '#dpr-sidebar-v2') return { classList: rootClassList, querySelector: () => collapseButton };
    return null;
  };
  window.matchMedia = (query) => ({ matches: query.includes('max-width: 1023px') });

  tools.syncResponsiveSidebarMode();

  assert.equal(rootClassList.contains('is-collapsed'), false);
  assert.equal(bodyClassList.contains('dpr-sidebar-v2-collapsed'), false);
  assert.equal(collapseButton.attrs['aria-label'], '收起侧边栏');
}

function testSidebarSortsByNewestTimeFirst() {
  const sidebar = loadSidebarForTest('#/202606/25/new');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(unorderedSidebar);

  const dailyView = tools.buildDailyDateView(model, '');
  assert.deepEqual(dailyView.tabs.map((tab) => tab.key), ['20260625', '20260623']);

  const confView = tools.buildConferenceConfView(model, '');
  assert.deepEqual(confView.tabs.map((tab) => tab.key), ['iclr-2025', 'neurips-2024']);

  const neuripsView = tools.buildConferenceConfView(model, 'neurips-2024');
  assert.deepEqual(neuripsView.groups[0].papers.map((paper) => paper.title), ['Conf New', 'Conf Old']);
}

function testSidebarUtilityHelpers() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;

  assert.equal(typeof tools.statusForMarkIndex, 'function');
  assert.equal(tools.statusForMarkIndex('1'), 'good');
  assert.equal(tools.statusForMarkIndex('2'), 'blue');
  assert.equal(tools.statusForMarkIndex('3'), 'orange');
  assert.equal(tools.statusForMarkIndex('4'), 'bad');
  assert.equal(tools.statusForMarkIndex('5'), '');

  assert.equal(typeof tools.shouldAutoMarkRead, 'function');
  assert.equal(tools.shouldAutoMarkRead(''), true);
  assert.equal(tools.shouldAutoMarkRead(null), true);
  assert.equal(tools.shouldAutoMarkRead('read'), false);
  assert.equal(tools.shouldAutoMarkRead('good'), false);

  assert.equal(typeof tools.clampSidebarWidth, 'function');
  assert.equal(tools.clampSidebarWidth(undefined), 298);
  assert.equal(tools.clampSidebarWidth(180), 240);
  assert.equal(tools.clampSidebarWidth(360), 360);
  assert.equal(tools.clampSidebarWidth(720), 520);
  assert.equal(typeof tools.loadPersistedSidebarWidth, 'function');
  global.window.localStorage.getItem = () => '373';
  assert.equal(tools.loadPersistedSidebarWidth(), 298);
  global.window.localStorage.getItem = () => '360';
  assert.equal(tools.loadPersistedSidebarWidth(), 360);
  global.window.localStorage.getItem = () => null;
  assert.equal(tools.loadPersistedSidebarWidth(), 298);

  assert.equal(typeof tools.rerenderOptionsForReadStateEvent, 'function');
  assert.deepEqual(tools.rerenderOptionsForReadStateEvent(), {
    syncActive: true,
    centerActive: false,
    autoMark: false,
    preserveScroll: true,
  });
  assert.equal(typeof tools.rerenderOptionsForStatusClick, 'function');
  assert.deepEqual(tools.rerenderOptionsForStatusClick(), {
    updateInPlace: true,
    syncActive: false,
    centerActive: false,
    autoMark: false,
    preserveScroll: true,
    dispatchUpdated: false,
  });
  assert.equal(typeof tools.syncActiveOptionsForInitialLoad, 'function');
  assert.deepEqual(tools.syncActiveOptionsForInitialLoad(), {
    center: true,
    autoMark: false,
  });
  assert.equal(typeof tools.rerenderOptionsForAxisInteraction, 'function');
  assert.deepEqual(tools.rerenderOptionsForAxisInteraction('daily'), {
    syncActive: false,
    scrollPanel: 'daily',
  });
  assert.equal(typeof tools.rerenderOptionsForAxisControlClick, 'function');
  assert.deepEqual(tools.rerenderOptionsForAxisControlClick(), {
    syncActive: false,
    centerActive: false,
    autoMark: false,
    preserveScroll: true,
    dispatchUpdated: false,
  });

  assert.equal(typeof tools.updatePaperTitleOverflowMarks, 'function');
  function fakePaper(scrollWidth, clientWidth) {
    const marks = {};
    const title = { scrollWidth, clientWidth };
    const li = {
      classList: {
        toggle: (name, value) => {
          marks[name] = value;
        },
      },
      querySelector: (selector) => selector === '.dpr-sidebar-paper-title' ? title : null,
    };
    return { li, marks };
  }
  const overflowing = fakePaper(160, 100);
  const fitting = fakePaper(98, 100);
  tools.updatePaperTitleOverflowMarks({
    querySelectorAll: (selector) => selector === '.dpr-sidebar-paper'
      ? [overflowing.li, fitting.li]
      : [],
  });
  assert.equal(overflowing.marks['is-title-overflowing'], true);
  assert.equal(fitting.marks['is-title-overflowing'], false);
}

function testEvidenceCssIsPersistent() {
  const css = fs.readFileSync('app/app.css', 'utf8');
  assert.ok(!/\\.dpr-sidebar-paper-evidence\\s*{[^}]*display:\\s*none/i.test(css));
  assert.ok(!/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-evidence\s*{[^}]*display:\s*none/i.test(css));
  assert.ok(/\.dpr-sidebar-paper-actions\s*{[^}]*opacity:\s*0/i.test(css));
  assert.ok(css.includes('.dpr-sidebar-paper:hover .dpr-sidebar-paper-actions'));
  assert.ok(/\.dpr-sidebar-paper-evidence\s*{[^}]*background:\s*transparent/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\.dpr-sidebar-paper-conference\s*{[^}]*border-left-color:\s*#93c5fd/i.test(css));
}

function testSidebarPaperVisualStateCssContract() {
  const css = fs.readFileSync('app/app.css', 'utf8');
  const paperRule = cssRule(css, '.dpr-sidebar-paper');
  const scopedPaperRule = cssRule(css, '#dpr-sidebar-v2 .dpr-sidebar-paper');
  assert.ok(/\.dpr-sidebar-paper\s*{[^}]*background:\s*#ffffff/i.test(css));
  assert.ok(/margin:\s*8px 8px/i.test(paperRule));
  assert.ok(/\.dpr-sidebar-paper\s*{[^}]*min-height:\s*68px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\.is-active\s*{[^}]*background:\s*#e5e7eb/i.test(css));
  assert.ok(/body\.dpr-dark \.dpr-sidebar-paper\.is-active\s*{[^}]*background:\s*#334155/i.test(css));
  assert.ok(!css.includes('dpr-sidebar-unread-dot'));
  assert.ok(!css.includes('dpr-sidebar-axis-tab-dot'));
  assert.ok(!css.includes('dpr-sidebar-axis-section-dot'));
  assert.ok(/#dpr-sidebar-v2\s+\.dpr-sidebar-paper\s*{[^}]*position:\s*relative\s*!important/i.test(css));
  assert.ok(/margin:\s*8px 8px/i.test(scopedPaperRule));
  assert.ok(!/#dpr-sidebar-v2\s+\.dpr-sidebar-paper\s*{[^}]*margin:\s*2px 8px\s*!important/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*content:\s*""/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*background:\s*#ef4444/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*right:\s*6px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*top:\s*7px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*width:\s*8px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*height:\s*8px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*box-shadow:\s*0 0 0 2px #ffffff,\s*0 0 5px rgba\(239,\s*68,\s*68,\s*\.45\)/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read="0"\]::after\s*{[^}]*z-index:\s*6/i.test(css));
  assert.ok(!/#dpr-sidebar-v2\.is-filter-unread\s+\.dpr-sidebar-paper\[data-read="1"\]\s*{[^}]*display:\s*none/i.test(css));
  assert.ok(!/#dpr-sidebar-v2\.is-filter-unread\s+\.dpr-sidebar-paper\.is-active\[data-read="1"\]/i.test(css));
  assert.ok(!css.includes('.dpr-sidebar-axis-section.is-all-read:has(.dpr-sidebar-paper.is-active)'));
  assert.ok(!/#dpr-sidebar-v2\.is-filter-unread\s+\.dpr-sidebar-axis-section\.is-all-read\s*{[^}]*display:\s*none/i.test(css));
  assert.ok(!/#dpr-sidebar-v2\.is-filter-unread\s+\.dpr-sidebar-axis-section\.is-all-read\.has-active-paper/i.test(css));

  const mainRule = cssRule(css, '.dpr-sidebar-paper-main');
  assert.ok(/display:\s*block/i.test(mainRule));
  assert.ok(/position:\s*relative/i.test(mainRule));
  assert.ok(/min-width:\s*0/i.test(mainRule));

  const linkRule = cssRule(css, '.dpr-sidebar-paper-link');
  assert.ok(/width:\s*100%/i.test(linkRule));
  assert.ok(/box-sizing:\s*border-box/i.test(linkRule));
  assert.ok(/padding:\s*7px 8px 7px 14px/i.test(linkRule));

  const titleRule = cssRule(css, '.dpr-sidebar-paper-title');
  assert.ok(/display:\s*block/i.test(titleRule));
  assert.ok(/position:\s*relative/i.test(titleRule));
  assert.ok(/font-size:\s*14px/i.test(titleRule));
  assert.ok(/white-space:\s*nowrap/i.test(titleRule));
  assert.ok(/overflow:\s*hidden/i.test(titleRule));
  assert.ok(/text-overflow:\s*clip/i.test(titleRule));
  assert.ok(/width:\s*calc\(100%\s*-\s*2ch\)/i.test(titleRule));
  assert.ok(/padding-right:\s*calc\(20px \+ 1ch\)/i.test(titleRule));
  assert.ok(/box-sizing:\s*border-box/i.test(titleRule));
  assert.ok(!/-webkit-line-clamp/i.test(titleRule));

  const titleDotsRule = cssRule(css, '.dpr-sidebar-paper-title::after');
  assert.ok(/content:\s*""/i.test(titleDotsRule));
  assert.ok(/position:\s*absolute/i.test(titleDotsRule));
  assert.ok(/right:\s*-8px/i.test(titleDotsRule));
  assert.ok(/width:\s*calc\(28px \+ 3ch\)/i.test(titleDotsRule));
  assert.ok(/padding-left:\s*0/i.test(titleDotsRule));
  assert.ok(!/linear-gradient/i.test(titleDotsRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-paper-bg\)/i.test(titleDotsRule));
  assert.ok(/text-align:\s*left/i.test(titleDotsRule));
  assert.ok(/opacity:\s*0/i.test(titleDotsRule));

  assert.ok(!/\.dpr-sidebar-paper\.is-title-overflowing \.dpr-sidebar-paper-title::after\s*{[^}]*opacity:\s*1/i.test(css));
  assert.ok(/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-title,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-title\s*{[^}]*padding-right:\s*calc\(var\(--dpr-sidebar-paper-action-reserve\) \+ 1ch\)/i.test(css));
  assert.ok(/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-title::after,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-title::after\s*{[^}]*right:\s*-8px/i.test(css));
  assert.ok(/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-title::after,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-title::after\s*{[^}]*width:\s*calc\(\(var\(--dpr-sidebar-paper-action-reserve\) \+ 8px \+ 2ch\) \* 0\.66\)/i.test(css));
  assert.ok(/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-title::after,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-title::after\s*{[^}]*opacity:\s*1/i.test(css));

  const actionsRule = cssRule(css, '.dpr-sidebar-paper-actions');
  assert.ok(/position:\s*absolute/i.test(actionsRule));
  assert.ok(/right:\s*10px/i.test(actionsRule));
  assert.ok(/top:\s*50%/i.test(actionsRule));
  assert.ok(/transform:\s*translateY\(-50%\)/i.test(actionsRule));
  assert.ok(/width:\s*39px/i.test(actionsRule));

  assert.ok(/\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-evidence,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-evidence,\s*\.dpr-sidebar-paper:hover \.dpr-sidebar-paper-meta,\s*\.dpr-sidebar-paper:focus-within \.dpr-sidebar-paper-meta\s*{[^}]*padding-right:\s*var\(--dpr-sidebar-paper-action-reserve\)/i.test(css));

  const sectionLabelRule = cssRule(css, '.dpr-sidebar-axis-section-label');
  assert.ok(/font-size:\s*13px/i.test(sectionLabelRule));
  assert.ok(/line-height:\s*1\.25/i.test(sectionLabelRule));
  assert.ok(/padding:\s*7px 14px 6px 0/i.test(sectionLabelRule));
  assert.ok(/box-sizing:\s*border-box/i.test(sectionLabelRule));
  assert.ok(/(?:^|\n)\.dpr-sidebar-day-counts\s*{[^}]*font-size:\s*12px/i.test(css));
  const sectionCountRule = cssRule(css, '.dpr-sidebar-axis-section-label > .dpr-sidebar-day-counts');
  assert.ok(/font-size:\s*12\.5px/i.test(sectionCountRule));
  const metaRule = cssRule(css, '.dpr-sidebar-paper-meta');
  assert.ok(/font-size:\s*12px/i.test(metaRule));
  const starsRule = cssRule(css, '.dpr-sidebar-paper-stars');
  assert.ok(/font-size:\s*12px/i.test(starsRule));
  const tagRule = cssRule(css, '.dpr-sidebar-paper-tag');
  assert.ok(/font-size:\s*11px/i.test(tagRule));
  const evidenceRule = cssRule(css, '.dpr-sidebar-paper-evidence');
  assert.ok(/font-size:\s*12px/i.test(evidenceRule));

  const readRowRule = /\.dpr-sidebar-paper\[data-read-status="read"\]\s*{[^}]*background:/i;
  assert.ok(!readRowRule.test(css), 'read should not paint the whole row');

  assert.ok(/\.dpr-sidebar-paper\[data-read-status="good"\]\s*{[^}]*background:\s*#f0fdf4/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read-status="bad"\]\s*{[^}]*background:\s*#fef2f2/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read-status="blue"\]\s*{[^}]*background:\s*#eff6ff/i.test(css));
  assert.ok(/\.dpr-sidebar-paper\[data-read-status="orange"\]\s*{[^}]*background:\s*#faf5ff/i.test(css));

  const activeGoodRule = cssRule(css, '.dpr-sidebar-paper-status-good.is-active');
  const activeBlueRule = cssRule(css, '.dpr-sidebar-paper-status-blue.is-active');
  const activeOrangeRule = cssRule(css, '.dpr-sidebar-paper-status-orange.is-active');
  const activeBadRule = cssRule(css, '.dpr-sidebar-paper-status-bad.is-active');
  assert.ok(/background:\s*#86efac/i.test(activeGoodRule));
  assert.ok(/color:\s*#16a34a/i.test(activeGoodRule));
  assert.ok(/background:\s*#93c5fd/i.test(activeBlueRule));
  assert.ok(/color:\s*#2563eb/i.test(activeBlueRule));
  assert.ok(/background:\s*#c4b5fd/i.test(activeOrangeRule));
  assert.ok(/color:\s*#7c3aed/i.test(activeOrangeRule));
  assert.ok(/background:\s*#fca5a5/i.test(activeBadRule));
  assert.ok(/color:\s*#dc2626/i.test(activeBadRule));
}

function testSidebarStickyHierarchyCssContract() {
  const css = fs.readFileSync('app/app.css', 'utf8');
  const rootRule = cssRule(css, '#dpr-sidebar-v2');
  assert.ok(/--dpr-sidebar-surface:\s*#ffffff/i.test(rootRule));
  assert.ok(/--dpr-sidebar-paper-action-reserve:\s*calc\(52px \+ 2ch\)/i.test(rootRule));
  assert.ok(/--dpr-sidebar-sticky-mask-bg:\s*var\(--dpr-sidebar-surface\)/i.test(rootRule));
  assert.ok(/--dpr-sidebar-sticky-mask-bleed:\s*8px/i.test(rootRule));
  assert.ok(/--dpr-sidebar-sticky-panel-top:\s*0px/i.test(rootRule));
  assert.ok(/--dpr-sidebar-sticky-axis-top:\s*36px/i.test(rootRule));
  assert.ok(/--dpr-sidebar-sticky-section-top:\s*86px/i.test(rootRule));
  assert.ok(/width:\s*var\(--dpr-sidebar-width,\s*298px\)/i.test(rootRule));

  const panelHeaderBaseRule = cssRule(css, '.dpr-sidebar-panel-header');
  assert.ok(/padding:\s*8px 14px/i.test(panelHeaderBaseRule));

  const panelHeaderRule = cssRule(css, '.dpr-sidebar-panel.is-expanded > .dpr-sidebar-panel-header');
  assert.ok(/position:\s*sticky/i.test(panelHeaderRule));
  assert.ok(/top:\s*var\(--dpr-sidebar-sticky-panel-top\)/i.test(panelHeaderRule));
  assert.ok(/z-index:\s*18/i.test(panelHeaderRule));
  assert.ok(/isolation:\s*isolate/i.test(panelHeaderRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-sticky-mask-bg\)/i.test(panelHeaderRule));

  const axisRowRule = cssRule(css, '.dpr-sidebar-panel.is-expanded > .dpr-sidebar-panel-content > .dpr-sidebar-axis-row');
  assert.ok(/position:\s*sticky/i.test(axisRowRule));
  assert.ok(/top:\s*var\(--dpr-sidebar-sticky-axis-top\)/i.test(axisRowRule));
  assert.ok(/z-index:\s*17/i.test(axisRowRule));
  assert.ok(/isolation:\s*isolate/i.test(axisRowRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-sticky-mask-bg\)/i.test(axisRowRule));

  const axisRowBaseRule = cssRule(css, '.dpr-sidebar-axis-row');
  assert.ok(/min-height:\s*46px/i.test(axisRowBaseRule));
  assert.ok(/box-sizing:\s*border-box/i.test(axisRowBaseRule));

  const axisToggleRule = cssRule(css, '.dpr-sidebar-axis-toggle');
  assert.ok(/display:\s*inline-flex/i.test(axisToggleRule));
  assert.ok(/align-items:\s*center/i.test(axisToggleRule));
  assert.ok(/justify-content:\s*center/i.test(axisToggleRule));
  assert.ok(/box-sizing:\s*border-box/i.test(axisToggleRule));
  assert.ok(/padding:\s*0/i.test(axisToggleRule));

  const axisTabsRule = cssRule(css, '.dpr-sidebar-axis-tabs');
  assert.ok(/padding-top:\s*2px/i.test(axisTabsRule));
  assert.ok(!/margin-top:\s*-/i.test(axisTabsRule));

  const calendarRule = cssRule(css, '.dpr-sidebar-calendar');
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(calendarRule));
  assert.ok(/border-radius:\s*8px/i.test(calendarRule));
  assert.ok(/--dpr-sidebar-calendar-notch:\s*10px/i.test(calendarRule));
  assert.ok(/clip-path:\s*polygon\(/i.test(calendarRule));
  const calendarHeaderRule = cssRule(css, '.dpr-sidebar-calendar-header');
  assert.ok(/padding:\s*0 8px/i.test(calendarHeaderRule));
  const calendarGridRule = cssRule(css, '.dpr-sidebar-calendar-grid');
  assert.ok(/display:\s*grid/i.test(calendarGridRule));
  assert.ok(/grid-template-columns:\s*repeat\(7,\s*minmax\(0,\s*1fr\)\)/i.test(calendarGridRule));
  const calendarDayRule = cssRule(css, '.dpr-sidebar-calendar-day');
  assert.ok(/min-height:\s*42px/i.test(calendarDayRule));
  assert.ok(/position:\s*relative/i.test(calendarDayRule));
  assert.ok(/\.dpr-sidebar-calendar-day\s*{[\s\S]*flex-direction:\s*column/i.test(css));
  const calendarDayCountsRule = cssRule(css, '.dpr-sidebar-calendar-day-counts');
  assert.ok(/position:\s*absolute/i.test(calendarDayCountsRule));
  assert.ok(/left:\s*4px/i.test(calendarDayCountsRule));
  assert.ok(/right:\s*4px/i.test(calendarDayCountsRule));
  assert.ok(/bottom:\s*5px/i.test(calendarDayCountsRule));
  assert.ok(/display:\s*grid/i.test(calendarDayCountsRule));
  assert.ok(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/i.test(calendarDayCountsRule));
  assert.ok(/column-gap:\s*4px/i.test(calendarDayCountsRule));
  const calendarDayTotalRule = cssRule(css, '.dpr-sidebar-calendar-day-total');
  assert.ok(/min-width:\s*0/i.test(calendarDayTotalRule));
  assert.ok(/text-align:\s*right/i.test(calendarDayTotalRule));
  assert.ok(/color:\s*#94a3b8/i.test(calendarDayTotalRule));
  const calendarDayUnreadRule = cssRule(css, '.dpr-sidebar-calendar-day-unread');
  assert.ok(/min-width:\s*0/i.test(calendarDayUnreadRule));
  assert.ok(/text-align:\s*left/i.test(calendarDayUnreadRule));

  const sectionHeaderRule = cssRule(css, '.dpr-sidebar-panel.is-expanded .dpr-sidebar-axis-section-header');
  assert.ok(/position:\s*sticky/i.test(sectionHeaderRule));
  assert.ok(/top:\s*var\(--dpr-sidebar-sticky-section-top\)/i.test(sectionHeaderRule));
  assert.ok(/z-index:\s*16/i.test(sectionHeaderRule));
  assert.ok(/isolation:\s*isolate/i.test(sectionHeaderRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-sticky-mask-bg\)/i.test(sectionHeaderRule));
  const dailySectionHeaderRule = cssRule(css, '.dpr-sidebar-panel.is-expanded.dpr-sidebar-group-daily .dpr-sidebar-axis-section-header');
  assert.ok(/top:\s*var\(--dpr-sidebar-sticky-axis-top\)/i.test(dailySectionHeaderRule));

  const panelHeaderMaskRule = cssRule(css, '.dpr-sidebar-panel.is-expanded > .dpr-sidebar-panel-header::before');
  assert.ok(/content:\s*""/i.test(panelHeaderMaskRule));
  assert.ok(/inset:\s*calc\(var\(--dpr-sidebar-sticky-mask-bleed\) \* -1\) 0 0 0/i.test(panelHeaderMaskRule));
  assert.ok(/background:\s*var\(--dpr-sidebar-sticky-mask-bg\)/i.test(panelHeaderMaskRule));
  assert.ok(/z-index:\s*-1/i.test(panelHeaderMaskRule));

  assert.ok(/\.dpr-sidebar-panel\.is-expanded > \.dpr-sidebar-panel-content > \.dpr-sidebar-axis-row::before,\s*\.dpr-sidebar-panel\.is-expanded \.dpr-sidebar-axis-section-header::before\s*{[^}]*content:\s*""/i.test(css));
  assert.ok(/\.dpr-sidebar-panel\.is-expanded > \.dpr-sidebar-panel-content > \.dpr-sidebar-axis-row::before,\s*\.dpr-sidebar-panel\.is-expanded \.dpr-sidebar-axis-section-header::before\s*{[^}]*inset:\s*calc\(var\(--dpr-sidebar-sticky-mask-bleed\) \* -1\) 0 0 0/i.test(css));
  assert.ok(!/\.dpr-sidebar-panel\.is-expanded > \.dpr-sidebar-panel-content > \.dpr-sidebar-axis-row::before,\s*\.dpr-sidebar-panel\.is-expanded \.dpr-sidebar-axis-section-header::before\s*{[^}]*inset:\s*calc\(var\(--dpr-sidebar-sticky-mask-bleed\) \* -1\) 0\s*;/i.test(css));
  assert.ok(/\.dpr-sidebar-panel\.is-expanded > \.dpr-sidebar-panel-content > \.dpr-sidebar-axis-row::before,\s*\.dpr-sidebar-panel\.is-expanded \.dpr-sidebar-axis-section-header::before\s*{[^}]*background:\s*var\(--dpr-sidebar-sticky-mask-bg\)/i.test(css));
  assert.ok(/\.dpr-sidebar-panel\.is-expanded > \.dpr-sidebar-panel-content > \.dpr-sidebar-axis-row::before,\s*\.dpr-sidebar-panel\.is-expanded \.dpr-sidebar-axis-section-header::before\s*{[^}]*z-index:\s*-1/i.test(css));

  const panelContentRule = cssRule(css, '.dpr-sidebar-panel-content');
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(panelContentRule));
  const axisContentRule = cssRule(css, '.dpr-sidebar-axis-content');
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(axisContentRule));
  const axisSectionRule = cssRule(css, '.dpr-sidebar-axis-section');
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(axisSectionRule));
  const papersRule = cssRule(css, '.dpr-sidebar-axis-papers');
  assert.ok(/background:\s*var\(--dpr-sidebar-surface\)/i.test(papersRule));
}

function testRenderBodyPutsConferenceAboveDaily() {
  const sidebar = loadSidebarForTest('#/conference/neurips-2024/paper-c');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.renderBodyHtml, 'function');
  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
  });
  assert.ok(html.indexOf('dpr-sidebar-group-conference') < html.indexOf('dpr-sidebar-group-daily'));
  assert.ok(html.includes('data-axis-group="conference"'));
  assert.ok(html.includes('data-axis-group="daily"'));
  assert.ok(html.includes('data-axis-mode="conf"'));
  assert.ok(html.includes('data-axis-mode="tag"'));
  assert.ok(html.includes('class="dpr-sidebar-calendar'));
}

function testTopLevelPanelsDefaultExpanded() {
  const sidebar = loadSidebarForTest('#/conference/neurips-2024/paper-c');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  const html = tools.renderBodyHtml(model, {});

  assert.ok(/data-panel="conference"/.test(html));
  assert.ok(/data-panel="daily"/.test(html));
  assert.ok(/dpr-sidebar-group-conference[^"]*is-expanded/.test(html));
  assert.ok(/dpr-sidebar-group-daily[^"]*is-expanded/.test(html));
  assert.ok(/data-panel-toggle="conference" aria-expanded="true"/.test(html));
  assert.ok(/data-panel-toggle="daily" aria-expanded="true"/.test(html));
}

function testActivePaperCanForceOpenTopLevelPanel() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf('function syncAxisStateToHref(href)');
  const end = js.indexOf('function buildDailyCalendarView', start);
  assert.ok(start > 0 && end > start, 'syncAxisStateToHref should be present');
  const block = js.slice(start, end);

  assert.ok(block.includes('state.expandedGroups[panel] = true'));
  assert.ok(block.includes("isBacktrackDateKey(daily.dateKey) ? 'backtrack' : 'daily'"));
  assert.ok(block.includes('state.expandedGroups.conference = true'));
  assert.ok(block.includes("state[dailyPanelField(panel, 'Tag')] = '__all__';"));
}

function testPanelHeaderClickOnlyChangesSidebarViewState() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const axisStart = js.indexOf("var axisToggle = e.target.closest('.dpr-sidebar-axis-toggle');");
  const start = js.indexOf("var panelHeader = e.target.closest('[data-panel-toggle]');");
  const end = js.indexOf("var calendarNav = e.target.closest('.dpr-sidebar-calendar-nav');", start);
  assert.ok(start > 0 && end > start, 'panel header click handler should be present');
  assert.ok(axisStart > 0 && axisStart < start, 'axis toggle should be handled before panel header buttons');
  const block = js.slice(start, end);

  assert.ok(block.includes("var panel = panelHeader.getAttribute('data-panel-toggle');"));
  assert.ok(block.includes('state.expandedGroups[panel] = !state.expandedGroups[panel];'));
  assert.ok(block.includes('rerenderSidebarBody(rerenderOptionsForPanelToggle(panel));'));
  assert.ok(!block.includes('state.expandedGroups.daily ='));
  assert.ok(!block.includes('state.expandedGroups.conference ='));
}

function testAxisSectionsAreExpandable() {
  const sidebar = loadSidebarForTest('#/conference/neurips-2024/paper-c');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.axisSectionStateKey, 'function');

  const sectionKey = tools.axisSectionStateKey('conference', 'conf', 'neurips-2024:rl');
  const collapsedHtml = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
  });

  assert.ok(!/class="[^"]*dpr-sidebar-axis-section-conference[^"]*is-expanded[^"]*"/.test(collapsedHtml));
  assert.ok(collapsedHtml.includes(`data-axis-section-toggle="${sectionKey}"`));
  assert.ok(collapsedHtml.includes('aria-expanded="false"'));

  const expandedHtml = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    expandedAxisSections: new Set([sectionKey]),
  });

  assert.ok(expandedHtml.includes('data-axis-section-toggle="' + sectionKey + '" aria-expanded="true"'));
  assert.ok(/class="[^"]*dpr-sidebar-axis-section-conference[^"]*is-expanded[^"]*"/.test(expandedHtml));
}

function testPanelCountsUseVisibleAxisSlice() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.computeModelReadSummary, 'function');

  const summary = tools.computeModelReadSummary(model, {
    '202606/24/paper-a': 'read',
    'conference/neurips-2024/paper-c': 'good',
  });

  assert.deepEqual(summary.total, { papers: 5, unread: 3 });
  assert.deepEqual(summary.daily, { papers: 3, unread: 2 });
  assert.deepEqual(summary.conference, { papers: 2, unread: 1 });

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    readMap: {
      '202606/24/paper-a': 'read',
      'conference/neurips-2024/paper-c': 'good',
    },
  });
  assert.deepEqual(panelHeaderCounts(html, 'conference'), { unread: 0, total: 1 });
  assert.deepEqual(panelHeaderCounts(html, 'daily'), { unread: 1, total: 2 });
}

function testSearchResultsComeFromFullModel() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.buildDailyResultView, 'function');

  const view = tools.buildDailyResultView(model, {
    keyword: 'paper d',
    readMap: {},
    unreadOnly: false,
  });

  assert.equal(view.resultMode, true);
  assert.deepEqual(view.groups.map((group) => group.label), ['2026-06-23']);
  assert.deepEqual(view.groups[0].papers.map((paper) => paper.title), ['Paper D']);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    search: 'paper d',
    filter: 'all',
    readMap: {},
  });
  assert.ok(html.includes('Paper D'));
  assert.ok(!html.includes('Paper A'));
  assert.ok(!html.includes('dpr-sidebar-group-conference'));
  assert.ok(html.includes('dpr-sidebar-group-daily'));
}

function testSearchNoResultsShowsEmptyState() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    search: 'not in sidebar',
    filter: 'all',
    readMap: {},
  });

  assert.ok(!html.includes('dpr-sidebar-group-conference'));
  assert.ok(!html.includes('dpr-sidebar-group-daily'));
  assert.ok(html.includes('dpr-sidebar-empty'));
}

function testUnreadResultsComeFromFullModel() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.buildDailyResultView, 'function');

  const view = tools.buildDailyResultView(model, {
    keyword: '',
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
    },
    unreadOnly: true,
  });

  assert.deepEqual(view.groups.map((group) => group.label), ['2026-06-23']);
  assert.deepEqual(view.groups[0].papers.map((paper) => paper.title), ['Paper D']);
}

function testUnreadFilterReusesNormalSidebarViews() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-b');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const readMap = {
    '202606/24/paper-a': 'read',
    'conference/iclr-2025/paper-e': 'read',
  };
  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    filter: 'unread',
    readMap: readMap,
  });

  assert.ok(html.includes('data-axis-group="conference"'));
  assert.ok(html.includes('data-axis-mode="conf"'));
  assert.ok(html.includes('data-axis-key="neurips-2024"'));
  assert.ok(!html.includes('data-axis-key="__results__"'));
  assert.ok(!html.includes('dpr-sidebar-axis-row-results'));
  assert.ok(!html.includes('未读搜索'));
  assert.ok(!html.includes('>未读<'));

  assert.ok(html.includes('class="dpr-sidebar-calendar'));
  assert.ok(html.includes('data-calendar-date="20260624"'));
  assert.ok(html.includes('data-calendar-date="20260623"'));
  assert.ok(html.includes('data-axis-tab="daily"'));
  assert.ok(html.includes('data-axis-key="__all__"'));
  assert.ok(html.includes('title="标签上置"'));

  assert.ok(!html.includes('Paper A'));
  assert.ok(html.includes('Paper B'));
  assert.ok(html.includes('Paper C'));
  assert.ok(!html.includes('Paper E'));

  const dailyView = tools.buildAxisViewForMode(model, 'daily', 'date', {
    dailyViewMode: 'date',
    activeDailyDate: '20260624',
    filter: 'unread',
    readMap: readMap,
  }, readMap);
  assert.equal(dailyView.resultMode, undefined);
  assert.equal(dailyView.activeDateKey, '20260624');
  assert.equal(dailyView.activeKey, '__all__');
  assert.deepEqual(dailyView.groups[0].papers.map((paper) => paper.title), ['Paper B']);

  const confView = tools.buildAxisViewForMode(model, 'conference', 'conf', {
    conferenceViewMode: 'conf',
    activeConference: 'neurips-2024',
    filter: 'unread',
    readMap: readMap,
  }, readMap);
  assert.equal(confView.resultMode, undefined);
  assert.deepEqual(confView.tabs.map((tab) => tab.key), ['neurips-2024']);
  assert.deepEqual(confView.groups[0].papers.map((paper) => paper.title), ['Paper C']);
}

function testUnreadResultsKeepCurrentReadPaperVisible() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);

  const view = tools.buildDailyResultView(model, {
    keyword: '',
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
    },
    unreadOnly: true,
    currentPaperId: '202606/24/paper-a',
  });

  assert.deepEqual(view.groups.map((group) => group.label), ['2026-06-24', '2026-06-23']);
  assert.deepEqual(view.groups[0].papers.map((paper) => paper.title), ['Paper A']);
  assert.equal(view.groups[0].unreadCount, 0);
  assert.equal(view.tabs[0].unreadCount, 1);

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    filter: 'unread',
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
    },
  });
  assert.ok(html.includes('Paper A'));
  assert.ok(html.includes('data-paper-id="202606/24/paper-a"'));
  assert.ok(html.includes('data-read="1"'));
  assert.ok(/class="dpr-sidebar-axis-section dpr-sidebar-axis-section-daily[^"]*has-active-paper/.test(html));
  assert.ok(/class="dpr-sidebar-paper dpr-sidebar-paper-deep is-active"/.test(html));
}

function testUnreadSessionSnapshotKeepsSeenRowsVisibleUntilReload() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.collectUnreadPaperIdsForSnapshot, 'function');

  const snapshot = tools.collectUnreadPaperIdsForSnapshot(model, {
    '202606/23/paper-d': 'read',
  });
  assert.deepEqual(Array.from(snapshot).sort(), [
    '202606/24/paper-a',
    '202606/24/paper-b',
    'conference/iclr-2025/paper-e',
    'conference/neurips-2024/paper-c',
  ].sort());

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    filter: 'unread',
    unreadResultPaperIds: snapshot,
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
      '202606/23/paper-d': 'read',
      'conference/iclr-2025/paper-e': 'read',
      'conference/neurips-2024/paper-c': 'read',
    },
  });

  assert.ok(html.includes('Paper A'));
  assert.ok(html.includes('Paper B'));
  assert.ok(html.includes('Paper C'));
  assert.ok(html.includes('data-axis-key="iclr-2025"'));
  assert.ok(!html.includes('Paper E'));
  assert.ok(!html.includes('Paper D'));
  assert.equal((html.match(/data-read="1"/g) || []).length, 3);
  assert.equal((html.match(/data-read="0"/g) || []).length, 0);

  const iclrView = tools.buildAxisViewForMode(model, 'conference', 'conf', {
    conferenceViewMode: 'conf',
    activeConference: 'iclr-2025',
    filter: 'unread',
    unreadResultPaperIds: snapshot,
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
      '202606/23/paper-d': 'read',
      'conference/iclr-2025/paper-e': 'read',
      'conference/neurips-2024/paper-c': 'read',
    },
  });
  assert.deepEqual(iclrView.groups[0].papers.map((paper) => paper.title), ['Paper E']);
}

function testUnreadClickPendingHrefKeepsClickedPaperVisibleBeforeHashUpdates() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  const model = tools.parseSidebar(sampleSidebar);
  assert.equal(typeof tools.rememberPendingPaperHref, 'function');
  tools.rememberPendingPaperHref('#/202606/24/paper-b');

  const html = tools.renderBodyHtml(model, {
    expandedGroups: { conference: true, daily: true },
    conferenceViewMode: 'conf',
    dailyViewMode: 'date',
    activeConference: 'neurips-2024',
    activeDailyDate: '20260624',
    filter: 'unread',
    readMap: {
      '202606/24/paper-a': 'read',
      '202606/24/paper-b': 'read',
    },
  });

  assert.ok(!html.includes('Paper A'));
  assert.ok(html.includes('Paper B'));
  assert.ok(html.includes('data-paper-id="202606/24/paper-b"'));
  assert.ok(/class="dpr-sidebar-paper dpr-sidebar-paper-quick is-active"/.test(html));
  assert.ok(/class="dpr-sidebar-axis-section dpr-sidebar-axis-section-daily[^"]*has-active-paper/.test(html));
}

function testPaperLinkClickStoresPendingHrefBeforeRouteChange() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf("var paperLink = e.target.closest('.dpr-sidebar-paper-link');");
  const end = js.indexOf("// 顶部 Home / Tutorial", start);
  assert.ok(start > 0 && end > start, 'paper link click handler should be present');
  const block = js.slice(start, end);
  assert.ok(block.includes('rememberPendingPaperHref('));
  assert.ok(block.includes("paperLink.getAttribute('href')"));
}

function testStatusClickKeepsPaperRowInPlace() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf("var statusButton = e.target.closest('.dpr-sidebar-paper-status-btn');");
  const end = js.indexOf("var sectionToggle = e.target.closest('.dpr-sidebar-axis-section-header');", start);
  assert.ok(start > 0 && end > start, 'status button click handler should be present');
  const block = js.slice(start, end);
  assert.ok(block.includes('updateReadStateMarks();'));
  assert.ok(block.includes('applyFilterAndSearch();'));
  assert.ok(!block.includes('rerenderSidebarBody(rerenderOptionsForStatusClick())'));
  assert.ok(!block.includes('.blur('));
}

function testAxisControlClicksKeepSidebarScrollInPlace() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf("var axisToggle = e.target.closest('.dpr-sidebar-axis-toggle');");
  const end = js.indexOf("var statusButton = e.target.closest('.dpr-sidebar-paper-status-btn');", start);
  assert.ok(start > 0 && end > start, 'axis control click handlers should be present');
  const block = js.slice(start, end);
  assert.ok(block.includes('rerenderSidebarBody(rerenderOptionsForAxisControlClick())'));
  assert.ok(!block.includes('rerenderOptionsForAxisInteraction(axisGroup)'));
  assert.ok(!block.includes("rerenderOptionsForAxisInteraction('daily')"));
  assert.ok(!block.includes('rerenderOptionsForAxisInteraction(tabGroup)'));
}

function testAxisToggleCollapsesOnlyItsOwnPanel() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  const start = js.indexOf("var axisToggle = e.target.closest('.dpr-sidebar-axis-toggle');");
  const end = js.indexOf("var calendarNav = e.target.closest('.dpr-sidebar-calendar-nav');", start);
  assert.ok(start > 0 && end > start, 'axis toggle click handler should be present');
  const block = js.slice(start, end);

  assert.ok(block.includes('collapseAxisSectionsForGroup(axisGroup);'));
  assert.ok(block.includes('persistCollapse();'));
  assert.ok(!block.includes('state.expandedGroups[axisGroup] = false;'));
  assert.ok(!block.includes('state.expandedGroups.daily = false;'));
  assert.ok(!block.includes('state.expandedGroups.conference = false;'));
}

function testExpandedAxisSectionSetSerializesCorrectly() {
  const js = fs.readFileSync('app/dpr-sidebar.js', 'utf8');
  assert.ok(js.includes('Array.from(state.expandedAxisSections).forEach(function (key)'));
  assert.ok(js.includes('sections: state.expandedAxisSections ? Array.from(state.expandedAxisSections) : []'));
  assert.ok(!js.includes('Array.prototype.slice.call(state.expandedAxisSections)'));
}

function testReadStatusNormalization() {
  const sidebar = loadSidebarForTest('#/202606/24/paper-a');
  const tools = sidebar.__test;
  assert.ok(tools, 'dpr-sidebar.js should export test helpers');
  assert.equal(tools.normalizeReadStatus('good'), 'good');
  assert.equal(tools.normalizeReadStatus('bad'), 'bad');
  assert.equal(tools.normalizeReadStatus('blue'), 'blue');
  assert.equal(tools.normalizeReadStatus('orange'), 'orange');
  assert.equal(tools.normalizeReadStatus('read'), 'read');
  assert.equal(tools.normalizeReadStatus(true), 'read');
  assert.equal(tools.normalizeReadStatus(false), '');
  assert.equal(tools.normalizeReadStatus(null), '');
}

function testAnnualReviewReusesNativeSidebarReadingAndStatus() {
  const route = '20250910-20260909/2510.17595v1';
  const tools = loadSidebarForTest('#/' + route).__test;
  const payload = JSON.stringify({title: 'ATSP', score: 8, tags: [
    {kind: 'query', label: 'ATSP'}, {kind: 'paper', label: '核心'},
  ]}).replace(/"/g, '&quot;');
  const model = tools.parseSidebar('* Daily Papers\n' +
    '  * 2025-09-10 ～ 2026-09-09 <!--dpr-date:20250910-20260909-->\n' +
    '    * 速读区\n' +
    `      * <a href="#/${route}" data-sidebar-item="${payload}">ATSP</a>\n`);
  const view = tools.buildDailyCalendarTagView(model, '20260909', 'ATSP', {}, '202609');
  assert.equal(view.calendar.days.find(day => day.dateKey === '20260909').totalCount, 1);
  const html = tools.renderBodyHtml(model, {
    expandedGroups: {daily: true}, activeDailyDate: '20260909',
    readMap: {[route]: 'good'},
  });
  assert.ok(html.includes(`href="#/${route}"`));
  assert.ok(html.includes('data-panel="backtrack"'), '年度回溯独立分栏但复用原论文条目');
  assert.ok(html.includes('专题回溯'));
  assert.ok(!html.includes('data-panel="daily"'), '回溯不得重复计入日报');
  assert.ok(html.includes('data-paper-status="good"'));
  assert.ok(html.includes('data-read="1"'));
  assert.ok(!html.includes('target="_blank"'));
  const unreadHtml = tools.renderBodyHtml(model, {
    expandedGroups: {daily: true}, activeDailyDate: '20260909',
    filter: 'unread', currentPaperHref: '#/' + route,
    unreadResultPaperIds: [], readMap: {[route]: 'blue'},
  });
  assert.ok(unreadHtml.includes(`href="#/${route}"`), '首次切入未读也应保留当前正在阅读的论文');
  const source = fs.readFileSync(require.resolve('../app/dpr-sidebar.js'), 'utf8');
  assert.ok(!source.includes('dpr-long-range-nav'));
  assert.ok(!source.includes('独立报告，不计入日报未读数'));
}

function testBacktrackPanelKeepsIndependentNativeViews() {
  const tools = loadSidebarForTest('#/').__test;
  assert.equal(tools.isBacktrackDateKey('20260811-20260909'), false, '30天仍归日报');
  assert.equal(tools.isBacktrackDateKey('20260810-20260909'), true, '31天归专题回溯');
  assert.equal(tools.isBacktrackDateKey('20260612-20260909'), true, '90天归专题回溯');
  assert.equal(tools.isBacktrackDateKey('20250910-20260909'), true, '365天归专题回溯');
  const paper = (id, tag) => ({id, href: '#/' + id, title: id, tags: [{kind: 'query', label: tag}]});
  const model = {daily: [
    {dateKey: '20260909', papers: [paper('20260909/daily', 'RL')]},
    {dateKey: '20260811-20260909', papers: [paper('20260811-20260909/month', 'SR')]},
    {dateKey: '20250910-20260909', papers: [paper('20250910-20260909/annual', 'ATSP')]},
    {dateKey: '20260612-20260909', papers: [paper('20260612-20260909/quarter', 'SR')]},
  ], conferences: []};
  const readMap = {'20250910-20260909/annual': 'good'};
  const vs = {activeDailyDate: '20260909', activeDailyTag: 'RL',
    activeBacktrackDate: '20260909', activeBacktrackTag: 'ATSP', readMap};
  const daily = tools.buildAxisViewForMode(model, 'daily', 'tag', vs, readMap);
  const backtrack = tools.buildAxisViewForMode(model, 'backtrack', 'tag', vs, readMap);
  assert.deepEqual(daily.groups.flatMap(g => g.papers.map(p => p.title)), ['20260909/daily']);
  assert.deepEqual(backtrack.groups.flatMap(g => g.papers.map(p => p.title)), ['20250910-20260909/annual']);
  assert.equal(backtrack.calendar.days.find(d => d.dateKey === '20260909').totalCount, 1);
  assert.equal(backtrack.calendar.days.find(d => d.dateKey === '20260909').unreadCount, 0);
  const summary = tools.computeModelReadSummary(model, readMap);
  assert.deepEqual(summary.daily, {papers: 2, unread: 2});
  assert.deepEqual(summary.backtrack, {papers: 2, unread: 1});
  assert.deepEqual(summary.total, {papers: 4, unread: 3});
  const html = tools.renderBodyHtml(model, {...vs, expandedGroups: {daily: false, backtrack: true},
    backtrackCalendarPlacement: 'bottom', expandedAxisSections: new Set(['daily:tag:20260909:RL'])});
  assert.ok(html.includes('data-panel="backtrack"'));
  assert.ok(html.includes('data-panel="daily"'));
  assert.equal((html.match(/data-axis-toggle="backtrack"/g) || []).length, 0);
  assert.equal((html.match(/data-daily-calendar/g) || []).length, 1, '仅日报保留日历');
  assert.equal((html.match(/data-axis-toggle="daily"/g) || []).length, 1);
  assert.equal((html.match(/ href="#\/20250910-20260909\/annual"/g) || []).length, 1);
  assert.ok(!html.includes('target="_blank"'));
  const results = tools.buildAxisViewForMode(model, 'backtrack', 'results', {...vs, search: 'annual'}, readMap);
  assert.deepEqual(results.groups.flatMap(g => g.papers.map(p => p.title)), ['20250910-20260909/annual']);
  assert.equal(tools.resolveDailyAxisSectionStateKey(model, vs, readMap, 'backtrack'),
    'backtrack:tag:20250910-20260909:ATSP');
  const differentEnds = {daily: [model.daily[2], {
    dateKey: '20250101-20250401', papers: [paper('20250101-20250401/older', 'ATSP')],
  }], conferences: []};
  const allRanges = tools.buildAxisViewForMode(differentEnds, 'backtrack', 'tag', vs, readMap);
  assert.equal(allRanges.groups.length, 2, '无日历时不同结束日期的旧区间仍可访问');
}

testBacktrackPanelKeepsIndependentNativeViews();
testAnnualReviewReusesNativeSidebarReadingAndStatus();
testSidebarNavigationContract();
testAxisViewsForDailyAndConference();
testHyphenatedConferenceMarkerParsing();
testAxisTabsRenderUnreadCounts();
testDailyCalendarViewUsesMonthGridAndActiveDateOnly();
testDailyCalendarTagViewFiltersActiveDateByKeyword();
testDailyRangeReportsStayReachableFromCalendarEndDate();
testDailyRangeSelectableFromOrphanCalendarAnchorDay();
testDailyCalendarPlacementToggleKeepsControlRowFixedAboveLayers();
testConferenceAndDailyAxisTogglesRenderBesidePanelTitles();
testDailyCalendarInPlaceRefreshUsesActiveDailyTag();
testDailyAxisSectionKeyFollowsActiveDateAndTag();
testDailyDateAndTagClicksExpandCurrentSectionOnlyForDaily();
testPaperEvidenceAndActionButtonsRender();
testPaperMetaOrderKeepsEvidenceBetweenTitleAndStars();
testQuickLinksCenterTextAndDetachIcon();
testFeedbackEntryClickContractAndFallbacks();
testSidebarFooterControlsReplaceRefresh();
testCollapsedSidebarRecentersChatSurface();
testResponsiveModeClearsDesktopCollapsedStateOnOverlayViewports();
testSidebarSortsByNewestTimeFirst();
testSidebarUtilityHelpers();
testEvidenceCssIsPersistent();
testSidebarPaperVisualStateCssContract();
testSidebarStickyHierarchyCssContract();
testRenderBodyPutsConferenceAboveDaily();
testTopLevelPanelsDefaultExpanded();
testActivePaperCanForceOpenTopLevelPanel();
testPanelHeaderClickOnlyChangesSidebarViewState();
testAxisSectionsAreExpandable();
testPanelCountsUseVisibleAxisSlice();
testSearchResultsComeFromFullModel();
testSearchNoResultsShowsEmptyState();
testUnreadResultsComeFromFullModel();
testUnreadFilterReusesNormalSidebarViews();
testUnreadResultsKeepCurrentReadPaperVisible();
testUnreadSessionSnapshotKeepsSeenRowsVisibleUntilReload();
testUnreadClickPendingHrefKeepsClickedPaperVisibleBeforeHashUpdates();
testPaperLinkClickStoresPendingHrefBeforeRouteChange();
testStatusClickKeepsPaperRowInPlace();
testAxisControlClicksKeepSidebarScrollInPlace();
testAxisToggleCollapsesOnlyItsOwnPanel();
testExpandedAxisSectionSetSerializesCorrectly();
testReadStatusNormalization();

console.log('dpr sidebar v2 tests passed');
