---
title: Programmable domestication of thermophilic bacteria through removal of non-canonical defense systems
title_zh: 通过移除非规范防御系统实现嗜热细菌的可编程驯化
authors: "Sung, J.-Y., Lee, M.-H., Park, J., Kim, H., Ganbat, D., Kim, D., Cho, H.-W., Suh, M. K., Lee, J.-S., Lee, S. J., Kim, S. B., Lee, D.-W."
date: 2026-03-24
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.21.713436v1.full.pdf"
tags: ["query:gene"]
score: 9.0
evidence: 细菌的生物技术应用和遗传驯化
tldr: 嗜热细菌在工业生物技术中具有巨大潜力，但其强大的防御系统阻碍了基因改造。本研究开发了DNMB计算框架，通过多组学分析识别并删除了限制DNA摄取的非规范核酸酶防御系统（如Wadjet II），使转化效率提升高达六个数量级。结合内源CRISPR-Cas9等工具，成功将难转化的地芽孢杆菌驯化为可编程的工业底盘细胞，为非模式嗜热菌的开发提供了通用策略。
source: biorxiv
selection_source: fresh_fetch
motivation: 嗜热细菌因其复杂的防御系统阻碍外源DNA摄取，导致其在工业生物技术中的遗传改造面临巨大挑战。
method: 开发了名为DNMB的多组学引导计算框架，用于系统识别阻碍转化的遗传屏障，并结合靶向基因缺失和内源CRISPR工具进行菌株驯化。
result: 发现并删除了Wadjet II等非规范防御系统，使地芽孢杆菌的转化效率提升了多达100万倍，并实现了稳定的异源表达。
conclusion: 该研究建立了一套通用的可编程驯化框架，能够将遗传难操作的嗜热菌转化为高效的可编程工业底盘。
---

## 摘要
嗜热细菌在工业生物技术中具有显著优势，但由于细胞防御系统阻碍了高效的 DNA 获取，大多数嗜热细菌在遗传学上仍难以操作。在此，我们提出了一种可编程驯化策略，可将野生型地芽孢杆菌（Geobacillus）菌株转化为遗传可操作的嗜热宿主。我们开发了非模式细菌驯化（DNMB）套件，这是一个由多组学引导的计算框架，可系统地识别转化的遗传障碍。DNMB 分析显示，包括 Wadjet II 在内的基于核酸酶的非规范防御系统，构成了先前难以操作的地芽孢杆菌菌株中 DNA 摄取的主要障碍。针对这些位点的定向缺失使转化效率提高了多达六个数量级。我们进一步建立了一个分层嗜热工程工具包，该工具包集成了质粒人工修饰、接合辅助 DNA 递送以及利用内源性 CRISPR-Cas9 系统进行的基因组编辑。由此产生的驯化菌株支持在高温下进行稳定的异源表达和可调控的遗传控制。总之，这些结果建立了一个通用框架，用于将遗传难操作的嗜热菌转化为可编程的工业底盘。

## Abstract
Thermophilic bacteria offer major advantages for industrial biotechnology, yet most remain genetically intractable because cellular defense systems block efficient DNA acquisition. Here, we present a programmable domestication strategy that converts wild Geobacillus strains into genetically tractable thermophilic hosts. We developed the Domestication of Non-Model Bacteria (DNMB) Suite, a multi- omics-guided computational framework that systematically identifies genetic barriers to transformation. DNMB analysis revealed that non-canonical nuclease-based defense systems, including Wadjet II, constitute dominant barriers to DNA uptake in previously intractable Geobacillus strains. Targeted deletion of these loci increased transformation efficiency by up to six orders of magnitude. We further established a hierarchical thermophilic engineering toolkit that integrates plasmid artificial modification, conjugation-assisted DNA delivery, and genome editing using an endogenous CRISPR-Cas9 system. The resulting domesticated strains support stable heterologous expression and tunable genetic control at elevated temperatures. Together, these results establish a generalizable framework for transforming genetically intractable thermophiles into programmable industrial chassis.

---

## 论文详细总结（自动生成）

### 论文结构化总结：通过移除非规范防御系统实现嗜热细菌的可编程驯化

#### 1. 论文的核心问题与整体含义
*   **研究动机**：嗜热细菌（如地芽孢杆菌 *Geobacillus*）具有生长快、耐高温、减少污染风险等工业优势，但绝大多数野生菌株由于拥有复杂的细胞防御系统，导致外源 DNA 极难导入（遗传难操作性），严重阻碍了其作为工业底盘细胞的开发。
*   **核心问题**：传统的限制-修饰（R-M）系统绕过策略往往无法完全解决转化难题。论文旨在系统性地识别并消除阻碍 DNA 摄取的深层遗传屏障（尤其是非规范防御系统），从而将野生嗜热菌“驯化”为可编程的工业生产平台。

#### 2. 论文提出的方法论
论文开发了 **DNMB (Domestication of Non-Model Bacteria) Suite**，这是一个多组学引导的计算与实验集成框架：
*   **多组学计算分析**：整合比较基因组学、转录组学和基序挖掘，利用 DefenseFinder 和 REBASE 识别 R-M 系统、CRISPR-Cas 以及非规范防御系统（如 Wadjet II, Gabija, pAgo 等）。
*   **质粒人工修饰 (PAM)**：在工程化 *E. coli* 供体中模拟宿主特有的 DNA 甲基化模式，以逃避宿主的 R-M 限制。
*   **接合辅助工程 (PACE)**：结合甲基化匹配与 pRK24 介导的接合转移，提高 DNA 递送效率。
*   **内源 CRISPR-Cas9 编辑**：挖掘并优化菌株自带的 Type II-C CRISPR 系统（GeoCas9EF），实现高效的基因组定向编辑。
*   **翻译优化**：通过分析密码子偏好性和 RBS（核糖体结合位点）基序，优化异源基因的表达效率。

#### 3. 实验设计
*   **数据集/场景**：分析了 51 个完整的地芽孢杆菌属（*Geobacillus* 和 *Parageobacillus*）基因组。
*   **重点菌株**：选取了遗传极难操作的野生菌株 *G. stearothermophilus* EF60045 和 SJEF4-2。
*   **对比实验**：
    *   对比了不同甲基化修饰状态下的转化率。
    *   对比了电穿孔与接合转移的效率。
    *   **消融实验**：系统性地逐个删除预测的防御模块（如 SspBCDE, Gabija, Wadjet II, CBASS 等），观察转化效率的变化。
*   **Benchmark**：以未经修饰的 DNA 和标准 *E. coli* 产生的质粒作为对照基准。

#### 4. 资源与算力
*   **算力说明**：文中未详细列出具体的 GPU 算力或大规模计算集群配置。
*   **测序资源**：使用了 **PacBio SMRT 测序**进行甲基化组分析（检测 6mA 等修饰），以及 **Illumina NovaSeq 6000** 进行转录组测序（RNA-seq）和基因组重测序校正。

#### 5. 实验数量与充分性
*   **实验规模**：涵盖了 51 个菌株的泛基因组分析，针对 2 个核心菌株进行了多轮基因删除实验。
*   **充分性**：实验设计非常详尽，不仅通过消融实验确定了关键防御屏障，还测试了 11 种不同强度的启动子和多种复制子（质粒拷贝数从个位数到 100+），确保了工具包的梯度覆盖。
*   **客观性**：采用了流式细胞术定量荧光表达、qPCR 测定拷贝数以及生长曲线监测，数据具有高度的可重复性和客观性。

#### 6. 论文的主要结论与发现
*   **非规范系统是主因**：发现 **Wadjet II** 系统（而非传统的 R-M 系统）是阻碍地芽孢杆菌转化的主要遗传屏障。
*   **效率飞跃**：通过定向删除 Wadjet II 等防御位点，转化效率提升了 **6 个数量级**（100 万倍）。
*   **工具包建立**：成功构建了包含可调控启动子、诱导系统和多种复制子的嗜热菌专用遗传工具包。
*   **代谢重塑**：通过驯化菌株实现了 D-塔格糖（稀有糖）的代谢路径构建，证明了该底盘在高温工业生物技术中的应用潜力。

#### 7. 优点
*   **系统性强**：从计算预测到实验验证，再到工具开发和应用展示，形成了一个完整的闭环。
*   **突破性发现**：首次明确了 Wadjet II 系统在嗜热菌遗传难操作性中的核心作用，解决了该领域长期的痛点。
*   **通用性**：DNMB 框架不仅适用于地芽孢杆菌，也可推广至其他非模式微生物的驯化。

#### 8. 不足与局限
*   **物种覆盖**：虽然框架通用，但实验验证主要集中在地芽孢杆菌属，对于其他极端嗜热菌（如古菌或其他细菌门类）的适用性尚待验证。
*   **机制细节**：虽然证明了 Wadjet II 的阻碍作用，但其识别和切割外源 DNA 的具体分子机制（如对 DNA 拓扑结构的识别）在本文中未做深入探讨。
*   **长期稳定性**：大规模删除防御系统虽然提高了转化率，但可能降低菌株在复杂工业环境（如存在噬菌体污染）中的防御能力。

（完）
