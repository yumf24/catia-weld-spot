# JSON 数据契约

提取层、算法核心、回写层通过两份 JSON 文件交换数据。字段定义以
`src/weld_core/schema.py`（pydantic 模型）为准，本文件为说明。

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
| `faces[].vertices` | [[x,y,z]…] | 顶点，用于算投影 2D AABB，可能为空 |
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
| `candidates[].layer_type` | `two_layer`/`three_layer` | 层数分类 |
| `candidates[].spacing_mm` | float | 点间距 |
| `candidates[].region_bbox` | {min,max} | 候选区域包围盒 |
| `candidates[].reason` | str | 生成原因 |
