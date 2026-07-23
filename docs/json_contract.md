# JSON 数据契约

提取层、算法核心、回写层通过两份 JSON 文件交换数据。字段定义以
`src/weld_core/schema.py`（pydantic 模型）为准，本文件为说明。

## 目录清单（跨文件追溯）

业务 JSON 的 `meta.source` 只表示其直接输入；原始零件和运行产物的对应关系以目录清单为准：

```text
raw_data/<part-id>/manifest.json
data/<part-id>/<run-id>/manifest.json
```

原始清单的 `inputs` 按角色登记相对路径、SHA-256 和文件大小。运行清单记录 `part_id`、`run_id`、
原始清单、运行时输入哈希、执行参数、状态和 `artifacts` 路径。路径均为仓库相对路径，不写入本机绝对
路径。`component-simplify` 的 `surface_reference` 是平面提取验证基准，不是算法派生产物。

## plane_validation.json（平面提取正确性验证）

由 `scripts/validate_plane_reference.py <part-id>` 生成。默认比较注册的
`primary_model` STEP 与 `surface_reference`；使用 `--faces` 可验证 CATIA 完整流程的
`faces.enriched.json`。结果在独立运行目录中登记为 `plane_validation` 与
`plane_validation_report` 两个产物。

- `summary`：算法/参考平面数量、TP/FP/FN、precision、recall 与通过状态；仅 precision 和
  recall 都为 100% 才通过。
- `algorithm_faces` / `reference_faces`：逐面几何、所有多对多匹配及误差。
- `false_positive_faces` / `false_negative_faces`：待复核的额外算法平面与未检出的参考平面。

## faces.json（提取层输出 → 核心输入）

| 字段 | 类型 | 说明 |
|---|---|---|
| `meta.part` | str | 零件/文档名 |
| `meta.unit` | str | 单位，固定 `mm` |
| `meta.extractor_version` | str | 提取器版本 |
| `meta.context` | `part`/`product` | 提取语境（product 用 InContext 测量） |
| `meta.warnings` | str[] | 自检告警，如多实例/重名 |
| `faces[].id` | str | 唯一标识，如 `PartA/Body1/face_3` |
| `faces[].part` / `body` | str | 所属零件 / Body |
| `faces[].surface_type` | `planar`/`non_planar` | V1 只处理 planar |
| `faces[].area` | float | 面积 mm² |
| `faces[].normal` | [x,y,z] | 单位法向，**方向不保证**（比较忽略正负） |
| `faces[].plane_origin` | [x,y,z] | 平面上一点 |
| `faces[].centroid` | [x,y,z] | 重心 |
| `faces[].vertices` | [[x,y,z]…] | 顶点，用于算投影 2D AABB，可能为空；CATIA COM 逐面提取不可靠（见 DEVLOG），实际由 `scripts/enrich_faces_with_step.py` 离线解析同一文档的 STEP 导出补全，顶点顺序不保证、已按容差去重 |
| `faces[].manual_review` | bool | 曲面/顶点不足等置 true |
| `faces[].reason` | str | manual_review 原因 |

## candidates.json（核心输出 → 回写层输入）

| 字段 | 类型 | 说明 |
|---|---|---|
| `meta.source` | str | 来源零件名 |
| `meta.core_version` | str | 核心版本 |
| `meta.params` | obj | 本次运行的阈值参数 |
| `meta.selection_source` | obj | 可选追溯信息；当输入是受管 `faces.general-selected.json` 时，记录 `kind="general_planar_selection"`、`part_id`、`run_id`、`faces_artifact` 和通用选面 `parameters`，不包含评测参考、旧资产哈希或样本标签 |
| `candidates[].id` | str | 如 `wc_001` |
| `candidates[].position` | [x,y,z] | 建点坐标（中间厚度） |
| `candidates[].faces` | str[] | 关联面 id |
| `candidates[].layer_type` | `two_layer`/`three_layer` | 层数分类；V1 恒为 `two_layer`（按两张贴合面配对生成，三层板自动识别/合并未实现，见 DEVLOG） |
| `candidates[].spacing_mm` | float | 点间距 |
| `candidates[].region_bbox` | {min,max} | 候选区域包围盒 |
| `candidates[].reason` | str | 生成原因 |

## faces.general-selected.json（通用选面 → 核心输入）

由 `scripts/select_general_planes.py <part-id>` 生成，schema 仍是 `FacesDocument`，可直接作为
`python -m weld_core.pipeline` 输入。它只包含通过至少一个有效通用 face pair 支持的单个 planar
CAD face；`faces[].reason` 固定为 `generic_planar_selection`。运行时输入只来自 raw manifest
中的 `primary_model`。

## pair_audit.json（通用选面 pair 审计）

| 字段 | 类型 | 说明 |
|---|---|---|
| `format_version` | int | 当前为 1；新增字段保持向后兼容 |
| `part_id` / `run_id` | str | 所属受管运行 |
| `parameters` | obj | 通用选面阈值 |
| `pairs[].id` | str | `face_a_id::face_b_id` |
| `pairs[].accepted` / `reason` | bool / str? | pair 是否通过及拒绝原因 |
| `pairs[].normal_angle_deg` / `plane_gap_mm` | float? | 无向法向夹角和平面间隙 |
| `pairs[].gap_layer` | `strict`/`extended`/`beyond_extended`/null | 审计层：gap≤0.2 mm 为 `strict`，0.2<gap≤1.5 mm 为 `extended`，更大值为 `beyond_extended`；未量得 gap 时为 null。当前跨件生产默认的最大 gap 是 1.5 mm；该标签本身不改变阈值。 |
| `pairs[].aabb_overlap_width_mm` / `aabb_overlap_height_mm` | float? | 投影 AABB 预筛重叠尺寸 |
| `pairs[].common_area_mm2` | float | 精确投影公共面积 |
| `pairs[].coverage_a` / `coverage_b` | float | 双方覆盖率 |
| `pairs[].score` | float | 通用排序分数 |

## selection_audit.json（通用选面 face 审计）

| 字段 | 类型 | 说明 |
|---|---|---|
| `source.role` | str | 固定为 `primary_model` |
| `parameters` | obj | 通用选面阈值 |
| `total_planar_faces` / `selected_face_count` | int | 可处理平面数 / 选中面数 |
| `selected_faces[].face_id` | str | 选中的主 STEP CAD face |
| `selected_faces[].supporting_pair_ids` | str[] | 支持该 face 的有效 pair |
| `selected_faces[].supporting_pair_gap_layers` | obj[] | 每个 supporting pair 的 `pair_id` 与 `gap_layer`，用于在不读取离线评测数据的前提下追溯其 gap 审计层。 |
| `rejected_faces[].face_id` / `reason` | str | 未选中 face 及原因 |

## general_plane_selection_aabb_diagnosis.json（离线 AABB 复核）

由 `scripts/diagnose_general_plane_selection_aabb.py` 生成。它重新加载仅登记的 `primary_model`，对
`pair_audit.json` 中的 `projected_aabb_no_overlap` pair 跳过顶点 AABB 预筛执行精确投影 overlap；不读取
reference/truth，且绝不改变生产选面行为。`pairs[]` 包含 pair/端点/part、`plane_gap_mm`、精确公共面积和
双方 coverage、`exact_reason`、`prefilter_input_status`，以及 `review_status`：`true_no_overlap`、
`prefilter_false_rejection` 或 `projection_or_geometry_failure`。该报告只证明此单次离线复核的结果，不能外推。

## general_plane_selection_same_part_evaluation.json（离线同件风险）

由 `scripts/evaluate_general_plane_selection_same_part.py` 从受管参数扫描生成。它只比较固定的 1.5 mm、
coverage=0.05 条件下 same-part 关闭（生产护栏）与开启（离线实验）的 TP/FP/FN 和 precision/recall；
报告不是生产输入，`production_guardrail.allow_same_part_pairs` 固定为 false，且结论不代表跨零件泛化。

## general_plane_selection_error_analysis.json（离线误差分析）

由 `scripts/analyze_general_plane_selection_errors.py` 生成。它读取显式离线 evaluation/truth 和选择审计，不能被生产 selector、pipeline 或候选生成消费。使用 `--baseline-run-dir <0.2-mm-run>` 对 1.5 mm、same-part 关闭的候选运行做比较时，报告额外包含 `expanded_gap_false_positive_attribution`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `comparison.baseline_false_positives` / `candidate_false_positives` | int | 0.2 mm 基线与 1.5 mm 候选的 FP 数 |
| `comparison.inherited_false_positives` / `new_false_positives` | int | 候选 FP 中按 source face ID 继承/新增的数量 |
| `false_positives[].attribution` | `inherited`/`new` | 同一 source face 已在基线 FP 中则为 inherited，否则为 new |
| `false_positives[].supporting_pairs[]` | obj[] | 每个支持 pair 的 `gap_layer`、公共面积、双方 coverage、score、对侧 part 与离线 truth 关系 |

该比较仅适用于明确给定的单数据集离线运行，不构成跨零件泛化结论；当前生产默认最大跨件 gap 是 1.5 mm，same-part pair 仍关闭。

## general_plane_selection_evaluation.json（离线参考评测）

由 `scripts/evaluate_general_plane_selection.py` 生成。该文件只属于离线评测阶段：输入必须显式给出
参考 STEP 或从 raw manifest 读取 `surface_reference`，输出不得作为生产选面配置或 pipeline 输入。

| 字段 | 类型 | 说明 |
|---|---|---|
| `thresholds` | obj | 参考映射阈值：法向、平面距离、source/reference 覆盖率 |
| `truth_mapping.summary` | obj | 参考 face 到主 STEP face 的唯一映射统计和通过状态 |
| `truth_mapping.reference_faces[]` | obj[] | 每个参考 face 的候选 source face、几何证据和失败原因 |
| `summary.true_positives` / `false_positives` / `false_negatives` | int | face-level 指标 |
| `summary.precision` / `recall` | float | face-level 精确率和召回率 |
| `true_positive_faces` / `false_positive_faces` / `false_negative_faces` | obj[] | 逐 face 诊断 |

## ground_truth.json（真实焊点，评测用 → 核心输入）

由 `scripts/extract_ground_truth.py` 离线解析焊点标记球 STEP 文件（如 `raw_data/component/SPOT.step`）
产出，不需要 CATIA 运行；解析逻辑见 `weld_core.step_geometry.parse_step_spheres`
（每个真实焊点在这类文件里以一个 r=3mm 的球标记，球被导出成 2 个半球面，
按球心去重合并成 1 个点）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `meta.source` | str | 标记球 STEP 文件路径 |
| `meta.unit` | str | 单位，固定 `mm` |
| `points[].id` | str | 如 `gt_001` |
| `points[].position` | [x,y,z] | 球心坐标（真实焊点位置），与 `candidates.json` 同一全局坐标系 |
| `points[].radius` | float | 标记球半径 mm（信息性，不参与匹配） |
| `points[].label` | str | STEP 里的实例名（如 `04021210-R60_WP`）；**不对应真实装配体的 PartNumber**，只作追溯用，不能用于匹配 |

## evaluation.json（评测结果，`weld_core.evaluate` 输出）

将 `ground_truth.json` 与某次 `candidates.json` 按 3D 距离做一对一贪心匹配（每对
候选按距离从近到远认领，任一方被认领后不再参与后续匹配），距离超过容忍度
阈值（`--tolerance`，单位 mm）不算匹配。V1 以"不漏检"为先，`recall`（真实焊点的
命中率）是首要指标，`precision`（候选点里有多少是有效的）次要——多余候选交给
人工复核，不算失败。

| 字段 | 类型 | 说明 |
|---|---|---|
| `meta.ground_truth_source` / `candidates_source` | str | 两份输入文件路径 |
| `meta.tolerance_mm` | float | 本次评测用的容忍度阈值 |
| `summary.true_positives` | int | 命中的真实焊点数 |
| `summary.false_negatives` | int | 漏检的真实焊点数（容忍度内找不到候选） |
| `summary.false_positives` | int | 多余候选数（容忍度内没有对应真实焊点） |
| `summary.recall` / `precision` | float | `TP/(TP+FN)` / `TP/(TP+FP)` |
| `summary.mean_error_mm` / `max_error_mm` | float | 命中的匹配对里，候选点到真实焊点的距离统计 |
| `matches[].ground_truth_id` / `candidate_id` / `distance_mm` | — | 每一对命中的匹配详情 |
| `unmatched_ground_truth` / `unmatched_candidates` | str[] | 漏检的真实焊点 id / 多余候选 id 列表 |
