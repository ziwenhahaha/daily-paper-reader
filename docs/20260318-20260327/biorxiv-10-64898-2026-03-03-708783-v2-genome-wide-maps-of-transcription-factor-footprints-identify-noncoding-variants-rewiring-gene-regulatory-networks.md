---
title: Genome-wide maps of transcription factor footprints identify noncoding variants rewiring gene regulatory networks
title_zh: 全基因组转录因子足迹图谱识别出重构基因调控网络的非编码变异
authors: "Lin, J., Dong, W., Zhang, J., Xie, C., Jing, X., Zhao, J., Ma, K., Kang, H., Jiang, Y., Xie, X. S., Zhao, Y."
date: 2026-03-25
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.03.708783v2.full.pdf"
tags: ["query:gene"]
score: 8.0
evidence: 基因调节的全基因组图谱和变异效应预测
tldr: 本研究针对非编码区变异如何影响基因调控这一难题，利用单分子脱氨酶足迹技术（FOODIE）在K562细胞中实现了极高的遗传力富集。通过开发varTFBridge框架，结合AlphaGenome预测，研究者分析了近50万个英国生物样本库基因组，识别出113个影响红细胞性状的高置信度调控变异，揭示了变异-转录因子-基因-性状的级联关系，为理解非编码变异的致病机制提供了新工具。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-03-708783-v2/fig-001.webp\", \"caption\": \"\", \"page\": 5, \"index\": 1, \"width\": 2329, \"height\": 3279}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-03-708783-v2/fig-002.webp\", \"caption\": \"\", \"page\": 11, \"index\": 2, \"width\": 2458, \"height\": 3527}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-03-708783-v2/fig-003.webp\", \"caption\": \"\", \"page\": 14, \"index\": 3, \"width\": 2456, \"height\": 3222}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-03-708783-v2/fig-004.webp\", \"caption\": \"\", \"page\": 19, \"index\": 4, \"width\": 1430, \"height\": 1751}]"
motivation: 旨在解决全基因组关联研究中非编码变异（尤其是罕见变异）如何改变基因调控网络的识别难题。
method: 结合单分子脱氨酶足迹技术（FOODIE）与AlphaGenome变异效应预测，开发了集成框架varTFBridge。
result: 在红细胞性状研究中识别出113个关键调控变异，涉及64个转录因子和108个基因，并成功解析了rs112233623影响红细胞计数的分子机制。
conclusion: 该研究证明了高分辨率足迹图谱结合深度学习预测能有效解析非编码变异对基因调控网络的重构作用。
---

## 摘要
全基因组关联研究已识别出数百万个与人类性状相关的非编码位点，然而这些变异如何改变基因调控仍是一个重大挑战，特别是对于全基因组测序队列和高分辨率功能注释仍然有限的罕见变异。在此，我们展示了在 K562 细胞中进行的单分子脱氨酶足迹法（FOODIE）尽管仅覆盖基因组的 0.12%，却捕获了红细胞性状高达 103 倍的遗传力富集。我们推出了 varTFBridge，它整合了 FOODIE 足迹法与 AlphaGenome 变异效应预测，旨在识别改变转录因子（TF）介导调控的因果非编码变异。将 varTFBridge 应用于 13 种红细胞性状的 490,640 个英国生物样本库（UK Biobank）基因组，优先筛选出 113 个高置信度调节变异（104 个常见变异，9 个罕见变异），涵盖了跨越 64 个 TF 和 108 个基因的“变异-TF 结合-基因-性状”级联中的 2,173 条关联。varTFBridge 重现了 rs112233623 并解析了其机制：CCND3 增强子处的 GATA1/TAL1 协同结合被破坏，从而改变了红细胞计数和体积。

## Abstract
Genome-wide association studies have identified millions of noncoding loci linked to human traits, yet how these variants alter gene regulation remains a major challenge, particularly for rare variants where whole-genome sequencing cohorts and high-resolution functional annotations remain limited. Here we show that single-molecule deaminase footprinting (FOODIE) in K562 cells captures up to 103-fold heritability enrichment for erythroid traits despite covering 0.12% of the genome. We introduce varTFBridge, integrating FOODIE footprinting with AlphaGenome variant effect prediction to identify causal noncoding variants altering transcription factor (TF)-mediated regulation. Applied to 490,640 UK Biobank genomes across 13 erythrocyte traits, varTFBridge prioritises 113 high-confidence regulatory variants (104 common, 9 rare), encompassing 2,173 linkages along the variant-TF binding-gene-trait cascade across 64 TFs and 108 genes. varTFBridge recapitulates rs112233623 and resolves its mechanism: GATA1/TAL1 co-binding disruption at a CCND3 enhancer altering red blood cell count and volume.