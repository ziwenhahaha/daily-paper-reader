(function (root) {
  'use strict';
  var cache = new Map();
  function exportUrl(path) {
    if (!/^docs\/starter-pack\/\d{8}-[a-f0-9]{12}\/papers\.(md|json)$/.test(String(path || ''))) throw new Error('导出文件路径无效');
    var url = new URL(path, root.location.href.split('#')[0]);
    if (url.origin !== root.location.origin) throw new Error('导出文件必须来自当前站点');
    return url.href;
  }
  async function loadList(path) {
    var url = exportUrl(path);
    if (!/\/papers\.md$/.test(url)) throw new Error('复制清单必须读取已保存的 Markdown');
    if (!cache.has(url)) {
      var request = (async function () {
        var controller = new AbortController();
        var timer = setTimeout(function () { controller.abort(); }, 20000);
        try {
          var response = await root.fetch(url, {signal: controller.signal, credentials: 'same-origin'});
          if (!response.ok) throw new Error('清单加载失败（HTTP ' + response.status + '）');
          var text = await response.text();
          if (!text.trim() || /^\s*(?:<!doctype|<html)/i.test(text)) throw new Error('导出清单尚未生成');
          return text;
        } finally { clearTimeout(timer); }
      })();
      cache.set(url, request);
      request.catch(function () { cache.delete(url); });
    }
    return cache.get(url);
  }
  async function copyText(text) {
    try {
      if (root.navigator.clipboard && root.navigator.clipboard.writeText) {
        await root.navigator.clipboard.writeText(text);
        return;
      }
    } catch (_) { /* 权限被拒时尝试浏览器兼容路径，仍须检查返回值。 */ }
    var previous = root.document.activeElement;
    var textarea = root.document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.cssText = 'position:fixed;left:-9999px;top:0';
    root.document.body.appendChild(textarea);
    try {
      textarea.select();
      if (!root.document.execCommand || !root.document.execCommand('copy')) throw new Error('浏览器拒绝复制，请使用下载 Markdown 获取清单');
    } finally {
      textarea.remove();
      if (previous && previous.focus) previous.focus({preventScroll: true});
    }
  }
  async function continueContent(runId) {
    if (!/^\d{8}-[a-f0-9]{12}$/.test(String(runId))) throw new Error('任务标识无效');
    if (!root.DPRTopicResearch || typeof root.DPRTopicResearch.continueContent !== 'function') throw new Error('任务入口尚未加载，请刷新后重试');
    var result = await root.DPRTopicResearch.continueContent(runId);
    if (!result || result.ok === false || result.success === false || result.status === 'failed') throw new Error(result && result.message || '未确认任务已提交，请检查任务面板');
    return result;
  }
  function message(button, text) {
    var status = button.parentNode.querySelector('[data-topic-result-status]');
    if (!status) {
      status = root.document.createElement('span');
      status.setAttribute('data-topic-result-status', '');
      status.setAttribute('role', 'status');
      button.parentNode.appendChild(status);
    }
    status.textContent = text;
  }
  if (root.document && root.document.addEventListener) root.document.addEventListener('click', async function (event) {
    var button = event.target.closest && event.target.closest('[data-topic-copy], [data-topic-continue]');
    if (!button) return;
    event.preventDefault();
    if (button.disabled) return;
    button.disabled = true;
    message(button, '处理中…');
    try {
      if (button.hasAttribute('data-topic-copy')) {
        await copyText(await loadList(button.getAttribute('data-topic-copy')));
        message(button, '已复制完整最终清单（不受页面筛选、分页或已读状态影响）');
      } else {
        await continueContent(button.getAttribute('data-topic-continue'));
        message(button, '内容续生成任务已提交，请在任务面板查看进度');
      }
    } catch (error) { message(button, error.message || '操作失败，请稍后重试'); }
    finally { button.disabled = false; }
  });
  if (typeof module === 'object' && module.exports) module.exports = {exportUrl: exportUrl, loadList: loadList, copyText: copyText, continueContent: continueContent};
})(typeof window !== 'undefined' ? window : globalThis);
