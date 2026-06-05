---
title: "KBase Research Agent: Automated Multi-Agent Workflow Construction for Reproducible Genome Analysis"
authors: "Gupta, P., Riehl, W. J., Cashman, M., Chivian, D., Neely, C. J., Canon, S. R., Cottingham, R., Henry, C., Arkin, A. P., Dehal, P. S."
date: 2026-06-04
pdf: "https://www.biorxiv.org/content/10.64898/2026.06.01.729336v1.full.pdf"
tags: ["query:mas"]
score: 9.0
evidence: 用于自动化生物信息学工作流的多智能体系统
tldr: KBase研究智能体自动化多步骤生物信息学工作流。
source: biorxiv
selection_source: fresh_fetch
motivation: 用于自动化生物信息学工作流的多智能体系统。
method: 方法与实现细节请参考摘要与正文。
result: 结果与对比结论请参考摘要与正文。
conclusion: 总体而言，该工作在所述任务上展示了有效性，并提供了可复用的思路或工具。
---

## Abstract
Constructing multi-step bioinformatics workflows, from read quality control through genome assembly to functional annotation, requires expertise in both biology and computational tool selection, creating a bottleneck for scalable and reproducible analysis. We present the KBase Research Agent, a multi-agent system for automating such workflows within the DOE Systems Biology Knowledgebase (KBase). Given a set of sequencing reads and a research objective, the agent constructs an analysis plan grounded in KBase documentation and a Knowledge Graph (KG) of the KBase application catalog, then selects, parameterizes, validates and executes appropriate KBase applications to carry out the workflow. The resulting analysis is preserved as a reproducible KBase Narrative. We evaluate the system's planning and execution quality against ground truth constructed from reference workflows derived from peer-reviewed Microbiology Resource Announcements. We further apply the agent to 100 previously unanalyzed bacterial isolate genomes from the JGI IMG/M database, where it autonomously performed read quality control, genome assembly, taxonomic classification with GTDB-Tk, and downstream analysis producing annotated genomes, reproducible Narratives, and draft manuscripts without human intervention. Across these experiments, the KBase Research Agent demonstrates the feasibility of domain-grounded, end-to-end scientific workflow automation in a production bioinformatics platform.

---

## 论文详细总结（自动生成）

# 论文详细总结

## 1. 论文的核心问题与整体含义（研究动机和背景）

- **研究动机**：构建多步骤生物信息学工作流（如从测序reads质量控制到基因组组装和功能注释）需要同时具备生物学领域知识和计算工具选择的专业能力，这形成了可扩展和可重复分析的瓶颈。

- **背景**：DOE（美国能源部）系统生物学知识库（KBase）是一个生产级生物信息学平台，但用户需要手动选择和配置工具，门槛较高。

- **核心问题**：如何自动化构建和执行复杂生物信息学工作流，使得非专业用户也能完成高质量的基因组分析。

---

## 2. 论文提出的方法论：核心思想、关键技术细节

### 核心思想

- **KBase Research Agent**：一个多智能体（Multi-Agent）系统，用于在KBase平台上自动化构建和执行生物信息学工作流。
- 给定输入数据（测序reads）和研究目标，系统自动完成从计划到执行的完整流程。

### 关键技术细节

- **分析计划构建**：基于KBase文档和知识图谱（KG of KBase application catalog）构建分析计划。
- **知识图谱（KG）**：将KBase应用目录建模为知识图谱，支持应用选择和参数推荐。
- **多智能体协作**：系统由多个智能体组成，分别负责：
  - 任务分解与计划生成
  - 应用选择与参数化
  - 验证与执行
  - 结果记录与输出
- **工作流执行**：选择、参数化、验证和执行适当的KBase应用。
- **可重复性保证**：生成的KBase Narrative包含完整的工作流信息，可追溯和复现。

### 算法流程（文字说明）

1. **输入**：测序reads + 研究目标描述
2. **计划生成**：基于文档和KG构建分析计划（分解为多个子任务）
3. **应用选择**：根据子任务类型从KG中选择合适的KBase应用
4. **参数化**：基于文档推荐和历史数据确定应用参数
5. **验证**：检查参数合理性和数据兼容性
6. **执行**：调用KBase API执行应用
7. **迭代**：根据执行结果调整后续计划
8. **输出**：生成可重复的KBase Narrative

---

## 3. 实验设计：数据集、benchmark、对比方法

### 数据集

- **参考工作流**：从同行评审的*Microbiology Resource Announcements*中提取的参考工作流（ground truth）
- **应用数据集**：100个之前未分析的细菌分离基因组，来自JGI IMG/M数据库

### Benchmark

- 与专家构建的ground truth参考工作流进行对比，评估：
  - 规划质量（计划是否合理）
  - 执行质量（结果是否正确）

### 对比方法

- 论文主要与ground truth进行对比，验证自动化生成工作流与专家工作流的一致性

### 工作流覆盖

- **read quality control**（测序reads质量控制）
- **genome assembly**（基因组组装）
- **taxonomic classification with GTDB-Tk**（使用GTDB-Tk进行分类学分类）
- **downstream analysis**（下游分析）
- **annotated genomes**（带注释的基因组）
- **draft manuscripts**（草稿手稿）

---

## 4. 资源与算力

- **算力信息**：论文摘要中未明确提及具体的GPU型号、数量或训练时长等算力信息。
- **推断**：作为生产级平台的自动化系统，主要依赖KBase平台的计算资源，但具体细节未在摘要中说明。

---

## 5. 实验数量与充分性

### 实验数量

- **参考工作流对比**：使用从同行评审资源中提取的多个参考工作流进行评估
- **应用实验**：100个细菌分离基因组的完整分析

### 实验充分性

- **规模验证**：100个独立基因组的实验展示了系统的鲁棒性
- **ground truth对比**：提供了客观的评估标准
- **端到端验证**：从reads到draft manuscripts的完整流程验证
- **评价**：实验覆盖了规划、执行和输出多个维度，数量和场景较为充分

### 客观性与公平性

- 使用peer-reviewed来源的参考工作流作为ground truth，评估标准客观
- 100个未分析基因组的应用展示了真实世界场景的适用性

---

## 6. 论文的主要结论与发现

- **可行性验证**：展示了在生产生物信息学平台（KBase）中进行领域接地（domain-grounded）、端到端科学工作流自动化的可行性
- **全流程自动化**：系统成功完成了从read质量控制到基因组组装、分类学分类和下游分析的完整流程
- **输出产物**：生成了带注释的基因组、可重复的KBase Narrative和draft manuscripts
- **无需人工干预**：在100个细菌基因组分析中实现了完全自主的工作流构建和执行
- **可重复性**：输出的KBase Narrative确保了分析的可追溯和可复现

---

## 7. 优点：方法或实验设计上的亮点

- **多智能体架构**：通过多智能体协作实现复杂任务的分解和执行
- **领域知识整合**：充分利用KBase文档和知识图谱引导决策
- **端到端自动化**：覆盖从输入到输出的完整工作流，无需人工干预
- **可重复性设计**：输出KBase Narrative确保科学发现的可复现性
- **大规模验证**：100个基因组的应用展示了系统的实用性和鲁棒性
- **ground truth评估**：使用peer-reviewed参考工作流进行客观评估
- **真实数据**：使用JGI IMG/M数据库的真实未分析数据

---

## 8. 不足与局限

- **算力信息缺失**：未明确说明系统运行所需的计算资源
- **性能指标有限**：摘要中未提供具体的准确率、效率等量化指标
- **应用范围**：目前聚焦于细菌基因组分析，对真核生物或复杂基因组的适用性待验证
- **错误处理**：摘要中未涉及系统如何处理执行失败或异常情况
- **用户交互**：未说明系统是否支持用户干预或调整
- **基准对比**：缺少与其他自动化工作流系统（如Snakemake、Nextflow等）的对比

---

（完）
