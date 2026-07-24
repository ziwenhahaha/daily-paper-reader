const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const js = fs.readFileSync('app/docsify-plugin.js', 'utf8');
const css = fs.readFileSync('app/app.css', 'utf8');

function extractConstFunction(name) {
  const start = js.indexOf(`const ${name} =`);
  assert.ok(start >= 0, `${name} should be present`);
  const end = js.indexOf('\n      };', start);
  assert.ok(end > start, `${name} should have a complete function body`);
  return js.slice(start, end + '\n      };'.length);
}

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
  assert.ok(js.includes('class="dpr-pdf-preview-stage"'), 'embedded preview should render into an in-page stage');
  assert.ok(js.includes('renderPdfIntoPanel(panel, url);'), 'preview toggle should render PDF pages in the side panel');
  assert.ok(!js.includes('class="dpr-pdf-preview-frame"'), 'embedded preview should not depend on browser iframe PDF rendering');
  assert.ok(/\.paper-meta-pdf-row\s*{[^}]*align-items:\s*center/i.test(css), 'PDF action row should vertically align buttons');
  assert.ok(/\.dpr-pdf-preview-stage\s*{[^}]*overflow:\s*auto/i.test(css), 'PDF preview stage should scroll rendered pages');
  assert.ok(/\.dpr-pdf-preview-page canvas\s*{[^}]*background:\s*#fff/i.test(css), 'PDF pages should render as visible canvas sheets');
  assert.ok(/\.markdown-section \.paper-meta-row \.dpr-pdf-download-link[\s\S]*?text-decoration:\s*none/i.test(css), 'download link should be styled as a compact action button');
}

testPaperPdfRowUsesPreviewAndDownloadActions();

function testOpenReviewPreviewUsesOfficialTopLevelPage() {
  assert.ok(
    js.includes('const normalizePdfUrl = (url) => {'),
    'PDF preview should normalize provider-specific URLs before choosing a preview mode',
  );
  assert.ok(
    /parsed\.hostname\.toLowerCase\(\)\.endsWith\(['"]\.openreview\.net['"]\)/.test(js),
    'PDF preview should identify OpenReview URLs',
  );
  assert.ok(
    /parsed\.pathname\s*=\s*['"]\/pdf['"]/.test(js),
    'OpenReview forum URLs should be normalized to the official PDF endpoint',
  );
  assert.ok(
    /if\s*\(isOpenReviewPdfUrl\(normalizedUrl\)\)\s*{\s*return normalizedUrl;\s*}/m.test(js),
    'OpenReview new-window preview should use the official URL instead of the third-party PDF.js viewer',
  );
  assert.ok(
    /if\s*\(isOpenReviewPdfUrl\(previewUrl\)\)\s*{[\s\S]*closePdfPreview\(\);[\s\S]*window\.open\(previewUrl,\s*['"]_blank['"],\s*['"]noopener,noreferrer['"]\);[\s\S]*return;/m.test(js),
    'OpenReview preview clicks should open a top-level official page so browser verification can complete',
  );
}

testOpenReviewPreviewUsesOfficialTopLevelPage();

function runPdfPreviewClick(pdfUrl) {
  const button = {
    dataset: {},
    attributes: {
      'data-pdf-url': pdfUrl,
    },
    listener: null,
    textContent: '预览 PDF',
    addEventListener(type, listener) {
      assert.strictEqual(type, 'click');
      this.listener = listener;
    },
    getAttribute(name) {
      return this.attributes[name] || '';
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
  };
  const bodyClasses = new Set();
  const openLink = {
    href: '',
    setAttribute(name, value) {
      if (name === 'href') this.href = String(value);
    },
  };
  const panel = {
    dataset: {},
    querySelector(selector) {
      return selector === '.dpr-pdf-preview-open-link' ? openLink : null;
    },
  };
  const sandbox = {
    URL,
    button,
    document: {
      body: {
        classList: {
          contains(name) {
            return bodyClasses.has(name);
          },
          add(name) {
            bodyClasses.add(name);
          },
        },
      },
      querySelectorAll(selector) {
        assert.strictEqual(selector, '[data-pdf-preview-toggle]');
        return [button];
      },
    },
    window: {
      location: { href: 'https://reader.example/#/conference/icml-2025/paper' },
      openArgs: null,
      open(...args) {
        this.openArgs = args;
      },
    },
    closeCount: 0,
    ensureCount: 0,
    renderArgs: null,
    panel,
  };

  const source = [
    "const PDFJS_VIEWER_URL = 'https://mozilla.github.io/pdf.js/web/viewer.html';",
    'const closePdfPreview = () => { closeCount += 1; };',
    'const ensurePdfPreviewPanel = () => { ensureCount += 1; return panel; };',
    'const renderPdfIntoPanel = (...args) => { renderArgs = args; };',
    extractConstFunction('normalizePdfUrl'),
    extractConstFunction('isOpenReviewPdfUrl'),
    extractConstFunction('buildPdfPreviewUrl'),
    extractConstFunction('bindPdfPreviewToggle'),
    'bindPdfPreviewToggle();',
    'button.listener();',
  ].join('\n');

  vm.runInNewContext(source, sandbox);
  return {
    button,
    bodyClasses,
    closeCount: sandbox.closeCount,
    ensureCount: sandbox.ensureCount,
    openArgs: sandbox.window.openArgs && Array.from(sandbox.window.openArgs),
    openLinkHref: openLink.href,
    renderArgs: sandbox.renderArgs && Array.from(sandbox.renderArgs),
  };
}

function testOpenReviewPreviewClickBehavior() {
  const result = runPdfPreviewClick(
    'https://openreview.net/forum/?id=4sueqIwb4o#discussion',
  );
  assert.strictEqual(result.closeCount, 1, 'OpenReview preview should close any existing embedded panel');
  assert.strictEqual(result.ensureCount, 0, 'OpenReview preview should not create the cross-origin embedded panel');
  assert.deepStrictEqual(
    result.openArgs,
    ['https://openreview.net/pdf?id=4sueqIwb4o', '_blank', 'noopener,noreferrer'],
    'OpenReview preview should open the normalized official PDF as a top-level page',
  );
}

testOpenReviewPreviewClickBehavior();

function testArxivPreviewClickStillUsesEmbeddedPanel() {
  const pdfUrl = 'https://arxiv.org/pdf/1706.03762v1';
  const result = runPdfPreviewClick(pdfUrl);
  assert.strictEqual(result.closeCount, 0, 'arXiv preview should not close itself before opening');
  assert.strictEqual(result.ensureCount, 1, 'arXiv preview should keep using the embedded panel');
  assert.strictEqual(result.openArgs, null, 'arXiv preview should not open a new browser window');
  assert.ok(
    result.openLinkHref.startsWith('https://mozilla.github.io/pdf.js/web/viewer.html?file='),
    'arXiv new-window action should keep using the PDF.js viewer',
  );
  assert.deepStrictEqual(
    result.renderArgs.slice(1),
    [pdfUrl],
    'arXiv preview should render the original PDF URL in the local panel',
  );
  assert.ok(result.bodyClasses.has('dpr-pdf-preview-open'), 'arXiv preview should open the side panel');
  assert.strictEqual(result.button.attributes['aria-expanded'], 'true');
  assert.strictEqual(result.button.textContent, '关闭预览');
}

testArxivPreviewClickStillUsesEmbeddedPanel();

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
