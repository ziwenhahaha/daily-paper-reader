---
title: Linking Codon- and Protein-Level Mutation Scores to Population Genetics Reveals Heterogeneous Selection Efficiency Across Escherichia coli Lineages
title_zh: 将密码子和蛋白质水平的突变评分与群体遗传学联系起来，揭示了大肠杆菌谱系中异质的选择效率
authors: "Mischler, M., Vigue, L., Croce, G., Weigt, M., Tenaillon, O."
date: 2026-03-18
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.16.711857v1.full.pdf"
tags: ["query:gene"]
score: 8.0
evidence: 群体遗传学和突变的选择效应
tldr: "本研究利用81,440个大肠杆菌基因组数据，结合统计物理学的直接耦合分析（DCA）模型，量化了不同突变类型的选择效应。研究揭示了非同义突变与同义突变在选择强度上的巨大差异，并发现选择效率与遗传漂变及生态生活方式（如致病性）密切相关，为理解群体遗传学与蛋白质适应度预测之间的关系提供了新视角。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-16-711857-v1/fig-001.webp\", \"caption\": \"\", \"page\": 12, \"index\": 1, \"width\": 1776, \"height\": 1776}]"
motivation: 旨在通过大规模基因组数据量化个体突变的突变效应，并探究不同突变类型及群体间的选择效率差异。
method: 采用直接耦合分析（DCA）模型对8万多个大肠杆菌基因组中的非同义突变进行评分，并结合密码子使用偏好评估同义突变。
result: 发现非同义突变的选择强度跨越六个数量级，而同义突变仅跨越一个数量级，且致病种群的选择效率比整个物种低一万倍。
conclusion: 研究证明了蛋白质变体适应度预测指标与群体遗传学数据的互补性，揭示了生态生活方式对选择效率的显著影响。
---

## 摘要
量化单个突变的选择效应对于理解其群体频率在自然选择和遗传漂变下如何演化至关重要。大型基因组数据集提供了一个现实实验，我们利用它来表征不同突变类型和群体中的选择效率。利用统计物理学模型——直接耦合分析（Direct Coupling Analysis, DCA），我们为在 81,440 个大肠杆菌基因组中识别出的单个非同义突变推导出了基于蛋白质信息的评分。我们表明，这些评分作为潜变量，捕捉了突变是有益、中性还是轻微到高度有害的概率。我们通过证明在大肠杆菌物种中，

## Abstract
Quantifying the selective effects of individual mutations is essential to understand how their population-wise frequencies evolve under natural selection and genetic drift. Large genomic datasets provide a real-life experiment that we exploit to characterize the efficiency of selection across different mutations types and populations. Using Direct Coupling Analysis, a model from statistical physics, we derive protein-informed scores for individual non-synonymous mutations identified in 81,440 Escherichia coli genomes. We show that these scores act as a latent variable capturing the probability that a mutation is beneficial, neutral, or mildly to highly deleterious. We contribute to the debate on the importance of synonymous mutations by demonstrating that their selection intensities span a single order of magnitude in the E. coli species, whereas non-synonymous mutations span six orders of magnitude. We further relate selection efficiency to genetic drift, defined as the inverse of population size, and to ecological lifestyle, and we identify a 10,000-fold reduction in selection efficiency between the entire E. coli species and its most pathogenic populations. Together, these results highlight how population genetics and protein variant fitness predictors inform one another: variation in selection efficiency is associated with shifts in the distribution of mutation scores, and population genetics data provide a benchmark to assess the accuracy of these scores.

Graphical abstract

O_FIG O_LINKSMALLFIG WIDTH=200 HEIGHT=182 SRC="FIGDIR/small/711857v1_ufig1.gif" ALT="Figure 1">
View larger version (51K):
org.highwire.dtl.DTLVardef@b43d76org.highwire.dtl.DTLVardef@12f199forg.highwire.dtl.DTLVardef@13b1f8forg.highwire.dtl.DTLVardef@952377_HPS_FORMAT_FIGEXP  M_FIG Schematic representation of the analysis of polymorphism in 81,440 Escherichia coli genomes.

458,443 polymorphic codon sites were identified and oriented using homologous sequences from closely related species. Mutations can be classified as synonymous or non-synonymous based on whether they alter the amino-acid sequence encoded, and real-valued scores predictive of fitness effects can be attributed to mutations within each of these classes. Codon scores reflect the global codon usage preference within the E. coli genome. DCA scores capture position- and amino-acid-specific preference as well as epistatic constraints and are obtained for each protein from a set of distantly related homologous sequences. Coupled with the abundance of polymorphic sites within different E. coli subpopulations, these different polymorphism classifications allow to precisely compare the intensity of selection between different types of mutations and across populations with distinct lifestyles, illustrated here by their pathogenic power.

C_FIG