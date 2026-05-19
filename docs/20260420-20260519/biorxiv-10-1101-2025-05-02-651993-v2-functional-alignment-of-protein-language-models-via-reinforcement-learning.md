---
title: Functional alignment of protein language models via reinforcement learning
title_zh: 通过强化学习实现蛋白质语言模型的功能对齐
authors: "Blalock, N., Seshadri, S., Nakamura, K., Babbar, A., Fahlberg, S. A., Kulkarni, A., Romero, P. A."
date: 2026-05-08
pdf: "https://www.biorxiv.org/content/10.1101/2025.05.02.651993v2.full.pdf"
tags: ["query:rl"]
score: 6.0
evidence: 强化学习用于蛋白质模型对齐
tldr: 蛋白质语言模型缺乏对功能的明确理解，无法超越自然进化生成高效变异。研究提出RLXF（从实验反馈中进行强化学习）框架，对模型进行功能对齐并在五大蛋白质家族验证，尤其在CreiLOV无氧荧光蛋白中产生史上最高荧光强度突变体，显著提升生成成功率和协同突变发现能力。
source: biorxiv
selection_source: fresh_fetch
motivation: 现有预训练蛋白质语言模型缺乏对特定功能目标的显式理解，导致生成序列的功能改进受限。
method: RLXF通过强化学习结合实验测得的蛋白质功能反馈，对预训练语言模型进行微调，实现功能对齐。
result: 在五种不同蛋白质家族中，RLXF模型生成的高功能变异显著优于预训练基线，尤其在CreiLOV中实现了史上最高荧光强度突变体。
conclusion: RLXF提供可扩展且易用的方法，将实验观测与预训练模型的进化知识结合，推动功能驱动的蛋白质设计超越自然进化的限制。
---

## 摘要
蛋白质语言模型（pLMs）能够生成新的蛋白质序列，但因缺乏对功能的明确理解，往往无法超越自然界中发现的属性进行改进。我们提出了 Reinforcement Learning from eXperimental Feedback (RLXF)，一个通用的框架，通过实验测量的功能目标对蛋白质语言模型进行对齐，灵感来源于像 ChatGPT 这样的大型语言模型的对齐方法。在五个不同的蛋白质家族中应用 RLXF，生成的具有高功能的变体超过了预训练基线。我们通过 CreiLOV（一种不依赖氧气的荧光蛋白）展示了这一点，经过 RLXF 对齐的模型生成的序列表现出显著增强的荧光活性，包括迄今为止报告的荧光强度最高的 CreiLOV 变体。我们的结果表明，RLXF 对齐的模型有效地整合了预训练 pLMs 中编码的进化知识和实验观察，提高了生成序列的成功率，并能够发现通过零样本或进化方法难以识别的协同突变组合。RLXF 提供了一种可扩展且易于获取的方法，将生成模型引导向期望的生化特性，实现超越自然进化限制的功能驱动蛋白质设计。

## Abstract
Protein language models (pLMs) enable generative design of novel protein sequences but remain fundamentally misaligned with protein engineering goals, as they lack explicit understanding of function and often fail to improve properties beyond those found in nature. We introduce Reinforcement Learning from eXperimental Feedback (RLXF), a general framework that aligns protein language models with experimentally measured functional objectives, drawing inspiration from the methods used to align large language models like ChatGPT. Applied across five diverse protein families, RLXF improves generation of high-functioning variants beyond pre-trained baselines. We demonstrate this with CreiLOV, an oxygen-independent fluorescent protein, where RLXF-aligned models generate sequences with significantly enhanced fluorescence, including the most fluorescent CreiLOV variants reported to date. Our results indicate that RLXF-aligned models effectively integrate the evolutionary knowledge encoded in pre-trained pLMs with experimental observations, improving the success rate of generated sequences and enabling the discovery of synergistic mutation combinations that are difficult to identify through zero-shot or evolutionary approaches. RLXF provides a scalable and accessible approach to steer generative models toward desired biochemical properties, enabling function-driven protein design beyond the limits of natural evolution.