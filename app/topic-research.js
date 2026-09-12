// 专题任务草稿仅在本面板内持有；最终安全快照随工作流保存，不改日常订阅。
window.DPRTopicResearch = (function () {
  const englishTerms = profile => [...new Set((profile.keywords || []).filter(item => item && item.enabled !== false)
    .map(item => String(typeof item === 'string' ? item : item.keyword || item.query || '').trim()).filter(term => /[A-Za-z]/.test(term) && !/[\u3400-\u9fff]/.test(term)))];
  const previewLabel = result => {
    const count = result && typeof result.count === 'number' && Number.isFinite(result.count) ? result.count : null;
    const status = result && result.status;
    if (status === 'exact' && count !== null) return `关键词候选 ${count} 篇（不等于完整相关论文数）`;
    if (status === 'lower_bound' && count !== null) return `至少 ${count} 篇候选，尚未完整统计`;
    if (status === 'partial') return `预览部分完成${count === null ? '' : `，已知 ${count} 篇`}；不是全量计数`;
    return '暂时无法可靠统计候选数量；不代表没有论文';
  };
  const previewThreshold = result => result && Number.isSafeInteger(result.threshold) && result.threshold > 0 ? result.threshold : 1500;
  const dispatchAcknowledged = result => result === true || !!(result && typeof result === 'object' && result.ok !== false && result.success !== false && result.status !== 'failed' && (result.ok === true || result.success === true));
  const refineProfile = async (profile, refinement, category) => {
    const text = String(refinement || '').trim();
    if (!text) throw new Error('请填写本次希望限定的具体范围，或选择继续整个方向。');
    const bridge = window.SubscriptionsSmartQuery;
    if (!bridge || typeof bridge.generateResearchCandidates !== 'function') throw new Error('查询生成器未加载，不能仅修改显示文案后继续。');
    const originalIntents = [...(profile.keywords || []), ...(profile.intent_queries || [])]
      .filter(item => item && item.enabled !== false)
      .map(item => typeof item === 'string' ? item : item.query || item.keyword || '').filter(Boolean);
    const description = `${profile.description || profile.tag}\n原始语义意图（必须保留已有的全部限定，仅在原需求内收窄）：\n${originalIntents.join('\n')}\n本次研究限定（${category || '具体范围'}）：${text}\n请生成符合原始语义意图及本次限定的英文检索词和语义查询，关键词最多4个，应体现正向限定条件，不要仅重复原来的宽泛方向，也不得丢掉原有范围限定。排除要求保留为评审语义，不宣称执行关键词NOT过滤。`;
    const candidates = await bridge.generateResearchCandidates(profile.tag, description);
    const safe = window.DPRWorkflowRunner.sanitizeResearchProfile({ ...candidates, tag: profile.tag, description, refinement: text });
    const constraint = englishTerms(safe);
    if (!constraint.length) throw new Error('未生成可执行的英文限定词，请修改限定描述重试；未触发工作流。');
    const base = englishTerms(profile);
    safe.constraint_groups = base.length ? [base, constraint] : [constraint];
    return window.DPRWorkflowRunner.sanitizeResearchProfile(safe);
  };
  const render = () => `
    <div class="dpr-topic-research">
      <div class="chat-quick-run-title">专题研究</div>
      <p class="dpr-task-hint">选择一个已保存词条。先预览范围，再按固定预算评审；不保证找全。日常订阅不会被本次细化修改。</p>
      <div id="arxiv-admin-topic-profile-picker" class="dpr-profile-picker-row"></div>
      <div class="dpr-task-action-grid dpr-task-action-grid--radio" role="radiogroup" aria-label="专题研究模式">
        <label class="chat-quick-run-item dpr-task-radio-card"><input type="radio" name="dpr-topic-mode" value="90" checked><span class="dpr-task-action-title">90天 arXiv</span><span class="dpr-task-action-cost">聚焦近期研究</span></label>
        <label class="chat-quick-run-item dpr-task-radio-card"><input type="radio" name="dpr-topic-mode" value="365"><span class="dpr-task-action-title">365天 arXiv</span><span class="dpr-task-action-cost">梳理一年进展</span></label>
        <label class="chat-quick-run-item dpr-task-radio-card"><input type="radio" name="dpr-topic-mode" value="starter"><span class="dpr-task-action-title">研究方向大礼包</span><span class="dpr-task-action-cost">365天 arXiv + 近24个月会议</span></label>
      </div>
      <p class="dpr-task-hint">大礼包包括调研问题、方法与子方向、数据与评测、近期进展、局限与待研究问题、阅读路线及资源。资料不足会明确标注，不编造结论。</p>
      <p class="dpr-task-hint">会议范围沿用“会议论文”中勾选的会议名称；未选择则全部支持会议，年份勾选不限制近24个月窗口。</p>
      <label>UTC 截止日期（不含当天） <input id="dpr-topic-as-of" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
      <p class="dpr-task-hint">每任务最多评审300篇，最终结果最多100篇；内容每批生成10篇。继续生成仅补已有结果内容，不重新检索或扩大评审预算。仅在 GitHub Pages 通过 Actions 执行。</p>
      <button id="dpr-topic-start" class="chat-quick-run-run-btn dpr-task-start-btn" type="button">预览并开始专题研究</button>
      <div id="dpr-topic-status" class="chat-quick-run-msg" role="status" aria-live="polite"></div>
      <div id="dpr-topic-results-entry" hidden><a id="dpr-topic-results-link" class="arxiv-tool-btn" href="#/starter-pack/README">查看研究结果</a><p class="dpr-task-hint">这里是研究结果总览，任务完成后刷新查看；已派发不代表已完成。</p></div>
      <div id="dpr-topic-refine" class="dpr-topic-refinement" hidden>
        <div class="chat-quick-run-title">候选范围较大，要缩小本次研究范围吗？</div>
        <p class="dpr-task-hint">本任务只询问这一次。也可以继续整个方向，评审预算仍为300篇。</p>
        <label>限定维度 <select id="dpr-topic-refine-category"><option>具体研究问题</option><option>方法或技术</option><option>任务或应用场景</option><option>数据或评测条件</option></select></label>
        <label>本次限定 <textarea id="dpr-topic-refine-text" rows="3" placeholder="描述你想重点研究的具体范围"></textarea></label>
        <p class="dpr-task-hint">限定词将作为组间AND检索条件；文字中的排除要求用于模型评审，不是数据库NOT硬过滤。</p>
        <button id="dpr-topic-refine-apply" class="arxiv-tool-btn" type="button">生成限定查询并继续</button>
        <button id="dpr-topic-refine-skip" class="arxiv-tool-btn" type="button">继续整个方向</button>
        <button id="dpr-topic-refine-cancel" class="arxiv-tool-btn" type="button">取消本次任务</button>
      </div>
    </div>`;
  const mount = (root, context) => {
    if (!root || root._topicBound) return;
    root._topicBound = true;
    const el = id => root.querySelector('#' + id);
    const status = (text, error = false) => { el('dpr-topic-status').textContent = text; el('dpr-topic-status').style.color = error ? '#c00' : ''; };
    let draft = null;
    let busy = false;
    const lock = value => {
      busy = value;
      ['dpr-topic-start', 'dpr-topic-refine-apply', 'dpr-topic-refine-skip', 'dpr-topic-refine-cancel'].forEach(id => { el(id).disabled = value; });
    };
    const preview = async () => {
      if (!window.TopicResearchPreview || typeof window.TopicResearchPreview.preview !== 'function') return { status: 'unknown' };
      try { return await window.TopicResearchPreview.preview({ ...draft, config: context.getConfig() }); }
      catch (_) { return { status: 'unknown' }; }
    };
    const dispatch = async () => {
      const runner = window.DPRWorkflowRunner;
      const request = runner.buildTopicResearchRequest({ profile: draft.profile, mode: draft.mode, as_of: draft.asOf, conferences: draft.conferences });
      if (!window.confirm(`本次 ${draft.mode === 'starter' ? '研究方向大礼包' : draft.mode + '天 arXiv'}：最多评审300篇、保留100篇、先生成10篇内容。模型调用按实际用量计费；不是全量相关性证明。确认触发 GitHub Actions？`)) { status('已取消，未触发任务。'); return false; }
      const success = await runner.runWorkflowByKey(request.key, request.inputs);
      if (!dispatchAcknowledged(success)) throw new Error('未确认工作流已提交，请检查权限或配置。');
      el('dpr-topic-results-entry').hidden = false;
      status('已发起专题研究。完成后从 Sidebar「专题回溯」进入；内容未完成可按10篇继续生成。');
      return true;
    };
    el('dpr-topic-start').addEventListener('click', async () => {
      if (busy || draft) return;
      lock(true);
      try {
        if (context.hasUnsaved()) throw new Error('请先保存词条修改。');
        const profiles = context.getProfiles();
        if (profiles.length !== 1) throw new Error('请恰好选择一个已保存词条。');
        const runner = window.DPRWorkflowRunner;
        if (!runner || !runner.isStarterPackSupported()) throw new Error('请在 GitHub Pages 站点使用专题研究；不会在本地执行。');
        const request = runner.buildTopicResearchRequest({ profile: profiles[0], mode: root.querySelector('input[name="dpr-topic-mode"]:checked').value, as_of: el('dpr-topic-as-of').value, conferences: context.getConferences() });
        draft = { profile: JSON.parse(request.inputs.profile_snapshot), mode: request.inputs.mode, asOf: request.inputs.as_of, conferences: request.inputs.conferences.split(',') };
        status('正在预览候选范围…');
        const result = await preview();
        const threshold = previewThreshold(result);
        status(previewLabel(result) + `；本次范围细化提示阈值为 ${threshold} 篇。`);
        if (typeof result.count === 'number' && Number.isFinite(result.count) && result.count > threshold) { el('dpr-topic-refine').hidden = false; return; }
        await dispatch();
        draft = null;
      } catch (error) { status(error.message || String(error), true); draft = null; }
      finally { lock(false); }
    });
    const finishRefinement = async apply => {
      if (busy || !draft) return;
      lock(true);
      try {
        if (apply && draft.profile.refinement !== el('dpr-topic-refine-text').value.trim()) {
          status('正在生成本次限定查询；此步骤会调用现有模型…');
          draft.profile = await refineProfile(draft.profile, el('dpr-topic-refine-text').value, el('dpr-topic-refine-category').value);
          const result = await preview();
          status(previewLabel(result) + '；本任务不再重复询问。');
        }
        await dispatch();
        el('dpr-topic-refine').hidden = true;
        draft = null;
      } catch (error) { status(error.message || String(error), true); }
      finally { lock(false); }
    };
    el('dpr-topic-refine-apply').addEventListener('click', () => finishRefinement(true));
    el('dpr-topic-refine-skip').addEventListener('click', () => finishRefinement(false));
    el('dpr-topic-refine-cancel').addEventListener('click', () => { if (busy) return; draft = null; el('dpr-topic-refine').hidden = true; status('已取消本次任务。'); });
    el('dpr-topic-results-link').addEventListener('click', () => {
      const close = document.getElementById('arxiv-search-close-btn');
      if (close) close.click();
    });
  };
  return { render, mount, continueContent: runId => window.DPRWorkflowRunner.continueTopicResearch(runId), __test: { previewLabel, previewThreshold, dispatchAcknowledged, refineProfile, englishTerms } };
})();
