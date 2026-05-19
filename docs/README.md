<div class="dpr-home-notice-card">
  <h3 class="dpr-home-notice-title">🚀 Start Here</h3>
  <ul class="dpr-home-notice-list">
    <li><a href="#/tutorial/README">使用教程</a></li>
  </ul>
</div>

## 每次日报
- 最新运行日期：2026-04-20 ~ 2026-05-19
- 运行时间：2026-05-19 14:32:53 UTC
- 运行状态：成功
- 本次总论文数：27
- 精读区：16
- 速读区：11

### 今日简报（AI）
<think>The user is speaking Chinese. They want a summary: three lines, no markdown headings, no JSON. They gave data: the daily report date range, status, total number of articles (27), detailed reading 16, speed reading 11. Then they have "精读列表" (detailed reading list) with two entries with scores: "《OpenGame: Open Agentic Coding for Games》（9.0/10）", "《Empowering NPC Dialogue with Environmental Context Using LLMs and Panoramic Images》（9.0/10）". And "速读列表" (speed reading list) with three entries: same two (maybe duplicates?), actually they have the same article again, plus other two: "《CreativeGame:Toward Mechanic-Aware Creative Game Generation》（8.0/10）", "《Co-Evolving LLM Decision and Skill Bank Agents for Long-Horizon Tasks》（8.0/10）". So the list shows a duplicate entry: "《Empowering NPC Dialogue with Environmental Context Using LLMs and Panoramic Images》（8.0/10）" appears as speed reading with 8.0/10, which is less than its detailed reading version. So perhaps we have duplicates across lists.

Goal: output 1-3 lines: line 1: a one-sentence summary of what was done today, suitable for title. Probably: "本周共阅读27篇文章，其中16篇精读，11篇速读。" Something like that.

Line 2: one sentence giving the most worth-reading directions/conclusions. Must be based on data: the highest-scoring detailed reading (9.0) includes OpenGame (agentic coding for games) and Empowering NPC Dialogue with environmental context. The speed reading list includes same article and CreativeGame and Co-Evolving LLM Decision. So perhaps we can say: the top-scoring works focus on open agentic coding for games and LLM-driven NPC dialogue with environment context, indicating trends in interactive gaming and autonomous agents.

Line 3: suggestion for next steps for ordinary readers. E.g., "建议关注游戏自动化生成、NPC情境感知等前沿方向，了解LLM在游戏中的创新应用。" Something like that. Must be within 3 sentences total? Actually lines: we need to output 1-3 lines (one line per each sentence). So each line corresponds to a sentence. The instructions: "一句概括今天做了什么，适合标题感官。" So line 1: one-sentence summary of what was done, suitable for headline.

Line 2: "一句给出最值得看的 1~2 个方向/结论。" So one sentence giving the most worth-reading 1~2 directions or conclusions. So we need to pick maybe two top topics: OpenGame and Empowering NPC Dialogue; also maybe CreativeGame and Co-Evolving LLM Decision. But we need to give only 1~2 directions. Possibly the best direction is "基于LLM的游戏智能化（NPC对话和游戏机制生成）" and "开放代理式代码生成在游戏开发中的应用". So we can mention both.

Line 3: "一句给出下步建议（面向普通读者）". So a suggestion for next steps for the general reader.

Thus final output should be three lines, no markdown, no JSON, just lines of text.

We need to base on given data; not fabricate info. Avoid adding info not present. Keep concise.

Let's draft:

1: "本周共阅读27篇文章，其中16篇精读、11篇速读。" This works as summary.

2: "最高评分（9.0/10）聚焦于开放代理式游戏代码生成和基于全景图像的NPC环境感知对话，显示出AI在游戏</think>
- 详情：[/20260420-20260519/README](/20260420-20260519/README)

### 精读区论文标签
1. [OpenGame: Open Agentic Coding for Games](/20260420-20260519/2604.18394v1-opengame-open-agentic-coding-for-games)  
   标签：评分：9.0/10、query:game-ai
   evidence：开源智能体框架用于游戏开发
2. [Empowering NPC Dialogue with Environmental Context Using LLMs and Panoramic Images](/20260420-20260519/2604.19192v2-empowering-npc-dialogue-with-environmental-context-using-llms-and-panoramic-images)  
   标签：评分：9.0/10、query:game-ai
   evidence：NPC对话增强结合大语言模型和环境上下文
3. [Revac: A Social Deduction Reasoning Agent](/20260420-20260519/2604.19523v1-revac-a-social-deduction-reasoning-agent)  
   标签：评分：9.0/10、query:game-ai
   evidence：社交推理游戏Mafia的AI智能体
4. [From World-Gen to Quest-Line: A Dependency-Driven Prompt Pipeline for Coherent RPG Generation](/20260420-20260519/2604.25482v1-from-world-gen-to-quest-line-a-dependency-driven-prompt-pipeline-for-coherent-rpg-generation)  
   标签：评分：9.0/10、query:game-ai
   evidence：RPG程序化内容生成管线依赖建模
5. [StratFormer: Adaptive Opponent Modeling and Exploitation in Imperfect-Information Games](/20260420-20260519/2604.25796v1-stratformer-adaptive-opponent-modeling-and-exploitation-in-imperfect-information-games)  
   标签：评分：9.0/10、query:game-ai
   evidence：不完全信息博弈对手建模
6. [From LLM-Driven Trading Card Generation to Procedural Relatedness: A Pokémon Case Study](/20260420-20260519/2604.27972v1-from-llm-driven-trading-card-generation-to-procedural-relatedness-a-pokmon-case-study)  
   标签：评分：9.0/10、query:game-ai
   evidence：程序化生成TCG卡牌
7. [Strat-Reasoner: Reinforcing Strategic Reasoning of LLMs in Multi-Agent Games](/20260420-20260519/2605.04906v1-strat-reasoner-reinforcing-strategic-reasoning-of-llms-in-multi-agent-games)  
   标签：评分：9.0/10、query:mas
   evidence：多智能体游戏策略推理的强化学习框架
8. [Mazocarta: A Seeded Procedural Deckbuilder for Instrumented Game Development](/20260420-20260519/2605.08319v1-mazocarta-a-seeded-procedural-deckbuilder-for-instrumented-game-development)  
   标签：评分：9.0/10、query:game-ai
   evidence：基于种子的程序化套牌构建游戏及确定性模拟
9. [Towards Generalist Game Players: An Investigation of Foundation Models in the Game Multiverse](/20260420-20260519/2605.09965v1-towards-generalist-game-players-an-investigation-of-foundation-models-in-the-game-multiverse)  
   标签：评分：9.0/10、query:game-ai
   evidence：基础模型作为通用游戏智能体在游戏多元宇宙中研究
10. [Policy Gradient Methods for Non-Markovian Reinforcement Learning](/20260420-20260519/2605.10816v1-policy-gradient-methods-for-non-markovian-reinforcement-learning)  
   标签：评分：9.0/10、query:rl
   evidence：非马尔可夫决策过程的策略梯度强化学习理论
11. [DelAC: A Multi-agent Reinforcement Learning of Team-Symmetric Stochastic Games](/20260420-20260519/2605.12555v1-delac-a-multi-agent-reinforcement-learning-of-team-symmetric-stochastic-games)  
   标签：评分：9.0/10、query:mas
   evidence：团队对称博弈的多智能体强化学习算法
12. [Macro-Action Based Multi-Agent Instruction Following through Value Cancellation](/20260420-20260519/2605.12655v1-macro-action-based-multi-agent-instruction-following-through-value-cancellation)  
   标签：评分：9.0/10、query:mas
   evidence：多智能体强化学习中的价值校正方法实现指令跟随
13. [CA2: Code-Aware Agent for Automated Game Testing](/20260420-20260519/2605.13918v1-ca2-code-aware-agent-for-automated-game-testing)  
   标签：评分：9.0/10、query:game-ai
   evidence：强化学习智能体自动游戏测试
14. [Watermarking Game-Playing Agents in Perfect-Information Extensive-Form Games](/20260420-20260519/2605.14283v1-watermarking-game-playing-agents-in-perfect-information-extensive-form-games)  
   标签：评分：9.0/10、query:game-ai
   evidence：完美信息博弈中游戏智能体的水印技术
15. [Data-Augmented Game Starts for Accelerating Self-Play Exploration in Imperfect Information Games](/20260420-20260519/2605.14379v1-data-augmented-game-starts-for-accelerating-self-play-exploration-in-imperfect-information-games)  
   标签：评分：9.0/10、query:game-ai
   evidence：多智能体强化学习用于不完全信息游戏，自我对局加速
16. [ReactiveGWM: Steering NPC in Reactive Game World Models](/20260420-20260519/2605.15256v1-reactivegwm-steering-npc-in-reactive-game-world-models)  
   标签：评分：9.0/10、query:game-ai
   evidence：显式解耦玩家操作与NPC行为的反应式游戏世界模型

### 速读区论文标签
1. [Empowering NPC Dialogue with Environmental Context Using LLMs and Panoramic Images](/20260420-20260519/2604.19192v1-empowering-npc-dialogue-with-environmental-context-using-llms-and-panoramic-images)  
   标签：评分：8.0/10、query:game-ai
   evidence：LLM增强NPC对话
2. [CreativeGame:Toward Mechanic-Aware Creative Game Generation](/20260420-20260519/2604.19926v1-creativegametoward-mechanic-aware-creative-game-generation)  
   标签：评分：8.0/10、query:game-ai
   evidence：用于迭代游戏生成的多智能体系统，智能化游戏创作
3. [Co-Evolving LLM Decision and Skill Bank Agents for Long-Horizon Tasks](/20260420-20260519/2604.20987v1-co-evolving-llm-decision-and-skill-bank-agents-for-long-horizon-tasks)  
   标签：评分：8.0/10、query:game-ai
   evidence：长时程任务中大语言模型游戏智能体的技能学习
4. [Nemobot Games: Crafting Strategic AI Gaming Agents for Interactive Learning with Large Language Models](/20260420-20260519/2604.21896v1-nemobot-games-crafting-strategic-ai-gaming-agents-for-interactive-learning-with-large-language-models)  
   标签：评分：8.0/10、query:game-ai
   evidence：用于战略游戏和智能角色设计的LLM驱动游戏智能体
5. [Cutscene Agent: An LLM Agent Framework for Automated 3D Cutscene Generation](/20260420-20260519/2604.25318v1-cutscene-agent-an-llm-agent-framework-for-automated-3d-cutscene-generation)  
   标签：评分：7.0/10、query:game-ai
   evidence：视频游戏自动过场动画生成框架
6. [Building Persona-Based Agents On Demand: Tailoring Multi-Agent Workflows to User Needs](/20260420-20260519/2604.27882v1-building-persona-based-agents-on-demand-tailoring-multi-agent-workflows-to-user-needs)  
   标签：评分：7.0/10、query:mas
   evidence：动态角色化智能体生成的多智能体系统
7. [Population-Aware Imitation Learning in Mean-field Games with Common Noise](/20260420-20260519/2605.03357v1-population-aware-imitation-learning-in-mean-field-games-with-common-noise)  
   标签：评分：7.0/10、query:mas
   evidence：平均场博弈中的模仿学习
8. [Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning](/20260420-20260519/2605.06130v1-skill1-unified-evolution-of-skill-augmented-agents-via-reinforcement-learning)  
   标签：评分：7.0/10、query:rl
   evidence：智能体强化学习技能蒸馏
9. [Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning](/20260420-20260519/2605.06130v3-skill1-unified-evolution-of-skill-augmented-agents-via-reinforcement-learning)  
   标签：评分：6.0/10、query:mas
   evidence：多智能体强化学习与技能库演化
10. [Do Vision-Language-Models show human-like logical problem-solving capability in point and click puzzle games?](/20260420-20260519/2605.11223v1-do-vision-language-models-show-human-like-logical-problem-solving-capability-in-point-and-click-puzzle-games)  
   标签：评分：6.0/10、query:game-ai
   evidence：VLM逻辑问题解决能力 puzzle游戏基准测试
11. [WebGameBench: Requirement-to-Application Evaluation for Coding Agents via Browser-Native Games](/20260420-20260519/2605.17637v1-webgamebench-requirement-to-application-evaluation-for-coding-agents-via-browser-native-games)  
   标签：评分：6.0/10、query:game-ai
   evidence：通过浏览器原生游戏评估编码智能体的基准测试


<div class="dpr-home-promo-card">
  <h3 class="dpr-home-promo-title">💬 社区与支持</h3>
  <ul class="dpr-home-promo-list">
    <li>欢迎 Star / Fork / Issue / PR</li>
    <li>QQ群：583867967（欢迎交流，已有：1151人）</li>
  </ul>
</div>
