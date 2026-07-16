const assert = require('assert');
const fs = require('fs');

const js = fs.readFileSync('app/docsify-plugin.js', 'utf8');
const css = fs.readFileSync('app/app.css', 'utf8');

function testPrefetchCachesMissingMarkdown() {
  const start = js.indexOf('const prefetchHref = async (href) => {');
  const end = js.indexOf('const prefetchAdjacent = () => {', start);
  assert.ok(start > 0 && end > start, 'prefetchHref should be present');
  const block = js.slice(start, end);

  assert.ok(
    /if\s*\(!res\.ok\)\s*{[\s\S]*PREFETCH_STATE\.cache\.set\(key,\s*{[\s\S]*missing:\s*true[\s\S]*}\);[\s\S]*return;/m.test(block),
    'prefetchHref should cache non-ok responses so missing paper markdown is not refetched on every sidebar update',
  );
}

testPrefetchCachesMissingMarkdown();

function testPaperPdfRowUsesPreviewAndDownloadActions() {
  const oldPdfLinkOnly = /<a class="paper-meta-link" href="\$\{escapeHtml\(meta\.pdf\)\}" target="_blank">/;
  assert.ok(!oldPdfLinkOnly.test(js), 'paper PDF row should not render the raw PDF URL as the primary click target');
  assert.ok(js.includes('data-pdf-preview-toggle'), 'paper PDF row should render a preview toggle');
  assert.ok(js.includes('data-pdf-url="${safePdf}"'), 'preview toggle should keep the PDF URL for the preview panel');
  assert.ok(js.includes('class="dpr-pdf-download-link"'), 'paper PDF row should render a separate download link');
  assert.ok(js.includes('download>下载 PDF</a>'), 'download link should be explicitly labelled');
  assert.ok(js.includes("const PDFJS_VIEWER_URL = 'https://mozilla.github.io/pdf.js/web/viewer.html'"), 'preview should use PDF.js viewer instead of raw PDF iframe');
  assert.ok(js.includes("const PDFJS_SCRIPT_URL = 'app/vendor/pdfjs/3.11.174/pdf.min.js'"), 'embedded preview should load the local PDF.js bundle');
  assert.ok(js.includes("const PDFJS_WORKER_URL = 'app/vendor/pdfjs/3.11.174/pdf.worker.min.js'"), 'embedded preview should configure the local PDF.js worker');
  assert.ok(js.includes('return `${PDFJS_VIEWER_URL}?file=${encodeURIComponent(parsed.href)}`;'), 'preview URL should wrap the raw PDF URL');
  assert.ok(js.includes("openLink.setAttribute('href', previewUrl);"), 'new-window preview should open the preview viewer rather than the raw PDF');
  assert.ok(!js.includes("openLink.setAttribute('href', url);"), 'new-window preview must not point at the raw PDF URL');
  assert.ok(js.includes('class="dpr-pdf-preview-stage"'), 'embedded preview should render into an in-page stage');
  assert.ok(js.includes('renderPdfIntoPanel(panel, url);'), 'preview toggle should render PDF pages in the side panel');
  assert.ok(!js.includes('class="dpr-pdf-preview-frame"'), 'embedded preview should not depend on browser iframe PDF rendering');
  assert.ok(/\.paper-meta-pdf-row\s*{[^}]*align-items:\s*center/i.test(css), 'PDF action row should vertically align buttons');
  assert.ok(/\.dpr-pdf-preview-stage\s*{[^}]*overflow:\s*auto/i.test(css), 'PDF preview stage should scroll rendered pages');
  assert.ok(/\.dpr-pdf-preview-page canvas\s*{[^}]*background:\s*#fff/i.test(css), 'PDF pages should render as visible canvas sheets');
  assert.ok(/\.markdown-section \.paper-meta-row \.dpr-pdf-download-link[\s\S]*?text-decoration:\s*none/i.test(css), 'download link should be styled as a compact action button');
}

testPaperPdfRowUsesPreviewAndDownloadActions();

function testPdfPreviewDoesNotHijackPaperChatLayout() {
  assert.ok(
    /\.dpr-pdf-preview-panel\s*{[^}]*z-index:\s*1600/i.test(css),
    'PDF preview panel should sit above paper chat controls instead of being covered by them',
  );
  assert.ok(
    /body\.dpr-pdf-preview-open\s*{[^}]*--dpr-pdf-preview-left-space:\s*calc\(100vw\s*-\s*var\(--dpr-pdf-preview-width\)\)/i.test(css),
    'PDF preview mode should expose the remaining left-side reading space as a layout variable',
  );
  assert.ok(
    /body\.dpr-sidebar-v2\.dpr-pdf-preview-open #paper-chat-container \.input-area[\s\S]*?--dpr-pdf-preview-left-space/i.test(css),
    'paper chat input should be centered in the left reading area while PDF preview is open',
  );
  assert.ok(
    /body\.dpr-pdf-preview-open\s*{[^}]*--dpr-pdf-preview-content-shift:\s*min\(/i.test(css),
    'PDF preview mode should compute a bounded content shift for the reading body',
  );
  assert.ok(
    /body\.dpr-paper-page\.dpr-pdf-preview-open \.markdown-section \.dpr-page-content:not\(\.dpr-page-enter\):not\(\.dpr-page-exit\)\s*{[^}]*transform:\s*translate3d\(calc\(-1 \* var\(--dpr-pdf-preview-content-shift,\s*0px\)\),\s*0,\s*0\)/i.test(css),
    'PDF preview mode should move only the page content wrapper left, not the whole article',
  );
  assert.ok(
    /body\.dpr-sidebar-v2\.dpr-pdf-preview-open #paper-chat-container::before,\s*body\.dpr-sidebar-v2\.dpr-pdf-preview-open #paper-chat-container::after\s*{[^}]*right:\s*var\(--dpr-pdf-preview-width\)/i.test(css),
    'paper chat bottom masks should stop before the PDF preview panel',
  );
  assert.ok(
    /@media \(max-width:\s*1180px\)[\s\S]*body\.dpr-pdf-preview-open #paper-chat-container \.input-area[\s\S]*display:\s*none/i.test(css),
    'narrow preview mode should hide paper chat controls so they cannot intercept the preview',
  );
  assert.ok(
    /@media \(min-width:\s*1024px\) and \(max-width:\s*1180px\)[\s\S]*body\.dpr-sidebar-v2\.dpr-pdf-preview-open\s*{[^}]*--dpr-pdf-preview-width:\s*min\(760px,\s*calc\(100vw\s*-\s*var\(--dpr-sidebar-width,\s*298px\)\)\)/i.test(css),
    'medium desktop preview width should leave the sidebar click target uncovered',
  );
  assert.ok(
    !/body\.dpr-paper-page\.dpr-pdf-preview-open article\.markdown-section\s*{[^}]*transform:/i.test(css),
    'PDF preview mode must not transform the markdown article because it breaks fixed chat positioning',
  );
}

testPdfPreviewDoesNotHijackPaperChatLayout();

console.log('docsify prefetch tests passed');
