<div class="dpr-home-notice-card">
  <h3 class="dpr-home-notice-title">🚀 Start Here</h3>
  <ul class="dpr-home-notice-list">
    <li><a href="#/tutorial/README">使用教程</a></li>
  </ul>
</div>

## 每次日报
- 最新运行日期：2026-04-20 ~ 2026-05-19
- 运行时间：2026-05-19 13:58:39 UTC
- 运行状态：成功
- 本次总论文数：21
- 精读区：10
- 速读区：11

### 今日简报（AI）
<think>
The user asks: "日报日期：2026-04-20 ~ 2026-05-19 状态：成功 总数：21 篇 精读：10 篇 速读：11 篇 精读列表（含分数）：["《CODA: Coordination via On-Policy Diffusion for Multi-Agent Offline Reinforcement Learning》（9.0/10）", "《A Reward-Free Viewpoint on Multi-Objective Reinforcement Learning》（9.0/10）"] 速读列表（含分数）：["《Transformers Provably Implement In-Context Reinforcement Learning with Policy Improvement》（8.5/10）", "《Efficient Federated RLHF via Zeroth-Order Policy Optimization》（8.0/10）", "《Lever: Inference-Time Policy Reuse under Support Constraints》（8.0/10）"]"

Then they ask to output 1-3 lines of text (no markdown titles or JSON) with:

1) A summary sentence about what was done today, suitable for a headline.
2) A sentence giving the most worthwhile directions / conclusions.
3) A sentence giving next step suggestions for the general reader.

We need to produce 3 sentences, each on its own line, no markdown or JSON. Must be Chinese. The content must be based on the given data. Must not fabricate any paper info beyond what is given.

We have the daily report from 2026-04-20 to 2026-05-19. The total of 21 papers read, 10 thorough reads, 11 fast reads. The top rated papers:

- CODA: Coordination via On-Policy Diffusion for Multi-Agent Offline RL (9.0)
- A Reward-Free Viewpoint on Multi-Objective RL (9.0)
- Transformers Provably Implement In-Context RL with Policy Improvement (8.5)
- Efficient Federated RLHF via Zeroth-Order Policy Optimization (8.0)
- Lever: Inference-Time Policy Reuse under Support Constraints (8.0)

Thus the summary of work: reading many RL papers, focusing on multi-agent coordination, reward-free MO RL, transformer RL, federated RLHF, inference-time policy reuse.

Thus the headline: maybe "本月完成21篇论文阅读，聚焦多智能体协同、奖励无关多目标RL、Transformer上下文强化学习等前沿方向" etc.

Second sentence: highlight top directions: multi-agent coordination via diffusion and reward-free multi-objective RL are high-scoring, also transformer RL appears promising.

Third sentence: suggestions: for ordinary readers, keep an eye on diffusion-based coordination methods and reward-free approaches, explore federated RLHF for efficient training, etc.

Now produce the output. Must be 3 lines only, no markdown. Ensure each line is concise but contains at least some specifics.

Make sure to not include bullet points or numbering. Just sentences separated by line breaks.

Potential answer:

"本月共完成21篇论文阅读，其中10篇深度研读，重点关注多智能体协同与奖励无关多目标强化学习。最高评分的两篇分别提出基于扩散策略的多智能体离线强化学习协同机制和无需显式奖励的多目标RL新视角，另有Transformer在情境强化学习中的可证明实现值得关注。建议读者关注扩散协同方法在多智能体场景的潜力，及奖励自由视角在复杂目标优化中的实际应用。"

That's three sentences.

Make sure each line is separate. Let's output that.
</think>

本月共完成21篇论文阅读，其中10篇深度研读，重点关注多智能体协同与奖励无关多目标强化学习。最高评分的两篇分别提出基于扩散策略的多智能体离线强化学习协同机制和无需显式奖励的多目标RL新视角，另有Transformer在情境强化学习中的可证明实现
- 详情：[/20260420-20260519/README](/20260420-20260519/README)

### 精读区论文标签
1. [CODA: Coordination via On-Policy Diffusion for Multi-Agent Offline Reinforcement Learning](/20260420-20260519/2604.23308v1-coda-coordination-via-on-policy-diffusion-for-multi-agent-offline-reinforcement-learning)  
   标签：评分：9.0/10、query:mas
   evidence：基于扩散协调的多智能体离线强化学习
2. [A Reward-Free Viewpoint on Multi-Objective Reinforcement Learning](/20260420-20260519/2604.24532v1-a-reward-free-viewpoint-on-multi-objective-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：多目标强化学习结合无奖励学习框架
3. [Model-Based Reinforcement Learning with Double Oracle Efficiency in Policy Optimization and Offline Estimation](/20260420-20260519/2605.00393v1-model-based-reinforcement-learning-with-double-oracle-efficiency-in-policy-optimization-and-offline-estimation)  
   标签：评分：9.0/10、query:rl
   evidence：基于模型的可提强化学习算法
4. [Breaking the Computational Barrier: Provably Efficient Actor-Critic for Low-Rank MDPs](/20260420-20260519/2605.01242v1-breaking-the-computational-barrier-provably-efficient-actor-critic-for-low-rank-mdps)  
   标签：评分：9.0/10、query:rl
   evidence：可证明高效的Actor-Critic强化学习算法设计
5. [Unified Framework of Distributional Regret in Multi-Armed Bandits and Reinforcement Learning](/20260420-20260519/2605.05102v1-unified-framework-of-distributional-regret-in-multi-armed-bandits-and-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：统一分布遗憾框架用于 bandit 和情景强化学习
6. [Towards Differentially Private Reinforcement Learning with General Function Approximation](/20260420-20260519/2605.07049v1-towards-differentially-private-reinforcement-learning-with-general-function-approximation)  
   标签：评分：9.0/10、query:rl
   evidence：差分私有强化学习理论分析
7. [Policy Gradient Methods for Non-Markovian Reinforcement Learning](/20260420-20260519/2605.10816v1-policy-gradient-methods-for-non-markovian-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：非马尔可夫决策过程的策略梯度方法
8. [Stochastic Minimum-Cost Reach-Avoid Reinforcement Learning](/20260420-20260519/2605.11975v1-stochastic-minimum-cost-reach-avoid-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：随机可达避让强化学习与理论认证
9. [Multi-Objective and Mixed-Reward Reinforcement Learning via Reward-Decorrelated Policy Optimization](/20260420-20260519/2605.13641v1-multi-objective-and-mixed-reward-reinforcement-learning-via-reward-decorrelated-policy-optimization)  
   标签：评分：9.0/10、query:rl
   evidence：多目标强化学习奖励处理算法
10. [Fast Rates for Inverse Reinforcement Learning](/20260420-20260519/2605.14599v1-fast-rates-for-inverse-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：逆强化学习理论分析

### 速读区论文标签
1. [Transformers Provably Implement In-Context Reinforcement Learning with Policy Improvement](/20260420-20260519/2605.05755v1-transformers-provably-implement-in-context-reinforcement-learning-with-policy-improvement)  
   标签：评分：8.5/10、query:rl
   evidence：transformer实现上下文强化学习，含策略改进与收敛保证
2. [Efficient Federated RLHF via Zeroth-Order Policy Optimization](/20260420-20260519/2604.17747v1-efficient-federated-rlhf-via-zeroth-order-policy-optimization)  
   标签：评分：8.0/10、query:rl
   evidence：基于零阶策略优化的联邦强化学习
3. [Lever: Inference-Time Policy Reuse under Support Constraints](/20260420-20260519/2604.20174v1-lever-inference-time-policy-reuse-under-support-constraints)  
   标签：评分：8.0/10、query:rl
   evidence：推理时强化学习策略复用框架
4. [Task-specific Subnetwork Discovery in Reinforcement Learning for Autonomous Underwater Navigation](/20260420-20260519/2604.21640v1-task-specific-subnetwork-discovery-in-reinforcement-learning-for-autonomous-underwater-navigation)  
   标签：评分：8.0/10、query:rl
   evidence：强化学习用于自主水下航行器导航
5. [Agent-Centric Visual Reinforcement Learning under Dynamic Perturbations](/20260420-20260519/2604.24661v2-agent-centric-visual-reinforcement-learning-under-dynamic-perturbations)  
   标签：评分：7.5/10、query:rl
   evidence：动态扰动下的视觉强化学习，智能体中心观测设计
6. [Efficient Rationale-based Retrieval: On-policy Distillation from Generative Rerankers based on JEPA](/20260420-20260519/2604.23336v1-efficient-rationale-based-retrieval-on-policy-distillation-from-generative-rerankers-based-on-jepa)  
   标签：评分：7.0/10、query:self-distillation
   evidence：教师模型向学生模型进行在线策略蒸馏
7. [Value-Decomposed Reinforcement Learning Framework for Taxiway Routing with Hierarchical Conflict-Aware Observations](/20260420-20260519/2605.08754v2-value-decomposed-reinforcement-learning-framework-for-taxiway-routing-with-hierarchical-conflict-aware-observations)  
   标签：评分：7.0/10、query:rl
   evidence：基于价值分解的多飞机滑行道路由强化学习
8. [A Single Deep Preference-Conditioned Policy for Learning Pareto Coverage Sets](/20260420-20260519/2605.08946v1-a-single-deep-preference-conditioned-policy-for-learning-pareto-coverage-sets)  
   标签：评分：7.0/10、query:mas
   evidence：偏好条件多目标强化学习，用于在马尔可夫决策过程中学习帕累托覆盖集
9. [Hierarchical Support Vector State Partitioning for Distilling Black Box Reinforcement Learning Policies](/20260420-20260519/2605.04254v1-hierarchical-support-vector-state-partitioning-for-distilling-black-box-reinforcement-learning-policies)  
   标签：评分：6.0/10、query:rl
   evidence：基于SVM可解释子策略的强化学习策略蒸馏
10. [REAP: Reinforcement-Learning End-to-End Autonomous Parking with Gaussian Splatting Simulator for Real2Sim2Real Transfer](/20260420-20260519/2605.08713v1-reap-reinforcement-learning-end-to-end-autonomous-parking-with-gaussian-splatting-simulator-for-real2sim2real-transfer)  
   标签：评分：6.0/10、query:rl
   evidence：强化学习端到端自主泊车应对复杂场景
11. [Functional alignment of protein language models via reinforcement learning](/20260420-20260519/biorxiv-10-1101-2025-05-02-651993-v2-functional-alignment-of-protein-language-models-via-reinforcement-learning)  
   标签：评分：6.0/10、query:rl
   evidence：强化学习用于蛋白质模型对齐


<div class="dpr-home-promo-card">
  <h3 class="dpr-home-promo-title">💬 社区与支持</h3>
  <ul class="dpr-home-promo-list">
    <li>欢迎 Star / Fork / Issue / PR</li>
    <li>QQ群：583867967（欢迎交流，已有：1151人）</li>
  </ul>
</div>
