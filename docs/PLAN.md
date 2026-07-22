目标
自动筛选可能需要布置焊点的区域，并生成候选焊点。
V1 重点是：
- 尽量不漏检；
- 允许一定误检；
- 最终由工程师人工复核。


---
Summary: 
作为粗筛，以不漏检并且保证一定的准确率为目标 具备可行性，需要后续人工复核。

---
输入
- CATIA V5 零件；
- 优先处理平面；
- 支持两层板和简单三层板。

---
算法流程
1. 遍历模型面
提取每个面的：
- 所属零件或 Body；
- 面类型；
- 法向；
- 面积；
- 空间位置；
- 包围盒。
V1 只处理平面，曲面暂时跳过或标记人工检查。
2. 筛选候选贴合面
两张面满足以下条件时，认为可能存在焊接关系：
法向夹角 小于 5度
面间距离 小于 0.1 mm
同时要求两个面的投影包围盒存在重叠。
法线方向可能相反，因此比较法线时忽略正负方向。
3. 生成候选焊接区域
将两张候选面的重叠部分作为候选焊接区域。
V1 可以先使用投影包围盒重叠区域近似，不要求精确计算复杂轮廓交集。
4. 生成候选焊点
根据候选区域尺寸布点：
- 小区域：在区域中心生成一个焊点；
- 长条区域：沿长方向均匀布点；
- 焊点间距控制在 20～70 mm；
- 区域不足 20 mm 时，只生成一个点。
焊点厚度方向位置取参与板层整体厚度的中间位置。
5. 基础过滤
删除明显不合理的候选点：
- 不在重叠区域内；
- 距离其他焊点小于 20 mm；
- 焊接面宽度明显不足；
- 法向偏差超过 5°。
孔边、折弯区和复杂曲面暂不自动判断，统一交由人工复核。

---
输出
在 CATIA 中创建独立集合：
Weld_Candidates
每个候选点记录：
- 三维坐标；
- 对应零件和面；
- 两层或三层分类；
- 点间距；
- 生成原因。

---
V1 判定原则
面接近 + 法向平行 + 投影重叠 -> 候选焊接区域
候选区域 -> 按 20～70 mm 生成候选焊点
V1 不追求完全准确，只验证该方法能否较完整地找出潜在焊接位置。所有结果都需要人工复核。

Links
- https://link.springer.com/article/10.1007/s00170-021-07186-0
- https://www.cad-journal.net/files/vol_11/CAD_11%283%29_2014_263-274.pdf
两篇论文的前半阶段和我们讨论的思路相似，可以作为参考

---
---

# 工程实现计划（V1 原型 · pycatia 路线）

> 以上为业务算法思路，保持不变。以下补充工程落地细节：技术栈、架构、
> 数据契约、分阶段任务、验收标准与风险应对。本节随实现进度更新为"当前状态"；
> 逐步验证的过程记录见 `DEVLOG.md`。

## 约束与前提
- 开发环境：**Windows + 运行中的 CATIA V5**（已完全迁移到该机器，不再区分 Mac/Windows 两地）。
- 项目本地 `.venv`（该机器无 conda），非 conda env。`weld_core` 仍严禁 import pycatia/pywin32，
  以保持可脱离运行中的 CATIA 独立跑 `pytest`（详见 `CLAUDE.md`）。
- CATIA 接口采用 **pycatia**（Windows COM 自动化，硬依赖 pywin32）。
- 重叠区域计算用**投影包围盒（2D AABB）近似**即可（V1 粗筛定位），已在 `weld_core/geometry.py`
  实现（`project_to_plane`/`aabb_2d`/`aabb_overlap_2d`）。

## 关键技术结论（决定架构，已用真实装配体验证）
1. **pycatia 仅 Windows 可用** → 算法核心（`weld_core`）不得依赖 pycatia，保持可独立测试。
2. **面遍历**：在 Product/Part 文档层面用 `Selection.Search("Topology.CGMFace,all")` 一次性
   拿到全部面（含子零件），用 `SelectedElement.leaf_product` 定位面所属零件实例
   （`leaf_product.com_object.PartNumber`——pycatia 的 `.name` 对装配体内实例恒为空，
   需绕过 pycatia 走底层 COM 对象读 `PartNumber`）。
3. **平面几何量**：`SPAWorkbench.GetMeasurableInContext(face_ref, leaf_product)`（Part 内直接
   打开时用 `GetMeasurable`）→ `GetPlane()`（对非平面面会抛异常，借此判平面/曲面）、
   `GetArea()`（单位 **m²**，需 ×1e6 转 mm²）、`GetCOG()`（mm）。
4. **CATIA COM 顶点/边界提取不可靠（已验证坐实）**：`Selection.Search` 用 `,sel`/`,(sel)`/
   `,under.sel` 等写法把作用域限定到单个面后再搜 `Topology.CGMVertex`/`CGMEdge`，结果要么恒为
   0，要么静默放大到不可控的范围（抽样验证出过一条"边"长度达 25000mm）。`HybridShapeFactory.
   AddNewBoundary` 需要具体 `PartDocument` 的 `hybrid_shape_factory`，但装配体内子零件不是独立
   可 activate 的文档，此路也不通。**现状**：`catia/extract_faces.py` 里 `faces[].vertices`
   恒为空，`manual_review=True`。

   **解法（已验证可行）：STEP 导出 + OCP/OCCT 离线解析**。`Document.ExportData(path, "stp")`
   （pycatia 确认支持）把装配体导出成 STEP，再用 `cadquery`（内含 `OCP`，即 OpenCASCADE 的
   Python 绑定，Windows + Python 3.9–3.12 有官方 pip wheel，本机 `.venv` 装了 `cadquery==2.8.0`
   验证通过）离线解析：
   - `cq.importers.importStep(path)` 解析 `raw_data/component/component.step`（226MB，55 个真实零件，
     10366 面 vs pycatia COM 数出的 10706 面，~3% 差异属正常）耗时约 47s，一次性成本，
     不是逐面 COM 调用那种量级（COM 观测约 3~4 faces/sec，全量要 45~70 分钟）。
   - `Face.Vertices()` 直接给出真实顶点，不经过任何 `,sel` 式作用域搜索，完全可靠——
     这就是要补的 `faces[].vertices`。
   - **重要坑**：STEP 导出会把所有面都写成通用参数曲面，OCCT 的
     `BRepAdaptor_Surface(face).GetType()` 在真实装配体上**没有一个面被标记为
     `GeomAbs_Plane`**（不能指望「曲面类型」这个信息在 STEP 里保真）。改用**顶点共面拟合**判平面：
     对 `Face.Vertices()` 做最小二乘平面拟合（SVD 取最小奇异向量为法向），最大残差 < 0.01mm
     记为 planar——实测 10366 面里 6348 个残差 ≈0.000000mm，判定耗时仅 3.66s。
   - **已知方法论缺陷（留给实现时处理）**：恰好 3 个顶点的面用这个方法必然"通过"（任意 3 点
     必共面），会把小三角面片误判成平面；需要 ①要求顶点数 ≥4，或 ②额外在面内部采样参数点
     （如 `Face.positionAt(u,v)` 中点）二次校验是否也落在拟合平面上。
   - **尚未解决**：STEP 里的 10366 个面目前是一个整体 compound shape，还没有验证怎么把每个面
     映回 CATIA 侧的 PartNumber/Body（`faces.json` 契约要求 `part`/`body` 字段）——需要解析 STEP
     的装配结构（`PRODUCT`/`NAUO` 实体）或按零件分别导出 STEP 再分别解析，两种都待验证。
   - 结论：这条路径完全不依赖 pycatia，可以放进 `weld_core`（或新增一个不依赖 CATIA 的
     `step_geometry` 模块），不违反"算法核心不依赖 CATIA"的架构原则；
     `pythonocc-core` 是同类替代品，未测试，`cadquery`/`OCP` 已验证够用。
5. **建点回写**：`HybridShapeFactory.add_new_point_coord` 放入 `Weld_Candidates` 集合
   （Phase 3，尚未实现/验证）。

## 架构：三层解耦 + JSON 契约
```
CATIA ──①extract(COM，面积/法向/零件号)──▶ faces.json ──②core──▶ candidates.json
  │                                           纯Python+numpy         │
  └─①b STEP导出+OCP解析(顶点/边界，已验证可行)──────────────┘   ③write(COM)──▶ CATIA
```
- ①提取层(`catia/extract_faces.py`)：只读 CATIA COM，导出 `faces.json`，不含算法。已实现并用
  真实装配体（`component.CATProduct`，10706 面）验证跑通；`vertices` 恒为空（原因见上第 4 条）。
- ①b STEP 旁路（已验证可行，未落地为代码）：导出 STEP + `cadquery`/`OCP` 离线解析，补
  `faces[].vertices`；`faces.json` 契约字段不变，只是这个字段的填充方式从"COM 提取"变成
  "STEP 解析"。落地时要解决"面→零件号"的映射（见上第 4 条"尚未解决"）。
- ②算法核心(`src/weld_core/`，纯 Python+numpy)：筛选/配对/布点/过滤，全部可离线单测；
  `geometry.py` 已实现 2D 投影/AABB 重叠等基础几何；`pairing/region/points/filtering.py`
  仍是占位，待实现。
- ③回写层(`catia/write_candidates.py`，未创建)：读 `candidates.json` 建点，Phase 3。

目录结构、数据契约字段、各阶段详细任务见配套文件 `docs/json_contract.md`
与仓库 `src/weld_core/`、`catia/`、`scripts/`、`tests/`。

## 数据契约（摘要）
- `faces.json`：`meta{part,unit,context,warnings}` + `faces[]{id,part,body,
  surface_type,area,normal,plane_origin,centroid,vertices[],manual_review,reason}`。
- `candidates.json`：`meta{source,core_version,params}` + `candidates[]{id,position,
  faces[],layer_type,spacing_mm,region_bbox,reason}`。

## 分阶段计划
| 阶段 | 目标 | 输入→输出 | 验收 | 状态 | 主要风险/应对 |
|---|---|---|---|---|---|
| **P0 环境** | `.venv` + 骨架 | 计划→环境/骨架/验证脚本 | check 脚本通过；pytest 可运行 | 完成 | pywin32 COM 未注册→`pywin32_postinstall.py -install` |
| **P1 提取** | 导出全部平面几何 | 零件→faces.json | 面数=人工计数；抽样几何量误差<1% | 跑通，vertices 由 P1.5 补全 | 顶点不可靠→见上第 4 条，已用 STEP+OCP 解决 |
| **P1.5 顶点补全** | 解决 vertices 缺失 | STEP 文件→精确顶点/边界 | 抽样与 CATIA 面积/法向交叉核对一致 | **完成**（`step_geometry.py`+`enrich_faces_with_step.py`，真实装配体验证：planar 面 manual_review 100%→1.7%，顶点与 COM 平面吻合误差<0.001mm） | 面→零件号映射：XCAF assembly tree 已解决；3 顶点面误判：2 个非对称 UV 采样点已解决 |
| **P2 核心** | 离线实现筛选/布点/过滤 | faces.json→candidates.json | 合成夹具单测全绿 | **完成**（真实装配体验证：0.47s 跑通，产出 192 个候选/41 组零件配对，间距全部落在 20-70mm） | 三层板分类未做（留待后续，见 DEVLOG）；`body` 字段仍占位 |
| **P3 回写** | 建 Weld_Candidates | candidates.json→CATIA 点集 | 位置一致；重复运行幂等 | **完成**（真实会话验证：坐标/参数精确匹配，幂等性验证通过——不用删除类 API，改成按 id 原地更新点坐标，详见 DEVLOG） | `Selection.Delete`/`Products.remove`+`Document.close` 在这套环境里均不可靠，已避开，改用"找到则更新、找不到则新建、多余的标记 stale 不删除"策略 |
| **P4 集成** | 端到端+调参+日志+文档 | 真实零件→全链路 | 无明显漏检；一键复现 | **完成**（`catia/export_step.py` + `scripts/run_full_pipeline.py` 一键跑通 extract→export→enrich→core→write 全链路，对着真正的原生 `.CATProduct` 验证；过程中发现并修复候选点 id 跨会话不稳定的问题，详见 DEVLOG） | 漏检高→放宽阈值/加边采样；调参决策仍待工程师人工复核后反馈，本阶段未改动 `WeldParams` 默认值 |
| **P5 评测** | 用真实焊点（`raw_data/component/SPOT.step`）量化候选点漏检/误检 | ground_truth.json + candidates.json → evaluation.json | 合成夹具单测全绿；真实数据出具 recall/precision | **完成**（`weld_core.evaluate` + `scripts/extract_ground_truth.py`；真实评测：286 个真实焊点 vs 200 候选，10mm 容忍度下 recall 22.7%/precision 32.5%，20mm 容忍度 recall 48.3%——即使放宽容忍度到接近 20mm 最小点间距上限，仍有约一半真实焊点找不到对应候选，说明当前 V1 阈值/算法离"不漏检"目标有明显差距，见 DEVLOG） | 真实焊点标记的实例名（如 `04021210-R60_WP`）不对应装配体真实 PartNumber，评测按纯 3D 距离匹配，不按零件配对 |

## 里程碑
- **M0** 环境就绪（完成）· **M1** 提取可用（完成，附带顶点限制）· **M1.5** 顶点补全
  （完成，见 P1.5）· **M2** 算法可用（完成，见 P2）· **M3** 回写可用（完成，见 P3）·
  **M4** 端到端交付（完成，见 P4——一键复现脚本 + 真实原生文件全链路验证 + id 稳定性修复）·
  **M5** 真实焊点评测（完成，见 P5——发现明显的 recall 缺口，是否需要回头调参/改进算法
  待产品侧决策）

## 环境（不改动系统/全局 Python）
- 单一环境：项目本地 `.venv`（Windows，Python 3.12，本机无 conda）：
  `python -m venv .venv` → `pip install pycatia pywin32 numpy "pydantic>=2" cadquery` →
  `pywin32_postinstall.py -install` → `pip install -e .`。
- `cadquery`（含 `OCP`，OpenCASCADE 绑定，2.8.0）已装并验证可用，用于 P1.5 的 STEP 解析。
- `environment.yml`/`environment-catia.yml`（conda）是早期 Mac/Windows 两机方案的遗留文件，
  当前未使用，未删除。
- 本机曾出现 `HTTP_PROXY`/`HTTPS_PROXY=127.0.0.1:7897` 导致 pip 安装 `SSLEOFError` 失败，
  重试后已恢复正常，如再出现同类问题优先怀疑这个本地代理。

## 默认假设
- Python 3.12（本机实际版本，不再强制 3.11）；曲面/顶点不足统一 `manual_review`。
- 顶点提取采用 STEP+OCP 路线（已验证可行，见上第 4 条），落地时需解决面→零件号映射，
  并把 `catia/extract_faces.py` 或新模块接入这条路径；如涉及契约变化同步
  `docs/json_contract.md`。

