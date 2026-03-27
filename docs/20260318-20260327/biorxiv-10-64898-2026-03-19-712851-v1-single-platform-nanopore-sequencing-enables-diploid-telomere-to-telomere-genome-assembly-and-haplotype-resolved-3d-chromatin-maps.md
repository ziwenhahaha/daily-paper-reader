---
title: Single-Platform Nanopore Sequencing Enables Diploid Telomere-to-Telomere Genome Assembly and Haplotype-Resolved 3D Chromatin Maps
title_zh: 单平台纳米孔测序实现二倍体从端粒到端粒（T2T）基因组组装和单倍型解析的 3D 染色质图谱
authors: "Gross, C., Potabattula, R., Cheng, F., Leuchtenberg, S., Hartung, H. S., Kristmann, B., Buena Atienza, E., Casadei, N., Ossowski, S., Riess, O. H."
date: 2026-03-21
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.19.712851v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 二倍体端粒到端粒基因组组装
tldr: 本研究提出了一种仅基于纳米孔（Nanopore）测序平台的简化工作流，实现了人类二倍体端粒到端粒（T2T）基因组组装。通过结合超长读段和Pore-C技术，研究者在23个样本中生成了高质量的无缝染色体，并实现了单倍型解析的3D染色质图谱和甲基化分析。该方法降低了技术门槛，为大规模人群T2T基因组学研究提供了高效、低成本的单平台解决方案。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712851-v1/fig-001.webp\", \"caption\": \"Figure 2: Nanopore-only assemblies achieve hybrid-grade T2T quality metrics. (A) Comparison of 23 Nanopore-only assemblies (red) with 20 multi-platform HPRC assemblies (gray) using identical quality control metrics. Shown are assembled genome length, number of gapless T2T contigs, number of near-complete T2T scaffolds, gene completeness, fraction of missing multi-copy genes (MMC), and fraction of missing single-copy genes (MSC). Distributions are comparable across datasets. (B) Chromosome-level assembly continuity across both haplotypes for all individuals. Dark blue indicates gapless T2T contigs; light blue indicates near-complete T2T scaffolds containing ≥1 gap; white indicates incomplete chromosomes. (C) Potential assembly issues detected by NucFlag following realignment of HQ reads to assembled genomes. Each bar represents one haplotype; variability reflects differences in sequencing and library preparation performance across samples.\", \"page\": 25, \"index\": 1, \"width\": 943, \"height\": 727}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712851-v1/fig-002.webp\", \"caption\": \"Figure 3: Phased variant discovery and ancestry validation in diploid T2T genomes. (A) Geographic origin of the 23 study participants, grouped by 1000 Genomes superpopulation (European [EUR], East Asian [EAS], South Asian [SAS], Admixed American [AMR]). (B) Ancestry inference of the assembled genomes, performed with RFMix using the 1000 Genomes Project reference panel. (C) Small variant counts in Nanopore-only assemblies (red) and 20 HPRC assemblies (gray), including single nucleotide variants (SNVs), insertions (INS), deletions (DEL), and multinucleotide variants (MNVs). Right panel shows size distributions of insertions and deletions. (D) Structural variant (SV) distribution across chromosomes, summed over all samples (left). Right panel shows allelic distribution of heterozygous and homozygous SVs in the study cohort compared to HPRC samples.\", \"page\": 26, \"index\": 2, \"width\": 943, \"height\": 804}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712851-v1/fig-003.webp\", \"caption\": \"Figure 5: Nanopore-only assemblies reconstruct complete centromeric structures. (A) Number of fully resolved and structurally validated centromeres per chromosome across all 23 individuals and both haplotypes. (B) Total number of complete, validated centromeres per individual. (C) Example centromere structure for chromosome 5 across individuals. Colors denote higher-order repeat (HOR) classes. Black arrows indicate HOR arrays; centromeric dip regions (CDRs) are highlighted in pink. (D) Repeat homology plot for chromosome 5 centromere (haplotype 2, sample T2T18). Top track shows CpG methylation with CDR annotation. Second track shows HOR class annotation. Heatmap indicates pairwise nucleotide identity within satellite repeat arrays.\", \"page\": 28, \"index\": 3, \"width\": 887, \"height\": 971}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712851-v1/fig-004.webp\", \"caption\": \"Figure 4: Haplotype-resolved Pore-C reveals allele-specific 3D chromatin organization. (A) Haplotype-specific chromatin contact maps (10 kb resolution) for the imprinted IGF2-H19 locus (chr11:1.5–2.5 Mb) in sample T2T12. Insulation scores highlight topologically associating domain (TAD) boundaries. Tracks include RefSeq gene annotation, H3K27ac signal, CTCF binding sites and motifs, and smoothed CpG methylation frequency (5mC). Distinct haplotype-specific chromatin structures are evident. (B) Chromosome-wide haplotype-separated contact maps (100 kb resolution) for chromosome X in T2T12, demonstrating differences between active and inactive X chromosomes. Bottom track shows smoothed CpG methylation frequency. (C) Number of chromatin contacts per sample. Unphased contacts were generated using wf-pore-c; haplotype-resolved contacts were obtained using a modified dip3d pipeline (cis interactions only).\", \"page\": 27, \"index\": 4, \"width\": 943, \"height\": 704}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-19-712851-v1/fig-005.webp\", \"caption\": \"Figure 1: Graphical abstract. Graphical overview of the experimental and computational workflow. Fresh peripheral blood is processed to generate ultra-long (UL) Nanopore libraries and Pore-C libraries. UL reads are errorcorrected to produce high-quality (HQ) reads for graph-based de novo assembly using Verkko. PoreC data enables chromosome-scale scaffolding and haplotype phasing. Downstream analyses include assembly quality control, phased variant detection, centromere characterization, haplotype-resolved methylation profiling, and 3D chromatin contact map generation. Our standardized T2T-3D procedure integrates all steps into a unified workflow.\", \"page\": 24, \"index\": 5, \"width\": 943, \"height\": 975}]"
motivation: 旨在解决目前二倍体T2T基因组组装依赖多平台测序导致的高成本、低可扩展性及技术复杂性问题。
method: 采用单一Nanopore平台，结合超长读段和Pore-C测序技术，在无需亲本信息的情况下进行组装和单倍型相位解析。
result: 成功组装了360条无缝染色体，共识准确度达到QV50，并揭示了等位基因特异性的染色质组织和X染色体失活特征。
conclusion: 证明了单平台测序即可实现参考级二倍体组装和多组学分析，显著推动了T2T时代人群和功能基因组学的规模化发展。
---

## 摘要
从端粒到端粒（T2T）基因组组装通过解析着丝粒、分段重复序列和其他先前无法访问的区域，彻底改变了人类基因组学。然而，大多数二倍体 T2T 组装依赖于多平台测序策略的组合，包括短读长基因组测序、PacBio HiFi、Oxford Nanopore 超长读长以及染色质构象捕获数据（Hi-C），这限制了其可扩展性和可及性。在此，我们展示了一种精简的仅使用 Nanopore 的工作流程，用于二倍体人类 T2T 组装，每个个体使用三个超长读长和一个 Pore-C PromethION 测序芯片。在 23 个具有遗传多样性的个体中，我们生成了 360 条无间隙染色体和 446 个近乎完整的 T2T 支架，在没有双链（Duplex）测序或混合校正的情况下，实现了 QV50 的中位数一致性准确度。组装连续性、基因完整性和结构变异检测与多平台人类泛基因组参考联盟（HPRC）的组装结果相当。Pore-C 数据在无需亲本信息的情况下实现了染色体尺度的单倍型定相，并支持生成单倍型解析的染色质接触图谱。整合的甲基化和 3D 基因组分析揭示了印记位点的等位基因特异性染色质组织，以及 X 染色体失活的清晰特征。我们的公开数据集扩展了公共 T2T 资源，并证明了参考级二倍体组装、定相甲基化组和 3D 基因组图谱可以从单一测序平台获得。这种方法降低了技术壁垒，并支持 T2T 时代可扩展的人群和功能基因组学研究。

## Abstract
Telomere-to-telomere (T2T) genome assembly has transformed human genomics by resolving centromeres, segmental duplications, and other previously inaccessible regions. However, most diploid T2T assemblies rely on the combination of multi-platform sequencing strategies including short read genome sequencing, PacBio HiFi, Oxford Nanopore ultra-long reads, and chromatin conformation capture data (Hi-C), limiting both scalability and accessibility. Here, we present a streamlined Nanopore-only workflow for diploid human T2T assembly using three ultra-long and one Pore-C PromethION flow cell per individual. Across 23 genetically diverse individuals, we generated 360 gapless chromosomes and 446 near-complete T2T scaffolds, achieving median consensus accuracy of QV50 without Duplex sequencing or hybrid polishing. Assembly continuity, gene completeness, and structural variant detection were comparable to multi-platform Human Pangenome Reference Consortium assemblies. Pore-C data enabled chromosome-scale haplotype phasing without parental information and supported generation of haplotype-resolved chromatin contact maps. Integrated methylation and 3D genome analyses revealed allele-specific chromatin organization at imprinted loci and clear signatures of X-chromosome inactivation. Our openly accessible dataset expands public T2T resources and demonstrates that reference-grade diploid assemblies, phased methylomes, and 3D genome maps can be derived from a single sequencing platform. This approach reduces technical barriers and supports scalable population and functional genomics in the T2T era.

---

## 论文详细总结（自动生成）

### 论文详细总结：单平台纳米孔测序实现二倍体 T2T 基因组组装与 3D 染色质图谱

#### 1. 核心问题与研究动机
*   **核心问题**：目前的二倍体端粒到端粒（T2T）基因组组装高度依赖多平台技术组合（如 PacBio HiFi 用于高精度、ONT 超长读段用于跨越重复序列、Hi-C 用于定相和支架搭建），这导致实验流程复杂、成本高昂且难以在大规模人群研究中普及。
*   **研究动机**：探索是否能仅通过单一的 Oxford Nanopore（ONT）测序平台，在不依赖亲本数据（Trio-binning）和双链测序（Duplex）的情况下，实现高质量、二倍体、且包含功能基因组信息（甲基化、3D 染色质结构）的 T2T 组装。

#### 2. 核心方法论
*   **核心思想**：采用“3+1”策略，即每个样本使用 3 个 PromethION 超长读段（UL）芯片和 1 个 Pore-C 芯片。
*   **关键技术细节**：
    *   **读段校正**：使用 **HERRO** 工具对 UL 读段进行生物信息学纠错，生成高精度（HQ）读段，以此替代 PacBio HiFi 读段作为组装图谱的基础。
    *   **组装算法**：利用 **Verkko** 组装器，将 HQ 读段作为输入，并结合原始 UL 读段解析复杂重复序列。
    *   **单倍型定相（Phasing）**：利用 **Pore-C** 数据捕获的染色质远程接触信息进行染色体级别的定相，无需亲本序列即可区分父本和母本单倍型。
    *   **多组学整合**：利用 ONT 测序同时保留原生 DNA 甲基化信息的特性，结合定相后的 Pore-C 接触图，同步构建单倍型解析的 3D 染色质图谱和甲基化组。

#### 3. 实验设计
*   **数据集**：选取了 23 名具有遗传多样性的个体（包括欧洲、东亚、南亚、拉丁美洲背景），其中包括两个亲本-子女三人组（Trio）用于验证定相准确性。
*   **Benchmark（基准）**：
    *   与 **HPRC（人类泛基因组参考联盟）** 的多平台（PacBio + ONT + Hi-C）组装结果进行对比。
    *   使用 **T2T-CHM13 v2.0** 作为参考基因组进行变异调用评估。
*   **对比方法**：
    *   组装器对比：Verkko vs. Hifiasm。
    *   定相策略对比：基于 Pore-C 的定相 vs. 基于亲本（Trio）的定相。
    *   校正策略对比：评估了 ONT 官方 APK 抛光工具对 QV 值的实际提升效果。

#### 4. 资源与算力
*   **硬件资源**：实验主要在 **PromethION R10.4.1** 测序平台上完成。
*   **计算算力**：文中提到组装步骤（Verkko）在**单个计算节点**上以本地模式运行。
*   **说明**：论文未详细列出具体的 GPU 型号、核心数或总训练/计算时长，但强调了该流程的自动化和相对较低的计算门槛。

#### 5. 实验数量与充分性
*   **实验规模**：对 23 个二倍体基因组进行了完整组装，共生成了 46 个单倍型基因组。
*   **充分性评估**：
    *   **多样性**：涵盖了多种族样本，验证了方法的普适性。
    *   **深度分析**：不仅做了序列组装，还进行了结构变异（SV）检测、着丝粒结构解析、X 染色体失活分析及印记位点（如 IGF2-H19）的 3D 构象分析。
    *   **客观性**：通过与 HPRC 标准数据集的横向对比，证明了单平台方法在基因完整性、连续性和准确性上已达到混合平台水平。

#### 6. 主要结论与发现
*   **组装质量**：在 23 个个体中重建了 **360 条无间隙染色体**，中位数一致性准确度达到 **QV50**（每兆碱基约 10 个错误），且无需双链测序。
*   **定相性能**：Pore-C 定相效果与亲本定相相当，能够产生染色体级别的单倍型块，转换错误率极低。
*   **功能基因组学**：成功绘制了单倍型解析的 TAD（拓扑相关结构域）图谱，观察到等位基因特异性的染色质组织和甲基化模式。
*   **着丝粒解析**：成功解析了高度重复的着丝粒区域，揭示了不同个体间着丝粒长度和高级重复（HOR）组织的显著差异。

#### 7. 优点
*   **简化流程**：将测序平台统一为 ONT，极大地降低了实验室的操作复杂性和物流成本。
*   **无需亲本**：Pore-C 的引入解决了临床或人群研究中往往缺乏亲本样本的难题。
*   **信息丰富**：单一实验流即可同时获得序列、相位、甲基化和 3D 结构四维度信息。
*   **高连续性**：UL 读段的优化使得近 80% 的染色体达到了 T2T 或近 T2T 水平。

#### 8. 不足与局限
*   **碱基准确度**：虽然达到 QV50，但在**同聚物（Homopolymer）区域**仍存在少量短插入/缺失错误，略逊于 PacBio HiFi 驱动的组装。
*   **复杂区域挑战**：近端着丝粒染色体（Acrocentric chromosomes）和核糖体 DNA（rDNA）阵列的自动化组装仍具挑战性，部分样本仍存在间隙。
*   **样本要求高**：超长读段（UL）的提取对原始血液样本的新鲜度和 DNA 完整性要求极高，技术门槛依然存在于文库构建阶段。

（完）
