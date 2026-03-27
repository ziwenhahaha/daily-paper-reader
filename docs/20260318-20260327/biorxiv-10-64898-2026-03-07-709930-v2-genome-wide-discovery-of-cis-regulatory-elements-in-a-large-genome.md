---
title: Genome-wide discovery of cis-regulatory elements in a large genome
title_zh: 大基因组中顺式调控元件的全基因组发现
authors: "Forbes, G., Skafida, E., Karapidaki, I., Moinet, S., Dandamudi, M., Cevrim, C., Momtazi, F., Anastasiadou, C., Lo Brutto, S., Averof, M., Paris, M."
date: 2026-03-19
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.07.709930v2.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 在大基因组中全基因组范围内发现调节元件
tldr: 本研究针对大型基因组中顺式调控元件（CREs）识别难的问题，以3.6 Gbp的钩虾（Parhyale hawaiensis）为对象，结合ATAC-seq技术与比较基因组学方法。通过分析不同组织及细胞类型的染色质开放性，并利用低覆盖度测序识别近缘物种间的保守序列，成功构建了高效的CREs发现流程。该方法显著降低了成本与劳动强度，为大型基因组的功能元件鉴定提供了重要资源和技术参考。
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-07-709930-v2/fig-001.webp\", \"caption\": \"Table 2. Overview of short-read genome sequencing on three Parhyale species\", \"page\": 27, \"index\": 1, \"width\": 973, \"height\": 294}]"
motivation: 在大型真核生物基因组中，顺式调控元件被大量非功能DNA分隔，导致传统的试错法识别效率极低且极具挑战性。
method: 综合运用大体及单核ATAC-seq分析染色质开放性，并采用低覆盖度短读长测序对比近缘物种以确定进化保守区域。
result: 成功构建了基因组范围的调控元件图谱，并验证了能够驱动全域或特定细胞类型表达的荧光报告基因调控元件。
conclusion: 该研究证明了结合染色质可及性和低成本序列保守性分析是识别大型基因组中功能性调控元件的有效且通用的策略。
---

## 摘要
在大多数生物中，鉴定基因组中的非编码调控元件是一项挑战。传统方法依赖于通过报告基因构建体进行反复试验，以测试 DNA 片段的调控活性。在大型真核生物基因组中，顺式调控元件可能分布在很长的距离内，并被大段非功能性 DNA 隔开，这使得反复试验的方法尤其困难。在本研究中，我们生成了两种资源，可用于缩小在夏威夷跳钩虾（Parhyale hawaiensis）3.6 Gbp 基因组（大小与人类基因组相当）中搜索此类顺式调控元件的范围。首先，我们利用 bulk ATACseq 揭示了 Parhyale 胚胎和成年组织（完整胚胎和腿部）中染色质可及性的全基因组模式，并利用单核 ATACseq 鉴定了从成年腿部回收的多种细胞类型（包括表皮、神经、肌肉和血细胞）中的开放染色质区域。其次，通过对夏威夷跳钩虾的三种同属物种（P. darvishi、P. aquilina 和 P. plumicornis）进行基因组测序，我们鉴定了全基因组范围内的序列保守岛，这些岛对应于在进化过程中受到功能约束的 DNA 元件。我们提出了一种方法，即低覆盖度（10-15x）的短读长基因组测序，在无需基因组组装的情况下，足以提供可靠的序列保守性图谱。这种方法降低了生成这些图谱所需的成本和劳动力，使顺式调控元件的鉴定更加普及。我们通过鉴定能够驱动荧光报告基因在全身及特定细胞类型中稳健表达的顺式调控元件，证明了这些资源的实用性。

## Abstract
Identifying non-coding regulatory elements in the genome poses a challenge in most organisms. Classical methods rely on trial and error to test the regulatory activities of DNA fragments using reporter constructs. In large eukaryotic genomes, where cis-regulatory elements can spread over long distances, separated by large stretches of non-functional DNA, this trial and error approach is particularly challenging. Here, we generate two types of resources that can be used to narrow the search for such cis-regulatory elements in the 3.6 Gbp genome of Parhyale hawaiensis (comparable in size to the human genome). First, we use bulk ATACseq to uncover genome-wide patterns of chromatin accessibility in embryonic and adult tissues of Parhyale (whole embryos and legs), and single-nucleus ATACseq to identify regions of open chromatin in diverse cell types recovered from adult legs, including epidermal, neuronal, muscle and blood cells. Second, by sequencing the genomes of three congeneric species of Parhyale hawaiensis - P. darvishi, P. aquilina and P. plumicornis - we identify islands of sequence conservation across the genome, corresponding to DNA elements that are functionally constrained during evolution. We present an approach by which low-coverage (10-15x) short-read genome sequencing, without genome assembly, is sufficient to provide reliable maps of sequence conservation. This approach cuts the cost and labour required to generate these maps, making the identification of cis-regulatory elements more widely accessible. We demonstrate the utility of these resources by identifying cis-regulatory elements that drive robust expression of fluorescent reporters ubiquitously and in specific cell types.

---

## 论文详细总结（自动生成）

这是一份关于论文《Genome-wide discovery of cis-regulatory elements in a large genome》的结构化深度总结：

### 1. 论文的核心问题与整体含义（研究动机和背景）
*   **核心问题**：在大型真核生物基因组（如本研究中 3.6 Gbp 的夏威夷跳钩虾 *Parhyale hawaiensis*）中，顺式调控元件（CREs）往往远离编码序列，且被大量非功能性 DNA 淹没。传统的“试错法”鉴定效率极低。
*   **研究动机**：针对非模式生物或具有大基因组的生物，缺乏高效、低成本且普适的全基因组 CREs 鉴定手段。
*   **整体含义**：通过整合染色质可及性（ATAC-seq）和进化保守性（比较基因组学）两种正交方法，为大基因组生物的功能基因组学研究提供了一套高效的资源构建流程。

### 2. 论文提出的方法论
*   **核心思想**：结合“空间开放性”与“进化约束性”。只有既处于开放染色质区域，又在近缘物种间保持序列保守的非编码片段，才最有可能是功能性 CREs。
*   **关键技术细节**：
    1.  **染色质剖析**：利用 **Bulk ATAC-seq** 获取胚胎和组织水平的开放图谱；利用 **Single-nucleus ATAC-seq (snATAC-seq)** 鉴定特定细胞类型（神经、肌肉、表皮等）的差异开放区域。
    2.  **低成本比较基因组学**：这是本文的一大创新。研究者并未对近缘种进行高深度测序和组装，而是采用 **10-15x 的低覆盖度短读长测序**，直接将 Read 比对到参考基因组上，通过比对密度识别“保守岛”。
    3.  **候选元件筛选**：筛选在特定细胞簇中显著开放且在同属物种（*P. darvishi* 等）中保守的片段。

### 3. 实验设计
*   **数据集/场景**：
    *   **ATAC-seq**：涵盖了 *Parhyale* 的多个发育阶段（S20-S24 胚胎、胚胎腿、成年腿）。
    *   **物种对比**：选取了同属的三个物种（*P. darvishi, P. aquilina, P. plumicornis*）进行测序。
*   **Benchmark（基准对比）**：
    *   对比了远缘物种 *Hyalella azteca*（约 1.1-1.4 亿年分化时间），证明其保守性过低，无法有效识别 CREs。
    *   对比了以往仅基于启动子近端序列的失败尝试（10 个候选片段均未成功），证明了本方法在远端增强子识别上的优越性。
*   **验证方法**：使用 **Minos 转座子系统** 构建荧光报告基因（mNeonGreen/EGFP），通过显微注射观察其在转基因钩虾中的表达模式。

### 4. 资源与算力
*   **测序平台**：使用了 Illumina NextSeq 500 进行测序。
*   **算力说明**：文中**未明确说明**具体的 GPU 型号或总算力消耗。生物信息学分析主要依赖常规 CPU 集群进行比对（Bowtie2）、峰值调用（MACS2）和单细胞分析（Signac/Seurat）。
*   **数据规模**：snATAC-seq 包含约 1.6 万个细胞核，测序深度达数亿 Reads。

### 5. 实验数量与充分性
*   **实验规模**：
    *   **组学实验**：进行了 12 组 Bulk ATAC-seq 和 2 组大型 snATAC-seq。
    *   **功能验证**：测试了 2 个全域表达候选元件（2/2 成功）、7 个神经特异性元件（2/7 成功）、2 个肌肉特异性元件（2/2 成功）以及 13 个发育基因相关元件（仅 1 个表现出微弱活性）。
*   **充分性评价**：实验设计较为充分，涵盖了从全基因组预测到单细胞分辨率分析，再到体内转基因验证的完整闭环。验证实验不仅关注成功案例，也客观记录了失败案例（如发育基因元件）。

### 6. 论文的主要结论与发现
*   **方法有效性**：证明了 10-15x 的低覆盖度基因组测序足以生成可靠的序列保守性图谱，无需昂贵的基因组组装。
*   **CREs 特征**：非编码区的保守岛与 ATAC-seq 峰显著重叠，证实了功能约束与染色质开放性的相关性。
*   **新工具开发**：成功鉴定了能够驱动全域、神经系统和肌肉组织稳健表达的新型调控元件，为钩虾这一新兴模式生物提供了宝贵的遗传工具。

### 7. 优点（亮点）
*   **成本效益极高**：提出的“无需组装的比较基因组学”方法极大地降低了非模式生物研究的门槛。
*   **多维度整合**：将发育阶段、细胞类型特异性与进化时间尺度结合，提高了 CREs 预测的准确度。
*   **实用性强**：直接产出了可用于转基因标记的 DNA 序列资源。

### 8. 不足与局限
*   **发育基因预测困难**：在鉴定发育调控基因（如 *Dll-e, dac*）的增强子时成功率较低，可能是因为这些元件距离更远、活性更弱或存在多个冗余增强子（Shadow Enhancers）。
*   **物种距离敏感性**：该方法高度依赖于选择进化距离适中的近缘种（本文建议 2000 万至 1 亿年分化时间），若物种太近则背景噪音大，太远则保守性丢失。
*   **验证通量**：虽然预测是全基因组规模的，但体内验证仍受限于显微注射的低通量，无法大规模测试所有预测元件。

（完）
