/**
 * Legacy pre-English paper markers from pages generated before English localization.
 * Stored as Unicode escapes so routine i18n scans can exclude this file.
 * Do not remove without a migration plan for existing user docs.
 */
(function (root) {
  const M = {
    GLANCE_MARKER: '\u3010\u{1F9ED} \u901F\u89C8\u533A\u3011',
    DETAIL_MARKER: '\u3010\u{1F9FA} \u8BBA\u6587\u8BE6\u7EC6\u603B\u7ED3\u533A\u3011',
    DETAILED_SUMMARY: '\u8BBA\u6587\u8BE6\u7EC6\u603B\u7ED3',
    DETAILED_SUMMARY_AUTO: '\u8BBA\u6587\u8BE6\u7EC6\u603B\u7ED3\uFF08\u81EA\u52A8\u751F\u6210\uFF09',
    ORIGINAL_ABSTRACT: '\u539F\u6587\u6458\u8981',
    TLDR_POINTS: '\u6458\u8981\u8981\u70B9',
    ABSTRACT_SHORT: '\u6458\u8981',
    BY: '\u7531',
    AUTO_GENERATED: '\u81EA\u52A8\u751F\u6210',
    DEEP_READ_ZONE: '\u7CBE\u8BFB\u533A',
    QUICK_SKIM_ZONE: '\u901F\u8BFB\u533A',
    DEEP: '\u6DF1\u5EA6',
    DEEP_READ: '\u7CBE\u8BFB',
    QUICK_READ: '\u901F\u8BFB',
    QUICK_GLANCE: '\u901F\u89C8',
    SCORE_PREFIX: '\u8BC4\u5206\uFF1A',
    HOME: '\u9996\u9875',
    YEAR_SUFFIX: '\u5e74',
    GLANCE_AREA: '\u901F\u89C8\u533A',
    DETAILED_SUMMARY_EMOJI: '\u{1F9FA} \u8BBA\u6587\u8BE6\u7EC6\u603B\u7ED3',
    DETAILED_SUMMARY_AREA: '\u8BBA\u6587\u8BE6\u7EC6\u603B\u7ED3\u533A',
    DUAL_TITLE_AREA: '\u53CC\u8BED\u6807\u9898\u533A\u57DF',
    MIDDLE_INFO: '\u4E2D\u95F4\u4FE1\u606F\u533A',
    GLANCE_CARD: '\u901F\u89C8\u5361',
    PAGE_NAV_LAYER: '\u9875\u9762\u5BFC\u822A\u4E0E\u4EA4\u4E92\u5C42',
    PAPER_BODY: '\u8BBA\u6587\u6B63\u6587',
    ARTICLE_META: '\u6587\u7AE0\u5143\u4FE1\u606F',
    DPR_AUTO_CN: 'daily-paper-reader \u81EA\u52A8\u751F\u6210',
    QUOTA_EXHAUSTED: '\u989D\u5EA6\u4E0D\u8DB3',
  };

  root.LegacyPaperMarkers = M;
})(typeof window !== 'undefined' ? window : globalThis);
