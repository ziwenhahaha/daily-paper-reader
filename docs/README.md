<div class="dpr-home-notice-card">
  <h3 class="dpr-home-notice-title">🚀 Start Here</h3>
  <ul class="dpr-home-notice-list">
    <li><a href="#/tutorial/README">使用教程</a></li>
  </ul>
</div>

## 每次日报
- 最新运行日期：2026-04-21 ~ 2026-05-20
- 运行时间：2026-05-20 02:21:41 UTC
- 运行状态：成功
- 本次总论文数：18
- 精读区：7
- 速读区：11

### 今日简报（AI）
<think>用户需要我作为日报编辑，输出3句以内的中文总结。内容必须基于给定的推荐数据。

根据数据：
- 日期：2026-04-21 ~ 2026-05-20
- 状态：成功
- 总数：18篇
- 精读：7篇
- 速读：11篇
- 精读列表中有2个给出了分数（9.0/10）：《Contextual Linear Activation Steering of Language Models》和《Test-Time Safety Alignment》
- 速读列表中有3个给出了分数（8.0/10）：机器翻译、价值对齐、LLM生成文本检测

用户要求：
1) 一句概括今天做了什么，适合标题感官
2) 一句给出最值得看的1~2个方向/结论
3) 一句给出下步建议（面向普通读者）

注意：不要编造论文信息，要基于给定数据。

第1句：总结性，概括本期工作
第2句：基于数据给出值得看的方向
- 精读中的两篇都是9.0分，都是关于语言模型的控制和安全
- 速读中有三个方向：机器翻译的价值向量、价值对齐、LLM生成文本检测

第3句：下步建议，面向普通读者

让我组织语言：

1) 本期精读7篇、速读11篇，共18篇论文，重点关注语言模型控制与安全对齐方向


2) 精读聚焦于语言模型激活控制和测试时安全对齐，这两个领域直接触及模型可控性和安全性的核心挑战

3) 对于有兴趣的读者，可以深入研究激活控制和价值对齐，这些方向可能是理解模型内部机制和提升安全性的关键切入点。</think>

本期精选18篇论文，重点探索语言模型激活控制和测试时安全对齐的最新进展。激活控制与安全对齐领域值得关注，两篇精读论文均获9.0分，建议优先关注。普通读者可从理解语言模型"可控性"切入，了解模型如何被引导遵循人类意图。
- 详情：[/20260421-20260520/README](/20260421-20260520/README)

### 精读区论文标签
1. [Contextual Linear Activation Steering of Language Models](/20260421-20260520/2604.24693v1-contextual-linear-activation-steering-of-language-models)  
   标签：评分：9.0/10、query:intervention
   evidence：线性激活引导控制LLM行为
2. [Test-Time Safety Alignment](/20260421-20260520/2604.26167v1-test-time-safety-alignment)  
   标签：评分：9.0/10、query:intervention
   evidence：输入词嵌入优化作为控制变量引导大语言模型行为
3. [Minimizing Collateral Damage in Activation Steering](/20260421-20260520/2605.01167v1-minimizing-collateral-damage-in-activation-steering)  
   标签：评分：9.0/10、query:intervention
   evidence：通过向量干预控制LLM行为的激活转向
4. [Towards Steering without Sacrifice: Principled Training of Steering Vectors for Prompt-only Interventions](/20260421-20260520/2605.05983v1-towards-steering-without-sacrifice-principled-training-of-steering-vectors-for-prompt-only-interventions)  
   标签：评分：9.0/10、query:intervention
   evidence：微调 steering vectors 用于 LLM 行为干预
5. [Don't Lose Focus: Activation Steering via Key-Orthogonal Projections](/20260421-20260520/2605.06342v1-dont-lose-focus-activation-steering-via-key-orthogonal-projections)  
   标签：评分：9.0/10、query:intervention
   evidence：通过关键正交投影进行激活 steering 控制 LLM 行为
6. [UniSD: Towards a Unified Self-Distillation Framework for Large Language Models](/20260421-20260520/2605.06597v1-unisd-towards-a-unified-self-distillation-framework-for-large-language-models)  
   标签：评分：9.0/10、query:self-distillation
   evidence：自蒸馏框架与自蒸馏需求直接对应
7. [Do LLMs Experience an Internal Polylogue? Investigating Reasoning through the Lens of Personas](/20260421-20260520/2605.09159v1-do-llms-experience-an-internal-polylogue-investigating-reasoning-through-the-lens-of-personas)  
   标签：评分：9.0/10、query:intervention
   evidence：将人格向量作为激活空间中的线性方向用于行为引导和干预

### 速读区论文标签
1. [Exploring Language-Agnosticity in Function Vectors: A Case Study in Machine Translation](/20260421-20260520/2604.19678v1-exploring-language-agnosticity-in-function-vectors-a-case-study-in-machine-translation)  
   标签：评分：8.0/10、query:intervention
   evidence：从模型激活中提取用于任务级引导的功能向量
2. [Toward Stable Value Alignment: Introducing Independent Modules for Consistent Value Guidance](/20260421-20260520/2605.11712v1-toward-stable-value-alignment-introducing-independent-modules-for-consistent-value-guidance)  
   标签：评分：8.0/10、query:intervention
   evidence：隔离价值空间实现稳定LLM引导与干预主题相符
3. [Steer-to-Detect: Probing Hidden Representations for Detection of LLM-Generated Texts](/20260421-20260520/2605.12890v1-steer-to-detect-probing-hidden-representations-for-detection-of-llm-generated-texts)  
   标签：评分：8.0/10、query:intervention
   evidence：向LLM隐藏态注入引导向量
4. [Tracing Persona Vectors Through LLM Pretraining](/20260421-20260520/2605.13329v1-tracing-persona-vectors-through-llm-pretraining)  
   标签：评分：8.0/10、query:intervention
   evidence：persona vectors 用于引导和干预模型行为
5. [From Insight to Action: A Novel Framework for Interpretability-Guided Data Selection in Large Language Models](/20260421-20260520/2604.25167v1-from-insight-to-action-a-novel-framework-for-interpretability-guided-data-selection-in-large-language-models)  
   标签：评分：7.0/10、query:intervention
   evidence：干预过滤用于特征激活
6. [MTA: Multi-Granular Trajectory Alignment for Large Language Model Distillation](/20260421-20260520/2605.01374v1-mta-multi-granular-trajectory-alignment-for-large-language-model-distillation)  
   标签：评分：7.0/10、query:self-distillation
   evidence：知识蒸馏对齐师生层轨迹
7. [Chain-based Distillation for Effective Initialization of Variable-Sized Small Language Models](/20260421-20260520/2605.07783v1-chain-based-distillation-for-effective-initialization-of-variable-sized-small-language-models)  
   标签：评分：7.0/10、query:self-distillation
   evidence：链式蒸馏初始化小型语言模型
8. [Automated Interpretability and Feature Discovery in Language Models with Agents](/20260421-20260520/2605.01555v1-automated-interpretability-and-feature-discovery-in-language-models-with-agents)  
   标签：评分：6.0/10、query:intervention
   evidence：激活空间特征发现与向量空间操控相关
9. [Self-Consolidating Language Models: Continual Knowledge Incorporation from Context](/20260421-20260520/2605.07076v2-self-consolidating-language-models-continual-knowledge-incorporation-from-context)  
   标签：评分：6.0/10、query:self-distillation
   evidence：自蒸馏模型更新自身权重
10. [NyayaAI: An AI-Powered Legal Assistant Using Multi-Agent Architecture and Retrieval-Augmented Generation](/20260421-20260520/2605.10155v1-nyayaai-an-ai-powered-legal-assistant-using-multi-agent-architecture-and-retrieval-augmented-generation)  
   标签：评分：6.0/10、query:mas
   evidence：多智能体架构协调法律助手
11. [Query-Conditioned Test-Time Self-Training for Large Language Models](/20260421-20260520/2605.13369v2-query-conditioned-test-time-self-training-for-large-language-models)  
   标签：评分：6.0/10、query:intervention
   evidence：测试时LLM参数干预


<div class="dpr-home-promo-card">
  <h3 class="dpr-home-promo-title">💬 社区与支持</h3>
  <ul class="dpr-home-promo-list">
    <li>欢迎 Star / Fork / Issue / PR</li>
    <li>QQ群：583867967（欢迎交流，已有：1151人）</li>
  </ul>
</div>
