<div class="dpr-home-notice-card">
  <h3 class="dpr-home-notice-title">🚀 Start Here</h3>
  <ul class="dpr-home-notice-list">
    <li><a href="#/tutorial/README">使用教程</a></li>
  </ul>
</div>

## 每次日报
- 最新运行日期：2026-04-20 ~ 2026-05-19
- 运行时间：2026-05-19 05:59:05 UTC
- 运行状态：成功
- 本次总论文数：20
- 精读区：9
- 速读区：11

### 今日简报（AI）
<think>The user wants a summary based on the data. The user says:

"日报日期：2026-04-20 ~ 2026-05-19
状态：成功
总数：20 篇
精读：9 篇
速读：11 篇
精读列表（含分数）：["《Power Distribution Bridges Sampling, Self-Reward RL, and Self-Distillation》（9.0/10）", "《Strat-Reasoner: Reinforcing Strategic Reasoning of LLMs in Multi-Agent Games》（9.0/10）"]
速读列表（含分数）：["《Stratagem: Learning Transferable Reasoning via Trajectory-Modulated Game Self-Play》（8.0/10）", "《Randomly Initialized Networks Can Learn from Peer-to-Peer Consensus》（8.0/10）", "《Guiding Distribution Matching Distillation with Gradient-Based Reinforcement Learning》（8.0/10）"]"

Then: "请按以下格式输出：
1) 一句概括今天做了什么，适合标题感官。
2) 一句给出最值得看的 1~2 个方向/结论。
3) 一句给出下步建议（面向普通读者）。
直接输出 1-3 行文本，不要 Markdown 标题，也不要 JSON。"

We need to respond in Chinese, three lines, each line separate a single sentence. We must not output markdown titles or JSON. Should not include bullet points. Should be plain text lines.

Line 1: summary of what was done for the day (or period). The period is 2026-04-20 ~ 2026-05-19 (like a month). "成功" status means successful. We can say "本期完成20篇论文阅读，其中精读9篇，速读11篇" or something. But "today" is ambiguous; maybe "本期" is okay.

Line 2: The most noteworthy directions/conclusions (1~2). We can say two key insights: Self-reward RL and self-distillation; strategic reasoning in multi-agent games; and transferable reasoning via game self-play. So we can mention the best-scored papers: The two 9.0/10 papers. So maybe "重点关注自奖励强化学习与自蒸馏实现的高效采样，以及策略推理在多智能体博弈中的提升" etc.

Line 3: Suggest next steps for ordinary readers: "建议关注上述高分论文的实际应用，尝试将自奖励和自蒸馏方法用于自己的模型" etc. Something like that.

We need to keep each line concise, within a sentence, not too long. Possibly about 20-30 characters each? The instruction: "一句概括今天做了什么，适合标题感官。" So we can produce a concise title-like sentence: "本月完成20篇论文阅读，含9篇精读、11篇速读" Something like that.

Line 2: "最值得关注的两大方向为自奖励强化学习结合自蒸馏的采样优化，以及在多智能体博弈中提升LLM策略推理的框架。" That's maybe okay.

Line 3: "普通读者可从阅读高分论文的摘要与实验结果入手，尝试在项目中引入自奖励机制或策略推理模块。" That is a suggestion.

Make sure not to include any Markdown or JSON. So output exactly three lines:

Line 1: "本月完成20篇论文阅读，其中9篇精读、11篇速读。"
Line 2: "最值得关注的方向是自奖励强化学习与自蒸馏实现的高效采样，以及多智能体博弈中LLM策略推理的提升。"
Line 3: "普通读者可先阅读这两篇9分论文的摘要和实验，尝试将自奖励或策略推理机制引入自己的模型。"

Check the length: Line</think>
- 详情：[/20260420-20260519/README](/20260420-20260519/README)

### 精读区论文标签
1. [Power Distribution Bridges Sampling, Self-Reward RL, and Self-Distillation](/20260420-20260519/2605.04542v1-power-distribution-bridges-sampling-self-reward-rl-and-self-distillation)  
   标签：评分：9.0/10、query:rlg
   evidence：幂分布连接自奖励强化学习与自蒸馏
2. [Strat-Reasoner: Reinforcing Strategic Reasoning of LLMs in Multi-Agent Games](/20260420-20260519/2605.04906v1-strat-reasoner-reinforcing-strategic-reasoning-of-llms-in-multi-agent-games)  
   标签：评分：9.0/10、query:rlg
   evidence：多智能体游戏AI基于强化学习的策略推理
3. [Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning](/20260420-20260519/2605.06130v2-skill1-unified-evolution-of-skill-augmented-agents-via-reinforcement-learning)  
   标签：评分：9.0/10、query:rlg
   evidence：统一强化学习框架协同进化技能选择利用和蒸馏
4. [Evidence Over Plans: Online Trajectory Verification for Skill Distillation](/20260420-20260519/2605.09192v1-evidence-over-plans-online-trajectory-verification-for-skill-distillation)  
   标签：评分：9.0/10、query:rlg
   evidence：使用后验蒸馏指数的在线轨迹验证技能蒸馏
5. [TRACE: Distilling Where It Matters via Token-Routed Self On-Policy Alignment](/20260420-20260519/2605.10194v1-trace-distilling-where-it-matters-via-token-routed-self-on-policy-alignment)  
   标签：评分：9.0/10、query:rlg
   evidence：RLVR中策略自我教学的在策略自蒸馏方法
6. [Rebellious Student: Reversing Teacher Signals for Reasoning Exploration with Self-Distilled RLVR](/20260420-20260519/2605.10781v1-rebellious-student-reversing-teacher-signals-for-reasoning-exploration-with-self-distilled-rlvr)  
   标签：评分：9.0/10、query:rlg
   evidence：大语言模型后训练中自蒸馏的强化学习框架
7. [Learning to Foresee: Unveiling the Unlocking Efficiency of On-Policy Distillation](/20260420-20260519/2605.11739v2-learning-to-foresee-unveiling-the-unlocking-efficiency-of-on-policy-distillation)  
   标签：评分：9.0/10、query:rlg
   evidence：在线策略蒸馏通过预见机制提升训练效率
8. [Learning from Language Feedback via Variational Policy Distillation](/20260420-20260519/2605.15113v1-learning-from-language-feedback-via-variational-policy-distillation)  
   标签：评分：9.0/10、query:rlg
   evidence：用于语言反馈强化学习的变分策略蒸馏
9. [Self-Distilled Agentic Reinforcement Learning](/20260420-20260519/2605.15155v1-self-distilled-agentic-reinforcement-learning)  
   标签：评分：9.0/10、query:rlg
   evidence：自蒸馏智能体强化学习结合OPSD与门控辅助目标

### 速读区论文标签
1. [Stratagem: Learning Transferable Reasoning via Trajectory-Modulated Game Self-Play](/20260420-20260519/2604.17696v1-stratagem-learning-transferable-reasoning-via-trajectory-modulated-game-self-play)  
   标签：评分：8.0/10、query:rlg
   evidence：游戏Agent自博弈训练,轨迹推理机制
2. [Randomly Initialized Networks Can Learn from Peer-to-Peer Consensus](/20260420-20260519/2604.18390v1-randomly-initialized-networks-can-learn-from-peer-to-peer-consensus)  
   标签：评分：8.0/10、query:rlg
   evidence：在自监督表示学习中分离自蒸馏效应
3. [Guiding Distribution Matching Distillation with Gradient-Based Reinforcement Learning](/20260420-20260519/2604.19009v1-guiding-distribution-matching-distillation-with-gradient-based-reinforcement-learning)  
   标签：评分：8.0/10、query:rlg
   evidence：结合强化学习与蒸馏的RL引导扩散蒸馏方法
4. [Lever: Inference-Time Policy Reuse under Support Constraints](/20260420-20260519/2604.20174v2-lever-inference-time-policy-reuse-under-support-constraints)  
   标签：评分：8.0/10、query:rlg
   evidence：推理时强化学习策略复用与组合
5. [LiteResearcher: A Scalable Agentic RL Training Framework for Deep Research Agent](/20260420-20260519/2604.17931v1-literesearcher-a-scalable-agentic-rl-training-framework-for-deep-research-agent)  
   标签：评分：7.0/10、query:rlg
   evidence：用于AI智能体的可扩展智能体RL训练框架
6. [Agent-World: Scaling Real-World Environment Synthesis for Evolving General Agent Intelligence](/20260420-20260519/2604.18292v1-agent-world-scaling-real-world-environment-synthesis-for-evolving-general-agent-intelligence)  
   标签：评分：7.0/10、query:rlg
   evidence：用于智能体智能的自我进化训练场
7. [StepPO: Step-Aligned Policy Optimization for Agentic Reinforcement Learning](/20260420-20260519/2604.18401v1-steppo-step-aligned-policy-optimization-for-agentic-reinforcement-learning)  
   标签：评分：7.0/10、query:rlg
   evidence：面向智能体强化学习的步对齐策略优化
8. [Mask World Model: Predicting What Matters for Robust Robot Policy Learning](/20260420-20260519/2604.19683v2-mask-world-model-predicting-what-matters-for-robust-robot-policy-learning)  
   标签：评分：7.0/10、query:rlg
   evidence：机器人策略学习的世界模型
9. [Training LLM Agents for Spontaneous, Reward-Free Self-Evolution via World Knowledge Exploration](/20260420-20260519/2604.18131v1-training-llm-agents-for-spontaneous-reward-free-self-evolution-via-world-knowledge-exploration)  
   标签：评分：6.0/10、query:rlg
   evidence：LLM智能体的免奖励自我进化训练
10. [AJ-Bench: Benchmarking Agent-as-a-Judge for Environment-Aware Evaluation](/20260420-20260519/2604.18240v1-aj-bench-benchmarking-agent-as-a-judge-for-environment-aware-evaluation)  
   标签：评分：6.0/10、query:rlg
   evidence：面向环境感知评估的智能体裁判基准
11. [ClawEnvKit: Automatic Environment Generation for Claw-Like Agents](/20260420-20260519/2604.18543v1-clawenvkit-automatic-environment-generation-for-claw-like-agents)  
   标签：评分：6.0/10、query:rlg
   evidence：面向智能体训练的自动化环境生成


<div class="dpr-home-promo-card">
  <h3 class="dpr-home-promo-title">💬 社区与支持</h3>
  <ul class="dpr-home-promo-list">
    <li>欢迎 Star / Fork / Issue / PR</li>
    <li>QQ群：583867967（欢迎交流，已有：1151人）</li>
  </ul>
</div>
