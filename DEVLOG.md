# DEVLOG — 开发进度记录

> 每次 fresh session 先读本文件；每推进一步后立即在顶部追加带日期的条目。
> 最新在上。日期格式 YYYY-MM-DD。

---

## 2026-07-16 — Phase 2 完成：pairing/region/points/filtering 落地，真实装配体端到端跑通

**做了什么**
- 把 `src/weld_core/pairing.py`/`region.py`/`points.py`/`filtering.py` 从占位（`NotImplementedError`）
  实现为可跑的算法，按 `PLAN.md` 最上面"算法流程"章节逐条对应：
  - `pairing.find_mating_pairs`：不同零件 + 法向夹角 ≤5°（忽略正负）+ 面间距 ≤0.1mm + 投影 2D AABB
    重叠。法向夹角这一层先用 `normals @ normals.T` 一次性向量化算出全部两两夹角做预过滤，再对通过的
    候选对做逐对的 gap/AABB 检查——真实数据里参与配对的面约 1892 个，朴素双重循环预计要 1-2 分钟，
    向量化预过滤后整体跑下来只要 0.47 秒。
  - `region.build_region`：两张贴合面之间沿法向的中点作为焊点厚度方向位置（"参与板层整体厚度的
    中间位置"，V1 只有两张贴合面数据，取中点是最直接的对应）；重叠区域短边 < `min_face_width_mm`
    时判定区域无效，返回 `None`（对应"焊接面宽度明显不足"的基础过滤规则，放在区域构建阶段而不是
    生成点之后再过滤，因为宽度不足这个区域根本不成立）。
  - `points.layout_points`：区域长边 <20mm 时中心生成 1 点；否则按 20-70mm 间距沿长边均匀布点
    （`N = max(2, ceil(long_dim/70)+1)`），2D 坐标通过新增的 `geometry.unproject_from_plane`
    （`project_to_plane` 的逆操作）转回 3D。
  - `filtering.filter_candidates`：法向偏差和面宽已经在上游 pairing/region 处理，这里只做两件
    "全局"的事——候选点是否落在自己的 `region_bbox` 内（防御性检查，按当前构造方式恒成立，但对应
    PLAN 明确列出的规则）、以及跨"不同面对"生成的候选点之间距离 <20mm 时去重（同一区域内部的点
    本来就按 20-70mm 布的，这个去重专门处理不同面对意外挨得太近的情况）。
  - `pipeline.run` 按已有的 TODO 注释接线，最后统一把候选点编号成 `wc_001`、`wc_002`...。
- **明确不做的事（scope 取舍）**：`layer_type` 目前全部标 `"two_layer"`，不做三层板自动识别/合并——
  PLAN 的算法流程章节全程按"两张面配对"描述，没有给三层板判定的具体规则；真实场景里三层板会自然
  表现为两组相邻的两层配对，人工复核能看出来，这个简化留到以后需要时再定规则实现。
- 新增测试：`tests/test_pairing.py`、`test_region.py`、`test_points.py`、`test_filtering.py`
  （构造简单几何直接测每个模块），`geometry.py` 加 `unproject_from_plane` 和往返测试，
  更新 `tests/test_pipeline.py`（原来 Phase 0 阶段断言"空列表"，现在断言 `two_layer.json` 夹具
  应该产出 3 个点、间距 45mm、z=1.025）。全部 27 个用例通过。

**真实装配体验证结果**（`data/faces_component_full.enriched.json`，P1.5 产出，1892 个已补全
vertices 的 planar 面）
- 端到端跑通：加载 0.24s + 算法 0.47s，总共不到 1 秒。
- 产出 **192 个候选焊点**，涉及 **41 组不同零件配对**（前几名如
  `(2JVB4T5BI0, JPG81WS6QG)` 27 个点、`(1EAVWXKUA9, 84CK99UPEH)` 20 个点，量级和真实钣金装配体
  "多处法兰贴合"的直觉吻合）。
- 其中 14 个是小区域单点候选（`spacing_mm=0`），其余 178 个的间距全部落在 [20.04, 69.65]mm，
  符合"20~70mm"的设计约束。
- 抽样候选的 `reason` 显示 `gap≈0.000mm, normal_angle≈0.00°`——真实钣金件贴合面通常是精确重合的
  平面，符合预期。

**结论**
- Phase 2 算法核心完成，且已经用真实数据（而不仅是 `tests/fixtures/two_layer.json` 合成夹具）
  跑通验证，产出的候选数量级、间距分布、涉及的零件对都看起来合理。
- 三层板分类、`body` 字段仍是已知的简化/占位，不阻塞当前阶段。

**下一步**
- Phase 3：`catia/write_candidates.py`（读 `candidates.json`，在 CATIA 里建 `Weld_Candidates`
  集合并建点，尚未开始）。
- 如果需要，可以把这次全量跑出的 192 个候选导出看看，请工程师/产品侧对结果做一次人工复核，
  反馈阈值（`WeldParams`）是否需要调整，再决定要不要在 Phase 3 之前先调参。

---

## 2026-07-16 — P1.5 落地为正式代码：`step_geometry.py` + `enrich_faces_with_step.py`，真实装配体验证通过

**做了什么**
- 把上一条记录里"验证通过但未写成代码"的 STEP+OCP 路线落地为正式模块，解决了当时列出的两个坑：
  1. **面→零件号映射**：没有用会把装配体拍平的 `cq.importers.importStep`，改用
     `STEPCAFControl_Reader` + XCAF（`XCAFDoc_ShapeTool`）遍历 assembly tree，从名字节点拿到
     PartNumber。**过程中发现一个原计划没预见的坑**：assembly 里每个零件实例的位置由
     `TopLoc_Location` 决定，如果直接对被引用的原始 shape 取顶点，坐标是零件本地坐标系的，
     和 CATIA COM 测出来的全局坐标对不上——已解决：递归时用 `GetLocation_s` 累乘
     `TopLoc_Location`，叶子 shape 调用 `.Moved(累乘location)`，验证坐标与"整个 free shape
     一次性 GetShape_s"完全一致（同一顶点误差为 0）。
  2. **3 顶点面误判平面**：最初只加了 1 个 UV 中点校验点，结果在 `SPOT.step`（这是纯"焊点标记球"
     几何，不是真零件，上条记录已确认）上测出全部 572 个球面全部误判成 planar——排查发现：
     球面这类周期性参数曲面（u 从 0 到 2π）的"中点"恰好和顶点落在同一条经线平面上，
     属于对称退化，不能证伪弯曲。改成 2 个非对称 UV 采样点（`(0.35,0.65)` 和 `(0.7,0.3)`
     两组分数），重跑后 `SPOT.step` 全部 572 面正确判定为非平面，问题解决。
- 新增/改动文件：
  - `src/weld_core/geometry.py`：新增纯 numpy 函数 `fit_plane_residual`（SVD 平面拟合 + 最大残差），
    从 OCP 管道代码里剥离出来单独测试。
  - `src/weld_core/step_geometry.py`（新模块，不 import pycatia/pywin32）：`parse_step_faces(path)`
    解析 STEP，按 PartNumber 分组返回每个面的顶点（已去重）/面积/重心/法向/是否平面。
  - `scripts/enrich_faces_with_step.py`（新脚本）：读 COM 提取的 `faces.json` + STEP 文件，
    按 part 分组、按"重心距离(<1mm) + 法向夹角(<2°) + 面积相对误差(<5%)"做全局贪心一对一匹配，
    给匹配上且 STEP 判定平面的 `FaceRecord` 填充 `vertices` 并清 `manual_review`；不匹配/
    STEP 判非平面的保留 `manual_review=True` 并写明原因（区分"STEP 里找不到这个零件"/
    "没有匹配到候选面"/"STEP 判非平面但 COM 判平面"三种 reason）。参考 `extract_faces.py` 的
    `RunStats`/`write_run_log` 模式在 `logs/` 写运行日志。
  - `tests/test_geometry.py` / `tests/test_step_geometry.py`：分别单测 `fit_plane_residual`
    （含"3 点必共面"的已知缺陷、以及加第 4 个点后能正确识别弯曲）和 `step_geometry`
    （`pytest.importorskip("OCP")` 保护；用 OCP 原生 `BRepPrimAPI_MakeBox`/`MakeSphere`
    现场构造立方体/球面测试，不依赖 `data/` 下的大 STEP 文件；另有一个写 STEP 再解析的
    round-trip 测试验证 `parse_step_faces` 全流程）。全部 13 个用例（含原有的）通过。
  - `pyproject.toml`/`requirements.txt` 把 `cadquery` 加成正式依赖；`docs/json_contract.md`
    补充 `vertices` 字段说明。

**真实装配体验证结果**（`data/component.step`，226MB，STEP 解析约 55s）
- **零件名映射交叉核对**：单独跑 `MDAU54VBV4`（`data/faces_MDAU54VBV4.json`），STEP 侧解析出
  179 面、68 planar——和 DEVLOG 上上条记录里 pycatia COM 单独提取该零件的结果（179 面/68 planar）
  **完全一致**，证明零件名映射和新的平面判定都是对的，不是巧合（如果映射错了不可能连平面数都对上）。
  匹配后逐面核对：全部 68 个平面的 STEP 顶点到 COM 测出的 plane_origin/normal 定义的平面，
  最大距离 0.00027mm，基本是浮点精度级别的吻合。
- **全量装配体**（`data/faces_component_full.json`，10706 面，1925 planar/8781 non_planar）：
  匹配结果 1892/1925 个 planar 面成功匹配（98.3%），**0 个"STEP 判非平面但 COM 判平面"的冲突**
  （说明两套独立测量完全一致，没有发现矛盾），33 个未匹配（分散在各零件，量级和之前记录的
  "STEP 面数比 COM 少 ~3%"的正常导出损耗吻合，不是新问题）。
  - `manual_review=True` 比例：整体面从 100%（10706/10706，上条记录的状态）降到 82.3%
    （8814/10706——这里面 8781 个是 V1 本来就跳过的 non_planar，不算真正阻塞）；
    **在算法真正关心的 planar 面子集里，从 100% 降到 1.7%**（33/1925），达成了 DEVLOG
    上条记录里定的验收标准（"vertices 不再恒为空，manual_review 比例明显下降"）。

**结论**
- P1.5 顶点补全阶段完成：`vertices` 字段现在对绝大多数平面（98.3%）有真实数据，且和 CATIA COM
  独立测量的平面参数吻合到亚微米级，可以放心作为 Phase 2 投影包围盒计算的输入。
- 遗留的 33 个未匹配面、8781 个 non_planar 面按设计走 `manual_review=True`，符合"不漏检为先，
  人工复核兜底"的 V1 原则，不需要现在解决。

**下一步**
- 按 DEVLOG 既定顺序推进 Phase 2：实现 `src/weld_core/pairing.py`/`region.py`/`points.py`/
  `filtering.py`（目前仍是占位），用 `data/faces_component_full.enriched.json` 这类真实、
  已有 vertices 的数据做端到端验证，而不是只靠 `tests/fixtures/two_layer.json` 这个合成夹具。
- `body` 字段仍是 `"unknown"` 占位，不阻塞，暂不处理。

---

## 2026-07-16 — STEP+OCP 顶点提取方案验证通过，PLAN.md 更新为"可行"

**做了什么**
- 用户说本地代理恢复了，重试 `pip install cadquery`——这次装成功了（`cadquery` 2.8.0，
  内含 `OCP`）。
- 用 `data/SPOT.step`（4.6MB）做第一次测试：发现全部 572 个面都被判定成 `GeomAbs_Sphere`
  （半径恰好 3mm，面积约 56.57mm² 对应半球公式）。查了一下才反应过来 SPOT.step 不是零件
  几何，是"焊点"本身的标记几何（半径 3mm 的小球），选错测试对象了，不是 bug。
- 换成真正有代表性的 `data/component.step`（226MB，对应之前 pycatia COM 提取过的真实装配体）
  重新验证：
  - `cq.importers.importStep()` 解析耗时约 47~48s，得到 10366 个面（pycatia COM 之前数出
    10706 个，~3% 差异，STEP 导出/三角化的正常损耗）。
  - 用 OCCT 原生的 `BRepAdaptor_Surface(face).GetType()` 查曲面类型分布：**没有一个面被标记
    为 `GeomAbs_Plane`**，全是 `GeomAbs_CN`/`Uniform`/`SurfaceOfExtrusion`/`Torus` 等通用
    参数曲面——说明 CATIA 导出 STEP 时把平面也写成了通用曲面，不能指望 STEP 里的"曲面类型"
    字段来判断平面性。
  - 改用**顶点共面拟合**代替：对每个面的 `Face.Vertices()` 做 SVD 最小二乘平面拟合，取最大
    残差 < 0.01mm 判定为 planar。结果：10366 个面里 **6348 个残差 ≈0.000000mm**，拟合本身
    只花 3.66s（约 2830 faces/sec）。`Face.Vertices()` 本身完全可靠，不像 CATIA COM 那样
    受 `Selection.Search` 的 `,sel` 作用域问题困扰。

**结论**
- **STEP + OCP（cadquery）这条路径验证通过，可以解决 Phase 1 发现的顶点提取阻塞问题**：
  能拿到每个面真实的顶点，且比 pycatia COM 逐面调用快两个数量级（一次性 47s 导入 + 3.66s
  拟合 vs COM 观测的 3~4 faces/sec、全量要 45~70 分钟）。
- 已知要留给实现阶段解决的坑：
  1. 恰好 3 个顶点的面用"共面拟合"必然通过（任意 3 点必共面），需要 ≥4 顶点或额外采样面内部
     参数点二次校验，否则会把弯曲的小三角面片误判成平面。
  2. STEP 解析出来是一个整体 compound，还没验证怎么把每个面映回 CATIA 侧的
     PartNumber/Body（`faces.json` 契约需要 `part`/`body` 字段）。
- 已把这些验证细节和结论写进 `PLAN.md`（第 4 条关键技术结论、架构图、分阶段计划表、
  里程碑、环境章节），P1.5 状态从"待验证"改成"可行性已验证，未写成正式代码"。

**清理**
- 删掉了探测用的临时脚本（`scripts/_tmp_step_probe*.py`）和临时日志
  （`data/step_probe*.log`），保留有意义的验证产出（`data/faces_component_full.json` 等）。

**下一步**
- 把 STEP+OCP 路线写成正式代码（可能是 `weld_core` 下新增 `step_geometry` 模块，或
  `catia/` 下新增一个"导出 STEP + 解析"的脚本），解决 3 顶点面误判和 面→零件号映射这两个
  已知缺口。
- 落地后用真实装配体重新跑一遍 `extract_faces.py` 或新脚本，确认 `faces[].vertices` 不再
  恒为空，`manual_review` 比例明显下降，再推进 Phase 2 的 `pairing/region/points/filtering`。

---

## 2026-07-16 — 更新 PLAN.md：调研顶点提取的解法，标注为待验证提案

**做了什么**
- 按当前进度和 Phase 1 发现的问题重写了 PLAN.md 的"工程实现计划"部分（业务算法思路部分未动）：
  去掉 Mac/Windows 两地叙事和 conda 环境描述，改为单一 Windows `.venv`；补充真实验证过的
  API 结论（`Selection.Search("Topology.CGMFace,all")` + `leaf_product` 定位零件、
  `GetMeasurableInContext` 的单位陷阱等）；分阶段计划表加了"状态"列并新增 **P1.5 顶点补全**
  阶段；里程碑加了 M1.5。
- 上网查了顶点提取问题的可能解法：CATIA 侧 `Document.ExportData(path, "stp")` 确认可编程导出
  STEP（本机 pycatia 源码里能看到该方法且支持 stp/step）；调研到 Python 的 OpenCASCADE 绑定
  ——`OCP`（`cadquery-ocp`）对 Windows + Python 3.9–3.12 有官方 pip wheel，`pythonocc-core`
  是另一个选项——理论上可以离线解析 STEP 的 B-rep，拿到精确的面顶点/边界，且不依赖 pycatia，
  能放进 `weld_core` 而不破坏"核心不依赖 CATIA"的架构。
- 尝试在本机装 `cadquery` 验证这条路线是否真能解决顶点问题，**没能装成**：
  `pip install` 反复报 `SSLEOFError`，连体积很小的 `pytest` 都一样失败，查到本机配了
  `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7897`，判断是这个本地代理的问题（不是包体积或
  PyPI 连通性问题——`Test-NetConnection pypi.org -Port 443` 是通的）。

**结论**
- STEP+OCP/pythonocc-core 这条解法目前只是**调研出来、写进 PLAN.md 的提案**，没有在本机跑通验证，
  PLAN.md 里已经如实标注"待验证"而不是当作已解决。
- 真正验证（装上库、拿 `data/SPOT.step` 解析、和 CATIA COM 读到的面积/法向交叉核对、量一下耗时）
  需要先解决本地代理问题，这是下一步的前置阻塞项，不是我能在这台机器上直接绕过的。

**下一步**
- 人工检查/绕开 `127.0.0.1:7897` 这个代理，或换一个能正常访问 PyPI 的网络环境。
- 代理问题解决后：`pip install cadquery`（或 `pythonocc-core`），用 `data/SPOT.step` 做小规模
  验证（顶点数量级、面积/法向和 pycatia 结果的交叉核对、耗时对比）。
- 验证通过再决定：完全换成 STEP+OCP 路线，还是只用它补 `vertices` 字段、其余仍走 pycatia COM。

---

## 2026-07-16 — 更新 README.md / CLAUDE.md：单机 Windows 叙事 + git 说明

**做了什么**
- 和用户过了一遍 CLAUDE.md/README.md 该怎么改，确认几点：
  1. 开发已完全迁移到这台 Windows+CATIA 机器，不再保留"Mac 离线核心 / Windows 集成"两地叙事，
     "开发机"相关表述改为阶段无关的固定描述，避免再过时。
  2. Windows 侧环境正式方案是项目本地 `.venv`（本机无 conda），`environment*.yml`/conda 不再作为
     Windows 侧的文档主线。
  3. 顶点提取不可靠这条硬限制只留在 DEVLOG，不写进 CLAUDE.md（CLAUDE.md 保持流程/约定性质）。
  4. 加了一条简短的 git 说明（仓库已 `git init`，大文件/运行产物已在 `.gitignore`）。
- 更新了 `CLAUDE.md`（现 30 行，远低于 200 行上限）和 `README.md`（现 55 行）：
  去掉 Mac/Windows 双机叙事与 conda 指令，改为单一 `.venv` 环境说明；架构图去掉 `(Win)`/`(Mac)`
  机器标注；补充 `catia/extract_faces.py` 的用法和 `logs/` 性能日志说明；状态清单里 Phase 1
  标记为已跑通但附带顶点提取限制的说明。

**遗留（未改动，仅记录）**
- `PLAN.md` 里"工程实现计划"部分仍写着"开发机为 Mac；两套 conda 环境"等旧叙事，本次未动
  （用户只要求改 README/CLAUDE.md）；如果之后要统一，需要单独确认。
- `environment.yml`/`environment-catia.yml`/`requirements*.txt` 文件本身没有删除或改写，
  仍是历史遗留的 conda 描述，目前没有文档在指向它们作为主路径。

---

## 2026-07-16 — 全装配体验证 + 性能日志

**全装配体导出结果**
- `component.CATProduct` 全量导出：10706 个面，1925 个 planar，其余 non_planar。
- 个别面读取 `GetCOG` 报 `com_error`（如 `C9VWLI50MK/face_359` 等 8 处），已按设计降级为
  `centroid=plane_origin` 并记入 `meta.warnings`，不中断整体导出——符合"不漏检为先，异常不阻断"的思路。
- 用 `--part-number` 过滤单个零件时，仍会遍历全装配体的 10706 个面逐个取 `leaf_product`/`PartNumber`
  来判断是否匹配，被跳过的面也有 COM 调用开销，所以"过滤到 1 个零件"并不比全量快很多，
  这是当前实现的已知性能特征，不是 bug。

**新增：性能日志（`catia/extract_faces.py`）**
- 每次运行会在 `logs/` 目录生成一份人类可读的 `.log` 文件（纯文本，仓库 `.gitignore` 已忽略
  `logs/`/`*.log`，不会误入库），命名精确到"文档 + 零件过滤范围 + 运行时间戳"：
  `extract_faces_{document}_{part_number_or_ALL}_{YYYYMMDD-HHMMSS}.log`。
- 内容包含：搜索耗时、逐面提取耗时、总耗时、吞吐（faces/sec）、
  找到的总面数/被过滤跳过数/实际处理数、planar/non_planar 计数、读取失败计数、输出路径。
- 单零件（MDAU54VBV4，179 面）验证：搜索 1.2s，逐面提取 52.6s，约 3.4 faces/sec，0 读取错误。

**下一步**
- 顶点/边界提取仍是 open item（见上一条记录），需要产品侧决定是否投入 STEP 离线解析或 CAA 插件方案。
- 如果后续要跑更大规模或多次运行，可以考虑给 `--part-number` 之外加一个"先按 Product 结构过滤再
  搜面"的路径来避免全量扫描，但这属于性能优化，非 V1 必须项。

---

## 2026-07-16 — Phase 1 进行中：Windows+CATIA 环境就绪，extract_faces.py 首版

**环境**
- 装有 CATIA 的 Windows 机上没有 conda，只有系统 Python 3.12.8（约定要 3.11 但暂无 conda 可用）。
- 按"不改动系统/全局 Python"原则，改用项目本地 `.venv`（`python -m venv .venv`）代替 conda env，
  装了 `pycatia`/`pywin32`/`numpy`/`pydantic`，跑了 `pywin32_postinstall.py -install` 注册 COM，
  `pip install -e .` 使 `weld_core` 可导入。`scripts/check_env_catia.py` 通过，成功连上运行中的 CNEXT。
- **遗留**：`environment-catia.yml`/`requirements-catia.txt` 仍假设 conda；此机器实际用 `.venv`，
  后续如需固化建议在 README/环境文档里补一条"无 conda 时用 venv"的说明。
- pytest 一度因网络问题装不上（SSL EOF），未强行重试；本次没有改动 `weld_core`，用已装好的
  pydantic 直接跑 `load_faces()` 校验代替，后续需要时再补装 pytest 跑全量测试。

**CATIA 中的真实测试对象**
- 会话开始时 CATIA 里是简单测试件（cube_30mm 等），后来变成了真实装配体
  `SPOT.CATProduct`/`component.CATProduct`（对应 `data/SPOT.step`/`data/component.step`），
  含约 55 个真实钣金件（`04021210-R60_WP.CATPart` 等命名）。用户确认直接用这个真实装配体验证。
- 装配体内的子零件不是独立窗口（`app.windows` 只有 3 个：`SPOT.step`/`component.step`/`Part56`），
  必须在 Product 文档层面用 `Selection.Search("Topology.CGMFace,all")` 搜索全装配体的面，
  再用 `SelectedElement.leaf_product` 定位每个面所属的零件实例。

**关键 API 结论（写入 `catia/extract_faces.py` 注释）**
- 面积/平面/重心：`SPAWorkbench.GetMeasurableInContext(face_ref, leaf_product)`
  （Part 直接打开时用 `GetMeasurable`）。`area` 单位是 **m²**，需 ×1e6 转 mm²。
  `GetPlane()` 对非平面面会抛 `com_error` → 平面判定可靠（曲面/平面靠 try/except 区分）。
  `GetCOG()` 直接是 mm。
- 零件号：`leaf_product` 是 pycatia 的通用 `AnyObject`（`.name` 恒为空字符串），
  必须绕过 pycatia 走底层 COM 对象拿 `PartNumber`：`leaf_product.com_object.PartNumber`。
- **顶点提取不可靠（重要风险，已验证坐实）**：`Selection.Search` 用 `,sel` 把选择范围限定到单个面后
  再搜 `Topology.CGMVertex`/`CGMEdge` 恒返回 0；试过 `,(sel)`/`,under.sel`/`,in.sel` 等多种写法，
  返回的计数（如 2162/2818）远超单面应有的顶点/边数，且抽样一条"边"长度达 25000mm，
  证明这些写法根本没有正确限定范围（很可能退化成了不受控的更大范围），不可信。
  `HybridShapeFactory.AddNewBoundary` 需要具体 PartDocument 的 `part`/`hybrid_shape_factory`，
  但 Product 层面选中的子零件不是独立可 activate 的文档（见上），此路也不通。
  **结论**：V1 阶段 `faces[].vertices` 恒为空，`manual_review=True`（原因含 "vertices unavailable"），
  与 `docs/json_contract.md`/`PLAN.md` 里早就写好的兜底策略（"顶点缺失→标 manual_review"）一致，
  不是新问题而是被验证坐实的已知风险。这意味着 Phase 2 的投影包围盒重叠判定在这套真实装配体上
  暂时拿不到任何一个"非人工复核"的候选——如果要恢复自动初筛能力，需要另找顶点/边界提取路径
  （例如导出单个零件为 STEP 再离线解析，或找 CAA RADE 插件），这是需要产品侧决策的开放问题。
- `body`（Body 名）在 Product 层面也拿不到可靠的每面 Body 归属，`extract_faces.py` 里设为常量
  `"unknown"` 占位，并在 `meta.warnings` 里注明，不影响算法（`body` 只是信息字段）。

**产出**
- 新建 `catia/extract_faces.py`：连接 CATIA、按 `--part-number` 过滤/`--limit` 限量，导出 `faces.json`。
- 单零件试跑（`--part-number MDAU54VBV4`）：179 个面，68 个 planar，`load_faces()` 校验通过。
- 全装配体（约 10706 个面）导出正在后台跑，用于确认整机规模下的耗时与稳定性。

**下一步**
- 看全装配体导出结果（耗时、有无异常/告警堆积），把结论也补进本文件。
- 和用户/产品侧确认：vertices 恒为空、因此 Phase 2 自动初筛在真实件上基本失效，是否要投入解决
  （STEP 离线解析 / CAA 插件），还是 V1 先接受"全量人工复核"这个降级结果。
- Phase 2：`src/weld_core/pairing.py`/`region.py`/`points.py`/`filtering.py` 仍是占位，待实现。

---

## 2026-07-16 — 仓库 git 初始化

**做了什么**
- `git init`（本地 user.name/email 已配置，仅限本仓库）。
- 补充 `.gitignore`：新增忽略 `data/*.step`、`*.CATPart`、`*.CATProduct`、`*.stl`
  （`data/component.step` 226MB、`data/SPOT.step` 4.6MB 为大体积 CAD 输入，不入库）；
  新增忽略 `.claude/settings.local.json`（本地机器设置）。
- 按模块做原子化 commit（6 个）：
  1. `.gitignore`
  2. 环境/依赖配置（environment*.yml、requirements*.txt、pyproject.toml）
  3. 项目文档（README、CLAUDE.md、PLAN.md、docs/json_contract.md）
  4. `src/weld_core/` 包骨架
  5. `scripts/`（环境校验脚本）
  6. `tests/`（用例 + fixture）

**验证结果**
- `git status` 干净（除本次 DEVLOG 更新外无未跟踪文件）。
- 确认 `data/*.step`、`.venv/`、`.pytest_cache/`、`*.egg-info/`、
  `.claude/settings.local.json` 均被正确忽略，未进入任何 commit。

**未决 / 风险**
- 尚无远程仓库（未 push）。

**下一步**
- 迁移到装有 CATIA 的 Windows 机开发（Phase 1）。

---

## 2026-07-15 — Phase 0 完成：环境、骨架、契约

**做了什么**
- 确认技术路线：pycatia（CATIA V5 COM 自动化，Windows 专用），三层解耦架构。
- 更新 `PLAN.md`，追加工程实现计划（架构/契约/分阶段/里程碑/风险）。
- 建立仓库骨架：
  - `src/weld_core/`：`schema.py`(pydantic 契约)、`geometry.py`(已实现)、`config.py`(阈值)、`pairing/region/points/filtering.py`(Phase 2 占位)、`pipeline.py`(可运行 CLI)。
  - `catia/`：待建（Phase 1/3）。
  - 环境文件：`environment.yml`/`environment-catia.yml`/`requirements*.txt`/`pyproject.toml`。
  - 验证脚本：`scripts/check_env_core.py`、`check_env_catia.py`。
  - 测试与示例：`tests/`(6 用例) + `tests/fixtures/two_layer.json`。
  - 文档：`README.md`、`CLAUDE.md`、`docs/json_contract.md`。

**验证结果**
- 本机 numpy 2.4.6 / pydantic 2.12.4，`pytest` → 6 passed。
- `python -m weld_core.pipeline tests/fixtures/two_layer.json` 端到端产出合法 `candidates.json`（Phase 0 候选为空，符合预期）。

**关键决策**
- 有可随时使用的 Windows+CATIA V5；平台为 CATIA V5（非 3DEXPERIENCE）。
- 重叠区域用投影包围盒近似即可。

**未决 / 风险**
- CATIA 面搜索对多实例零件会漏检 → 测试件先用未实例化零件。
- 顶点提取可靠性需 Phase 1 用真实零件验证。

**下一步**
- 迁移到装有 CATIA 的 Windows 机开发。
- Phase 1：实现 `catia/extract_faces.py`，导出并核对 `faces.json`。
- Phase 2：填充算法核心 pairing/region/points/filtering + 补充 fixture 单测。
