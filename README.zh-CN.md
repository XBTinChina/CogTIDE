# cogTIDE

English version: [README.md](README.md)

**Cognitive Theory Ideation, Debate, and Epistemic Evaluation（认知理论构思、辩论与知识论评估）**
—— 一个经过同行校准、以审计为先的 LLM 流水线，用于心理学、认知神经科学与认知科学中的理论生成。

cogTIDE 通过一条多阶段流水线，将一个开放式研究问题转化为一组候选科学理论。它与
简单地「让 LLM 直接给出理论」的根本区别在于：阶段之间的每一次晋级都由外部同行评审、
预测能力以及下游存活情况决定，而非由综合表述的流畅度决定；并且它产出的每一个产物都可
追溯回其来源的构思。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

> ## ⚠️ 负责任使用 —— 请先阅读
>
> **cogTIDE 产出的是假设，而非经过验证的科学结论。**
> 它生成的理论是候选想法，旨在支持专家的构思与评审。它们*不是*经过同行评议的研究
> 发现，也没有针对实验或经验文献进行核验。
>
> - LLM 的输出可能是**错误的、编造的、过时的或带有偏见的**。请将每一个论断、机制和
>   预测的效应都视为未经证实。
> - 内部的同行预测与校准分数衡量的是模型生成的评审者之间的*相对*评审信号 ——
>   它们**不是**衡量科学真理或现实世界有效性的指标。
> - 这里的任何内容都不能替代领域专业知识、正规的文献综述、预注册或经验检验。
>
> 请将 cogTIDE 作为头脑风暴与审计的辅助工具，并在据其行动之前，让每一项输出都接受
> 人类专家的判断。

---

## cogTIDE 的功能

cogTIDE 运行一条以审计为先的五阶段流水线（Stage 0 → Stage 4），将研究问题转化为
结构化的理论候选：

- **多智能体构思** —— 一个由领域专家智能体组成的注册表在若干风险等级上生成原始
  构思，并附带一轮挑战者（challenger）复核。
- **同行筛选式综合** —— 盲审同行评审与评分卡决定哪些构思得以晋级；联盟（coalition）
  对其进行起草、批判并细化为更深入的理论，同时配有一个外部评审组。
- **同行预测** —— 每位评审者不仅报告自己的评分，还报告他/她预期*其他*评审者会给出的
  评价，以及该条目在下一阶段存活的概率。获得的支持超出预测（即「意外支持」，
  unexpected support）的条目会被凸显出来。
- **评审者校准** —— 评审者会根据其预测在多次运行中与实际情况的吻合程度被打分；更敏锐
  的评审者在校准加权分数中获得更大的权重。
- **跨运行记忆** —— 一个可选的、仅作参考的记忆子系统，让后续运行能够从先前运行中学习
  （主题快照、评审者校准，以及一个基于白名单的已学策略叠加层）。
- **完全可追溯** —— 每个规范产物都带有稳定的 ID 和血缘字段，每次运行都会记录自身的
  溯源信息，因此任何最终理论都可以经由 kernel、深度理论一路回溯到最初的构思。

## 流水线如何运作

流水线是一系列阶段的序列；每个阶段读取上一阶段的规范产物，并将自身产物写入
`runs/<run_id>/`。阶段的可调参数（智能体数量、评审组规模、目标数、记忆开关）位于
`configs/pipeline.yaml`。

- **Stage 0 —— 问题澄清。** 一个交互式澄清循环将原始问题规范化为一个
  `QuestionDossier`。它可以从 `question/` 下匹配的子文件夹中摄取本地材料，并可选择性地
  摄取先前运行的记忆。运行继续之前必须通过一道确认关卡（可用 `--non-interactive`
  跳过）。写入 `stage_00/question-*.json` / `.md`。
- **Stage 1 —— 多智能体构思。** 19 个领域专家智能体各自在 3 个风险等级上生成构思
  （19 × 3 = 57 条原始构思），随后进行一轮挑战者复核。写入
  `stage_01/raw-ideas-*.json`。
- **Stage 2 —— 同行筛选式联盟综合。** 盲审同行评审与评分卡对构思进行排序；联盟随后将
  其起草并批判为深度理论，由一个外部评审组打分。写入 `idea-peer-reviews.json`、
  `idea-scorecards.json`、`external-panel-reviews-D*.json` 以及
  `coalition-deep-theories-*.json`。
- **Stage 3 —— 委员会 / kernel 综合。** 一个经过引导的委员会（council）在深度理论之间
  开展工作，产出 kernel 假设，由外部评审组打分。写入 `council-kernels-*.json` / `.md`
  以及 `external-panel-reviews-K*.json`。
- **Stage 4 —— 理论三元组。** 每个 kernel 被扩展为一个 **core / solid / risky**
  三元组，经过同行打分与修订，并配有一份通俗易懂的讲解。写入
  `triplet-theories-*.json` / `.md`、`triplet-scorecard-K*.json` 以及
  `triplet-peer-reviews-K*.json`。

一次典型的运行会产出 **组织为 5 个三元组的 15 个最终理论**（每个 kernel 对应
core / solid / risky），不过这些数量都是可配置的。

## 仓库结构

```
CogTIDE/
├── cogtide/               # Python 包（以 `cogtide` 导入）
│   ├── cli.py             # 命令行入口
│   ├── registry.py        # 智能体注册表加载器
│   ├── stages/            # stage_00 … stage_04 各阶段驱动
│   ├── pipeline/          # 控制器、运行上下文、检查点、产物
│   ├── evaluation/        # 评分、同行评审、校准、预测
│   ├── memory/            # 跨运行记忆：存储、检索、策略、编译器
│   ├── models/            # 用于档案、构思、理论、评分卡的 pydantic 模型
│   ├── llm/               # OpenAI 兼容客户端、重试、提示词构建
│   ├── reporting/         # 各阶段 markdown 渲染器
│   ├── validators/        # 产物保全校验
│   └── utils/             # ID、IO、文本辅助工具
├── configs/               # models.yaml、retries.yaml、pipeline.yaml、agents.yaml
├── prompts/               # 各阶段 + 共享/记忆提示词模板
├── schemas/               # 每个规范产物的 JSON Schema
├── scripts/               # 实用脚本（如 export_schemas.py）
├── tests/                 # 单元测试
├── question/              # 在此放置 Stage 0 的本地材料（仅含脚手架）
├── paper/                 # 手稿 / 预印本源文件（TODO）
├── pyproject.toml
├── .env.example           # 复制为 .env 并填入你的 API key
├── CITATION.cff
├── LICENSE                # MIT
└── README.md
```

`runs/`（每次运行的产物）和 `memory/`（跨运行记忆）是**在运行时生成且被 git 忽略的**
—— 它们可能包含未发表的研究材料，绝不能提交到仓库。你在 `question/` 下添加的任何内容
同样被 git 忽略；仅脚手架会被纳入版本控制。

## 前置条件

- **Python 3.10+**。
- 一个 **OpenAI 兼容的 chat-completions 端点**及其 **API key**。cogTIDE 可与任何遵循
  OpenAI chat-completions 协议的提供方对接 —— OpenAI、智谱 GLM、月之暗面 Kimi，或
  vLLM、Ollama 等本地服务。

## 安装

提示词、配置与 schema 都是相对于仓库根目录加载的，因此从克隆仓库进行可编辑安装
（editable install）是受支持的方式。

```bash
git clone https://github.com/XBTinChina/CogTIDE.git   # TODO: confirm final URL
cd CogTIDE

python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate

pip install -e .                          # 运行时依赖
pip install -e ".[dev]"                   # + 测试依赖（pytest）
```

## 配置

所有配置都位于 `configs/` 下。**API key 绝不写入这些文件** —— 它们从环境变量或仓库
根目录的 `.env` 中读取。

### `configs/models.yaml` —— 提供方（OpenAI 兼容、与提供方无关）

设置 `api_base_url`、`model`，以及保存你 key 的环境变量名（`api_key_env`，若其未设置则
尝试 `fallback_api_key_env`）。默认配置指向**智谱 GLM**；你也可将其指向有权访问的任意提供方：

```yaml
default:
  provider: zhipu
  api_base_url: https://open.bigmodel.cn/api/paas/v4   # 智谱 GLM（默认）
  # api_base_url: https://api.openai.com/v1            # OpenAI
  # api_base_url: http://localhost:11434/v1            # 本地 Ollama
  api_key_env: ZHIPU_API_KEY
  fallback_api_key_env: OPENAI_API_KEY
  model: glm-4.6
  temperature: 1.0
  max_tokens: 8192
  response_format_json: true
```

### `configs/retries.yaml` —— 可靠性与限流

重试次数与等待时间、请求超时、`concurrency_limit`、调用之间的最小间隔，以及限流退避
乘数。默认值刻意保守（串行执行，约 30 请求/分钟），因此在低配额账户上也是安全的；只有
在确认你的提供方允许更高吞吐量之后，才应调高它们。

### `configs/pipeline.yaml` —— 阶段参数与记忆开关

各阶段的数量（专家数、每位专家的构思数、联盟规模、评审组规模、目标数）以及记忆子系统的
设置，包括各阶段的 `memory.per_stage` 开关。记忆功能默认关闭，需自行开启。

### `configs/agents.yaml`

流水线在启动时加载的智能体注册表（id、stage、substage、prompt、role、schema）。

### 通过 `.env` 提供 API key

```bash
cp .env.example .env
# 然后编辑 .env 并设置你的 key，例如（默认提供方为智谱 GLM）：
#   ZHIPU_API_KEY=...
```

`.env` 被 git 忽略。在 shell 中导出的变量优先级高于 `.env` 中的值。切勿提交真实的 key。

## 快速开始

针对一个问题运行整条流水线：

```bash
python -m cogtide.cli run --topic "How does prior expectation shape perception?"
```

可编辑安装还提供了一个控制台脚本，因此下面的写法等价：

```bash
cogtide run --topic "How does prior expectation shape perception?"
```

Stage 0 默认是交互式的（它会请你确认澄清后的问题）。在自动化运行中添加
`--non-interactive` 可跳过该关卡。

## 运行流水线

### 完整流水线（Stage 0 → Stage 4）

```bash
cogtide run --topic "..."                    # 交互式 Stage 0 关卡
cogtide run --topic "..." --non-interactive  # 跳过关卡
```

每次运行都会打印其 `run_id`；所有产物都落在 `runs/<run_id>/` 下。

### 逐阶段运行

Stage 0 创建运行；此后每个阶段都通过 `run_id` 恢复运行，并假定前序阶段的规范产物
已经存在。

```bash
cogtide stage_00 --topic "..."      # → 打印一个 run_id
cogtide stage_01 --resume <run_id>
cogtide stage_02 --resume <run_id>
cogtide stage_03 --resume <run_id>
cogtide stage_04 --resume <run_id>
```

### 恢复

要完成一次已经有 Stage 0 + Stage 1 产物的运行（运行 Stage 2–4）：

```bash
cogtide resume_pipeline --resume <run_id>
```

（所有命令都可以等价地写作 `python -m cogtide.cli <command> ...`。）

## 使用本地材料运行

要为 Stage 0 提供项目专属的上下文，请将 `.md`、`.txt` 或 `.rst` 文件放入 `question/`
下的一个主题子文件夹：

```
question/
└── expectation-perception/
    ├── notes.md
    ├── prior-work.txt
    └── open-questions.rst
```

当你运行 Stage 0 时，cogTIDE 会扫描 `question/`，寻找名称与你的问题最匹配的子文件夹
（简单的词元重叠匹配）。若找到一个候选，它会请你确认；若有多个匹配，则由你挑选一个。
被确认子文件夹中所有受支持的文件会被拼接在一起（受字符预算限制）并作为背景上下文交给
澄清器。你在 `question/` 下添加的材料被 git 忽略，因此未发表的笔记会留在本地。

## 输出与产物

每次运行都会写入 `runs/<run_id>/`，其中每个阶段一个子目录，外加运行级别的溯源信息：

```
runs/<run_id>/
├── run_meta.json          # run_id、topic、model、解析后的配置
├── artifacts.json         # 规范产物的注册表（血缘/溯源）
├── stage_00/
│   └── question-<slug>-<ts>.json / .md      # QuestionDossier
├── stage_01/
│   └── raw-ideas-<run_id>.json              # 构思 I001…
├── stage_02/
│   ├── idea-peer-reviews.json
│   ├── idea-scorecards.json
│   ├── external-panel-reviews-D*.json
│   └── coalition-deep-theories-<run_id>.json  # 深度理论 D…
├── stage_03/
│   ├── council-kernels-<run_id>.json / .md    # kernel K…
│   └── external-panel-reviews-K*.json
└── stage_04/
    ├── triplet-peer-reviews-K*.json
    ├── triplet-scorecard-K*.json
    └── triplet-theories-<run_id>.json / .md   # 最终理论（5 个三元组）
```

规范产物带有稳定的 ID（构思 `I001…`、深度理论 `D…`、kernel `K…`、最终理论）和血缘
字段（`contributing_idea_ids`、`contributing_deep_theory_ids` 等），因此任何最终理论
都可以经由其所来自的各个阶段回溯。

## 评分、校准与记忆如何运作

每次评审都会收集直接的维度评分（coherence 连贯性、defensibility 可辩护性、novelty
新颖性、distinctiveness 独特性、fertility 衍生力、upside 上行潜力）、**同行预测**
（一位评审者预期其他评审者会说什么）、**存活预测**（一个条目通过下一阶段的概率），
以及高估/低估标记。由这些数据，评分卡推导出若干信号，包括 `quality_score`、
`unexpected_support`（实际减去预测）、`survival_forecast` 和
`calibration_weighted_score`。

随后评审者会在多次运行中被**校准**：

```
calibration_score = 0.5 * quality_calibration + 0.5 * survival_accuracy
weight            = 0.5 + 0.5 * calibration_score      # 夹取到 [0.5, 1.0]
```

更敏锐（校准更好）的评审者在校准加权分数中获得更大的权重。**记忆**子系统（`memory/`）
为每次运行存储一条原始记录、主题快照、项目记忆，以及每次运行/汇总的校准；一个基于
白名单的已学策略叠加层（`memory/learned/active/`）可以在启动时被合并进配置。记忆仅作
参考，且按阶段可选开启。

关于评分、校准与记忆机制的更深入讲解，参见 [HOW_IT_WORKS.md](HOW_IT_WORKS.md)。

## 局限性

- **LLM 幻觉。** 生成的理论、机制与预测可能是编造的、错误的或内部不一致的，也可能
  错误地表述文献。
- **未经验证的假设。** 输出是供专家评审的候选想法，而非经过验证的研究发现；它们没有
  经过经验检验。
- **同行预测并非真值。** 评分与校准信号反映的是*模型生成的评审者之间*的一致程度与预测
  能力，而非科学正确性。
- **对提供方的依赖。** 结果在很大程度上取决于你所配置的模型与提供方；不同的端点和版本
  可能产出实质上不同的理论。
- **非确定性。** 运行是随机的（温度、采样、重试）；重复一次运行不会复现出完全相同的
  输出。
- **成本与延迟。** 一次完整运行会在所有阶段发起大量 LLM 调用，视你的提供方与限流情况，
  可能既慢又昂贵。

## 贡献

欢迎贡献。请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何搭建开发环境、运行测试
（先 `pip install -e ".[dev]"`，再 `pytest`），以及提交 issue 或 pull request。

## 引用

如果你在研究中使用了 cogTIDE，请予以引用。机器可读的元数据位于
[CITATION.cff](CITATION.cff)。一份纯文本 BibTeX 条目（在最终确定后填入 TODO 字段）：

```bibtex
@software{cogtide,
  title   = {cogTIDE: A Peer-Calibrated LLM Pipeline for Auditable Theory
             Generation in Psychology, Cognitive Neuroscience, and Cognitive
             Science},
  author  = {Teng, Xiangbin},
  year    = {2026},
  version = {0.1.0},
  license = {MIT},
  url     = {https://github.com/XBTinChina/CogTIDE},
  note    = {TODO: add DOI once a preprint/archive (e.g. bioRxiv, Zenodo) is minted}
}
```

## 许可证

以 **MIT License** 发布。完整文本见 [LICENSE](LICENSE)。

## 致谢

cogTIDE 构建于更广阔的开源 LLM 与科学 Python 生态之上。TODO: 在公开发布前补充资金来源、
所属机构以及其他任何致谢。
