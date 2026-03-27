---
title: Coupling codon and protein constraints decouples drivers of variant pathogenicity
title_zh: 耦合密码子与蛋白质约束解耦变异致病性的驱动因素
authors: "Chen, R., Palpant, N., Foley, G., Boden, M."
date: 2026-03-20
pdf: "https://www.biorxiv.org/content/10.1101/2025.03.12.642937v3.full.pdf"
tags: ["query:gene"]
score: 8.0
evidence: 分子遗传学与变异致病性预测
tldr: 本研究旨在解决基因变异功能影响预测的难题，指出传统模型往往忽视编码序列中的调控约束。通过结合密码子语言模型 (CaLM) 和蛋白质语言模型 (ESM-2)，研究者揭示了致病性由蛋白质产物和编码过程共同驱动。研究发现，功能缺失变异主要受残基特征影响，而功能获得变异则表现出更强的密码子约束，且这种信号在内源基因组环境中更为显著，强调了实验背景对变异评估的重要性。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-001.webp\", \"caption\": \"Fig. 7: Schematic of the proposed mechanism.\", \"page\": 25, \"index\": 1, \"width\": 775, \"height\": 538}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-002.webp\", \"caption\": \"Fig. 3: Decoupling evolutionary drivers of LoF and GoF mechanisms across DMS and CBGE platforms.\", \"page\": 21, \"index\": 2, \"width\": 775, \"height\": 394}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-003.webp\", \"caption\": \"Fig. 4: Codon-level constraints reflect nonsense and synonymous variant effects.\", \"page\": 22, \"index\": 3, \"width\": 777, \"height\": 723}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-004.webp\", \"caption\": \"Fig. 5: Dissecting the biological complementarity of CLM and PLM.\", \"page\": 23, \"index\": 4, \"width\": 775, \"height\": 640}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-005.webp\", \"caption\": \"Fig. 1: Linguistic duality reveals orthogonal evolutionary constraints across the central dogma.\", \"page\": 19, \"index\": 5, \"width\": 775, \"height\": 519}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-006.webp\", \"caption\": \"Fig. 6: Cross-platform comparison reveals context-dependent codon constraints in BRCA1 and TP53.\", \"page\": 24, \"index\": 6, \"width\": 777, \"height\": 777}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-03-12-642937-v3/fig-007.webp\", \"caption\": \"Fig. 2: Codon and protein constraints define a composite landscape of variant pathogenicity.\", \"page\": 20, \"index\": 7, \"width\": 777, \"height\": 509}]"
motivation: 现有预测模型主要关注蛋白质结构缺陷，忽略了编码序列中潜在的密码子水平调控约束。
method: 通过耦合密码子语言模型 (CaLM) 与蛋白质语言模型 (ESM-2)，量化分析不同层面对变异致病性的贡献。
result: 研究发现密码子和蛋白质特征对致病性预测贡献接近，且功能获得性变异比功能缺失性变异表现出更强的密码子水平信号。
conclusion: 变异致病性反映了蛋白质产物与编码过程的共同作用，且内源基因组环境会放大密码子层面的调控信号。
---

## 摘要
预测遗传变异的功能影响仍然是基因组学中的一个基本挑战。现有模型侧重于蛋白质内在缺陷，却忽视了嵌入在编码序列中的调控约束。在本研究中，我们将密码子语言模型 (CaLM) 与蛋白质语言模型 (ESM-2) 相结合，以剖析变异致病性的驱动因素。在 ClinVar 数据上，两种模态在区分致病性变异与良性变异方面的贡献几乎相等。在 ClinMAVE 的深度突变扫描和基于 CRISPR 的基因组编辑平台上的评估表明，功能缺失 (loss-of-function) 变异主要受残基水平特征支配，而功能获得 (gain-of-function) 变异则表现出密码子水平约束的更大相对贡献，尽管这具有基因特异性。对 BRCA1 和 TP53 中相同变异的对照比较进一步表明，密码子水平的信号在内源基因组背景下有所增强。总之，这些发现表明致病性既反映了“产物”也反映了“过程”，并且实验平台可能会影响哪个维度是可观察的。

## Abstract
Predicting the functional impact of genetic variants remains a fundamental challenge in genomics. Existing models focus on protein-intrinsic defects yet overlook regulatory constraints embedded within coding sequences. Here, we couple a codon language model (CaLM) with a protein language model (ESM-2) to dissect the drivers of variant pathogenicity. On ClinVar data, both modalities contribute near-equally to distinguishing pathogenic from benign variants. Evaluation across Deep Mutational Scanning and CRISPR-Based Genome Editing platforms in ClinMAVE reveals that loss-of-function variants are governed primarily by residue-level features, whereas gain-of-function variants show a greater relative contribution from codon-level constraints, albeit in a gene-specific manner. A controlled comparison of identical variants in BRCA1 and TP53 further suggests that codon-level signals are elevated in the endogenous genomic context. Together, these findings indicate that pathogenicity reflects both the "product" and the "process," and that the experimental platform may influence which dimension is observable.