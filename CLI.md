# CLI.md — 命令行工具一览

本文件列出项目当前提供的全部命令行入口：代码路径、输入/输出、用途。按 pipeline 顺序排列
（环境检查 → 提取 → 核心算法 → 回写 → 一键编排 → 评测）。业务背景见 `PLAN.md`，
数据格式定义见 `docs/json_contract.md`，踩坑记录见 `DEVLOG.md`。

所有命令均在项目根目录、激活 `.venv` 后运行（Windows：`.venv\Scripts\python.exe ...`）。
标注 **[需 CATIA]** 的命令必须在 Windows、CATIA V5 已打开且目标文档处于激活状态时运行；
其余命令纯离线（Python + numpy / OCP），不需要 CATIA。

## 仓库目录结构与职责

以下为当前仓库的顶层目录结构。目录中的运行产物、CAD 输入和本地环境受 `.gitignore`
管理；`data/` 与 `raw_data/` 中的 `manifest.json` 例外，会保留在仓库中用于记录数据来源和运行契约。

```text
test-catia/
├── .agents/                 # Agents-first 工作流的本地状态预留目录（当前为空）
├── .claude/                 # Claude Code 本地配置；不纳入版本控制
├── .git/                    # Git 版本库元数据
├── .pytest_cache/           # pytest 缓存；可随时重新生成
├── .venv/                   # 项目本地 Python 虚拟环境
├── catia/                   # CATIA V5 / pycatia 集成：提取、STEP 导出和候选点回写
├── data/                    # 按 data/<part-id>/<run-id>/ 存放受管流水线、评测和诊断产物
├── docs/                    # 长期项目文档、算法说明、数据契约和待办项
├── logs/                    # 本地运行日志与性能日志；不纳入版本控制
├── raw_data/                # 原始 CAD/STEP 输入，按 raw_data/<part-id>/ 管理，并以 manifest 登记
├── scripts/                 # 可直接执行的 CLI：环境检查、编排、离线分析、评测、ANSA 工具和打包
├── src/
│   └── weld_core/           # 平台无关的核心 Python 包：几何、选面、候选生成、评测和数据契约
├── templates/               # 面向特定数据集/流程的可复用模板目录
└── tests/                   # pytest 自动化测试与 fixtures 测试数据
```

根目录中的 `CLI.md` 是本命令索引；`CLAUDE.md` 是唯一的 Agent 工作指南，`AGENTS.md` 仅链接至该指南；
`DEVLOG.md` 记录近期变更与验证结果。`README.md` 提供项目概览，`RESULT.md` 汇总当前结果；
`pyproject.toml`、`requirements*.txt` 与 `environment*.yml` 用于定义 Python 包和环境依赖。

| 命令 | 代码路径 | 需 CATIA | 输入 | 输出 |
|---|---|:---:|---|---|
| [环境检查（核心）](#环境检查核心) | `scripts/check_env_core.py` | 否 | 无 | 终端提示 |
| [环境检查（CATIA）](#环境检查catia) | `scripts/check_env_catia.py` | 是 | 无 | 终端提示 |
| [提取面数据](#提取面数据) | `catia/extract_faces.py` | 是 | 激活的 CATIA 文档 | `faces.json` |
| [导出 STEP](#导出-step) | `catia/export_step.py` | 是 | 激活的 CATIA 文档 | `*.stp` |
| [用 STEP 补全顶点](#用-step-补全顶点) | `scripts/enrich_faces_with_step.py` | 否 | `faces.json` + `*.stp` | `faces.enriched.json` |
| [验证平面提取](#验证平面提取) | `scripts/validate_plane_reference.py` | 否 | 注册 STEP + 平面参考 | 受管运行目录内 JSON/报告 |
| [通用平面选面](#通用平面选面) | `scripts/select_general_planes.py` | 否 | 注册主 STEP | `faces.general-selected.json` + 审计 |
| [离线评测通用选面](#离线评测通用选面) | `scripts/evaluate_general_plane_selection.py` | 否 | 主 STEP + 显式参考 STEP + 通用选面结果 | 受管运行目录内 JSON/报告 |
| [复核通用选面 AABB 拒绝](#复核通用选面-aabb-拒绝) | `scripts/diagnose_general_plane_selection_aabb.py` | 否 | 主 STEP + pair 审计 | 受管运行目录内离线诊断 JSON |
| [评估通用选面同件风险](#评估通用选面同件风险) | `scripts/evaluate_general_plane_selection_same_part.py` | 否 | 离线参数扫描 | 受管运行目录内 JSON/报告 |
| [通用选面回归](#通用选面回归) | `scripts/run_general_plane_selection_regression.py` | 否 | 注册主 STEP + 显式评测参考 | 通用选面、评测、候选产物 |
| [运行核心算法](#运行核心算法) | `python -m weld_core.pipeline` | 否 | `faces.enriched.json` | `candidates.json` |
| [回写候选点到 CATIA](#回写候选点到-catia) | `catia/write_candidates.py` | 是 | `candidates.json` | CATIA 文档内 `Weld_Candidates` 点集 |
| [一键端到端](#一键端到端) | `scripts/run_full_pipeline.py` | 是 | 激活的 CATIA 文档 + 原始清单 | 一个受管运行目录（可选回写） |
| [提取真实焊点](#提取真实焊点) | `scripts/extract_ground_truth.py` | 否 | 焊点标记 STEP（如 `raw_data/component/SPOT.step`） | 运行目录内 `ground_truth.json` |
| [评测候选点](#评测候选点) | `python -m weld_core.evaluate` | 否 | `ground_truth.json` + `candidates.json` | `evaluation.json` |
| [构建焊点 operating frontier](#构建焊点-operating-frontier) | `scripts/build_operating_frontier.py` | 否 | 已完成候选运行 + 显式评测产物 | `operating_frontier.json/.md` |

---

## 环境检查（核心）

**代码路径**：`scripts/check_env_core.py`

**用途**：验证 `weld_core` 相关的纯 Python 依赖（numpy/pydantic）装好了，且 schema
可以正常序列化/反序列化。跨平台，不需要 CATIA、不需要 Windows——用于确认"核心算法层
可以脱离 CATIA 独立跑"这条架构约束（见 `CLAUDE.md`）。

**输入**：无。

**输出**：终端打印 `[OK]`/`[FAIL]`，退出码 0/1。不产生文件。

```bash
python scripts/check_env_core.py
```

---

## 环境检查（CATIA）

**代码路径**：`scripts/check_env_catia.py`

**用途**：验证 `pycatia`/`pywin32` 装好了，且能连接到一个正在运行的 CATIA V5 会话。
在改动任何 `catia/` 下的脚本后，先跑这个确认环境可用，再用真实零件验证（见 `CLAUDE.md`
"验证"章节）。

**输入**：无（隐式依赖：一个已打开的 CATIA V5 进程）。

**输出**：终端打印 `[OK]`/`[FAIL]`，退出码 0/1。不产生文件。

```bash
python scripts/check_env_catia.py
```

---

## 提取面数据

**代码路径**：`catia/extract_faces.py`

**用途**：Phase 1 提取层。通过 pycatia COM 遍历当前激活文档（Part 或 Product）的全部面，
读取每个面的所属零件号、面积、法向、平面判定、重心，写成 `faces.json`。**顶点字段恒为空**
（`Selection.Search` 按面作用域枚举顶点在这套环境里不可靠，已验证坐实，见 DEVLOG）——
顶点由下一步"用 STEP 补全顶点"单独解决，不在这一步。

**输入**：一个已在 CATIA 里打开并激活的 Part/Product 文档（隐式，通过 COM 读取当前
`active_document`）。

**输出**：`faces.json`（`weld_core.schema.FacesDocument`，字段见 `docs/json_contract.md`）
+ 一份运行性能日志（`logs/extract_faces_*.log`，含耗时/吞吐/告警计数，已 gitignore）。

```bash
python catia/extract_faces.py data/component/<run-id>/faces.json [--part-number NAME] [--limit N]
```
- `--part-number`：只提取指定零件号的面（Product 语境下有效）。
- `--limit`：处理到达该数量后提前停止（用于快速试跑）。

---

## 导出 STEP

**代码路径**：`catia/export_step.py`

**用途**：把当前激活文档通过 `Document.ExportData` 导出成中性交换格式 STEP，供离线的
`enrich_faces_with_step.py`/`step_geometry.py` 解析真实顶点用。**注意**：STEP 是中性交换
格式，不携带 CATIA 原生 feature 树/对象名字/参数——只用它做几何解析，不要用它做"保存工作
成果给同事看"（那种场景要用原生 `Document.SaveAs` 存 `.CATProduct`/`.CATPart`，见 DEVLOG
2026-07-16）。硬编码 `.stp` 扩展名+`"stp"`格式字符串（`.step`/`"step"`组合在这套环境里
验证会报错，见脚本内注释）。

**输入**：一个已在 CATIA 里打开并激活的文档（隐式，通过 COM 读取当前 `active_document`）。

**输出**：`<output>.stp`（体积随装配体大小，真实装配体约 200MB 量级，已在 `.gitignore`）
+ 一份运行日志（`logs/export_step_*.log`，含导出耗时）。

```bash
python catia/export_step.py data/component/<run-id>/component.stp
```

---

## 用 STEP 补全顶点

**代码路径**：`scripts/enrich_faces_with_step.py`（核心解析逻辑在
`src/weld_core/step_geometry.py::parse_step_faces`，纯 OCP，不依赖 pycatia）

**用途**：Phase 1.5，补上"提取面数据"步骤里恒为空的 `vertices` 字段。离线解析同一文档
导出的 STEP 文件（`STEPCAFControl_Reader` + XCAF 装配树遍历，顶点用最小二乘平面拟合判
平面性，因为 STEP 导出会丢失 `GeomAbs_Plane` 类型信息，细节见模块内 docstring 与 DEVLOG），
按"重心距离 + 法向夹角 + 面积相对误差"把每个 COM 提取的平面面匹配到对应的 STEP 面，
匹配成功则填入顶点并清除 `manual_review`；匹配失败/STEP 判非平面的保留
`manual_review=True` 并写明原因。

**输入**：`faces.json`（上一步 COM 提取产物）+ 同一文档导出的 `*.stp`。

**输出**：`faces.enriched.json`（同样是 `FacesDocument`，`vertices`/`manual_review`/`reason`
字段被更新）+ 运行日志（`logs/enrich_faces_with_step_*.log`，含匹配率统计，按零件分组）。

```bash
python scripts/enrich_faces_with_step.py data/component/<run-id>/faces.json data/component/<run-id>/component.stp data/component/<run-id>/faces.enriched.json
```

---

## 验证平面提取

**代码路径**：`scripts/validate_plane_reference.py`（核心比较逻辑在
`src/weld_core/plane_validation.py`，纯 Python/OCP，不依赖 CATIA）

**用途**：将注册的主模型 STEP 中算法判定的平面与 `surface_reference` 中的真实平面做双向
比较。匹配要求零件号相同、无向法向夹角 ≤0.1°、平面距离 ≤0.02mm，且投影边界 AABB 有
正面积重叠；支持不同 STEP 导出造成的一对多/多对一面切分。运行创建一个受管目录，写入
`plane_validation.json`（逐面匹配、TP/FP/FN、precision/recall）和 Markdown 报告；只有
precision 与 recall 都为 100% 才返回成功。

```bash
python scripts/validate_plane_reference.py component-simplify
```

完成 CATIA 一键流程后，可用其 `faces.enriched.json` 复核运行时平面分类，并把报告写回同一运行目录：

```bash
python scripts/validate_plane_reference.py component-simplify --faces data/component-simplify/<run-id>/faces.enriched.json --run-dir data/component-simplify/<run-id>
```

## 通用平面选面

**代码路径**：`scripts/select_general_planes.py`（核心逻辑在
`src/weld_core/general_plane_selection.py`，纯 OCP，不依赖 pycatia）

**用途**：只读取 raw manifest 中登记的 `primary_model`，从任意受支持主 STEP 解析平面 CAD face，
按跨 part 策略、无向法向夹角、平面间隙、投影 AABB 预筛、精确投影公共面积和双向覆盖率选出
可能参与焊接的单个 face。运行时不会读取人工参考 STEP，也不会按 part id、主 STEP 哈希、已知
面数或人工标签改变选面结果。

**输出**：新建 `data/<part-id>/<run-id>/`，包含：

- `faces.general-selected.json`：可直接交给 `python -m weld_core.pipeline` 的通用 `FacesDocument`。
- `pair_audit.json`：每个候选 face pair 的接受/拒绝原因及几何测量；`gap_layer` 将 gap≤0.2 mm 标为 `strict`、0.2<gap≤1.5 mm 标为 `extended`、更大间隙标为 `beyond_extended`。标签只用于审计，不会改写当前默认 gap。
- `selection_audit.json`：每个选中 face 的支持 pair 及其 `supporting_pair_gap_layers`、每个未选中 face 的原因、阈值和输入来源。
- `manifest.json`：只登记 `primary_model` 运行时输入和通用选面参数。

```bash
python scripts/select_general_planes.py component-simplify --run-label generic-regression
```

---

## 离线评测通用选面

**代码路径**：`scripts/evaluate_general_plane_selection.py`

**用途**：仅在显式评测阶段读取参考 STEP，把参考 face 用 part、无向法向、平面距离和精确投影
公共面积映射回主 STEP face，再对 `faces.general-selected.json` 计算 TP/FP/FN、precision/recall
和逐 face 诊断。参考映射无法唯一成立时评测失败，不自动猜测。

```bash
python scripts/evaluate_general_plane_selection.py component-simplify --run-dir data/component-simplify/<run-id>
```

## 复核通用选面 AABB 拒绝

**代码路径**：`scripts/diagnose_general_plane_selection_aabb.py`

**用途**：离线重新加载已登记的主 STEP，对既有 `pair_audit.json` 中
`projected_aabb_no_overlap` 的 pair 绕过顶点 AABB 预筛执行精确 CAD 边界 overlap。报告将每项归为
真实无重叠、预筛假拒绝或投影/几何失败，并登记到受管 manifest。它不读取 reference/truth，不能改变
运行时选择结果；单数据集诊断也不能证明跨零件泛化。

```bash
python scripts/diagnose_general_plane_selection_aabb.py component-simplify --run-dir data/component-simplify/<run-id>
```

## 评估通用选面同件风险

**代码路径**：`scripts/evaluate_general_plane_selection_same_part.py`

**用途**：从已生成的离线参数扫描中固定提取 1.5 mm / coverage=0.05 的 same-part 关闭和开启实验，
形成单独的 FP 风险证据。报告绝非运行时输入，生产 `allow_same_part_pairs` 仍固定关闭；结果只限该离线数据集。

```bash
python scripts/evaluate_general_plane_selection_same_part.py component-simplify --run-dir data/component-simplify/<run-id>
```

---

## 通用选面回归

**代码路径**：`scripts/run_general_plane_selection_regression.py`

**用途**：离线串联“通用平面选面 → 离线评测通用选面 → 运行核心算法”。该命令用于数据集回归，
其中选面和 pipeline 仍不接收参考 STEP；参考 STEP 只由中间的显式评测命令读取。

```bash
python scripts/run_general_plane_selection_regression.py component-simplify --run-label generic-regression
```

默认跨件 `max_plane_gap_mm` 为 1.5 mm；`allow_same_part_pairs` 默认且必须保持关闭。该默认的
`component-simplify` 受管离线证据为 TP/FP/FN=30/6/10、precision 83.33%、recall 75.00%，达到
本项目的单数据集质量门槛。此命令中的选面和 pipeline 不读取参考 STEP/truth；它们仅由中间的
显式离线评测读取。该结果不能作为未知零件能力或跨零件泛化声明；至少两个未参与阈值设定的独立
验证零件分别达标后，才可对外报告初步跨零件能力。

---

## 运行核心算法

**代码路径**：`src/weld_core/pipeline.py`（编排 `pairing.py`/`region.py`/`points.py`/
`filtering.py`）

**用途**：Phase 2 算法核心。纯 Python + numpy，不依赖 pycatia/pywin32，可脱离运行中的
CATIA 独立跑（也是 `pytest` 覆盖的部分）。从已补全顶点的面数据里：按法向夹角 ≤5°/面间距
≤0.1mm/投影包围盒重叠找候选贴合面对 → 取重叠区域中点作为焊接厚度方向位置 → 按
20~70mm 间距布点 → 过滤明显不合理的候选（不在区域内/相距过近）。候选 id（`wc_NNN`）
按内容（关联面 id + 坐标）排序后编号，不依赖输入顺序，保证跨会话重跑时同一个物理候选点
拿到同一个 id（供回写层按 id 做增量更新，见 DEVLOG）。

**输入**：任意符合契约的 `FacesDocument`，典型输入为 `faces.enriched.json` 或
`faces.general-selected.json`。核心只使用
`surface_type=="planar"`、`manual_review==False` 且 `vertices` 非空的面；是否来自受管运行目录
不改变算法行为。

**输出**：`candidates.json`（`weld_core.schema.CandidatesDocument`，字段见
`docs/json_contract.md`）。

```bash
python -m weld_core.pipeline data/component/<run-id>/faces.enriched.json data/component/<run-id>/candidates.json
```

---

## 回写候选点到 CATIA

**代码路径**：`catia/write_candidates.py`

**用途**：Phase 3 回写层。把 `candidates.json` 里的候选点在当前激活文档的根 Product 下
建成一个 `Weld_Candidates` Part 组件（含同名 `HybridBody`），每个候选建成一个真实的
`HybridShapePointCoord`，点名即候选 id，附带一条同名 `_info` 字符串参数记录关联面/层数
分类/间距/生成原因。**重复运行是幂等的、原地更新**：已存在的点直接改坐标参数值（不删除
重建——`Selection.Delete`/`Products.remove`+`Document.close` 在这套 CATIA/pycatia 环境
里均被验证不可靠，细节见脚本内 docstring 与 DEVLOG），本轮消失的候选不删除，只在其
`_info` 参数前加 `STALE` 前缀标记。

**输入**：`candidates.json` + 一个已在 CATIA 里打开并激活的 Product 文档（候选点坐标
假定与该文档的全局坐标系一致，回写前会校验新建组件的放置矩阵是单位阵）。

**输出**：修改当前激活的 CATIA 文档（内存中，需要用户自己 Save/SaveAs 落盘）；终端打印
本次新建/更新/新标记 stale 的点数。

```bash
python catia/write_candidates.py data/component/<run-id>/candidates.json
```

---

## 一键端到端

**代码路径**：`scripts/run_full_pipeline.py`

**用途**：Phase 4 编排脚本，把上面"提取面数据→导出 STEP→用 STEP 补全顶点→运行核心算法→
（可选）回写候选点到 CATIA"这条完整链路串成一次调用，复用各阶段已验证的独立实现（不重复
造轮子）。默认只读 CATIA（提取+导出）、只写本地文件，不碰当前打开的文档；传 `--write` 才
会在最后一步真正回写进 CATIA。

**输入**：一个已在 CATIA 里打开并激活的文档（隐式）。

**输出**：自动创建 `data/<part-id>/<run-id>/`，包含 `component.stp`、`faces.json`、
`faces.enriched.json`、`candidates.json`、`run.log` 和 `manifest.json`；传 `--write` 时额外
回写进当前 CATIA 文档，传 `--save-native` 时保存原生文件到 `native/`。

```bash
python scripts/run_full_pipeline.py component --run-label full [--write] [--save-native] [--part-number NAME] [--limit N]
```

---

## 提取真实焊点

**代码路径**：`scripts/extract_ground_truth.py`（核心解析逻辑在
`src/weld_core/step_geometry.py::parse_step_spheres`）

**用途**：Phase 5 评测能力的第一步——把"真实焊点在哪里"变成结构化数据。真实焊点不是
装配体自身几何的一部分，而是单独用小球（半径 3mm）标记出来的（如 `raw_data/component/SPOT.step`）。
纯离线解析：按 OCCT 解析出的球面类型（`GeomAbs_Sphere`，这个类型信息在 STEP 里是保真的，
不像平面那样会丢失）找到全部标记球面，每个真实焊点被导出成 2 个半球面，按球心距离
（容差 0.5mm）合并去重成 1 个点。**注意**：标记球的 STEP 实例名（如
`04021210-R60_WP`）不是真实装配体的 PartNumber，只作追溯参考，不能用于按零件匹配。

**输入**：焊点标记球 STEP 文件（如 `raw_data/component/SPOT.step`）。

**输出**：`ground_truth.json`（`weld_core.schema.GroundTruthDocument`，字段见
`docs/json_contract.md`）。

```bash
python scripts/extract_ground_truth.py raw_data/component/SPOT.step data/component/<run-id>/ground_truth.json
```

---

## 评测候选点

**代码路径**：`src/weld_core/evaluate.py`

**用途**：Phase 5 评测核心——回答"算法生成的候选焊点，有没有对上真实焊点"。纯
Python/numpy，不依赖 pycatia。做法：把每个真实焊点和每个候选点的 3D 距离算出来，只保留
距离 ≤ 容忍度阈值（`--tolerance`，单位 mm）的配对，按距离从近到远贪心做一对一匹配
（每对配对被认领后，双方都不再参与后续匹配——这是点集检测评测的标准近似算法，规模上
和精确最优分配不会产生分歧，细节见模块 docstring）。V1 的设计原则是"尽量不漏检"（见
`PLAN.md`），所以**召回率（recall）是首要指标**，精确率（precision）次要——多余的候选点
本来就是要交给人工复核的，不算失败。

**输入**：`ground_truth.json`（真实焊点，来自"提取真实焊点"这一步）+ `candidates.json`
（算法产出的候选点，来自"运行核心算法"这一步）。**前提**：两者必须是同一装配体、同一
全局坐标系下的数据——用前建议先核对两者的坐标 bbox 是否重合（见 DEVLOG 2026-07-17）。

**输出**：`evaluation.json`（`weld_core.schema.EvaluationDocument`）+ 终端打印的汇总报告
（含逐个漏检真实焊点的坐标/标签，便于按零件排查漏检是否集中在特定区域）。

```bash
python -m weld_core.evaluate data/component/<run-id>/ground_truth.json data/component/<run-id>/candidates.json data/component/<run-id>/evaluation.json --tolerance 10
```
- `--tolerance`：匹配容忍度，单位 mm，默认 10mm。不传时用这个默认值；容忍度设置需结合
  "焊点定位精度要求"和"20mm 最小点间距"来定——容忍度远小于 20mm 才不会让两个相邻的真实
  焊点抢同一个候选点。

### 评测指标说明（indicators）

`evaluation.json` 的 `summary` 字段：

| 字段 | 含义 |
|---|---|
| `num_ground_truth` / `num_candidates` | 真实焊点总数 / 候选点总数 |
| `true_positives`（TP） | 命中的真实焊点数：容忍度内找到了对应候选点 |
| `false_negatives`（FN） | **漏检**的真实焊点数：容忍度内没有任何候选点——V1 最关心的失败模式 |
| `false_positives`（FP） | **多余**候选点数：容忍度内没有对应任何真实焊点——交给人工复核，不算严重失败 |
| `recall` = TP/(TP+FN) | 召回率，**首要指标**：真实焊点里有多少被找到了 |
| `precision` = TP/(TP+FP) | 精确率，次要指标：候选点里有多少是有效的 |
| `mean_error_mm` / `max_error_mm` | 命中的匹配对里，候选点到真实焊点的距离均值/最大值——衡量"找到了但准不准" |

**真实数据基准**（2026-07-17，现归档为 `raw_data/component/SPOT.step` 解析出的 286 个真实焊点 vs
`data/component/legacy-20260717-e2e/candidates.json` 的 200 个候选点，同一装配体、坐标系已核对一致，
详见 DEVLOG 同日条目）：

| 容忍度 | recall | precision | mean_error_mm | max_error_mm |
|---|---|---|---|---|
| 5mm | 6.6% | 9.5% | 2.081 | 4.925 |
| 10mm | 22.7% | 32.5% | 6.345 | 9.987 |
| 15mm | 39.2% | 56.0% | 8.759 | 14.902 |
| 20mm（≈最小点间距上限） | 48.3% | 69.0% | 10.329 | 19.095 |
| 30mm | 54.9% | 78.5% | 11.988 | 28.680 |

**解读**：即使把容忍度放宽到接近 20mm 的点间距设计上限，recall 也只能到 ~50%——约一半
真实焊点在任何合理容忍度下都找不到邻近候选点。这不是容忍度选择的问题，是当前配对/布点
阈值（法向夹角 ≤5°、面间距 ≤0.1mm、点间距 20~70mm 等，见 `src/weld_core/config.py`）
产出的候选点位置和真实焊点位置系统性对不上，与"V1 不漏检为先"的目标有明显差距，是否
调参/改进算法待产品侧决策（见 PLAN.md P5、DEVLOG 2026-07-17）。

---

## 构建焊点 operating frontier

**代码路径**：`scripts/build_operating_frontier.py`

**用途**：在显式离线评测阶段发布固定候选顺序的每个非空前缀 `K`。报告同时保留全量
286 真值的 TP/FP/FN、precision/recall 与距离统计，以及 planar-supported 子集的 TP/FN、
recall 与距离统计；`K*` 仅表示首个达到 80% planar-supported recall 的评测前缀，绝不能写回
生产预算、阈值或 CATIA 回写。

**前提**：候选运行已经完成，并已由显式评测命令生成 `ground_truth.json` 和
`planar_truth_adjudication.json`。该命令读取它们是合理的，因为它本身是 evaluation-only；生产
selector、布局、pipeline 和 CATIA 写回不得调用它或读取其输出。

```bash
python scripts/build_operating_frontier.py --run-dir data/component-weld-evaluation/<run-id>
```

输出为运行目录中的 `operating_frontier.json` 和 `operating_frontier.md`。JSON 记录全部前缀、
Pareto 支配见证和候选 ID 池；只有两个排序的 ID 池完全一致时，才允许在相同 `K` 比较它们的
precision 或 planar-supported TP。

对于 RW01 冻结的既有观察值，使用不会重放旧输入的历史入口：

```bash
python scripts/build_operating_frontier.py --run-dir data/component-weld-evaluation/20260724-162131-pw06-planar-optimization --historical-only
```
