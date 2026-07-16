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
> 数据契约、分阶段任务、验收标准与风险应对。

## 约束与前提
- 开发机为 **Mac**；CATIA 只在一台**可随时使用的 Windows + CATIA V5** 机器上。
- CATIA 接口采用 **pycatia**（Windows COM 自动化，硬依赖 pywin32，Python ≥ 3.9）。
- 重叠区域计算用**投影包围盒（2D AABB）近似**即可（V1 粗筛定位）。

## 关键技术结论（决定架构）
1. **pycatia 仅 Windows 可用**，Mac 上无法安装/运行 → 算法核心不得依赖 pycatia。
2. **CATIA API 无"直接枚举全部面"接口**：用 `Selection.Search "Topology.CGMFace,sel"`
   按 Body 迭代（`Count2`）；**多实例/重名特征会漏检**，需提取阶段自检告警。
3. **平面几何量**：`SPAWorkbench.GetMeasurableInContext` → `GetPlane`(原点+两面内方向，
   叉乘得法向)、`GetArea`、`GetCOG`；面类型判 `PlanarFace`。
4. **无包围盒 API**：提取面**顶点**(`Topology.CGMVertex`)，核心侧投影算 2D AABB。
5. **建点回写**：`HybridShapeFactory.add_new_point_coord` 放入 `Weld_Candidates` 集合。

## 架构：三层解耦 + JSON 契约
```
CATIA(Win) ──①extract──▶ faces.json ──②core(Mac)──▶ candidates.json ──③write──▶ CATIA(Win)
  pycatia                  中间契约      纯Python+numpy      中间契约            pycatia
```
- ①提取层(Windows/pycatia)：只读 CATIA，导出 `faces.json`，不含算法。
- ②算法核心(Mac，纯 Python+numpy)：筛选/配对/布点/过滤，全部可离线单测。
- ③回写层(Windows/pycatia)：读 `candidates.json` 建点。

目录结构、数据契约字段、各阶段详细任务见配套文件 `docs/json_contract.md`
与仓库 `src/weld_core/`、`catia/`、`scripts/`、`tests/`。

## 数据契约（摘要）
- `faces.json`：`meta{part,unit,context,warnings}` + `faces[]{id,part,body,
  surface_type,area,normal,plane_origin,centroid,vertices[],manual_review,reason}`。
- `candidates.json`：`meta{source,core_version,params}` + `candidates[]{id,position,
  faces[],layer_type,spacing_mm,region_bbox,reason}`。

## 分阶段计划
| 阶段 | 目标 | 输入→输出 | 验收 | 主要风险/应对 |
|---|---|---|---|---|
| **P0 环境** | 两套 conda 环境 + 骨架 | 计划→环境/骨架/验证脚本 | 两 check 脚本通过；pytest 可运行 | pywin32 COM 未注册→`cnext.exe /regserver` |
| **P1 提取** | 导出全部平面几何 | 零件→faces.json | 面数=人工计数；抽样几何量误差<1% | 多实例漏检→自检告警+用未实例化测试件 |
| **P2 核心** | 离线实现筛选/布点/过滤 | faces.json→candidates.json | 合成夹具单测全绿 | 顶点缺失→标 manual_review |
| **P3 回写** | 建 Weld_Candidates | candidates.json→CATIA 点集 | 位置一致；重复运行幂等 | 集合重名→先查后建 |
| **P4 集成** | 端到端+调参+日志+文档 | 真实零件→全链路 | 无明显漏检；一键复现 | 漏检高→放宽阈值/加边采样 |

## 里程碑
- **M0** 环境就绪 · **M1** 提取可用 · **M2** 算法可用 · **M3** 回写可用 · **M4** 端到端交付

## 环境（不改动系统/全局 Python）
- `weld-core`(Mac/跨平台，Python 3.11，numpy+pydantic+pytest，**无 pycatia**)：`conda env create -f environment.yml`
- `weld-catia`(Windows，Python 3.11，pycatia+pywin32)：`conda env create -f environment-catia.yml` 后 `pip install -e .`

## 默认假设
- Python 3.11；曲面/顶点不足统一 `manual_review`；测试件先用未实例化零件。

