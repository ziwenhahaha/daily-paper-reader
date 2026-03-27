---
title: "WINDEX: A hierarchical integration of site- and window-based statistics for characterizing the footprint of positive selection in genome-wide population genetic data"
title_zh: WINDEX：一种层级整合基于位点和窗口统计量的方法，用于表征全基因组群体遗传数据中正向选择的足迹
authors: "Snell, H., McCallum, S., Raghavan, D., Singh, R., Ramachandran, S., Sugden, L."
date: 2026-03-26
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.26.714384v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 表征全基因组群体遗传数据中的选择
tldr: "WINDEX是一种新型计算方法，旨在通过分层整合位点级和窗口级统计数据，更精确地检测基因组中的正向选择信号。该方法利用嵌套隐状态模型区分中性、连锁和选择扫荡区域，克服了以往方法无法同时利用多分辨率数据的局限。在模拟数据和1000基因组项目数据中，WINDEX展现了更强的定位能力，并估算出人类基因组中约9.7-10.5%的区域受到正向选择压力。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-26-714384-v1/fig-001.webp\", \"caption\": \"Fig 3. Comparative performance of WINDEX vs. NB-SWIF(r) in evolutionary simulations at the site scale show superior localization of sweep loci using WINDEX. Similar to Fig. 2, WINDEX and NB-SWIF(r) were both evaluated in their abilities to localize the footprint of two strong positive selection scenarios using evolutionary simulations (see Methods). All four panels depict +/- 1kb around the true sweep locus inside the true sweep windows denoted by the labels in Fig. 2. (Fig. 3A and 3B) WINDEX classifies the true sweep locus in high proportions of testing simulations (red bars). Additionally, WINDEX accurately classifies sites labeled as linked that are close to the true sweep locus (yellow bars) with no classifications reported for neutral signals. (Fig. 3C and 3D) NB-SWIF(r) also identifies the true sweep locus in high proportions of testing simulations, but struggles to localize this signal within a small genetic window of the true sweep locus. In both scenarios, there are putative sweep sites nearby classified with varying proportions of testing simulations supporting them as well as many true-labeled linked sites classified as neutrally evolving.\", \"page\": 15, \"index\": 1, \"width\": 979, \"height\": 802}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-26-714384-v1/fig-002.webp\", \"caption\": \"Fig 2. Comparative performance of WINDEX vs. NB-SWIF(r) in evolutionary simulations at the non-overlapping window scale shows superior localization of sweep-containing windows with WINDEX. We trained WINDEX with evolutionary simulations using the Three Population out of Africa demographic model [20] with varying positive selective sweep scenarios (see Table 1). WINDEX was tested in two conditions: 300 generations before present, selection coefficient = 0.05 and 600 generations before present, selection coefficient = 0.02, both based on sweep mutation final allele frequency (≥ 60%, see ??). (Figs. 2A and 2B) WINDEX correctly classifies the true sweep window in a large proportion of testing simulations across two strong selection scenarios. The red centered bar shows the number of testing simulations where WINDEX accurately classifies the sweep window. Surrounding yellow bars also show that WINDEX classifies nearby windows as linked with increasingly higher proportions closer to the true sweep window, which is expected in a true positive selective sweep. (Figs. 2C and 2D) The Naive-Bayes version of SWIF(r) (NB-SWIF(r)) [17] was trained with the same simulation set for method comparison. While NB-SWIF(r) has the highest sweep proportion in the true sweep window in both scenarios, the number of testing simulations supporting this classification are much lower than with WINDEX. Similarly, the linked footprint around the true sweep window is diminished compared to the WINDEX classifications (yellow bars).\", \"page\": 13, \"index\": 2, \"width\": 979, \"height\": 797}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-26-714384-v1/fig-003.webp\", \"caption\": \"Table 2. Comparative whole-genome scans with WINDEX and S/HIC reveal similar classification proportions of positive selection across populations.\", \"page\": 19, \"index\": 3, \"width\": 975, \"height\": 537}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-26-714384-v1/fig-004.webp\", \"caption\": \"Fig 4. Comparative scans in EDAR and SLC24A5 with iSAFE and WINDEX show that WINDEX outperforms iSAFE in localization of candidate signals of positive selection. Using both iSAFE and WINDEX, 300kb regions of canonical selection signals were scanned in YRI and CEU genomes from the 1000 Genomes Project [18] and compared based on accuracy of localization. (Figs. 4A and 4D) In both canonical regions of positive selection, iSAFE ranks the putative variant within the top five strongest signals, but shows other highly ranked variants close by, which pose localization challenges. (Figs. 4B and 4E) WINDEX accurately localizes the putative variants in both canonical regions of positive selection while classifying all surrounding sites as linked. (Figs. 4C and 4F) Implementation of a stochastic backtrace evaluation algorithm at the site level allows for a measure of uncertainty to be assigned to WINDEX classifications. Over 100 stochastic backtraces, both putative signals are supported 94%, while low-level support is shown for nearby signals.\", \"page\": 17, \"index\": 4, \"width\": 976, \"height\": 1061}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-26-714384-v1/fig-005.webp\", \"caption\": \"Fig 1. Method outline and state structure of WINDEX. (Fig. 1A) WINDEX requires input of summary statistics calculated from aligned haplotype data, both at the non-overlapping window level (such as Tajima’s D [4]) and the site-level (such as iHS [3]). (Fig. 1B) WINDEX is a hierarchical hidden Markov model (HHMM) consisting of two main state levels: a window-based level that operates at a user-defined window size resolution with window statistics as emissions, and a site-based level that operates at an individual variant resolution with site statistics as emissions. WINDEX works by initializing first at the window level, then moving through the sites within that window in one of the site-level substructures, then transitioning back to the window level for the next window state transition. The window-level transitions are controlled by a single transition matrix, while the site substructures each have their own transition matrices. See Methods for emission training description and Supplementary Tables S3 and S4 for transition probability definitions.\", \"page\": 5, \"index\": 5, \"width\": 832, \"height\": 1040}]"
motivation: 现有方法通常只关注单一分辨率的统计数据，未能同时整合位点级和窗口级信息，限制了检测正向选择信号的效力。
method: 开发了WINDEX模型，通过将位点级隐状态嵌套在窗口级状态中，实现了对不同分辨率统计数据的分层集成与联合建模。
result: "在模拟和真实数据测试中，WINDEX显著提升了对选择扫荡区域的定位精度，并估算出不同人群基因组中受正向选择影响的比例为9.7-10.5%。"
conclusion: WINDEX通过多分辨率数据整合，为识别基因组适应性演化信号提供了更精确的工具，并为全基因组正向选择比例的估算提供了有力支持。
---

## 摘要
适应性突变，即赋予适应度优势的突变，会在遗传数据中留下独特的信号。计算方法利用一系列统计和机器学习分类技术，提高了遗传样本中适应性突变的定位能力。然而，这些方法错失了共同整合位点级和窗口级统计量的机会，因此未能利用所有可用的统计证据来检测选择。我们的方法 WINDEX 结合了这些不同分辨率的统计量，以提高在搭便车信号中检测适应性突变的能力。我们的模型通过定义对应于中性、连锁和选择清除区域的基于位点和窗口的隐状态，同时整合了不同分辨率的发射，其中基于位点的状态和转移模型嵌套在基于窗口的状态中。通过使用具有不同选择参数的进化模拟，我们验证了 WINDEX 分类正向选择清除的能力。利用 1000 基因组计划的数据，我们展示了 WINDEX 能够识别包含选择清除信号的区域，并比现有方法在这些区域内提供更好的定位。此外，在全基因组范围内使用 WINDEX 可以估算受正向选择压力影响的整个基因组比例；我们在不同群体中估算的 9.7-10.5% 这一结果，为这些数值的其他初步估算提供了支持。

## Abstract
Adaptive mutations, or mutations that confer a fitness benefit, can leave behind distinct signals in genetic data. Computational methods have improved the localization of adaptive mutations in genetic samples using a range of statistical and machine learning classification techniques. However, these methods miss the opportunity to jointly integrate statistics at both the site and window-based level, thus failing to harness all available statistical evidence to detect selection. Our method, WINDEX, combines these different resolutions of statistics to improve the detection of adaptive mutations among hitchhiking signals. Our model simultaneously integrates emissions at different resolutions by defining site-based and window-based latent states corresponding to neutral, linked, and sweep regions, with the site-based states and transition models nested within the window-based states. Using evolutionary simulations with varying selection parameters, we validate the ability of WINDEX to classify positive selective sweeps. Using data from the 1000 Genomes Project, we show that WINDEX is able to identify regions harboring signals of selective sweeps, and provides improved localization within those regions over existing methods. In addition, using WINDEX genome-wide allows for estimation of the proportion of whole genomes that are under positive selective pressures; our estimates of between 9.7-10.5% across different populations provide support for other preliminary estimates of these quantities.

---

## 论文详细总结（自动生成）

### 论文总结：WINDEX——层级整合多分辨率统计量检测正向选择

#### 1. 核心问题与整体含义（研究动机和背景）
在群体遗传学中，识别正向选择（Positive Selection）的足迹对于理解物种适应性演化至关重要。现有的检测方法通常存在局限性：要么关注**窗口级（Window-based）**统计量（如 Tajima’s D），擅长捕捉区域性的整体信号但分辨率较低；要么关注**位点级（Site-based）**统计量（如 iHS），分辨率高但容易受到背景噪声和连锁不平衡（LD）的干扰。
**核心问题：** 如何有效地整合不同基因组分辨率的统计证据，以更精确地定位适应性突变并区分真正的选择信号与周边的“搭便车”（Hitchhiking）连锁信号？

#### 2. 论文提出的方法论
论文提出了 **WINDEX**（Window-Integrated Detection of Evolutionary eXcursions），这是一种基于**层级隐马尔可夫模型（Hierarchical Hidden Markov Model, HHMM）**的新型计算框架。
*   **核心思想：** 将基因组视为具有嵌套结构的序列。高层级是“窗口状态”，底层级是嵌套在窗口内的“位点状态”。
*   **关键技术细节：**
    *   **双层状态结构：** 模型定义了三个主要演化状态：中性（Neutral）、连锁（Linked）和扫荡（Sweep）。
    *   **层级嵌套：** 窗口级状态决定了该区域的整体演化背景，而位点级状态则在窗口内部捕捉具体的变异特征。例如，一个“扫荡窗口”内可能包含真正的“扫荡位点”以及受其影响的“连锁位点”。
    *   **发射概率（Emissions）：** 窗口级发射基于区域统计量（如 Tajima’s D, $F_{ST}$），位点级发射基于单变异统计量（如 iHS, nSL）。
    *   **随机回溯（Stochastic Backtrace）：** 为了量化分类的不确定性，WINDEX 实现了随机回溯算法，通过多次采样路径来评估特定位点受选择支持的概率。

#### 3. 实验设计
*   **数据集：**
    *   **模拟数据：** 使用 SLiM 3 软件，基于“走出非洲”三群体人口历史模型生成合成数据，设置不同的选择系数（$s=0.02, 0.05$）和选择发生时间。
    *   **真实数据：** 1000 基因组计划（1000 Genomes Project）中的 YRI（约鲁巴人）和 CEU（北欧裔美国人）群体数据。
*   **Benchmark 与对比方法：**
    *   **NB-SWIF(r)：** 朴素贝叶斯版本的 SWIF(r)，用于评估多统计量整合的效果。
    *   **iSAFE：** 用于对比在已知选择区域（如 *EDAR*, *SLC24A5*）内的定位精度。
    *   **S/HIC：** 用于对比全基因组范围内选择区域比例的估算。

#### 4. 资源与算力
论文中**未明确说明**具体的硬件配置（如 GPU 型号、数量）或具体的训练时长。但提到 WINDEX 涉及复杂的 HHMM 参数训练和全基因组扫描，通常这类方法对 CPU 内存和计算时间有一定要求，尤其是进行多次随机回溯采样时。

#### 5. 实验数量与充分性
*   **实验规模：** 进行了大量的进化模拟以验证模型在不同选择强度和时间下的鲁棒性。
*   **充分性：** 实验设计较为全面，涵盖了从受控模拟到真实复杂基因组的应用。通过对比 iSAFE 等专门用于定位的方法，证明了其在精细定位上的优势；通过全基因组扫描，验证了其在大规模数据处理上的可行性。
*   **客观性：** 使用了标准的人口历史模型进行模拟，并选择了公认的正向选择位点（如 *EDAR*）作为“金标准”进行验证，实验结果具有较强的说服力。

#### 6. 主要结论与发现
*   **定位精度提升：** WINDEX 在模拟实验中表现出比 NB-SWIF(r) 更强的定位能力，能更准确地识别出扫荡窗口中心附近的真实选择位点。
*   **区分连锁信号：** 相比于传统方法容易将扫荡区域周边的连锁位点误报为选择位点，WINDEX 能有效将这些位点归类为“Linked”状态。
*   **人类基因组选择比例：** WINDEX 估算出人类基因组中约 **9.7% 至 10.5%** 的区域受到正向选择压力的影响。这一估算值与近期其他研究结果一致，为理解人类适应性演化的普遍性提供了证据。
*   **真实案例验证：** 在 *EDAR*（东亚人群选择信号）和 *SLC24A5*（欧洲人群肤色相关选择信号）区域，WINDEX 成功定位了候选变异，且不确定性较低。

#### 7. 优点
*   **多分辨率整合：** 首次通过 HHMM 框架有机结合了窗口级和位点级信息，克服了单一分辨率分析的片面性。
*   **不确定性量化：** 引入随机回溯机制，使得结果不仅是一个分类标签，还包含置信度评估。
*   **状态定义清晰：** 明确区分“连锁”与“扫荡”状态，有助于减少假阳性并提高生物学解释力。

#### 8. 不足与局限
*   **模型复杂性：** HHMM 的参数训练和推断比简单的机器学习模型（如随机森林或朴素贝叶斯）更复杂，计算开销可能较大。
*   **依赖模拟准确性：** 模型的发射概率依赖于模拟数据，如果模拟的人口历史模型与真实情况偏差较大，可能会影响分类准确性。
*   **应用限制：** 目前主要针对强正向选择（Hard Sweeps）设计，对于软扫荡（Soft Sweeps）或多基因选择（Polygenic Selection）的检测效力尚待进一步验证。

（完）
