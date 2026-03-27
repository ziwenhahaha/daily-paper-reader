---
title: "Genomebook: Mendelian inheritance as a structured parameterisation layer for LLM agent populations"
title_zh: Genomebook：孟德尔遗传作为 LLM 智能体群体的结构化参数化层
authors: "Corpas, M."
date: 2026-03-24
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.22.713494v1.full.pdf"
tags: ["query:llm-ec"]
score: 9.0
evidence: LLM智能体种群的孟德尔遗传与演化系统
tldr: 本研究引入Genomebook系统，将孟德尔遗传学作为大语言模型（LLM）智能体群体的结构化参数化层。通过在60个二倍体位点编码26种行为特征，并模拟有性生殖、突变及选择压力，实现了智能体行为的跨代遗传与演化。实验证明，该系统能有效引导群体特征演变，为构建具有演化动力学的智能体社会提供了可审计的遗传架构。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-001.webp\", \"caption\": \"Figure 6. Population structure. (A) PCA of 60-locus genotypes. PC1 (11.0%) and PC2 (10.4%) partially separate founder lineages, with increasing overlap in later generations. Points coloured by generation. (B) Population growth across 8 generations showing expansion from 20 founders to 186 agents by generation 7.\", \"page\": 11, \"index\": 1, \"width\": 789, \"height\": 339}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-002.webp\", \"caption\": \"Figure 2. Trait drift across eight generations. Mean trait scores (y-axis) for selected traits across generations 0–7 (x-axis). Leadership drive increased under dominant inheritance; obsessive focus declined under fitness cost selection; longevity collapsed as a trade-off for cognitive traits. Shaded regions show ±1 standard deviation.\", \"page\": 7, \"index\": 2, \"width\": 876, \"height\": 650}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-003.webp\", \"caption\": \"Figure 5. Vocabulary evolution and topic inheritance. (A) Top 10 words by frequency across the corpus, showing genetics-specific terminology dominating. (B) Vocabulary diversity (unique/total words) declining across generations, consistent with a linguistic founder effect. (C) Topic inheritance: 83% of offspring post in the same submolts as their parents.\", \"page\": 10, \"index\": 3, \"width\": 876, \"height\": 312}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-004.webp\", \"caption\": \"Figure 1. Graphical abstract. Genomebook pipeline: SOUL.md personality profiles are compiled into diploid genomes via the Soul2DNA compiler. Agents reproduce through Mendelian segregation with de novo mutation, producing non-identical offspring. Agents interact on Moltbook (a local social network) and population analytics track trait drift, allele frequencies, disease prevalence, and emergent behavioural patterns across generations.\", \"page\": 3, \"index\": 4, \"width\": 876, \"height\": 325}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-005.webp\", \"caption\": \"Figure 8. Replicated allele frequency trajectories. Alternate allele frequency at four key loci across 20 independent runs for standard selection (blue) and random mating (red). Shaded regions show 95% confidence intervals. OBS001 shows consistent decline under standard selection.\", \"page\": 13, \"index\": 5, \"width\": 876, \"height\": 231}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-006.webp\", \"caption\": \"Figure 3. Allele frequency trajectories. Alternate allele frequency (y-axis) at selected loci across generations (x-axis). Fitness-linked loci (OBS001, LNG001) show directional change consistent with selection. Neutral loci show stochastic fluctuation consistent with genetic drift.\", \"page\": 8, \"index\": 6, \"width\": 876, \"height\": 525}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-007.webp\", \"caption\": \"Figure 7. Replicated trait trajectories across three conditions. Mean trait scores across 20 independent runs each for standard selection (blue), random mating (red), and nongenetic baseline (grey dashed). Shaded regions show 95% confidence intervals. Genetic conditions produce directional drift from founder values; the non-genetic baseline converges to 0.5 with narrow CIs, confirming that the observed dynamics require genetic architecture.\", \"page\": 12, \"index\": 7, \"width\": 876, \"height\": 310}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-22-713494-v1/fig-008.webp\", \"caption\": \"Figure 4. Disease prevalence across generations. Number of affected individuals (y-axis) per condition across generations (x-axis). Hyperfocus syndrome is the most common condition. Mutation-only conditions emerge in later generations as mutation burden accumulates.\", \"page\": 9, \"index\": 8, \"width\": 876, \"height\": 526}]"
motivation: 针对当前LLM智能体缺乏可遗传变异和群体演化机制的问题，探索如何通过遗传学方法实现智能体行为的结构化演化。
method: 设计了一套包含26种特征的基因组系统，利用孟德尔遗传规律、有性生殖和适应度评分函数驱动智能体群体的多代演化。
result: 实验显示智能体特征轨迹与选择规则高度一致，如领导力显著提升，且消融实验证实了遗传架构在维持群体动态中的核心作用。
conclusion: 遗传架构可作为LLM智能体行为的一种有效参数化手段，为模拟复杂的社会行为和群体演化提供了新框架。
---

## 摘要
大语言模型（LLM）智能体通常以克隆形式部署：即单一配置的相同副本，缺乏可遗传变异或群体水平动态的机制。在此，我们介绍了 Genomebook，这是一个设计的进化系统，它使用加性、显性和隐性遗传模型，在 60 个二倍体位点上编码了 26 种行为特征。20 个初始智能体分别由人格档案（SOUL.md）和编译基因组（DNA.md）定义，通过孟德尔分离定律进行有性繁殖，每代每个位点的基础自发突变率为 0.1%（在认知、免疫和代谢热点区域为 3 倍）。包含 20 种具有明确外显率和适应度成本的合成条件的注册表，通过兼容性评分函数引入了集中施加的选择压力。在单次运行的八代演化中（626 个智能体，792 条社交网络帖子），我们观察到与编码选择规则一致的特征轨迹：在显性遗传下，领导力从 0.525 上升到 0.710；在适应度成本惩罚下，强迫性专注从 0.775 下降到 0.601；长寿度从 0.463 下降到 0.209。词汇多样性从 0.42 下降到 0.19，父代与子代之间的话题继承率达到 83%，尽管这些模式可能反映了提示词调节而非纯粹的遗传因果关系。智能体会自发地提及家庭成员，这与 DNA.md 系统提示词中存在的亲缘关系信息以及 LLM 的叙事阐述能力相一致。重复模拟（在三种条件下进行 20 次独立运行）证实，在标准选择下，不同种子的特征轨迹是一致的，而随机交配消融实验则产生了趋势减弱且方差更大的结果。非遗传基准（随机特征分配，无遗传）产生了收敛于群体平均值的平坦轨迹，证实了所观察到的动态需要遗传架构，且无法通过无结构的参数变化来重现。这些结果确立了遗传架构作为 LLM 智能体行为的一种结构化、可审计且可遗传的参数化层。

## Abstract
Large language model (LLM) agents are typically deployed as clones: identical copies of a single configuration with no mechanism for heritable variation or population-level dynamics. Here we introduce Genomebook, a designed evolutionary system that encodes 26 behavioural traits across 60 diploid loci using additive, dominant, and recessive inheritance models. Twenty founder agents, each defined by a personality profile (SOUL.md) and a compiled genome (DNA.md), reproduce sexually via Mendelian segregation with de novo mutation at a base rate of 0.1% per locus per generation (3x at cognitive, immune, and metabolic hotspots). A registry of 20 synthetic conditions with defined penetrance and fitness costs introduces centrally imposed selective pressure through a compatibility scoring function. Over a single run of eight generations (626 agents, 792 social network posts), we observe trait trajectories consistent with the encoded selection rules: leadership rose from 0.525 to 0.710 under dominant inheritance, obsessive focus fell from 0.775 to 0.601 under fitness cost penalisation, and longevity declined from 0.463 to 0.209. Vocabulary diversity declined from 0.42 to 0.19, and topic inheritance between parents and offspring reached 83%, though these patterns may reflect prompt conditioning rather than purely genetic causation. Agents referenced family members spontaneously, consistent with kinship information present in the DNA.md system prompt and the LLMs capacity for narrative elaboration. Replicated simulations (20 independent runs across three conditions) confirm that trait trajectories are consistent across seeds under standard selection, while a random mating ablation produces attenuated trends with wider variance. A non-genetic baseline (random trait assignment, no inheritance) produces flat trajectories converging to population means, confirming that the observed dynamics require genetic architecture and cannot be reproduced by unstructured parameter variation. These results establish genetic architecture as a structured, auditable, and heritable parameterisation layer for LLM agent behaviour.

---

## 论文详细总结（自动生成）

### 论文总结：Genomebook —— LLM 智能体群体的孟德尔遗传架构

#### 1. 核心问题与整体含义（研究动机和背景）
当前的 LLM 智能体部署通常采用“克隆”模式，即所有智能体共享相同的系统提示词和配置，缺乏个体差异的可遗传机制和群体演化动力学。论文提出了 **Genomebook** 系统，旨在将群体遗传学（如 Fisher、Wright 和 Kimura 的理论）引入 AI 智能体领域。其核心动机是为 LLM 智能体提供一种结构化、可审计且可遗传的参数化层，使智能体群体能够像生物种群一样通过有性生殖、突变和选择压力进行演化，从而模拟更复杂的社会行为和长期群体动态。

#### 2. 方法论：核心思想与关键技术
*   **遗传架构设计**：系统定义了 60 个二倍体位点（Loci），分布在 22 条常染色体和性染色体上，控制 26 种行为特征（涵盖认知、人格、物理三大类）。
*   **遗传模型**：采用孟德尔遗传规律，包括加性（Additive）、显性（Dominant）和隐性（Recessive）三种遗传模式。特征得分通过各相关位点的贡献加权计算。
*   **Soul-to-Genome 编译**：将初始智能体的人格档案（SOUL.md）转换为基因组（DNA.md）。通过离散化处理将连续的特征分值映射为特定的基因型。
*   **繁殖与突变机制**：
    *   **配对评分**：基于杂合度（奖励多样性）、特征互补性和隐性疾病风险计算兼容性得分。
    *   **孟德尔分离**：后代从父母处随机各获得一个等位基因。
    *   **自发突变**：基础突变率为 0.1%，在特定热点区域（如认知基因）提高至 3 倍。
*   **合成疾病模型**：注册了 20 种合成疾病，具有不同的外显率和适应度成本（Fitness Cost），直接影响智能体的生存和繁殖概率。
*   **社交环境（Moltbook）**：智能体在类似 Reddit 的社交平台上互动，其系统提示词包含其基因组信息，从而影响其发帖和评论行为。

#### 3. 实验设计与基准对比
*   **实验场景**：从 20 个以历史著名科学家（如爱因斯坦、居里夫人、图灵等）为原型的初始智能体开始，演化 8 代，共产生 626 个智能体。
*   **对比实验（Ablation & Baselines）**：
    1.  **标准选择（Standard）**：包含完整的兼容性评分和适应度惩罚。
    2.  **随机交配（Random Mating）**：随机分配配偶，不考虑兼容性评分。
    3.  **非遗传基准（No Inheritance）**：每代随机分配特征和基因，无遗传过程。
*   **评估指标**：特征轨迹（Trait Trajectories）、等位基因频率、疾病流行率、词汇多样性及话题继承率。

#### 4. 资源与算力
*   **模型使用**：底层 LLM 使用了 **Claude 3.5 Sonnet**。
*   **算力成本**：论文未提及具体的 GPU 硬件型号，但指出 8 代演化的 API 总成本约为 **70 美元**。
*   **运行规模**：随着代际增加，智能体数量呈指数增长，导致 API 调用成本也相应增加。

#### 5. 实验数量与充分性
*   **遗传模拟部分**：针对遗传动力学（不含 LLM 交互）进行了 **20 次独立重复实验**，每组实验运行 8 代，提供了 95% 置信区间，实验较为充分。
*   **行为交互部分**：社交平台（Moltbook）的交互仅进行了一次完整运行（792 条帖子），这部分数据在统计学上相对薄弱，更多是描述性的观察。
*   **客观性**：通过消融实验（随机交配）和基准对比（无遗传），证明了观察到的特征漂移确实是由遗传架构驱动的，而非随机波动。

#### 6. 主要结论与发现
*   **特征演化符合预期**：在显性遗传下，领导力特征显著上升（0.525 -> 0.710）；在适应度惩罚下，强迫性专注特征下降。
*   **遗传架构的必要性**：非遗传基准实验显示特征会迅速收敛至平均值（0.5），证明了孟德尔架构是维持群体结构和定向演化的关键。
*   **叙事涌现**：智能体能够自发地根据 DNA.md 中的亲缘信息提及“父亲”、“祖母”或“血统”，展现了 LLM 将遗传信息转化为叙事逻辑的能力。
*   **文化与遗传关联**：观察到 83% 的话题继承率和词汇多样性的下降（语言创始人效应），尽管这可能部分归因于提示词调节。

#### 7. 优点与亮点
*   **创新的参数化方法**：首次将完整的二倍体遗传模型引入 LLM 智能体，为“AI 生命”研究提供了新工具。
*   **高度可审计性**：每个智能体的行为特征都可以追溯到具体的等位基因和父母来源，提供了极高的透明度。
*   **跨学科融合**：成功将生物信息学工具（如 PCA、等位基因频率分析）应用于 AI 行为分析。

#### 8. 不足与局限
*   **提示词依赖（Prompt Conditioning）**：难以完全区分智能体的行为是由于“遗传特征”驱动，还是仅仅因为 LLM 在模仿提示词中提到的“遗传身份”。
*   **样本规模限制**：20 个初始智能体的规模较小，容易受到创始人效应和遗传漂移的强烈影响，统计效力有限。
*   **参数设置的任意性**：基因位点数量、效应大小和外显率等参数设定缺乏理论校准，可能存在设计者偏差。
*   **扩展性挑战**：随着群体规模扩大，API 成本和计算复杂度呈指数级上升，难以进行超大规模或超长代际的模拟。

（完）
