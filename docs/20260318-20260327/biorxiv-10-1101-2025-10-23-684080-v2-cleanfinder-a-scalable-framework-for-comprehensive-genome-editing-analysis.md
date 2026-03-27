---
title: "CleanFinder: A Scalable Framework for Comprehensive Genome Editing Analysis"
title_zh: CleanFinder：一个用于全面基因组编辑分析的可扩展框架
authors: "Ramachandran, H., Dobner, J., Nguyen, T., Binder, S., Tolle, I., Vykhlyantseva, I., Krutmann, J., Miccio, A., Staerk, C., Brusson, M., Kontarakis, Z., Prigione, A., Rossi, A."
date: 2026-03-25
pdf: "https://www.biorxiv.org/content/10.1101/2025.10.23.684080v2.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 全面的基因组编辑分析及CRISPR验证的生物技术应用
tldr: 针对基因编辑验证中扩增子定义与数据分析脱节的问题，本文开发了 CleanFinder 框架。这是一个无需安装、完全在客户端运行的浏览器应用，能根据 sgRNA 或引物自动定义扩增子并引导序列比对。它不仅能对编辑结果进行分类，还能识别 SNP 以评估等位基因丢失，并提供交互式基因结构可视化。该工具在确保数据隐私的同时，极大地简化了复杂的生物信息学流程，使非专业研究者也能高效进行精准的基因编辑分析。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-001.webp\", \"caption\": \"\", \"page\": 5, \"index\": 1, \"width\": 1047, \"height\": 529}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-002.webp\", \"caption\": \"\", \"page\": 5, \"index\": 2, \"width\": 1047, \"height\": 528}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-003.webp\", \"caption\": \"\", \"page\": 7, \"index\": 3, \"width\": 977, \"height\": 265}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-004.webp\", \"caption\": \"\", \"page\": 13, \"index\": 4, \"width\": 977, \"height\": 210}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-005.webp\", \"caption\": \"\", \"page\": 13, \"index\": 5, \"width\": 977, \"height\": 198}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-006.webp\", \"caption\": \"\", \"page\": 15, \"index\": 6, \"width\": 977, \"height\": 389}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-007.webp\", \"caption\": \"\", \"page\": 17, \"index\": 7, \"width\": 1173, \"height\": 888}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-008.webp\", \"caption\": \"\", \"page\": 48, \"index\": 8, \"width\": 959, \"height\": 476}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-009.webp\", \"caption\": \"\", \"page\": 49, \"index\": 9, \"width\": 958, \"height\": 224}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-010.webp\", \"caption\": \"\", \"page\": 49, \"index\": 10, \"width\": 958, \"height\": 224}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-011.webp\", \"caption\": \"\", \"page\": 49, \"index\": 11, \"width\": 958, \"height\": 224}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-012.webp\", \"caption\": \"\", \"page\": 51, \"index\": 12, \"width\": 1434, \"height\": 640}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-013.webp\", \"caption\": \"\", \"page\": 51, \"index\": 13, \"width\": 1434, \"height\": 640}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-014.webp\", \"caption\": \"\", \"page\": 51, \"index\": 14, \"width\": 1434, \"height\": 638}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-015.webp\", \"caption\": \"\", \"page\": 52, \"index\": 15, \"width\": 597, \"height\": 615}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-016.webp\", \"caption\": \"\", \"page\": 54, \"index\": 16, \"width\": 976, \"height\": 244}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-017.webp\", \"caption\": \"\", \"page\": 54, \"index\": 17, \"width\": 976, \"height\": 244}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-018.webp\", \"caption\": \"\", \"page\": 54, \"index\": 18, \"width\": 976, \"height\": 244}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-019.webp\", \"caption\": \"\", \"page\": 54, \"index\": 19, \"width\": 976, \"height\": 245}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-020.webp\", \"caption\": \"\", \"page\": 56, \"index\": 20, \"width\": 976, \"height\": 244}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-021.webp\", \"caption\": \"\", \"page\": 56, \"index\": 21, \"width\": 976, \"height\": 244}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-022.webp\", \"caption\": \"\", \"page\": 57, \"index\": 22, \"width\": 758, \"height\": 807}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-1101-2025-10-23-684080-v2/fig-023.webp\", \"caption\": \"\", \"page\": 58, \"index\": 23, \"width\": 819, \"height\": 861}]"
motivation: 现有的基因编辑验证工具在扩增子定义和数据分析上存在脱节，导致分析流程复杂且碎片化。
method: 开发了基于浏览器的 CleanFinder 应用，通过 sgRNA 或引物自动定义扩增子并利用序列锚点在客户端完成比对与分类。
result: 实现了从序列检索、编辑结果分类到 SNP 识别及基因结构可视化的全流程自动化，且无需上传数据，保障了隐私。
conclusion: CleanFinder 为研究人员提供了一个安全、高效且易用的全方位基因编辑分析解决方案，显著降低了生物信息学分析的门槛。
---

## 摘要
通过靶向测序对基因组编辑进行精确验证是一个关键的多步骤过程。现有工具通常将扩增子定义与数据分析分开，导致了流程的碎片化并增加了复杂性。我们开发了 CleanFinder，这是一个统一了这些步骤的浏览器原生应用程序。根据用户提供的 sgRNA 或引物，CleanFinder 会检索相应的基因组上下文，自动定义扩增子，并设置稳健的序列锚点。这些锚点随后引导测序 reads 的比对，从而在不依赖静态、预加载基因组数据库的情况下，实现对编辑结果的精确量化。其分析引擎对测序数据进行全面评估：它能自动将 reads 分类为关键功能类别，同时识别杂合单核苷酸多态性 (SNPs)，以便直接评估等位基因丢失 (allelic dropout)。为了提供关键的生物学背景，该工具集成了一个交互式基因查看器，可映射 sgRNA 靶点并可视化特定转录本的编码序列、蛋白质翻译以及整体基因结构。重要的是，CleanFinder 完全在客户端运行，由于基因组信息从未上传且无需安装，从而确保了完整的数据隐私。通过将这些先进的分析和可视化功能整合到一个安全的、一体化的解决方案中，CleanFinder 使任何研究人员都能进行稳健的基因组编辑分析，无论其生物信息学专业知识如何。

## Abstract
Precise validation of genome editing by targeted sequencing is a critical, multi-step process. Existing tools often separate amplicon definition from data analysis, creating fragmentation and added complexity. We developed CleanFinder, a browser-native application that unifies these steps. Based on user-provided sgRNAs or primers, CleanFinder retrieves the corresponding genomic context, automatically defines an amplicon, and sets robust sequence anchors. These anchors then guide alignment of sequencing reads, enabling accurate quantification of editing outcomes without relying on static, pre-loaded genome databases. Its analytical engine performs a comprehensive assessment of the sequencing data: it automates the classification of reads into key functional categories while simultaneously identifying heterozygous Single Nucleotide Polymorphisms (SNPs) to enable direct assessment of allelic dropout. To provide crucial biological context, the tool incorporates an interactive gene viewer that maps sgRNA targets and visualizes transcript-specific coding sequences, protein translations, and overall gene structure. Importantly, CleanFinder operates entirely client-side, ensuring complete data privacy as genomic information is never uploaded and no installation is required. By integrating these advanced analytical and visualization capabilities into a secure, all-in-one solution, CleanFinder makes robust genome editing analysis accessible to any researcher, regardless of their bioinformatics expertise.

---

## 论文详细总结（自动生成）

### CleanFinder：用于全面基因组编辑分析的可扩展框架

#### 1. 核心问题与整体含义（研究动机和背景）
基因组编辑技术（如 CRISPR/Cas9、碱基编辑 BE、先导编辑 PE）在生物医学研究中应用广泛，但其产生的等位基因结果极其复杂且具有异质性。现有的分析工具存在以下痛点：
*   **流程碎片化**：扩增子定义与数据分析往往脱节。
*   **技术门槛高**：许多工具依赖命令行、Docker 或复杂的 Python 环境，对非生物信息学背景的研究者不友好。
*   **隐私与性能冲突**：在线服务器工具虽然易用，但存在数据隐私风险且处理大规模数据（如高通量筛选）时吞吐量受限。
*   **平台兼容性不足**：对长读长测序（如 Oxford Nanopore, ONT）的错误特征（如同聚物区域的插入缺失）支持有限。

**CleanFinder** 旨在提供一个浏览器原生（无需安装、隐私安全）且可扩展的框架，统一扩增子定义、高精度分型、修复路径推断及等位基因丢失检测。

#### 2. 核心方法论
CleanFinder 采用了模块化架构，其核心技术包括：
*   **约束性半全局比对（Constrained Semi-global Alignment, "Glocal"）**：利用高置信度的 5' 和 3' 锚点序列定义比对窗口。在窗口内进行半全局比对，不惩罚末端空位，从而在保留读段连续性的同时，准确识别大片段插入、缺失和复杂重排。
*   **双竞争参考评分（Dual Competitive Reference Scoring）**：针对复杂的先导编辑（PE），将读段同时与野生型（WT）和预期编辑参考序列进行比对，通过评分竞争来区分精确编辑、中间体或旁观者变异。
*   **k-mer 引导的预过滤**：在动态规划比对前，通过短序列种子（k-mer）快速剔除无关读段，显著提升处理速度。
*   **Turbo 模式**：一种基于启发式锚点检测和规则分类的快速模式，处理速度可达每秒 $10^5$ 条读段，适用于初步筛选。
*   **等位基因感知模块**：利用杂合 SNP 作为内源性条形码，结合长读长测序相位分析，检测因大片段缺失导致的等位基因丢失（Allelic Dropout）。
*   **RIMA/Repairome 集成**：自动推断 DNA 修复路径（如 NHEJ 与 MMEJ），分析微同源序列（Microhomology）特征。

#### 3. 实验设计
论文通过多维度实验验证了 CleanFinder 的性能：
*   **编辑系统**：涵盖 Cas9、Cas12、腺嘌呤碱基编辑（ABE）、胞嘧啶碱基编辑（CBE）以及线粒体碱基编辑（DdCBE）。
*   **细胞模型**：包括人诱导多能干细胞（iPSCs）、HEK293T、K562 和造血干祖细胞（HSPCs）。
*   **测序平台对比**：对比了 Illumina（短读长）与 ONT（长读长，SUP 模式）的一致性。
*   **基准测试（Benchmark）**：与 OutKnocker、Cas-Analyzer、CRISPResso2 等现有工具在功能、速度和准确性上进行了对比。
*   **应用场景**：对 1,849 种小分子化合物进行了高通量筛选，寻找能调节先导编辑（PE）效率的药物。

#### 4. 资源与算力
*   **硬件环境**：作者在多种个人计算设备上进行了测试，包括 Apple M4（14 核，24GB RAM）、Intel Core Ultra 7 165H（16 核，64GB RAM）以及 Intel Core i5-10210U。
*   **算力需求**：由于该工具基于浏览器原生技术（JavaScript/HTML5）或轻量级 Python CLI，**不需要高性能 GPU 或服务器集群**。其设计初衷是在普通笔记本电脑上即可完成大规模数据分析。

#### 5. 实验数量与充分性
*   **实验规模**：进行了数十个基因位点的编辑分析，包括单克隆验证和混合群体分析。
*   **灵敏度测试**：通过 0% 到 100% 的稀释实验验证了对低频等位基因（低至 0.02%）的检测能力。
*   **高通量验证**：1,849 种化合物的筛选实验产生了大量数据，证明了框架的扩展性。
*   **充分性评价**：实验设计较为全面，涵盖了核基因组与线粒体基因组、不同核酸酶系统及主流测序平台，结果具有客观性和跨平台的一致性。

#### 6. 主要结论与发现
*   **高一致性**：ONT（SUP 模式）与 Illumina 在分型频率上表现出极强的相关性（Pearson r = 0.97）。
*   **PE 复杂性解决**：双参考评分机制能有效解析 PE 产生的复杂插入/缺失组合。
*   **筛选发现**：通过小分子筛选识别出 HDAC 抑制剂（如 Vorinostat）在特定位点会抑制 PE 效率，而 ROCK 抑制剂可能通过提高细胞存活率间接提升编辑表现。
*   **隐私与便捷**：证明了完全在客户端（浏览器内）进行大规模生物信息分析的可行性。

#### 7. 优点
*   **隐私保护**：数据无需上传服务器，完全在本地浏览器处理。
*   **全流程集成**：从扩增子定义、基因组查看器可视化到修复路径分析，功能高度集成。
*   **跨平台支持**：对长读长测序支持良好，并能处理线粒体 DNA 编辑这种特殊场景。
*   **易用性**：提供了图形化界面（GUI）和命令行（CLI）两种模式，兼顾了普通用户和高级开发者。

#### 8. 不足与局限
*   **ONT 固有偏差**：尽管使用了 SUP 模式，但在同聚物（Homopolymer）区域仍存在测序噪声导致的伪 Indel 风险，需谨慎解读。
*   **筛选深度**：小分子筛选仅在单一浓度（10 μM）下进行，未完全排除细胞毒性对编辑效率的干扰，部分“命中”化合物仍需进一步验证。
*   **浏览器内存限制**：虽然有 Turbo 模式，但浏览器环境在处理超大规模 FASTQ 文件时仍受限于系统分配给浏览器的内存，此时需切换至 CLI 版本。

（完）
