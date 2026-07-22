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
| `candidates[].id` | str | 如 `wc_001` |
| `candidates[].position` | [x,y,z] | 建点坐标（中间厚度） |
| `candidates[].faces` | str[] | 关联面 id |
| `candidates[].layer_type` | `two_layer`/`three_layer` | 层数分类；V1 恒为 `two_layer`（按两张贴合面配对生成，三层板自动识别/合并未实现，见 DEVLOG） |
| `candidates[].spacing_mm` | float | 点间距 |
| `candidates[].region_bbox` | {min,max} | 候选区域包围盒 |
| `candidates[].reason` | str | 生成原因 |

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
