---
title: "A near chromosome-scale genome assembly of the Common pine sawfly (Diprion pini, Linnaeus, 1758)"
title_zh: "普通松叶蜂（Diprion pini, Linnaeus, 1758）的近染色体水平基因组组装"
authors: "Wutke, S., Michell, C., Lindstedt, C."
date: 2026-03-21
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.19.712881v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 染色体级基因组组装与图谱绘制
tldr: "普通松叶蜂（Diprion pini）是欧亚地区重要的森林害虫，但此前缺乏高质量基因组资源。本研究利用PacBio HiFi、Nanopore和10x Genomics技术，在未采用Hi-C的情况下，结合近缘种参考基因组，成功构建了268 Mb的近染色体级参考基因组。该基因组完整度达97.2%，包含2.6万个编码基因，为害虫防治及膜翅目进化研究提供了重要基础。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-001.webp\", \"caption\": \"Fig. 3. Mitochondrial genome map of Diprion pini. Inner histogram represents coverage (up 224 to 13,000×) of linked reads and blue line shows GC content. 225 226\", \"page\": 11, \"index\": 1, \"width\": 754, \"height\": 675}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-002.webp\", \"caption\": \"Fig. 6. Synteny of BUSCO genes (hymenoptera_odb10) with D. pini in the middle, D. similis in 288 the top and N. lecontei in the bottom. 289 290\", \"page\": 15, \"index\": 2, \"width\": 649, \"height\": 400}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-003.webp\", \"caption\": \"Fig. 1. Snail plot visualization of the assembly statistics created with BlobToolKit with scaffold 202 statistics in the top left corner. The red line marks the longest scaffold. 203 204 205\", \"page\": 10, \"index\": 3, \"width\": 726, \"height\": 652}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-004.webp\", \"caption\": \"Fig. 2. Genome survey and quality metrics for the D. pini reference genome. (A) BUSCO 207 completeness based on the hymenoptera_odb10 database for the newly generated D. pini 208 genome compared to published genomes of other Diprionidae species. (B) GenomeScope 209 profile of 21-mer analysis using paired-end reads as input. 210 211\", \"page\": 10, \"index\": 4, \"width\": 1016, \"height\": 396}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-005.webp\", \"caption\": \"Fig. 5. Word clouds of the 30 most abundant gene ontology (GO) terms in the D. pini unique 266 protein set. (A) Annotations of biological processes (BP); (B) Annotations of molecular 267 functions (MF). 268 269 Comparative genomics 270\", \"page\": 14, \"index\": 5, \"width\": 1016, \"height\": 393}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-006.webp\", \"caption\": \"Fig. 4. UpSet plot showing the intersection of orthogroups identified by OrthoFinder across 258 the 11 hymenopteran protein sets included here. Horizontal bars (= set sizes) indicate the total 259 number of orthogroups found in each species’ genome, while vertical bars represent the number 260 of orthogroups shared by a given intersection of species. Dots in the lower panel indicate the 261 species in each intersection with single dots representing orthogroups unique to a particular 262 species, and dots connected by lines representing orthogroups shared by several species. 263 264\", \"page\": 13, \"index\": 6, \"width\": 1016, \"height\": 567}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712881-v1/fig-007.webp\", \"caption\": \"Table 1. Assembly and annotations statistics. 199\", \"page\": 9, \"index\": 7, \"width\": 489, \"height\": 776}]"
motivation: 针对普通松叶蜂这一重要森林害虫缺乏基因组资源、阻碍分子生态学和害虫管理研究的问题，本研究旨在构建其高质量参考基因组。
method: 综合利用PacBio HiFi、Oxford Nanopore长读长和10x Genomics链接读段技术，并结合近缘种参考基因组进行组装。
result: "获得了大小为268 Mb、N50达18.7 Mb的近染色体级基因组，包含26,335个编码基因，并发现其线粒体基因组因非编码区延长而异常庞大。"
conclusion: 本研究证明在有近缘高质量参考基因组时，无需Hi-C也可实现染色体级组装，为松叶蜂爆发监测和膜翅目演化研究奠定了基础。
---

## 摘要
普通松叶蜂（Diprion pini）是遍布欧亚大陆松林的广泛分布的食叶害虫，其爆发会导致严重的生态和经济损失。然而，该物种的基因组资源一直有限，阻碍了分子生态学或害虫管理方面的进展。在本研究中，我们利用 PacBio HiFi 读段、Oxford Nanopore MinION 长读段和 10x Genomics linked reads，构建了 D. pini 的近染色体水平参考基因组。最终组装结果主要由染色体大小的支架（scaffolds）组成。基因组全长 268 Mb，包含 81 个支架，支架 N50 为 18.7 Mb。BUSCO 分析（hymenoptera_odb10）显示基因组完整度高达 97.2%。线粒体基因组大小为 22.7 kb，由于存在延长的非编码控制区（6,874 bp），其体积异常庞大。基因预测识别出 26,335 个蛋白质编码基因，其中 12,769 个获得了功能注释。与其他叶蜂和细腰亚目（Apocrita）的比较分析识别出 2,472 个 D. pini 特有的蛋白质，其中一些推测与植物次生代谢物的处理有关。值得注意的是，我们的基因组组装表明，当存在近缘的高质量参考基因组时，无需 Hi-C 测序即可生成染色体水平的组装。该基因组为开发改进的 D. pini 爆发监测和管理策略提供了宝贵基础，并有助于推动膜翅目（Hymenoptera）进化的基础研究。

## Abstract
The common pine sawfly, Diprion pini, is a widespread defoliator of pine forests across Europe and Asia, with outbreaks causing substantial ecological and economic damages. However, genomic resources for this species have been limited, hindering advances in molecular ecology or pest management. Here, we present a near chromosome-level reference genome for D.pini, generated using PacBio HiFi reads, Oxford Nanopore MionION long reads, and 10x Genomics linked reads. The final assembly is organized into mostly chromosome-sized scaffolds. It spans a length of 268 Mb, comprises 81 scaffolds, and has a scaffold N50 of 18.7 Mb. BUSCO analysis (hymenoptera_odb10) indicates a high genome completeness of 97.2%. With 22,7 kb the mitochondrial genome is unusually large due to an extended non-coding control region (6,874 bp). Gene prediction identified 26,335 protein-coding genes, of which 12,769 were functionally annotated. Comparative analyses with other sawflies and Apocrita identified 2,472 proteins unique to D. pini, some of which are putatively associated with the processing of plant secondary metabolites. Notably, our genome assembly highlights that, when a closely related, high-quality reference genome is available, chromosome-scale assemblies can be generated without the need of Hi-C sequencing. The genome provides a valuable foundation for the development of improved monitoring and management strategies for D. pini outbreaks and contributes to advancing fundamental research on Hymenoptera evolution.

---

## 论文详细总结（自动生成）

这是一份关于论文《A near chromosome-scale genome assembly of the Common pine sawfly (*Diprion pini*, Linnaeus, 1758)》的结构化深入总结：

### 1. 核心问题与整体含义（研究动机和背景）
*   **核心问题**：普通松叶蜂（*Diprion pini*）是欧亚大陆松林的主要食叶害虫，其爆发会导致严重的生态破坏和经济损失。然而，此前该物种缺乏高质量的基因组资源，限制了对其分子生态学、害虫爆发监测及针对性管理策略的研究。
*   **整体含义**：本研究旨在构建首个近染色体水平的参考基因组，填补膜翅目（Hymenoptera）中较为原始的叶蜂类群（Symphyta）的基因组空白，为理解膜翅目早期演化、寄生性与社会性的起源提供关键数据。

### 2. 论文提出的方法论
*   **核心思想**：采用“长读长+链接读段+近缘种辅助”的混合组装策略，在不使用昂贵的 Hi-C 测序情况下，实现近染色体级别的组装。
*   **关键技术细节**：
    *   **测序技术**：结合了 PacBio HiFi（47× 覆盖度，高精度长读段）、Oxford Nanopore MinION（2× 覆盖度，超长读段）和 10x Genomics Linked Reads（提供物理连接信息）。
    *   **组装流程**：
        1.  使用 **Hifiasm** 进行初始单倍型解析组装。
        2.  使用 **purge_dups** 去除单倍型冗余。
        3.  **RagTag "correct"**：利用近缘种 *Diprion similis* 的基因组作为参考，识别并修复潜在的组装错误。
        4.  **三步支架搭建（Scaffolding）**：依次使用 **scaff10x**（利用 10x 链接读段）、**LINKS**（利用长读段）和 **RagTag "scaffold"**（基于共线性排序）。
    *   **注释流程**：使用 **EDTA** 进行重复序列注释；结合 RNA-seq 数据和蛋白质证据，通过 **BRAKER2** 管道进行基因预测。

### 3. 实验设计
*   **数据集/样本**：样本采集自波兰西北部的松叶蜂茧，分别对雌性和雄性个体进行测序。
*   **Benchmark（评估指标）**：
    *   **完整性**：使用 BUSCO（hymenoptera_odb10 数据库）。
    *   **准确性**：使用 Merqury 计算 QV 值和 k-mer 完整度。
    *   **污染检测**：使用 BlobToolKit 进行分类群筛选。
*   **对比方法**：将组装结果与已发表的同科物种（如 *D. similis*、*Neodiprion lecontei*）以及细腰亚目（如蜜蜂、蚂蚁）进行比较基因组学分析（共线性分析和正交群推断）。

### 4. 资源与算力
*   **算力说明**：论文中**未明确说明**具体的计算资源（如 GPU/CPU 型号、核心数或总计算时长）。
*   **设备信息**：提到了测序平台，包括 PacBio Sequel II、Illumina NovaSeq 和 ONT MinION。

### 5. 实验数量与充分性
*   **实验组数**：研究涵盖了基因组组装、线粒体组装、重复序列分析、基因预测、功能注释、共线性分析、正交群分析等多个环节。
*   **充分性与客观性**：
    *   实验设计较为全面，采用了多种独立技术（HiFi, ONT, 10x）相互校验。
    *   通过对端粒重复序列（TTAGG）n 的搜索，验证了支架搭建的物理完整性。
    *   **客观性**：作者诚实地指出，由于使用了近缘种辅助组装，其共线性结果在一定程度上受到参考基因组的影响，但在有细胞学证据支持的情况下，这种方法是合理的。

### 6. 论文的主要结论与发现
*   **基因组特征**：组装大小为 268 Mb，包含 81 个支架，Scaffold N50 达 18.7 Mb。BUSCO 完整度为 97.2%，QV 值为 61.3（极高精度）。
*   **线粒体异常**：发现了一个异常庞大的线粒体基因组（22.7 kb），其中非编码控制区长达 6,874 bp，且通过读段深度验证确认非组装错误。
*   **基因内容**：预测出 26,335 个编码基因。识别出 2,472 个该物种特有的蛋白，部分基因涉及毒素活性和植物次生代谢物（如松树萜类）的处理，这可能与其食性适应有关。
*   **演化发现**：尽管 *Diprion*（n=14）与 *Neodiprion*（n=7）染色体数目差异巨大，但基因组间保持了高度的共线性，表明染色体演化主要通过融合/裂变（Robertsonian 变化）而非大规模重排。

### 7. 优点
*   **高性价比策略**：证明了在拥有高质量近缘种参考基因组的前提下，利用长读长和链接读段即可达到近染色体水平，无需 Hi-C，为非模型生物基因组研究提供了参考。
*   **高质量注释**：结合了转录组和蛋白质证据，基因预测结果详实。
*   **线粒体解析**：对复杂且易被忽略的线粒体控制区进行了深度解析，挑战了传统对昆虫线粒体大小的认知。

### 8. 不足与局限
*   **参考偏差风险**：由于在组装过程中使用了 *D. similis* 进行纠错和排序，可能会掩盖这两个物种之间真实的细微结构变异。
*   **样本代表性**：仅使用了来自单一地理区域（波兰）的样本，可能无法完全代表该物种在整个欧亚大陆的遗传多样性。
*   **功能验证缺失**：虽然识别出了与植物防御相关的特有基因，但尚未进行实验验证（如 RNAi 或蛋白质功能实验）来确认其生理功能。

（完）
