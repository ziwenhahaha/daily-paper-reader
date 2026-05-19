---
title: The Computational and Neural Basis of Zero-Shot Control in Dynamic Pursuit
title_zh: ...
authors: "Kim, D., Lee, J. J., Hayden, B. Y., Yoo, S. B. M."
date: 2026-05-10
pdf: "https://www.biorxiv.org/content/10.64898/2026.03.30.715455v2.full.pdf"
tags: ["query:rl"]
score: 6.0
evidence: 基于认知构念的零样本控制
tldr: 提出认知构念（关系结构、聚光灯注意、可供性）以实现动态追踪中的零样本迁移。
source: biorxiv
selection_source: fresh_fetch
motivation: 基于认知构念的零样本控制。
method: 方法与实现细节请参考摘要与正文。
result: 结果与对比结论请参考摘要与正文。
conclusion: 总体而言，该工作在所述任务上展示了有效性，并提供了可复用的思路或工具。
---

## 摘要
...

## Abstract
Biological agents flexibly adapt their behavior to novel goals and environmental demands without additional training, yet the computational principles enabling such control remain unclear. Here, we propose that three cognitive constructs constitute minimal computational motifs for flexible control: relational structure, spotlight attention, and affordance computation. We examine whether these constructs underpin flexible control in an embodied dynamic pursuit task requiring continuous integration of inter-entity relations, reward, and action feasibility, making it a suitable testbed for real-time control. By implementing these constructs within a multi-module graph convolutional network, we show that the model achieves zero-shot transfer across novel pursuit scenarios without additional training. Although not explicitly trained to do so, the model also exhibits change-of-mind behavior, a hallmark of flexible control exhibited by biological agents. Neural recordings from the primate dorsal anterior cingulate cortex revealed population-level signatures linking these constructs to neural dynamics, providing biological support for the proposed computational architecture.