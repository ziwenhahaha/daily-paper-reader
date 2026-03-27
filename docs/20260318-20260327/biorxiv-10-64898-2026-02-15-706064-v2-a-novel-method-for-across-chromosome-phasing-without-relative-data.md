---
title: A Novel Method for Across-Chromosome Phasing without Relative Data
title_zh: 一种无需亲属数据的跨染色体定相新方法
authors: "Sapin, E., Kelly, K., keller, m."
date: 2026-03-27
pdf: "https://www.biorxiv.org/content/10.64898/2026.02.15.706064v2.full.pdf"
tags: ["query:gene"]
score: 8.0
evidence: 单倍型跨染色体定相的新方法
tldr: "跨染色体定相旨在确定不同染色体的单倍型是否来自同一父母。针对无亲属数据的无关个体，本文提出一种基于窗口SNP相似性度量的新方法，无需依赖亲缘关系或IBD检测。在UK Biobank数据测试中，该方法在无染色体内定相错误时准确率达95%，即使使用计算预定相数据，准确率也达到83.1%，为大规模人群遗传学研究提供了有力工具。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-02-15-706064-v2/fig-001.webp\", \"caption\": \"Figure 2: Violin plots of ACPA scores for trio offspring. The left half of each plot shows the ACPA scores for trio offspring when using the method of Noto et. al. while the right part of each violin shows ACPA scores using our method. The bottom plot shows results when input data has no within-chromosome phasing errors, while the top plot shows results when within-chromosome phasing errors are present. For each focal individual, color indicates the highest degree of relatedness (based on π̂) to any non-focal individual.\", \"page\": 6, \"index\": 1, \"width\": 641, \"height\": 1268}]"
motivation: 现有的跨染色体定相方法在缺乏亲属数据或无关个体样本中表现不佳。
method: 提出一种基于窗口SNP相似性度量的新算法，无需亲属数据即可实现跨染色体单倍型匹配。
result: "在理想实验条件下准确率达95%，在实际计算预定相数据下准确率达到83.1%。"
conclusion: 该方法主要受限于染色体内定相的准确性，随着定相技术的进步，其跨染色体匹配精度将趋于完美。
---

## 摘要
动机：跨染色体定相旨在识别不同染色体的哪些单倍型来自同一双亲。这与染色体内定相不同，后者利用连锁不平衡模式来确定每条染色体内哪些等位基因是共同遗传的，但无法匹配跨不同染色体的单倍型。虽然可以利用父母或近亲的基因型进行跨染色体定相，但现有方法在处理无关个体的样本时表现不佳。在此，我们介绍了一种跨染色体定相的新方法，该方法采用基于窗口的 SNP 相似性度量，消除了对近亲数据或血缘同源（IBD）单倍型检测的需求。结果：我们以双亲均经过基因分型的 UK Biobank 后代作为金标准，在不使用父母数据的情况下对后代进行定相，从而评估了该方法的性能。在没有染色体内定相误差的基因组数据中，我们的算法实现了 95% 的平均跨染色体定相准确率，其中 53% 的个体实现了完美定相。当使用标准的染色体内定相算法对数据进行计算预定相时，跨染色体定相的平均准确率下降到 83.1%。因此，我们的方法主要受限于染色体内定相的准确性，并且随着染色体内定相准确性的提高，可以接近完美的跨染色体定相准确率。

## Abstract
Motivation: Across-chromosome phasing identifies which haplotypes of different chromosomes come from the same parent. This differs from within-chromosome phasing, which uses linkage disequilibrium patterns to determine which alleles were co-inherited within each chromosome but does not match haplotypes across different chromosomes. While across-chromosome phasing can be conducted using genotypes from parents or close relatives, current methods perform poorly for samples of unrelated individuals. Here, we introduce a novel approach for across-chromosome phasing that employs a window-based SNP-similarity metric, eliminating the need for data from close relatives or detection of identical-by-descent haplotypes. Results: Using UK Biobank offspring with both parents genotyped as a gold standard, we evaluated the performance of our method by phasing the offspring without using parental data. In genomic data with no within-chromosomal phase errors, our algorithm achieved a mean across-chromosome phasing accuracy of 95%, with 53% of individuals phased perfectly. When data was pre-phased computationally using a standard within-chromosomal phasing algorithm, mean accuracy for across-chromosome phasing dropped to 83.1%. Thus, our method is limited primarily by the accuracy of within-chromosome phasing, and can approach near perfect across-chromosome phasing accuracy as within-chromosome phasing accuracy improves.