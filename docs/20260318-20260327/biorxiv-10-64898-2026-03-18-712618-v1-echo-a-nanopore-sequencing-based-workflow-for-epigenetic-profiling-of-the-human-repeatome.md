---
title: "ECHO: a nanopore sequencing-based workflow for (epi)genetic profiling of the human repeatome"
title_zh: ECHO：一种基于纳米孔测序的人类重复组（表观）遗传图谱分析工作流
authors: "Poggiali, B., Putzeys, L., Andersen, J. D., Vidaki, A."
date: 2026-03-20
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.18.712618v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 人类重复序列组的遗传图谱绘制
tldr: 人类基因组中重复序列的变异对基因调控和疾病至关重要，但缺乏整合的分析工具。本文推出了 ECHO，一个基于 Snakemake 的纳米孔测序分析工作流，旨在提供端到端的人类重复组（表观）遗传表征。该工具支持单倍型解析和 DNA 甲基化分析，为研究复杂重复区域提供了可扩展且可重复的解决方案。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-18-712618-v1/fig-001.webp\", \"caption\": \"Figure 1: Overview and testing of the ECHO pipeline for human repeatome profiling using ONT data. 90 (A) Two main modules of the pipeline: (I) preprocessing and phasing, and (II) repeatome profiling. Module I 91 includes basecalling, QC, read filtering, alignment to a reference genome (GRCh38 or T2T-CHM13v2), 92 variant calling, and phasing to generate haplotype-resolved BAM and VCF files. Based on user-defined 93 repeat catalogues, module II performs TR and TE genotyping (both reference and non-reference TE 94 insertions), along with the extraction of haplotype-specific DNA methylation at single-CpG resolution 95 across the repeat region, as well as averaged across the repeat element and its up- and downstream 96 flanking regions. External bioinformatic tools and custom Bash scripts are shown in italics, and key output 97 file types are indicated at each step. (B) Yield of called repeat loci in HG002 across sequencing coverage 98 (30× vs 15×). Left: percentage of TR loci successfully genotyped by LongTR relative to the genome-wide TR 99 catalog (n = 1,784,804). Right: number of detected non-reference TE insertions by TLDR (filter = PASS). (C) 100 Concordance between ECHO- and WGBS-derived DNA methylation values for the HG002 30× dataset. 101 Hexbin (2D density) plots compare CpG methylation levels measured by ONT and WGBS genome-wide, 102 within TRs (defined using genome-wide Adotto catalogue (English et al., 2025)) and TEs (defined using 103 GRCh38 RepeatMasker annotation). Bin colour indicates the number of CpGs per hexagon. Pearson 104 correlation coefficients (r) are indicated; dashed lines represent y = x. 105 INDEL – insertion–deletion; non-ref TE – TE not present in the reference genome; ONT – Oxford Nanopore 106 Technologies; QC – quality control; r – Pearson correlation coefficient; ref TE – TE annotated in the reference 107 genome; SNV – single nucleotide variant; SV – structural variant; TE – transposable element; TR – tandem 108 repeat; WGBS – whole-genome bisulfite sequencing. 109\", \"page\": 5, \"index\": 1, \"width\": 1012, \"height\": 767}]"
motivation: 旨在解决目前缺乏能够全面、同时表征人类重复组中多样化遗传和表观遗传变异的整合分析工具的问题。
method: 开发了基于 Snakemake 的 ECHO 工作流，利用 Oxford Nanopore 全基因组测序数据进行端到端的重复序列分析。
result: ECHO 提供了一个可重现且可扩展的框架，实现了对人类基因组中复杂重复区域的单倍型解析和甲基化信息的综合分析。
conclusion: ECHO 为深入探索人类重复组的（表观）遗传特征提供了一个高效、用户友好的平台，有助于揭示其在基因组功能和疾病中的作用。
---

## 摘要
摘要：人类基因组主要由重复 DNA 组成，其遗传和表观遗传变异在基因调控、基因组稳定性和疾病中发挥着关键作用。长读长测序的最新进展使得对人类基因组（包括此前无法触及的复杂和重复区域）进行大规模、单倍型解析且包含 DNA 甲基化信息的分析成为可能。然而，对“人类重复组”进行全面且同步的表征仍然具有挑战性，这主要是由于缺乏集成在单一流程中的综合工具来捕获各种类型 DNA 重复序列的全谱变异。在此，我们推出了 ECHO，这是一个基于 Snakemake 的用户友好型流程，用于“利用牛津纳米孔测序对人类重复元件进行（表观）基因组表征”。ECHO 为全基因组纳米孔测序数据的端到端分析提供了一个可重复且可扩展的框架，实现了对人类重复组的综合且定制化的（表观）遗传分析。

可用性与实现：ECHO 可在 Github 免费获取：https://github.com/leenput/ECHO-pipeline，存档版本见 Zenodo：https://zenodo.org/records/19068468。

联系方式：athina.vidaki@mumc.nl; athina.vidaki@maastrichtuniversity.nl。

## Abstract
SummaryThe human genome is dominated by repetitive DNA, whose genetic and epigenetic variation plays a key role in gene regulation, genome stability, and disease. Recent advances in long-read sequencing now enable large-scale, haplotype-resolved, and DNA methylation-informative analysis of the human genome, including on previously inaccessible complex and repetitive regions. However, the comprehensive, simultaneous characterisation of the "human repeatome" remains challenging, largely due to the lack of comprehensive tools integrated in a single pipeline that can capture the full spectrum of variation across diverse types of DNA repeats. Here, we present ECHO, a user-friendly, Snakemake-based pipeline for the "(Epi)genomic Characterisation of Human Repetitive Elements using Oxford Nanopore Sequencing". ECHO provides a reproducible and scalable framework for end-to-end analysis of whole-genome nanopore sequencing data, enabling integrative but also tailored (epi)genetic analyses of the human repeatome.

Availability and implementationECHO is freely available at Github: https://github.com/leenput/ECHO-pipeline, with the archived version at Zenodo: https://zenodo.org/records/19068468

Contactathina.vidaki@mumc.nl; athina.vidaki@maastrichtuniversity.nl

---

## 论文详细总结（自动生成）

### ECHO：一种基于纳米孔测序的人类重复组（表观）遗传图谱分析工作流

#### 1. 核心问题与整体含义
人类基因组中超过 50% 的序列由重复 DNA 组成，包括串联重复（TR）和转座元件（TE）。这些区域在基因调控、基因组稳定性和疾病（如神经系统疾病和癌症）中起着至关重要作用。然而，由于重复序列的复杂性，传统的短读长测序难以准确解析。虽然长读长测序（如 ONT）提供了新机会，但现有的分析工具往往功能单一（仅针对特定重复类型或仅分析序列变异），缺乏一个能够同时表征多种重复序列及其 DNA 甲基化状态的集成化、单倍型解析的分析流程。**ECHO** 的提出旨在填补这一空白，提供一个端到端、可扩展且易于使用的自动化工作流。

#### 2. 方法论
ECHO 是一个基于 **Snakemake** 的生物信息学流程，其核心思想是将先进的变异检测工具与甲基化分析深度集成。
*   **核心流程分为两个阶段：**
    *   **阶段 I（预处理与定相）：** 使用 `Dorado` 进行碱基识别（保留甲基化标签），`minimap2` 进行比对，`Clair3` 和 `Sniffles2` 分别检测小变异（SNV/Indel）和结构变异（SV），最后通过 `LongPhase` 实现变异与甲基化信息的协同定相（Phasing），生成单倍型解析的 BAM 文件。
    *   **阶段 II（重复组表征）：** 
        *   **TR 分析：** 利用 `LongTR` 进行基因型鉴定，并结合 `modkit` 提取单倍型特异性的单 CpG 位点及区域平均甲基化水平。
        *   **TE 分析：** 区分参考基因组已有的 TE（基于 RepeatMasker）和非参考插入 TE（使用 `TLDR` 鉴定），并计算其主体及侧翼区域的甲基化。
*   **关键技术细节：** 采用 `Singularity` 容器化管理所有软件依赖，确保了跨平台的可重复性和移植性。

#### 3. 实验设计
*   **数据集：** 使用了来自“瓶中基因组”（GIAB）项目的 **HG002** 样本的 ONT 测序数据。
*   **Benchmark（基准）：** 
    *   **甲基化基准：** 使用全基因组亚硫酸氢盐测序（WGBS）数据作为金标准。
    *   **覆盖度对比：** 将数据下采样至 **30×** 和 **15×** 两个深度，以评估流程在不同测序深度下的稳健性。
*   **对比维度：** 评估了全基因组范围、TE 区域及 TR 区域内 ONT 甲基化调用与 WGBS 的相关性（Pearson 相关系数）。

#### 4. 资源与算力
*   **算力消耗：** 实验在高性能计算（HPC）系统上运行。
    *   **30× 数据：** 总墙钟时间（Wall-clock time）为 **38.5 小时**，累计消耗 **234 CPU 小时**。
    *   **15× 数据：** 总墙钟时间为 **26.6 小时**，累计消耗 **172 CPU 小时**。
*   **存储需求：** 30× 数据的项目目录约占用 **100 GB** 磁盘空间。
*   **GPU 使用：** 论文提到 `Dorado` 碱基识别步骤需要 GPU 资源（SUP 模式），但未详细说明具体的 GPU 型号和数量。

#### 5. 实验数量与充分性
*   **实验规模：** 论文主要针对 HG002 这一标准样本进行了深度验证，包括不同覆盖度的对比实验以及与 WGBS 金标准的交叉验证。
*   **充分性评价：** 
    *   **客观性：** 通过与 WGBS 的高度相关性（r=0.94-0.96）证明了结果的准确性。
    *   **局限性：** 实验主要集中在单个标准样本上，虽然对于工具发布而言验证了核心功能，但尚未在更大规模的多样本人群队列或临床样本中进行广泛测试。

#### 6. 主要结论与发现
*   **高准确性：** ECHO 在重复区域（TR 和 TE）测得的 DNA 甲基化水平与 WGBS 金标准高度一致，相关系数达到 0.94 以上。
*   **单倍型解析能力：** 流程能够成功区分不同单倍型（Haplotype）之间的遗传变异和表观遗传差异，这对于研究印记基因或等位基因特异性表达至关重要。
*   **稳健性：** 即使在 15× 的较低覆盖度下，ECHO 依然能保持较高的重复序列检测率和甲基化测量精度。

#### 7. 优点
*   **高度集成：** 首次将 TR、TE 鉴定与单倍型解析的甲基化分析整合进单一流程，避免了研究者自行拼接多个工具的繁琐。
*   **用户友好：** 基于 Snakemake 和容器化技术，降低了安装和运行门槛，支持从原始 POD5 文件到最终报告的端到端分析。
*   **多分辨率：** 提供单 CpG 位点和区域平均两个层级的甲基化数据，兼顾了精细分析和总体趋势观察。

#### 8. 不足与局限
*   **计算资源限制：** 为了平衡计算效率，默认配置下 TR 的甲基化分析仅针对包含 CpG 的短串联重复（STR）区域，可能忽略部分不含 CpG 但具有生物学意义的区域。
*   **样本覆盖面：** 验证工作仅基于 HG002，对于不同种族背景或复杂疾病样本（如高度重排的癌细胞基因组）的适用性仍需进一步验证。
*   **依赖性风险：** 流程的性能高度依赖于底层第三方工具（如 LongTR, TLDR）的更新和准确性。

（完）
