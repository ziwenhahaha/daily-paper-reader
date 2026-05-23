# 日报 · 2026-05-22

- 生成时间：2026-05-22 21:40:56 UTC
- 当次推荐总数：41
- 精读区：26
- 速读区：15

## 今日简报（AI）
<think>The user wants a daily report summary in Chinese, three sentences maximum, attractively concise. The user provides date, status, total 41 papers, 26 refined reading, 15 rapid reading. The refined reading list includes two papers with scores 9.0/10. The rapid reading includes three papers with scores 8.0/10.

We need to output three lines, each a sentence. The sentences must be:

1) Summarize what was done today, suitable for a title vibe.
2) Provide the most noteworthy 1-2 directions or conclusions.
3) Give next step suggestions for a general audience.

We must base on the given data. Must not fabricate information. Must stay within 3 sentences.

We need to ensure each line is a separate sentence (or separated by newline). Not Markdown. No extra formatting.

So we output:

Line 1: Something like "今日完成了 41 篇论文的筛选，其中 26 篇进入精读，15 篇速读，涵盖离线到在线强化学习、语言反馈等多领域。" But this is longer than 1 sentence? That is fine. It must be a sentence, not multiple sentences. We'll keep it one sentence.

Line 2: Provide the most noteworthy direction(s): The two top-scoring精读 papers: ROAD (adaptive data mixing for offline-to-online RL) and Learning from Language Feedback via Variational Policy Distillation (both 9.0). Also maybe mention the three速读 papers collectively. But need 1-2 directions: maybe "离线到在线强化学习的数据混合和语言反馈策略提炼成为本轮最高评分亮点（均 9.0）" That is a direction.

Line 3: Next step suggestion: "建议读者重点关注离线到在线 RL 的自适应数据混合方法及语言反馈的学习框架，可先阅读 ROAD 与语言反馈两篇精读文章获取核心思路。" That gives suggestion.

Make sure it's 3 lines, each sentence, not too many characters, but attractively concise. Ensure Chinese and no markdown. The user said "直接输出 1-3 行文本，不要 Markdown 标题，也不要 JSON。" So plain text.

We should avoid bullet points. Just plain lines. The three sentences can be separated by newline characters.

We have to ensure the content is accurate: The date is 2026-05-22, success, 41 total, 26精读, 15速读. The list of精读 includes those two papers. The list of速读 includes three.

Hence sentence 1: "2026-05-22 成功完成 41 篇论文筛选，其中 26 篇进入精读，15 篇进入速读，覆盖离线到在线强化学习、语言反馈等多个前沿方向。" That is a single sentence.

Sentence 2: "本轮最高评分亮点是《ROAD：基于双层优化的离线到在线强化学习自适应数据混合》和《通过变分策略提炼学习语言反馈》两项，均获 9.0 分。" That mentions the top direction.

Sentence 3: "建议读者先细读这两篇 9.0 分精读，兼顾速读的均衡分布信息，以快速把握自适应数据混合和语言反馈的关键技术路径。" That is a suggestion.

Make sure it's within 3 sentences. Use newline separation.

Check for any potential policy issues: It's about summarizing. No disallowed content. It's fine.

Potential nuance: Ensure we are not giving false claims about results; just referencing the titles and scores. Should be fine.

Make sure the language is appropriate and succinct.

Alright let's produce final output.
</think>



2026‑05‑22 成功完成 41 篇论文筛选，其中 26 篇进入精读、15 篇进入速读，覆盖离线到在线强化学习、语言反馈

## 精读区
1. [ROAD: Adaptive Data Mixing for Offline-to-Online Reinforcement Learning via Bi-Level Optimization](/202605/22/2605.14497v1-road-adaptive-data-mixing-for-offline-to-online-reinforcement-learning-via-bi-level-optimization) （9.0/10）
2. [Learning from Language Feedback via Variational Policy Distillation](/202605/22/2605.15113v1-learning-from-language-feedback-via-variational-policy-distillation) （9.0/10）
3. [ReactiveGWM: Steering NPC in Reactive Game World Models](/202605/22/2605.15256v1-reactivegwm-steering-npc-in-reactive-game-world-models) （9.0/10）
4. [Response-Conditioned Parallel-to-Sequential Orchestration for Multi-Agent Systems](/202605/22/2605.15573v1-response-conditioned-parallel-to-sequential-orchestration-for-multi-agent-systems) （9.0/10）
5. [Tighter Regret Bounds for Contextual Action-Set Reinforcement Learning](/202605/22/2605.15692v1-tighter-regret-bounds-for-contextual-action-set-reinforcement-learning) （9.0/10）
6. [Decoupling KL and Trajectories: A Unified Perspective for SFT, DAgger, Offline RL, and OPD in LLM Distillation](/202605/22/2605.16826v1-decoupling-kl-and-trajectories-a-unified-perspective-for-sft-dagger-offline-rl-and-opd-in-llm-distillation) （9.0/10）
7. [D$^2$Evo: Dual Difficulty-Aware Self-Evolution for Data-Efficient Reinforcement Learning](/202605/22/2605.17037v1-d2evo-dual-difficulty-aware-self-evolution-for-data-efficient-reinforcement-learning) （9.0/10）
8. [From Imitation to Interaction: Mastering Game of Schnapsen with Shallow Reinforcement Learning](/202605/22/2605.17162v1-from-imitation-to-interaction-mastering-game-of-schnapsen-with-shallow-reinforcement-learning) （9.0/10）
9. [AMATA: Adaptive Multi-Agent Trajectory Alignment for Knowledge-Intensive Question Answering](/202605/22/2605.17352v1-amata-adaptive-multi-agent-trajectory-alignment-for-knowledge-intensive-question-answering) （9.0/10）
10. [The Capability Paradox: How Smarter Auditors Make Multi-Agent Systems Less Secure](/202605/22/2605.17480v2-the-capability-paradox-how-smarter-auditors-make-multi-agent-systems-less-secure) （9.0/10）
11. [Self-Distillation is Optimal Among Spectral Shrinkage Estimators in Spiked Covariance Models](/202605/22/2605.17778v1-self-distillation-is-optimal-among-spectral-shrinkage-estimators-in-spiked-covariance-models) （9.0/10）
12. [Balancing Knowledge Distillation for Imbalance Learning with Bilevel Optimization](/202605/22/2605.17839v2-balancing-knowledge-distillation-for-imbalance-learning-with-bilevel-optimization) （9.0/10）
13. [HINT-SD: Targeted Hindsight Self-Distillation for Long-Horizon Agents](/202605/22/2605.17873v1-hint-sd-targeted-hindsight-self-distillation-for-long-horizon-agents) （9.0/10）
14. [Multi-agent AI systems outperform human teams in creativity](/202605/22/2605.17885v1-multi-agent-ai-systems-outperform-human-teams-in-creativity) （9.0/10）
15. [LIFT and PLACE: A Simple, Stable, and Effective Knowledge Distillation Framework for Lightweight Diffusion Models](/202605/22/2605.19729v1-lift-and-place-a-simple-stable-and-effective-knowledge-distillation-framework-for-lightweight-diffusion-models) （9.0/10）
16. [Smaller Abstract State Spaces Enable Cross-Scale Generalization in Reinforcement Learning](/202605/22/2605.20272v1-smaller-abstract-state-spaces-enable-cross-scale-generalization-in-reinforcement-learning) （9.0/10）
17. [What Do Agents Communicate? Characterizing Information Exchange in Multi-Agent Systems](/202605/22/2605.20548v1-what-do-agents-communicate-characterizing-information-exchange-in-multi-agent-systems) （9.0/10）
18. [AVSD: Adaptive-View Self-Distillation by Balancing Consensus and Teacher-Specific Privileged Signals](/202605/22/2605.20643v1-avsd-adaptive-view-self-distillation-by-balancing-consensus-and-teacher-specific-privileged-signals) （9.0/10）
19. [Behavior-Consistent Deep Reinforcement Learning](/202605/22/2605.21214v1-behavior-consistent-deep-reinforcement-learning) （9.0/10）
20. [Behavior-Consistent Deep Reinforcement Learning](/202605/22/2605.21214v2-behavior-consistent-deep-reinforcement-learning) （9.0/10）
21. [Scalable On-Policy Reinforcement Learning via Adaptive Batch Scaling](/202605/22/2605.21557v1-scalable-on-policy-reinforcement-learning-via-adaptive-batch-scaling) （9.0/10）
22. [On the Sample Complexity of Discounted Reinforcement Learning with Optimized Certainty Equivalents](/202605/22/2605.21763v1-on-the-sample-complexity-of-discounted-reinforcement-learning-with-optimized-certainty-equivalents) （9.0/10）
23. [Tailoring Teaching to Aptitude: Direction-Adaptive Self-Distillation for LLM Reasoning](/202605/22/2605.22263v1-tailoring-teaching-to-aptitude-direction-adaptive-self-distillation-for-llm-reasoning) （9.0/10）
24. [Incentive-Aligned Vehicle-to-Vehicle Energy Trading via Nash-Integrated Multi-Agent Reinforcement Learning](/202605/22/2605.22363v1-incentive-aligned-vehicle-to-vehicle-energy-trading-via-nash-integrated-multi-agent-reinforcement-learning) （9.0/10）
25. [Self-Evolving Multi-Agent Systems via Decentralized Memory](/202605/22/2605.22721v1-self-evolving-multi-agent-systems-via-decentralized-memory) （9.0/10）
26. [Superhuman Safe and Agile Racing through Multi-Agent Reinforcement Learning](/202605/22/2605.22748v1-superhuman-safe-and-agile-racing-through-multi-agent-reinforcement-learning) （9.0/10）

## 速读区
1. [Watermarking Game-Playing Agents in Perfect-Information Extensive-Form Games](/202605/22/2605.14283v1-watermarking-game-playing-agents-in-perfect-information-extensive-form-games) （8.0/10）
2. [Dynamic Latent Routing](/202605/22/2605.14323v1-dynamic-latent-routing) （8.0/10）
3. [Distributionally Robust Multi-Task Reinforcement Learning via Adaptive Task Sampling](/202605/22/2605.14350v1-distributionally-robust-multi-task-reinforcement-learning-via-adaptive-task-sampling) （8.0/10）
4. [Data-Augmented Game Starts for Accelerating Self-Play Exploration in Imperfect Information Games](/202605/22/2605.14379v1-data-augmented-game-starts-for-accelerating-self-play-exploration-in-imperfect-information-games) （8.0/10）
5. [Collaborative Yet Personalized Policy Training: Single-Timescale Federated Actor-Critic](/202605/22/2605.14423v1-collaborative-yet-personalized-policy-training-single-timescale-federated-actor-critic) （8.0/10）
6. [Not All Timesteps Matter Equally: Selective Alignment Knowledge Distillation for Spiking Neural Networks](/202605/22/2605.14252v1-not-all-timesteps-matter-equally-selective-alignment-knowledge-distillation-for-spiking-neural-networks) （7.0/10）
7. [BiFedKD: Bidirectional Federated Knowledge Distillation Framework for Non-IID and Long-Tailed ECG Monitoring](/202605/22/2605.14886v1-bifedkd-bidirectional-federated-knowledge-distillation-framework-for-non-iid-and-long-tailed-ecg-monitoring) （7.0/10）
8. [Critic-Driven Voronoi-Quantization for Distilling Deep RL Policies to Explainable Models](/202605/22/2605.14897v1-critic-driven-voronoi-quantization-for-distilling-deep-rl-policies-to-explainable-models) （7.0/10）
9. [Distributionally Robust Nash Equilibrium Seeking with Partial Observations and Distributed Communication](/202605/22/2605.15534v1-distributionally-robust-nash-equilibrium-seeking-with-partial-observations-and-distributed-communication) （7.0/10）
10. [TopoClaw: A Human-Centric and Topology-Aware Agent Operating System](/202605/22/2605.15556v1-topoclaw-a-human-centric-and-topology-aware-agent-operating-system) （7.0/10）
11. [BOOKMARKS: Efficient Active Storyline Memory for Role-playing](/202605/22/2605.14169v1-bookmarks-efficient-active-storyline-memory-for-role-playing) （6.0/10）
12. [AudioMosaic: Contrastive Masked Audio Representation Learning](/202605/22/2605.14231v1-audiomosaic-contrastive-masked-audio-representation-learning) （6.0/10）
13. [Joint Communication and Computation Design for Mobile Embodied AI Network (MEAN)](/202605/22/2605.14300v1-joint-communication-and-computation-design-for-mobile-embodied-ai-network-mean) （6.0/10）
14. [Learning with Semantic Priors: Stabilizing Point-Supervised Infrared Small Target Detection via Hierarchical Knowledge Distillation](/202605/22/2605.14346v1-learning-with-semantic-priors-stabilizing-point-supervised-infrared-small-target-detection-via-hierarchical-knowledge-distillation) （6.0/10）
15. [How to Choose Your Teacher for Fine Grained Image Recognition](/202605/22/2605.15689v1-how-to-choose-your-teacher-for-fine-grained-image-recognition) （6.0/10）

---
使用键盘方向键可在日报/论文之间快速切换。
