# 日报 · 2026-04-21 ~ 2026-05-20

- 生成时间：2026-05-20 02:21:41 UTC
- 当次推荐总数：18
- 精读区：7
- 速读区：11

## 今日简报（AI）
<think>
The user wants a summary for a daily report (but actually a monthly period). The output must be 3 sentences or less, attractive, concise, but specific, based on the given recommendation data. No Markdown title, no JSON.

We need to produce three sentences:
1) A sentence summarizing what was done today (the daily report period?). Should be a title-like phrase, i.e., "本期共推荐 18 篇论文，其中 7 篇精读". Something like "本期共精选 18 篇论文，精读 7 篇，速读 11 篇".
2) One sentence about the most noteworthy 1-2 directions or conclusions. The data includes two high-scoring精读 papers (both 9.0): "Contextual Linear Activation Steering of Language Models" and "Test-Time Safety Alignment". Also three速读 papers scoring 8.0: "Exploring Language-Agnosticity in Function Vectors", "Toward Stable Value Alignment", "Steer-to-Detect". So we could highlight the direction of activation steering and safety alignment, and maybe value alignment or detection of LLM-generated texts. But we need to pick 1-2 directions or conclusions. So we could say: "激活调控与安全对齐是本周期最高分的研究前沿，分别获得 9.0 分，显示上下文线性激活转向和测试时安全对齐的突破性进展。" Or we can mention stable value alignment. Probably mention the top two精读 papers: "Contextual Linear Activation Steering" and "Test-Time Safety Alignment". Or mention that "Contextual Linear Activation Steering of Language Models" and "Test-Time Safety Alignment" both achieved highest scores, indicating emerging control mechanisms and safety alignment. Provide one sentence about the most noteworthy direction: activation steering and safety alignment.

3) One sentence for next steps for general readers: maybe "建议关注激活转向的最新实现方法以及测试时安全对齐的实验评估，以提升模型的可靠性和可控性" or "如果想快速了解可解释性和安全对齐的前沿，可以先阅读这两篇 9 分精读并关注功能向量语言无关性研究". We need to provide suggestion for ordinary readers.

Constraints: 3 sentences, Chinese. No markdown, no JSON. Must not fabricate information. Must base on given data. Should be concise but specific. The data includes that we have精读 papers: both scored 9.0. We can mention they are highly recommended. For next steps: "可先阅读这两篇高分精读，搭桥了解模型激活调控和安全对齐的核心思路" etc.

Thus produce:

"本期共推荐 18 篇论文，其中 7 篇精读、11 篇速读。最高分的两篇精读《Contextual Linear Activation Steering of Language Models》与《Test‑Time Safety Alignment》均获 9.0 分，指向模型激活调控与测试时安全对齐的前沿突破。普通读者可先阅读这两篇高分精读，快速把握模型可控性和安全对齐的核心思路。"

Check length: 3 sentences, no bullet points, no markdown. Good.

Make sure to keep within 3 sentences, not more. Provide a period after each.

Now produce final.
</think>

本期共推荐 18 篇论文，其中 7 篇精读、11 篇速读。最高分的两篇精读《Contextual Linear Activation Steering of Language Models》与《Test‑Time Safety Alignment》均获 9.0 分，指向模型激活调控与测试时安全对齐的前沿突破。普通读者可先阅读这两篇高分精读，快速把握模型可控性和安全对齐的核心思路。

## 精读区
1. [Contextual Linear Activation Steering of Language Models](/20260421-20260520/2604.24693v1-contextual-linear-activation-steering-of-language-models) （9.0/10）
2. [Test-Time Safety Alignment](/20260421-20260520/2604.26167v1-test-time-safety-alignment) （9.0/10）
3. [Minimizing Collateral Damage in Activation Steering](/20260421-20260520/2605.01167v1-minimizing-collateral-damage-in-activation-steering) （9.0/10）
4. [Towards Steering without Sacrifice: Principled Training of Steering Vectors for Prompt-only Interventions](/20260421-20260520/2605.05983v1-towards-steering-without-sacrifice-principled-training-of-steering-vectors-for-prompt-only-interventions) （9.0/10）
5. [Don't Lose Focus: Activation Steering via Key-Orthogonal Projections](/20260421-20260520/2605.06342v1-dont-lose-focus-activation-steering-via-key-orthogonal-projections) （9.0/10）
6. [UniSD: Towards a Unified Self-Distillation Framework for Large Language Models](/20260421-20260520/2605.06597v1-unisd-towards-a-unified-self-distillation-framework-for-large-language-models) （9.0/10）
7. [Do LLMs Experience an Internal Polylogue? Investigating Reasoning through the Lens of Personas](/20260421-20260520/2605.09159v1-do-llms-experience-an-internal-polylogue-investigating-reasoning-through-the-lens-of-personas) （9.0/10）

## 速读区
1. [Exploring Language-Agnosticity in Function Vectors: A Case Study in Machine Translation](/20260421-20260520/2604.19678v1-exploring-language-agnosticity-in-function-vectors-a-case-study-in-machine-translation) （8.0/10）
2. [Toward Stable Value Alignment: Introducing Independent Modules for Consistent Value Guidance](/20260421-20260520/2605.11712v1-toward-stable-value-alignment-introducing-independent-modules-for-consistent-value-guidance) （8.0/10）
3. [Steer-to-Detect: Probing Hidden Representations for Detection of LLM-Generated Texts](/20260421-20260520/2605.12890v1-steer-to-detect-probing-hidden-representations-for-detection-of-llm-generated-texts) （8.0/10）
4. [Tracing Persona Vectors Through LLM Pretraining](/20260421-20260520/2605.13329v1-tracing-persona-vectors-through-llm-pretraining) （8.0/10）
5. [From Insight to Action: A Novel Framework for Interpretability-Guided Data Selection in Large Language Models](/20260421-20260520/2604.25167v1-from-insight-to-action-a-novel-framework-for-interpretability-guided-data-selection-in-large-language-models) （7.0/10）
6. [MTA: Multi-Granular Trajectory Alignment for Large Language Model Distillation](/20260421-20260520/2605.01374v1-mta-multi-granular-trajectory-alignment-for-large-language-model-distillation) （7.0/10）
7. [Chain-based Distillation for Effective Initialization of Variable-Sized Small Language Models](/20260421-20260520/2605.07783v1-chain-based-distillation-for-effective-initialization-of-variable-sized-small-language-models) （7.0/10）
8. [Automated Interpretability and Feature Discovery in Language Models with Agents](/20260421-20260520/2605.01555v1-automated-interpretability-and-feature-discovery-in-language-models-with-agents) （6.0/10）
9. [Self-Consolidating Language Models: Continual Knowledge Incorporation from Context](/20260421-20260520/2605.07076v2-self-consolidating-language-models-continual-knowledge-incorporation-from-context) （6.0/10）
10. [NyayaAI: An AI-Powered Legal Assistant Using Multi-Agent Architecture and Retrieval-Augmented Generation](/20260421-20260520/2605.10155v1-nyayaai-an-ai-powered-legal-assistant-using-multi-agent-architecture-and-retrieval-augmented-generation) （6.0/10）
11. [Query-Conditioned Test-Time Self-Training for Large Language Models](/20260421-20260520/2605.13369v2-query-conditioned-test-time-self-training-for-large-language-models) （6.0/10）

---
使用键盘方向键可在日报/论文之间快速切换。
