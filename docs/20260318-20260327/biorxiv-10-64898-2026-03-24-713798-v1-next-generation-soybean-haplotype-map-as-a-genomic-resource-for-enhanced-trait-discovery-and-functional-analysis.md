---
title: Next-Generation Soybean Haplotype Map as A Genomic Resource for Enhanced Trait Discovery and Functional Analysis
title_zh: 下一代大豆单倍型图谱：用于增强性状发现和功能分析的基因组资源
authors: "Khan, A. W., Doddamani, D., Song, Q., Vuong, T. D., Chhapekar, S. S., Ye, H., Garg, V., Varshney, R. K., Nguyen, H. T."
date: 2026-03-26
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.24.713798v1.full.pdf"
tags: ["query:gene"]
score: 10.0
evidence: 全球大豆单倍型图谱与基因组资源
tldr: "本研究通过对1,278份大豆品种进行全基因组测序，构建了包含1137万个SNP和205万个短插入缺失的第二代大豆单倍型图谱（GmHapMap-II）。该图谱揭示了全球大豆的遗传多样性与群体结构，并成功应用于鉴定蛋白质含量相关的新基因组区域及大豆胞囊线虫抗性位点的变异分析。该资源为大豆性状挖掘、功能分析及分子育种提供了重要的基因组学支撑。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-24-713798-v1/fig-001.webp\", \"caption\": \"Figure 6: Machine learning-based genomic prediction of SCN resistance integrating 1077 haplotype and copy number variation data at the rhg1 locus. (A) Heatmap showing 1078 phenotypic responses of soybean accessions to different SCN HG types (races 1, 3, 5, and 14). 1079 Accessions are hierarchically clustered (left dendrogram) with population structure indicated by 1080 colored bars (left margin). (B) Cross-validation accuracy comparison across feature types for 1081 multi-class (blue bars) and binary (orange bars) classification of SCN resistance. Three feature 1082 sets were evaluated: haplotype information alone, copy number variation data as continuous 1083 variables, and combined haplotype + CNV features. (C) Performance comparison of nine 1084 machine learning algorithms for multi-class SCN resistance prediction using combined haplotype 1085 and CNV features. Top-performing models include AdaBoost, LDA, and Random Forest. 1086\", \"page\": 31, \"index\": 1, \"width\": 1064, \"height\": 361}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-24-713798-v1/fig-002.webp\", \"caption\": \"Figure 7. Deleterious mutation burden across soybean populations. (A) Box plots showing 1088 the number of deleterious alleles per individual in wild (G. soja), landrace, and modern cultivar 1089 accessions. Boxes represent the interquartile range (IQR); whiskers extend to 1.5× IQR; dots 1090 represent outliers. *** p < 0.001 (Mann-Whitney U test). (B) Pairwise Mann-Whitney U test p-1091 value matrix (displayed as −log (p-value)) for all three population comparisons. Red indicates 1092 high significance. (C) Bar plots showing the proportion of coding variants classified as 1093 deleterious (nonsynonymous, SIFT < 0.05), tolerated (nonsynonymous, SIFT ≥ 0.05), or 1094 synonymous in each population. Error bars represent ± standard error. (D) Scatter plot of 1095 deleterious alleles vs. tolerated alleles per individual accession. The dashed line represents equal 1096 burden (slope = 1). Colors correspond to population groups as indicated in the legend. 1097\", \"page\": 31, \"index\": 2, \"width\": 1065, \"height\": 341}]"
motivation: 旨在构建更高密度的全球大豆单倍型图谱，以克服低密度标记在性状挖掘和功能基因组研究中的局限性。
method: "对1,278份大豆资源进行全基因组重测序，并结合群体结构分析、连锁不平衡分析及机器学习预测模型进行综合研究。"
result: 成功构建了GmHapMap-II，发现了影响蛋白质含量的新位点，并详细刻画了抗线虫病关键位点的单倍型多样性与拷贝数变异。
conclusion: 该单倍型图谱是增强大豆性状发现和功能分析的重要基因组资源，将显著推动高产抗病大豆新品种的选育。
---

## 摘要
我们展示了一个通过对 1,278 份大豆（Glycine max）和野大豆（Glycine soja）种质进行全基因组测序生成的全球大豆单倍型图谱，包含 1,137 万个 SNP 和 205 万个短插入和缺失。该图谱（GmHapMap-II）捕捉到了前所未有的全球遗传多样性，反映了全球大豆基因库的广泛范围。群体结构分析揭示了六个地理上截然不同的亚群，这些亚群影响了连锁并塑造了重组。该单倍型变异图谱被用于鉴定 15 号染色体上与粗蛋白含量相关的新基因组区域，而这些区域在较低 SNP 密度的芯片中未被检测到。基于连锁不平衡（LD）的单倍型分析揭示了一个与粗蛋白含量相关的优异单倍型。构建的单倍型图谱实现了对大豆胞囊线虫（SCN）相关的 rhg-1 和 Rhg-4 位点的单倍型多样性和拷贝数多态性的详细表征，揭示了新的单倍型结构以及相对于先前表征的基因型具有更高拷贝数变异（CNV）的种质系。我们利用单倍型图谱矩阵，采用基于机器学习（ML）的多类变异基因组预测方法来预测 SCN 表型，并将以基因为中心的单倍型编入一个用户友好的数据库中。分析揭示了大豆种质中存在的有害等位基因的程度，以及育种者如何利用有益等位基因并清除有害等位基因。该单倍型图谱将作为基于性状定位的主要基因组资源，助力通过基因组学手段开发改良品种。

## Abstract
We present a global soybean haplotype map generated from whole-genome sequencing of 1,278 Glycine max and Glycine soja accessions, comprising 11.37 million SNPs and 2.05 million short insertions and deletions. This map (GmHapMap-II) captures unprecedented worldwide genetic diversity, reflecting the broad extent of the global soybean gene pool. Population structure analyses revealed six geographically distinct subpopulations that affected the linkage and shaped the recombination. The haplotype variation map was used to identify novel genomic regions associated with crude protein content on chromosome 15 that were not detected by a lower SNP density array. LD-based haplotype analysis revealed a superior haplotype for crude protein content. The constructed haplotype map enabled detailed characterization of haplotype diversity and copy number polymorphism at the SCN-associated rhg-1 and Rhg-4 loci, revealing both novel haplotype structures and germplasm lines with elevated CNV relative to previously characterized genotypes. We employed the HapMap matrix for a multi-class variations ML-based genomic prediction approach to predict phenotypes for SCN and catalogued the gene-centric haplotypes in a user-friendly database. The analysis revealed the extent of deleterious alleles present in the soybean germplasm and how breeders have deployed beneficial alleles and purged deleterious ones. The haplotype map will serve as a major genomic resource for trait-based mapping, enhancing efforts in the genomics-enabled development of improved cultivars.

---

## 论文详细总结（自动生成）

这是一份关于论文《Next-Generation Soybean Haplotype Map as A Genomic Resource for Enhanced Trait Discovery and Functional Analysis》（下一代大豆单倍型图谱：用于增强性状发现和功能分析的基因组资源）的结构化分析报告：

### 1. 核心问题与整体含义（研究动机和背景）
*   **核心问题**：尽管大豆是全球重要的蛋白质和油脂来源，但现有的基因组资源（如低密度SNP芯片）在捕捉结构变异、完整连锁不平衡（LD）以及解释复杂性状遗传力方面存在局限。
*   **研究动机**：为了满足2050年对植物蛋白的需求，迫切需要利用全球种质资源中的遗传多样性。研究者旨在通过全基因组重测序构建一个高分辨率、全球覆盖的单倍型图谱（GmHapMap-II），以克服传统标记密度不足的问题，精准定位控制关键农艺性状的基因。

### 2. 论文提出的方法论
*   **核心思想**：通过整合全球1,278份大豆资源的重测序数据，利用统一的生物信息学流程鉴定变异，并结合单倍型块（Haplotype Blocks）分析和机器学习模型，提升性状关联分析和表型预测的精度。
*   **关键技术细节**：
    *   **变异鉴定**：使用GATK4硬过滤流程，将短读段比对至近无缺口的Williams 82 v5参考基因组。
    *   **单倍型构建**：基于LD衰减和Gabriel置信区间法定义单倍型块，并使用`geneHapR`进行基因中心（Gene-centric）的单倍型分析。
    *   **性状关联**：采用FarmCPU和混合线性模型（MLM）进行多性状GWAS分析。
    *   **机器学习预测**：针对大豆胞囊线虫（SCN）抗性，整合了单倍型信息和拷贝数变异（CNV）作为特征，使用AdaBoost、随机森林、SVM等多种算法构建预测模型。
    *   **有害等位基因评估**：利用SIFT算法预测非同义突变的功能影响，量化不同群体（野生、农家种、品种）的遗传负荷。

### 3. 实验设计
*   **数据集**：共1,278份大豆资源，包括1,116份公开数据和162份新测序样本。涵盖了野生大豆（*G. soja*）、农家种、育种系和现代栽培种（*G. max*），地理来源覆盖美、中、韩、日、巴、澳等国。
*   **Benchmark（基准）**：
    *   将新开发的GmHapMap-II与目前广泛使用的**SoySNP50K芯片**进行对比，评估其在GWAS定位中的分辨率。
    *   在SCN抗性预测中，对比了“仅单倍型”、“仅CNV”以及“两者结合”三种特征集的预测效果。
*   **对比场景**：针对种子蛋白含量、含油量、倒伏性、茎生长习性和棕榈酸含量等多个农艺性状进行了关联分析验证。

### 4. 资源与算力
*   **算力说明**：论文提到计算工作是在密苏里大学（University of Missouri）IT部门研究支持解决方案运营的高性能计算（HPC）基础设施上完成的。
*   **具体细节**：文中**未明确列出**具体的GPU/CPU型号、核心数量或具体的训练/分析时长。但考虑到1,278份样本的重测序数据量（约27.45万亿碱基对），该研究涉及大规模的并行计算处理。

### 5. 实验数量与充分性
*   **实验规模**：
    *   鉴定了1137万个SNP和205万个InDel。
    *   对6个地理亚群进行了群体结构分析。
    *   针对5个主要农艺性状进行了GWAS分析。
    *   对*rhg1*和*Rhg4*两个关键抗病位点进行了深入的单倍型+CNV整合分析。
    *   测试了9种机器学习算法在SCN抗性预测中的表现。
*   **充分性评价**：实验设计非常充分且具有多维度。通过对比芯片数据证明了高密度图谱的优越性，并通过野生种到栽培种的演化分析验证了有害等位基因的清除过程，逻辑闭环完整，实验结果客观公平。

### 6. 论文的主要结论与发现
*   **新位点发现**：利用GmHapMap-II在15号染色体上发现了一个SoySNP50K芯片无法检测到的蛋白含量相关新QTL，并锁定候选基因为糖转运蛋白*GmSWEET39*。
*   **抗病机制深化**：揭示了SCN抗性不仅取决于*rhg1*的单倍型，还高度依赖于拷贝数（CNV）。例如，H2型单倍型需要至少2-3个拷贝才能产生部分抗性，3-5个拷贝才能产生稳健抗性。
*   **遗传负荷演化**：发现大豆在驯化和改良过程中，有害等位基因负担显著降低（野生 > 农家种 > 栽培种），证明了人工选择在清除有害突变方面的有效性。
*   **资源贡献**：开发了用户友好的大豆单倍型数据库（SoyHapDB），为全球育种者提供资源。

### 7. 优点
*   **高分辨率**：相比传统芯片，该图谱能捕捉到更细微的遗传变异和结构变异。
*   **多组学整合**：创新性地将单倍型与CNV结合进行机器学习预测，显著提升了复杂抗病性状的预测准确率（二分类准确率达93%以上）。
*   **演化视角**：不仅关注育种应用，还从群体遗传学角度解析了有害等位基因的动态变化。

### 8. 不足与局限
*   **稀有变异限制**：尽管样本量已达千份级别，但对于某些极稀有的单倍型（如*rhg1*中的H4），由于样本量过少，仍难以准确评估其表型效应。
*   **表型预测挑战**：在SCN抗性的多类分类（R/MR/MS/S）预测中，准确率仅为73%左右，说明复杂抗性的微调机制仍受其他未知遗传因素或环境影响。
*   **应用范围**：目前的研究主要集中在已知的主效QTL上，对于极度多基因控制的微效性状（如产量），该图谱的直接贡献仍需进一步验证。

（完）
