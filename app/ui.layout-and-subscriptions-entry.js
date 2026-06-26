// Global UI behavior: layout + subscription entry button
// 1. API Base: distinguish local development from production deployment
(function() {
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    window.API_BASE_URL = 'http://127.0.0.1:8008';
  } else {
    window.API_BASE_URL = '';
  }
})();

// 2. Sidebar width drag script
(function() {
  function setupSidebarResizer() {
    // Treat "narrowish + narrow" screens uniformly: at <1024 the sidebar is an overlay and width-dragging is disabled
    if (window.innerWidth < 1024) return;
    if (document.getElementById('sidebar-resizer')) return;

    var resizer = document.createElement('div');
    resizer.id = 'sidebar-resizer';
    document.body.appendChild(resizer);

    var dragging = false;

    resizer.addEventListener('mousedown', function (e) {
      dragging = true;
      document.body.classList.add('sidebar-resizing');
      e.preventDefault();
    });

    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      var styles = getComputedStyle(document.documentElement);
      var min =
        parseInt(styles.getPropertyValue('--sidebar-min-width')) || 180;
      var max =
        parseInt(styles.getPropertyValue('--sidebar-max-width')) || 480;
      var newWidth = e.clientX;
      if (newWidth < min) newWidth = min;
      if (newWidth > max) newWidth = max;
      document.documentElement.style.setProperty(
        '--sidebar-width',
        newWidth + 'px',
      );
      // Sync the shadow width of the selected area
      if (window.syncSidebarActiveIndicator) {
        window.syncSidebarActiveIndicator({ animate: false });
      }
    });

    window.addEventListener('mouseup', function () {
      dragging = false;
      document.body.classList.remove('sidebar-resizing');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupSidebarResizer);
  } else {
    setupSidebarResizer();
  }

  var resizeTimer = null;
  // Sidebar auto expand/collapse threshold (kept in sync with SIDEBAR_AUTO_COLLAPSE_WIDTH in docsify-plugin.js)
  var SIDEBAR_COLLAPSE_THRESHOLD = 1024;
  // Record the previous window-width state to avoid duplicate triggers
  var lastWasWide = window.innerWidth >= SIDEBAR_COLLAPSE_THRESHOLD;

  // On page load, set the initial sidebar state based on screen width
  function initSidebarState() {
    var body = document.body;
    if (window.innerWidth < SIDEBAR_COLLAPSE_THRESHOLD) {
      // Small screens collapse the sidebar by default: following Docsify semantics, `close` means expanded and the absence of `close` means collapsed
      if (body.classList.contains('close')) {
        body.classList.remove('close');
      }
    }
  }

  // Initialize the sidebar state after the DOM has loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebarState);
  } else {
    initSidebarState();
  }

  window.addEventListener('resize', function () {
    var resizer = document.getElementById('sidebar-resizer');
    if (window.innerWidth < 1024) {
      if (resizer) resizer.style.display = 'none';
    } else {
      if (resizer) {
        resizer.style.display = 'block';
      } else {
        setupSidebarResizer();
      }
    }

    // Auto-sync the sidebar expand/collapse state based on window width
    // Desktop: body.close = collapsed; mobile (<1024): body.close = expanded (following Docsify semantics)
    var isWide = window.innerWidth >= SIDEBAR_COLLAPSE_THRESHOLD;
    var body = document.body;
    if (isWide !== lastWasWide) {
      if (isWide) {
        // Window widened: auto-expand the sidebar (remove the close class)
        if (body.classList.contains('close')) {
          body.classList.remove('close');
        }
      } else {
        // Window narrowed: following Docsify mobile semantics, the absence of close means collapsed
        if (body.classList.contains('close')) {
          body.classList.remove('close');
        }
      }
      lastWasWide = isWide;
    }

    // Immediately sync the size of the selected area
    if (window.syncSidebarActiveIndicator) {
      window.syncSidebarActiveIndicator({ animate: false });
    }

    // Add dpr-resizing during window resize to disable input/bottom-bar transitions for a more responsive feel
    document.body.classList.add('dpr-resizing');
    if (resizeTimer) {
      clearTimeout(resizeTimer);
    }
    resizeTimer = setTimeout(function () {
      document.body.classList.remove('dpr-resizing');
      resizeTimer = null;
    }, 150);
  });
})();

// 3. Custom subscription-management entry button script (bottom-left 📚)
(function() {
  function createCustomButton() {
    if (document.getElementById('custom-toggle-btn')) return;

    var sidebarToggle = document.querySelector('.sidebar-toggle');
    if (!sidebarToggle) {
      setTimeout(createCustomButton, 100);
      return;
    }

    var btn = document.createElement('button');
    btn.id = 'custom-toggle-btn';
    btn.className = 'custom-toggle-btn';
    btn.innerHTML = '⚙️';
    btn.title = 'Admin';

    btn.addEventListener('click', function () {
      var event = new CustomEvent('ensure-arxiv-ui');
      document.dispatchEvent(event);

      setTimeout(function () {
        var loadEvent = new CustomEvent('load-arxiv-subscriptions');
        document.dispatchEvent(loadEvent);

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
    });

    document.body.appendChild(btn);
  }

  // Keep a standalone trigger function in the bottom-left; do not auto-mount the button for now (prevents duplicate entries)
  function createQuickRunButton() {
    if (document.getElementById('custom-quick-run-btn')) return;

    function requestQuickRunPanel() {
      window.__dprQuickRunOpenRequested = true;

      if (window.PrivateDiscussionChat && typeof window.PrivateDiscussionChat.openQuickRunPanel === 'function') {
        const opened = window.PrivateDiscussionChat.openQuickRunPanel();
        if (opened) {
          window.__dprQuickRunOpenRequested = false;
          return;
        }
      }

      if (window.DPRWorkflowRunner && typeof window.DPRWorkflowRunner.open === 'function') {
        window.__dprQuickRunOpenRequested = false;
        window.DPRWorkflowRunner.open();
        return;
      }

      var event = new CustomEvent('dpr-open-quick-run');
      document.dispatchEvent(event);
    }

    var quickBtn = document.createElement('button');
    quickBtn.id = 'custom-quick-run-btn';
    quickBtn.className = 'custom-toggle-btn custom-quick-run-btn';
    quickBtn.innerHTML = '🚀';
    quickBtn.title = 'Quick fetch';
    quickBtn.setAttribute('aria-label', 'Quick fetch');

    quickBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      requestQuickRunPanel();
    });

    document.body.appendChild(quickBtn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createCustomButton);
  } else {
    createCustomButton();
  }
})();
