---
title: "Standalone nanopore sequencing for foodborne pathogen surveillance: a large-scale evaluation and quality control framework"
title_zh: 独立纳米孔测序用于食源性病原体监测：大规模评估与质量控制框架
authors: "Biggel, M., Cernela, N., Horlbog, J., DeMott, M. S., Dedon, P. C., Hall, M. B., Chen, J., Smith, P., Carleton, H. A., Stephan, R., Urban, L."
date: 2026-03-24
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.20.713089v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 用于病原体监测和基因组组装的全基因组测序
tldr: "本研究评估了单机纳米孔（ONT）测序在食源性致病菌监测中的可行性。通过对294个分离株的大规模测试，证实97.3%的ONT组装与混合组装分型一致。研究揭示了DNA修饰引起的特定误差，并开发了QC工具alpaqa，证明在适当质控下，ONT测序足以支持常规基因组监测。"
source: biorxiv
selection_source: fresh_fetch
figures_json: "[{\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-20-713089-v1/fig-001.webp\", \"caption\": \"Figure 1. Accuracy of 294 ONT-only assemblies at varying sequencing depths. The number of mismatching cgMLST alleles was determined by comparing ONT-only assemblies generated at 30x, 40x, 50x, and full depth (up to 100x) to their corresponding hybrid assembly. Each dot represents the assembly of a single isolate. The y-axis is plotted on a logarithmic scale.\", \"page\": 7, \"index\": 1, \"width\": 943, \"height\": 469}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-20-713089-v1/fig-002.webp\", \"caption\": \"Figure 2. Per-base consensus quality scores across representative genomic assembly windows. Bar plots show the Phred-scaled quality scores for each base in the final assembly. (A) Salmonella enterica Kentucky N18-0332, carrying a putative GGCC-targeting phosphorothioation system. (B) Listeria monocytogenes N19-1094, containing a GAAGAC-targeting methyltransferase. Red squares indicate the incorrectly called recognition motifs of the DNA modification systems, each containing a lowquality base (LQB). The genome-wide density of LQBs can be used as a predictor of systematic errors and overall assembly accuracy.\", \"page\": 8, \"index\": 2, \"width\": 829, \"height\": 217}, {\"url\": \"assets/figures/biorxiv/biorxiv-10-64898-2026-03-20-713089-v1/fig-003.webp\", \"caption\": \"Figure 3. Correlation between LQB density and cgMLST allelic mismatches. The scatterplots illustrate the relationship between the frequency of low-quality bases (LQB) per Mbp determined with alpaqa and the number of mismatching cgMLST alleles across 294 ONT-only assemblies (50x target coverage) from (A) SUP- and (B) HAC-basecalled data. Each dot represents an assembly. A small vertical jitter was applied to dots with 0 and 1 mismatching alleles to reduce overlap. Tables summarize the frequency of assemblies across different LQB densities and allelic mismatch counts.\", \"page\": 9, \"index\": 3, \"width\": 943, \"height\": 627}]"
motivation: 评估单机纳米孔测序在食源性致病菌监测中的准确性，并解决DNA修饰可能导致的系统性测序误差。
method: 对294个食源性致病菌分离株进行大规模ONT测序评估，并开发了名为alpaqa的轻量级系统性误差检测工具。
result: "97.3%的ONT组装结果在cgMLST分型上与混合组装高度一致，但在特定菌株中发现了由DNA修饰引起的误差。"
conclusion: 配合适当的质量控制框架，单机ONT测序已足够准确，可用于常规的食源性致病菌基因组监测。
---

## 摘要
全基因组测序（WGS）是食源性病原体监测和跨境疫情检测的核心。使用 Oxford Nanopore Technologies (ONT) 的长读长测序有望在单一工作流中实现快速、完整且具有成本效益的基因组组装。然而，由于担心 DNA 修饰可能会损害单碱基测序准确性和下游基因分型，独立 ONT 原生 DNA 测序的应用进展缓慢。我们评估了代表 10 种主要食源性病原体的 294 个遗传多样性分离株的纯 ONT 测序性能。在 50x 覆盖度下，97.3% (286/294) 的 ONT 组装结果产生了与 Illumina 修正的混合组装结果相同或近乎相同（等位基因差异 ≤3）的 cgMLST 谱图。在 4 个肯塔基沙门氏菌（Salmonella enterica serovar Kentucky）和 4 个单核细胞增生李斯特菌（Listeria monocytogenes）分离株中观察到错误率升高，这与特定的 DNA 硫代磷酸化或甲基化系统的存在有关。为了能够快速识别不可靠的组装结果，我们开发了 alpaqa，这是一种轻量级计算工具，无需补充短读长数据或参考基因组即可检测系统性纳米孔组装错误。通过标记受系统误差影响的组装结果，alpaqa 为纯 ONT 工作流提供了质量保障。屏蔽被 alpaqa 标记的组装结果中的低质量碱基提高了 cgMLST 的准确性，尽管这减少了可调用位点的数量，从而降低了基因分型分辨率。我们的研究结果表明，在当前的化学试剂、软件和适当的质量控制下，独立 ONT 原生 DNA 测序对于常规食源性病原体监测具有足够的准确性，支持其在统一的基因组监测框架中使用。

## Abstract
Whole-genome sequencing (WGS) is central to foodborne pathogen surveillance and cross-border outbreak detection. Long-read sequencing using Oxford Nanopore Technologies (ONT) promises rapid, complete, and cost-effective genome assemblies in a single workflow. However, the adoption of standalone ONT sequencing of native DNA has been slowed by concerns that DNA modifications can compromise per-base sequencing accuracy and downstream genotyping.

We evaluated ONT-only sequencing performance across 294 genetically diverse isolates representing ten major foodborne pathogens. At 50x coverage, 97.3% (286/294) of the ONT assemblies produced identical or near-identical cgMLST profiles ([&le;]3 allelic differences) as Illumina-polished hybrid assemblies. Elevated error rates were observed in four Salmonella enterica serovar Kentucky and four Listeria monocytogenes isolates and were associated with the presence of specific DNA phosphorothioation or methylation systems.

To enable rapid identification of unreliable assemblies, we developed alpaqa, a lightweight computational tool that detects systematic nanopore assembly errors without requiring supplemental short-read data or reference genomes. By flagging assemblies affected by systematic errors, alpaqa provides a quality safeguard for ONT-only workflows. Masking low-quality bases in assemblies flagged by alpaqa improved cgMLST accuracy, although this reduced the number of callable loci and therefore genotyping resolution.

Our findings demonstrate that standalone ONT sequencing of native DNA is sufficiently accurate for routine foodborne pathogen surveillance with current chemistry, software, and appropriate quality control, supporting its use in harmonised genomic surveillance frameworks.

---

## 论文详细总结（自动生成）

### 论文总结：独立纳米孔测序用于食源性病原体监测

#### 1. 核心问题与整体含义（研究动机和背景）
全基因组测序（WGS）已成为食源性病原体监测和疫情溯源的核心技术。长期以来，Illumina 短读长测序因其高单碱基准确性被视为“金标准”，但其难以解决基因组中的重复区域。Oxford Nanopore Technologies (ONT) 的长读长测序虽然能提供完整的基因组组装且成本更低、速度更快，但其**原生 DNA 测序受到表观遗传修饰（如甲基化、硫代磷酸化）的影响**，可能导致系统性的碱基识别错误，进而影响核心基因组多位点序列分型（cgMLST）的准确性。本研究旨在评估最新 ONT 技术（R10.4.1, SUP 模型）在独立使用时是否足以支持常规监测，并建立质量控制框架。

#### 2. 核心方法论
研究提出了一套完整的生物信息学流程和质控工具：
*   **BOAP 自动化流程：** 基于 Nextflow 开发，整合了 `dorado`（碱基识别与抛光）、`Flye`（组装）、`DNApler`（环状基因组重定向）和 `medaka v2`。
*   **alpaqa 质控工具：** 这是本研究的核心创新。它是一种轻量级工具，**无需参考基因组或短读长数据**，直接分析 ONT 组装共识序列的质量得分（Phred scores）。
    *   **核心逻辑：** 识别低质量碱基（LQB，定义为 Q1-Q5）。
    *   **算法流程：** 使用滑动窗口（5000 bp）扫描最长 contig，屏蔽 LQB 密度异常高的区域（排除组装伪影），计算每 Mb 的标准化 LQB 密度。
    *   **k-mer 富集分析：** 通过二项式检验识别与 LQB 显著相关的特定序列基序（如 GGCC 或 GAAGAC），从而定位由特定 DNA 修饰系统引起的系统误差。

#### 3. 实验设计
*   **数据集：** 选取了 294 个遗传多样性分离株，涵盖 10 种主要食源性病原体（包括沙门氏菌、李斯特菌、空肠弯曲杆菌、蜡样芽孢杆菌等）。
*   **Benchmark（基准）：** 以 Illumina 读段修正后的“混合组装（Hybrid Assembly）”作为真值。
*   **对比维度：**
    *   不同测序深度（30x, 40x, 50x, 100x）。
    *   不同碱基识别模型（SUP 超高精度模型 vs. HAC 高精度模型）。
    *   外部验证：使用 147 个公开的临床分离株数据集验证 `alpaqa` 的普适性。
*   **验证指标：** cgMLST 等位基因差异数（≤3 个差异被认为高度一致）。

#### 4. 资源与算力
*   **测序设备：** 使用了 ONT MinION 和 PromethION 设备，配合 R10.4.1 芯片。
*   **软件环境：** 使用了 `dorado v1.2.0` 进行 SUP@v5.2 模型推理。
*   **算力说明：** 文中未明确列出具体的 GPU 型号或计算集群规模，但提到 `alpaqa` 是“轻量级”的，且 `BOAP` 流程旨在支持标准化、可扩展的监测工作流。

#### 5. 实验数量与充分性
*   **实验规模：** 294 个内部样本 + 147 个外部样本，总计超过 400 个基因组，样本量在同类评估研究中属于大规模。
*   **充分性：** 实验涵盖了多种病原体和不同的测序深度，并针对发现的异常样本（如肯塔基沙门氏菌）进行了深入的生化验证（LC-MS/MS 检测硫代磷酸化），实验设计严谨且具有互补性。
*   **客观性：** 通过下采样（Downsampling）实验客观评估了深度对准确性的影响，避免了因深度过高掩盖模型缺陷。

#### 6. 主要结论与发现
*   **高准确性：** 在 50x 深度下，**97.3% (286/294)** 的 ONT 组装结果与基准一致（≤3 个等位基因差异），86.7% 完全一致。
*   **误差来源：** 少数准确性较差的样本（如肯塔基沙门氏菌 ST152）与 **Dnd 硫代磷酸化系统**（针对 GGCC 基序）或特定的甲基化系统有关。
*   **质控有效性：** `alpaqa` 识别的 LQB 密度与 cgMLST 准确性高度相关。LQB 密度 < 5/Mbp 是组装可靠的强力预测指标。
*   **修复策略：** 屏蔽（Masking）低质量碱基可以显著提高分型准确性，但会略微降低分辨率。

#### 7. 优点
*   **实用性强：** 开发了无需短读长的质控工具 `alpaqa`，解决了 ONT 独立应用中的“信任危机”。
*   **生物学洞察：** 首次详细揭示了硫代磷酸化修饰（PT）对最新 ONT R10.4.1 测序准确性的具体影响基序。
*   **流程标准化：** 提供了开源的 Nextflow 流程，便于公共卫生实验室直接采用。

#### 8. 不足与局限
*   **物种覆盖不均：** 虽然涵盖 10 种病原体，但部分物种（如副溶血性弧菌）样本量较小（n=8），可能无法捕捉到所有罕见的 DNA 修饰系统。
*   **独立提取偏差：** Illumina 和 ONT 测序使用的是独立提取的 DNA，虽然不影响系统误差分析，但可能引入极少数因培养或提取产生的随机差异。
*   **模型依赖性：** 结论基于当前的 SUP@v5.2 模型，随着 ONT 算法的迭代，某些特定的修饰误差可能会消失，但也可能出现新的偏差。

（完）
