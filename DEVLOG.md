# DEVLOG — 开发进度记录

> 每次 fresh session 先读本文件；每推进一步后立即在顶部追加带日期的条目。
> 最新在上。日期格式 YYYY-MM-DD。

---

## 2026-07-22 16:17:56 +08:00 — G04 离线参考评测

**做了什么**
- 新增 `weld_core.general_plane_selection_evaluation`，仅在显式离线评测输入中使用参考 CAD face，构建 source face 真值映射并输出 TP/FP/FN、precision/recall 和逐 face 诊断。
- 真值映射使用 part、无向法向夹角、平面距离、投影后 OCCT 精确公共面积和 source/reference 双向覆盖率；无匹配、低覆盖和多 source 歧义均失败，不自动猜测。
- 新增 `scripts/evaluate_general_plane_selection.py` 作为离线评测 CLI；新增 `scripts/select_general_planes.py` 无 reference 依赖的运行时入口骨架，供 G05 继续实现。
- `docs/ALG_updatev2.json` 中 `G04_offline_reference_evaluation` 标记为通过。

**验证结果**
- `.venv\Scripts\python -m pytest tests\test_general_plane_selection_evaluation.py --basetemp .pytest_cache\g04-evaluation`：**8 passed**。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\g04-full`：**80 passed**。
- `rg -n "surface_reference|component_simplify_surface" src\weld_core\general_plane_selection.py scripts\select_general_planes.py`：退出码 **1**，运行时通用选面路径无参考 STEP 命中。

---

## 2026-07-22 16:11:55 +08:00 — G03 通用平面选面几何契约

**做了什么**
- 新增 `weld_core.general_plane_selection`，定义通用选面参数、平面 face、pair 审计、精确投影 overlap 测量和去重选面结果；不包含 template、reference 或数据集特定字段。
- 对平行且有间隙的候选 face，将第二张 CAD face 投影到公共比较平面后使用 OCCT boolean common 计算真实公共面积、双向覆盖率和评分；AABB 仅作为预筛。
- 实现同 part 默认排除、无向法向夹角、平面间隙、最小有效宽度、最小公共面积、覆盖率阈值和完整拒绝原因审计；同一 face 通过多个 pair 时只选中一次并保留支持 pair 追溯。
- `docs/ALG_updatev2.json` 中 `G03_general_selection_contract_and_geometry` 标记为通过。

**验证结果**
- `.venv\Scripts\python -m pytest tests\test_general_plane_selection_geometry.py --basetemp .pytest_cache\g03-geometry`：**10 passed**。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\g03-full`：**72 passed**。

---

## 2026-07-22 16:06:41 +08:00 — G02 移除冻结模板运行路径

**做了什么**
- 删除模板构建、模板选面、模板评测脚本，以及 `weld_core` 中的模板构建/运行时选择模块、模板文件和专属测试。
- `weld_core.pipeline` 恢复为统一消费任意 `FacesDocument`，不再按 `component-simplify`、受管选面文件名、模板哈希或主 STEP 哈希改变行为；受管目录中只登记通用 `candidates` 产物。
- `CandidatesMeta` 删除模板追溯字段；`CLI.md` 与 `docs/json_contract.md` 删除当前模板命令和候选元数据契约暴露，保留 STEP/OCP 几何与下游候选生成能力。
- `docs/ALG_updatev2.json` 中 `G02_remove_frozen_template_path` 标记为通过。

**验证结果**
- `rg -n "plane-selection-template|frozen_template|template_plane_selection|build_plane_selection_template|select_template_planes|faces\.selected|template_sha256|component-simplify.*template" src scripts tests CLI.md docs/json_contract.md templates`：退出码 **1**，指定范围无命中。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\g02-full`：**62 passed**。
- `.venv\Scripts\python -m weld_core.pipeline tests\fixtures\two_layer.json .pytest_cache\g02-candidates.json`：成功生成 **3** 个候选。

---

## 2026-07-22 16:01:19 +08:00 — G01 通用选面迁移基线与清点

**做了什么**
- 新增 `docs/generic_plane_selection_migration_inventory.md`，记录 G01 的干净基线、component-simplify 数据集统计、冻结模板链路待移除范围和可保留的通用 OCP/STEP 几何能力。
- 明确 `2834/525` 与 `89/40` 仅是数据集回归事实，冻结模板历史 40 TP/0 FP/0 FN 仅是单数据集历史指标，不得作为生产常量、特例分支或泛化能力证据。
- `docs/ALG_updatev2.json` 中 `G01_preflight_and_deprecation_inventory` 标记为通过；本步不改变算法行为。

**验证结果**
- `git status --short`：G01 开始前工作区干净。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\g01-full`：**72 passed**。
- `.venv\Scripts\python scripts\check_plane_selection_baseline.py component-simplify`：主 STEP **2834 faces / 525 planar**，参考 STEP **89 faces / 40 planar**。

---

## 2026-07-22 15:50:03 +08:00 — 新增算法流程说明文档

**做了什么**
- 新增 `docs/ALGORITHM.md`，基于当前 `catia/`、`scripts/` 与 `src/weld_core/` 实现梳理完整算法流程。
- 文档按执行顺序覆盖受管运行、CATIA 面提取、STEP 顶点富化、冻结模板选面、核心配对/区域/布点/过滤、候选输出、CATIA 回写与评测分支，并补充 Mermaid 线性流程图。

**验证结果**
- 人工核对文档步骤与 `scripts/run_full_pipeline.py`、`scripts/select_template_planes.py`、`weld_core.pipeline`、`weld_core.template_plane_selection`、`weld_core.pairing/region/points/filtering` 等关键实现一致。
- 本次仅更新文档，未运行 `pytest`。

---

## 2026-07-22 15:42:00 +08:00 — 通用选面改造计划（v2）

**做了什么**
- 新增 `docs/ALG_updatev2.json`，取代后续继续冻结模板的方向：明确完全移除 component-simplify 专属模板链路，人工参考 STEP 只允许离线评测，生产逻辑不得依赖样本的 SHA、face identity、已知数量或标签。
- 计划定义了通用选面几何：以面间平行度、间隙、跨 part 策略、精确修剪边界公共面积/覆盖率和可审计 pair 为依据，AABB 只作预筛。
- 计划按 G01–G07 给出清理、通用几何、离线真值评测、通用运行时、回归集成及多零件泛化门槛；所有步骤初始均为 `pass=false`，供 fresh session 顺序执行。

**验证结果**
- 待本次文件 JSON 校验、diff 检查和提交后完成；本次仅制定计划，未执行 G01–G07 的任何算法改动。

---

## 2026-07-22 15:37:00 +08:00 — component-simplify 当前平面算法复测

**做了什么**
- 新建受管运行 `data/component-simplify/20260722-153636-result-analysis/`，以当前冻结模板执行选面、精确 CAD 面评测和下游候选生成。
- 在项目根目录新增 `RESULT.md`，记录输入 SHA、阈值、逐阶段命令、审计统计、精确几何指标、候选结果、产物索引和适用边界。

**验证结果**
- 525 个主 STEP 平面中选中 40 个、排除 485 个；精确验收 TP/FP/FN 为 **40/0/0**，precision/recall 均为 **100.00%**。
- 40 个通过面最大法向夹角为 **0.0003008°**、最大平面距离为 **0.0000005584 mm**、最低 source 覆盖率为 **99.978%**；均优于正式阈值。
- 核心流程消费 `faces.selected.json`，生成 **13** 个 two-layer 候选；`.venv\Scripts\python -m pytest --basetemp .pytest_cache\result-full`：**72 passed**。

---

## 2026-07-22 15:32:00 +08:00 — S09 冻结模板选面文档与收尾

**做了什么**
- 更新 `docs/json_contract.md`：补充冻结模板、`faces.selected.json` 和 `selection_audit.json` 的字段、身份/哈希约束及输入改版后的重建要求；明确人工参考 STEP 仅可用于模板构建和评测。
- 更新 `CLI.md`：加入模板构建、运行时选面和精确评测入口，说明 SHA 不匹配时的失败行为、验收阈值与 component-simplify 核心流程必须消费 `faces.selected.json` 的约束。
- `docs/ALG_update.json` 中 S09 标记为通过；S01–S09 均已完成。该冻结模板仅适用于已登记的主 STEP SHA，原始人工参考仅作构建/评测用途，任何 STEP 改版均必须重新构建和验收模板。

**验证结果**
- `.venv\Scripts\python -m json.tool docs\ALG_update.json > NUL`：JSON 有效，S01–S09 的 `pass` 均为 `true`。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\s09-full`：全部测试通过。
- `git diff --check`：通过。

---

## 2026-07-22 15:26:00 +08:00 — S08 component-simplify 端到端验收运行

**做了什么**
- 创建独立受管运行目录 `data/component-simplify/20260722-152546-acceptance/`，依次完成冻结模板选面、精确选面评测和候选点生成；运行清单为 `completed`，登记选面、审计、评测及候选产物。
- 验收仅以注册主 STEP/OCP 作为选面几何真值；人工参考 STEP 仅由评测命令读取。主/参考 SHA、冻结模板路径和 SHA、参数与正式指标均写入受管清单及产物。
- `docs/ALG_update.json` 中 S08 标记为通过。

**验证结果**
- `.venv\Scripts\python scripts\select_template_planes.py component-simplify --run-label acceptance`：选中 **40** 个冻结 face。
- `.venv\Scripts\python scripts\evaluate_template_plane_selection.py component-simplify --run-dir data\component-simplify\20260722-152546-acceptance`：**precision 100.00%，recall 100.00%**。
- `.venv\Scripts\python -m weld_core.pipeline ...\faces.selected.json ...\candidates.json`：生成 **13** 个候选；`scripts\inspect_run.py` 确认四项必需产物均已登记。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\s08-full`：**72 passed**。

---

## 2026-07-22 15:23:00 +08:00 — S07 冻结模板选面接入核心流程

**做了什么**
- `weld_core.pipeline` 在 component-simplify 的受管运行目录中强制只接受登记的 `faces.selected.json`；误传 `faces.enriched.json` 或缺失冻结模板追溯信息会以非零退出。
- 候选输出的 `meta` 新增 selected-face 来源、冻结模板 SHA-256 和主 STEP SHA-256；受管 `candidates.json` 同步登记到运行清单。通用 `faces.json` 流程保持兼容且不写模板专属元数据。
- `docs/ALG_update.json` 中 S07 标记为通过，并补充候选元数据契约。

**验证结果**
- `.venv\Scripts\python -m pytest tests\test_pipeline.py tests\test_template_plane_selection.py --basetemp .pytest_cache\s07-targeted`：**8 passed**（原通用流程、冻结模板输入强制、候选 face 范围和追溯字段）。
- `.venv\Scripts\python -m weld_core.pipeline data\component-simplify\20260722-151828-s06-evaluation\faces.selected.json data\component-simplify\20260722-151828-s06-evaluation\candidates.json`：生成 **13** 个候选；全部关联 face 均属于 40 个冻结选面。

---

## 2026-07-22 15:18:00 +08:00 — S06 冻结模板的精确选面评测

**做了什么**
- 新增 `weld_core.exact_plane_selection_evaluation` 与 `scripts/evaluate_template_plane_selection.py`：仅在评测命令中读取人工 `surface_reference` STEP，以 OCCT 布尔公共 CAD 面积、法向、平面距离及 source 覆盖率计算单 CAD face 口径的 TP/FP/FN、precision 和 recall；投影 AABB 不参与任何通过判断。
- 评测输出并登记 `plane_selection_evaluation.json` 与 Markdown 报告，逐参考面保留所有候选、公共面积、双向覆盖率、几何误差、拒绝原因和歧义状态；未命中或歧义不会被猜测为匹配。
- `docs/ALG_update.json` 中 S06 标记为通过，并在 JSON 契约中记录评测产物及阈值。

**验证结果**
- `.venv\Scripts\python -m pytest tests\test_exact_plane_selection_evaluation.py --basetemp .pytest_cache\s06-unit`：**2 passed**（TP/FP/FN、95% 覆盖、法向和平面距离拒绝）。
- `.venv\Scripts\python scripts\select_template_planes.py component-simplify --run-label s06-evaluation` 后执行精确评测：**precision 100.00%，recall 100.00%**；运行目录 `data/component-simplify/20260722-151828-s06-evaluation/` 已登记选面、审计和评测产物。

---

## 2026-07-22 15:15:00 +08:00 — S05 冻结模板运行时选面

**做了什么**
- 新增 `weld_core.template_plane_selection` 与 `scripts/select_template_planes.py`：运行时仅读取注册的主 STEP，先严格核验主输入 SHA-256，再校验每个冻结的 part、稳定 STEP face index 与边界指纹；任何不一致均以非零退出且不写出选面结果。
- 成功时输出符合 `FacesDocument` 的 `faces.selected.json` 与完整 `selection_audit.json`；审计覆盖全部 525 个主模型平面（40 个选中、485 个以 `not_in_frozen_template` 排除），并将两个产物登记到受管运行清单。
- `data_layout` 支持运行只核验指定输入角色，避免模板运行时读取人工 `surface_reference` STEP；`docs/ALG_update.json` 中 S05 标记为通过。

**验证结果**
- `.venv\Scripts\python scripts\select_template_planes.py component-simplify --run-label template-selection`：成功选出 **40** 个 face；运行清单仅记录并校验 `primary_model`。
- `.venv\Scripts\python -m pytest tests\test_template_plane_selection.py --basetemp .pytest_cache\s05-template-selection`：**4 passed**（稳定输出、索引/指纹/SHA 失配拒绝、完整排除审计）。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\s05-full`：**69 passed**。

---

## 2026-07-22 15:10:00 +08:00 — S04 冻结选面模板契约

**做了什么**
- 新增 `weld_core.plane_selection_template`：将 S03 的精确审计标签冻结为版本化模板，并在反序列化时拒绝缺字段、重复 face 身份、错误 SHA、错误边界指纹及低覆盖率条目。
- `scripts/build_plane_selection_template.py --output` 现在输出受控模板；已生成 `templates/component-simplify/plane-selection-template.json`，包含主/参考 SHA-256、阈值、40 个单 CAD face 的稳定索引、面积、重心、法向、边界顶点哈希、覆盖率和参考追溯。
- 新增 6 项模板契约回归；`docs/ALG_update.json` 中 S04 标记为通过。

**验证结果**
- `.venv\Scripts\python scripts\build_plane_selection_template.py component-simplify --output templates\component-simplify\plane-selection-template.json`：**40/40** 标签并成功写入模板。
- `.venv\Scripts\python -m pytest tests\test_plane_selection_template.py --basetemp .pytest_cache\s04-template-test`：**6 passed**。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\s04-full-basetemp`：**65 passed**。

---

## 2026-07-22 15:02:00 +08:00 — S03 精确参考面标签

**做了什么**
- 新增 `weld_core.plane_reference_labels`：按零件号、无向法向 ≤0.5°、平面距离 ≤0.05 mm 和精确 CAD 公共面积，给每个参考平面建立唯一的主 STEP 单 CAD face 标签，并保留全部候选、覆盖率、拒绝原因与歧义状态。
- `StepFace` 保留仅供内存几何操作的 OCCT face；新增 `scripts/build_plane_selection_template.py` 的 `--dry-run` 标签构建入口，构建前核验两个注册原始输入的 SHA-256。
- 为独立 STEP 导出的同一修剪面补充 0.003 mm OCP 布尔 fuzzy 容差（远小于 0.05 mm 平面契约）；法向/平面预检仍先执行，擦边和点接触仍不匹配。
- 新增一对一、擦边、重叠歧义和来源切分的合成 OCP 回归；`docs/ALG_update.json` 中 S03 标记为通过。

**验证结果**
- `.venv\Scripts\python scripts\build_plane_selection_template.py component-simplify --dry-run`：**40/40** 参考平面建立唯一可审计标签。
- `.venv\Scripts\python -m pytest tests\test_exact_face_overlap.py tests\test_plane_reference_labels.py --basetemp .pytest_cache\basetemp`：**13 passed**。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\s03-full-basetemp`：**59 passed**。

---

## 2026-07-22 14:44:29 +08:00 — S02 CAD face 精确公共面积

**做了什么**
- 新增 `weld_core.exact_face_overlap`：以 OCP `BRepAlgoAPI_Common` 和 `BRepGProp.SurfaceProperties` 计算两个已完成共面校验的 CAD face 的公共面积、源/参考双向覆盖率和可诊断拒绝原因。
- 正式匹配前强制法向夹角不大于 `0.5°`、平面距离不大于 `0.05 mm`；擦边、点接触和零面积公共形状均不能通过。
- 多个参考面覆盖同一源面时，先对公共形状做 OCP 融合，再测量并集面积，避免重叠区域重复累计。
- 新增 9 项合成 OCP 回归：完全/95%/部分重合、边界或点接触、非共面及超阈值拒绝、参考面重叠并集。
- `docs/ALG_update.json` 中 S02 标记为通过。

**验证结果**
- `.venv\Scripts\python -m pytest tests\test_exact_face_overlap.py --basetemp .pytest_cache\basetemp`：**9 passed**。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\basetemp`：**55 passed**。

---

## 2026-07-22 14:40:20 +08:00 — S01 选面改造前基线预检

**做了什么**
- 新增只读 `scripts/check_plane_selection_baseline.py`：先核验 `component-simplify` 原始清单的 SHA-256 与文件大小，再报告主 STEP 和人工参考 STEP 的面数/平面面数；不创建运行目录、不读取或修改任何算法产物。
- 新增本地回归测试，验证报告包含两个已核验输入，并固定主模型 `2834/525`、参考模型 `89/40` 的面/平面数基线。
- `docs/ALG_update.json` 中 S01 标记为通过。

**验证结果**
- 原始输入哈希核验通过：主模型 `8c79d336…c15287856`，参考模型 `d035d1f9…728d6a2ff`；报告面/平面数分别为 `2834/525` 和 `89/40`。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\basetemp`：**46 passed**。
- `.venv\Scripts\python -m pytest tests\test_step_geometry.py --basetemp .pytest_cache\basetemp`：**5 passed**。

---

## 2026-07-22 13:50:57 +08:00 — component-simplify CATIA 运行时复核

**做了什么**
- 按用户要求在仓库 `.venv` 安装 `pycatia 0.10.0` 与 `pywin32 312`；`scripts/check_env_catia.py` 已连接到运行中的 CATIA V5。
- 在同一 COM 进程打开注册的 `component_simplify.step`，以不带 `--write` 的方式运行完整流程。CATIA 实际提取 3125 个面、375 个平面。
- 导入的 STEP Product 在 CATIA `ExportData` 阶段报 COM 异常，故保留失败事实并使用已核验的注册 `primary_model` STEP 回退执行顶点补全、核心算法和运行时平面验证；生成 17 个候选点，未写回 CATIA。

**验证结果**
- 运行目录：`data/component-simplify/20260722-134641-plane-validation/`，状态 `completed_with_raw_step_fallback`。顶点补全 369/375（6 个未匹配）。
- CATIA 运行时平面 vs 40 个参考平面：算法平面 375，39 个匹配算法面、336 个额外平面；36/40 个参考面匹配（recall **90.00%**，precision **10.40%**），未通过完整金标准。

---

## 2026-07-22 12:44:33 +08:00 — component-simplify 平面参考验证落地

**做了什么**
- 新增 `weld_core.plane_validation` 和 `scripts/validate_plane_reference.py`：读取受管原始清单并核验哈希，将算法平面与 `surface_reference` 以零件号、无向法向、平面距离和投影 AABB 重叠进行多对多匹配。
- 验证结果写入受管运行目录的 `plane_validation.json` 与 Markdown 报告，记录逐面匹配误差、TP/FP/FN、precision/recall；只有两项指标均为 100% 才标记通过。支持后续传入 `faces.enriched.json` 复核 CATIA 完整流程。
- 补充 CLI 与 JSON 契约文档，新增法向反向、一对多切分、边界不重叠及超阈值的单元测试。

**验证结果**
- 离线运行：`data/component-simplify/20260722-124419-plane-validation/`。参考平面 40/40 均被检出（recall **100%**）；算法平面 525 个中 44 个映射到参考，481 个按完整金标准口径为额外平面（precision **8.38%**），结论未通过。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\basetemp`：**45 passed**。
- CATIA 复核未执行：CNEXT 正在运行，但本机没有 `weld-catia` Conda 环境，base 环境也未安装 `pycatia`/`pywin32`；未改动全局环境或 CATIA 文档。

---

## 2026-07-22 12:23:14 +08:00 — 原始 CAD 与运行产物目录解耦、可追溯清单落地

**做了什么**
- 新增 `raw_data/<part-id>/` 与 `data/<part-id>/<run-id>/` 目录契约；`raw_data` 登记不可变原始输入，`data` 每次运行单独建目录。两类 `manifest.json` 记录输入角色、SHA-256、参数、状态和产物索引。
- 新增 `weld_core.data_layout`：校验安全的 part/run 标识、核验原始输入哈希、创建不冲突的时间戳运行目录、登记产物、查询最新运行；新增只读 `scripts/inspect_run.py` 用于反向定位原始数据和结果。
- `scripts/run_full_pipeline.py` 改为接受 `part-id`，自动输出至受管运行目录；新增 `--run-label` 和仅随 `--write` 可用的 `--save-native`。原生 CATIA 输出及同目录生成的 CATPart 文件清单会写入运行清单。
- 独立真实焊点提取和评测命令在输出位于运行目录时自动登记 `ground_truth`/`evaluation` 产物，保留任意路径调试兼容性。
- 迁移本地历史数据：`component.step`/`SPOT.step` 进入 `raw_data/component/`；`component_simplify.step`/`component_simplify_surface.step` 进入独立 `raw_data/component-simplify/`，明确其为平面提取正确性验证基准；历史 JSON 按端到端、全量、零件过滤、真实焊点提取分入各自历史运行目录。已删除原 `data/` 根目录的 CATIA 临时锁/零字节文件。
- 更新 `.gitignore`、README、CLI、PLAN、JSON 契约与路径注释；新增小零件/平面参考 STEP 的 OCP 回归校验。

**验证结果**
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\basetemp`：**41 passed**（含小零件参考数据的 2834/525 与 89/40 面/平面基准）。
- `scripts/inspect_run.py component legacy-20260717-e2e` 正确显示原始输入及历史产物；两份原始清单 SHA-256 核验通过。
- `py_compile` 与 `git diff --check` 通过；文档和代码中的现行旧 `data/...` 路径引用已清除（DEVLOG 历史记录除外）。

---

## 2026-07-22 11:54:57 +08:00 — CLAUDE.md 补充 fresh session 环境要求

**做了什么**
- 在 `CLAUDE.md` 的 Session 初始化要求中补充：fresh session 必须先启用仓库内 `.venv`，命令使用 `.venv\Scripts\python`。
- 精简更新核心环境说明，明确核心命令使用仓库内 `.venv`，不改动系统/全局 Python。

**验证结果**
- 纯文档改动，未运行测试。

---

## 2026-07-22 11:51:44 +08:00 — 本地核心开发环境安装完成

**做了什么**
- 在仓库内创建 `.venv`，用 editable dev 模式安装 `weld-core` 及当前项目依赖。
- 已安装并验证核心依赖：`numpy 2.4.6`、`pydantic 2.13.4`、`pytest 9.1.1`、`cadquery 2.8.0`。
- 未改动系统/全局 Python。

**验证结果**
- `.venv\Scripts\python scripts\check_env_core.py` 通过。
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\basetemp` 通过：37 passed。

**备注**
- 直接运行 pytest 会因默认临时目录 `C:\Users\admin\AppData\Local\Temp\pytest-of-admin` 权限受限报错；在当前沙箱环境需显式使用仓库内 `--basetemp .pytest_cache\basetemp`。

---

## 2026-07-17 — 新增 CLI.md：汇总全部命令行入口

**做了什么**
- 用户要求做一份文档，列出项目现有的全部命令行功能：对应代码路径、输入/输出、用途，
  并把评测指标（`evaluation.json` 的 `summary` 字段含义）作为"indicators"说明放在
  评测命令下面。
- 新建 `CLI.md`：按 pipeline 顺序（环境检查 → 提取面数据 → 导出 STEP → 用 STEP 补全
  顶点 → 运行核心算法 → 回写候选点 → 一键端到端 → 提取真实焊点 → 评测候选点）逐一列出
  10 个命令入口，每个都写明代码路径、需不需要 CATIA、输入/输出文件、一句话用途、
  命令行示例；顶部加了一张速查表。"评测候选点"一节末尾加了"评测指标说明"小节
  （TP/FN/FP/recall/precision/mean_error_mm/max_error_mm 逐项解释）+ 上条记录里跑出的
  真实数据基准表（5/10/15/20/30mm 容忍度下的 recall/precision）。
- 没有新增/改动代码，纯文档整理，信息来源是各脚本自己的 docstring/argparse 定义和
  上一条 DEVLOG 记录的真实评测结果，没有引入新结论。

**下一步**
- 无阻塞，等待用户下一步指示（例如按 Phase 5 记录里提到的"按零件分组看漏检分布"排查
  recall 缺口，或推进其他方向）。

---


## 2026-07-17 — Phase 5 完成：新增真实焊点评测（`weld_core.evaluate`），真实数据显示明显 recall 缺口

**做了什么**
- 目标：用户提供的 `data/SPOT.step` 是真实焊点标记（不是零件几何），希望拿它和算法产出的
  候选焊点对比，评测漏检/误检情况，要求有容忍度阈值。
- 先探测 `data/SPOT.step` 的结构（新写的一次性探测脚本，未入库）确认可行性：
  - 572 个面全部被 OCCT 判定为 `GeomAbs_Sphere`，半径恰好 3mm——这条和上上条记录
    （2026-07-16 "STEP+OCP 顶点提取方案验证通过"）里"第一次拿错测试对象"时的发现一致，
    只是这次反过来利用它：SPOT.step 本来就是"焊点标记球"文件，正好可以当真实焊点的来源。
  - 每个焊点被导出成 2 个半球面（不是 1 个封闭球面），但两个半球面的 `BRepAdaptor_Surface.
    Sphere().Location()` 返回的解析球心完全相同（同一个球的两半），去重后 572 面 → 恰好
    286 个唯一球心，每个对应 1 个真实焊点。
  - **坐标系核对**（关键前提，必须先确认才能做 3D 距离比较）：`SPOT.step` 球心 bbox
    （X: -558.8~547.8, Y: -739.9~-218.7, Z: -92.8~590.1）与同一装配体产出的
    `data/component_e2e.candidates.json`（200 候选）bbox（X: -558~547.6,
    Y: -721.8~-218.7, Z: -85.3~590.2）几乎完全重合——确认两者是同一全局坐标系，
    可以直接做 3D 距离比较，不需要额外对齐/变换。
  - 另确认 `SPOT.step` 里每个球的 XCAF 实例名（如 `04021210-R60_WP`）不是真实装配体的
    PartNumber（真实零件命名是 `1EAVWXKUA9` 这类随机字符串）——评测按纯 3D 坐标距离匹配，
    不按零件/面配对，这个名字只作为结果里的追溯标签。
- 实现：
  - `src/weld_core/step_geometry.py`：把原来 `parse_step_faces` 私有的 `_walk` 递归重构成
    接受一个 `face_fn` 回调的通用版本（装配树遍历/实例名解析/位置矩阵累乘这部分逻辑不重复
    造轮子），新增 `parse_step_spheres()`——按 `BRepAdaptor_Surface.GetType() ==
    GeomAbs_Sphere` 直接读解析球心/半径（比 `parse_step_faces` 用的"顶点平面拟合"判平面完全
    不同的路子：球类型在 STEP 里保真，之前发现"丢失"的只是 `GeomAbs_Plane`），按球心距离
    （容差 0.5mm，远小于 20mm 最小点间距，不会误并两个真实焊点）合并同一个球的多个面。
  - `src/weld_core/schema.py`：新增 `GroundTruthPoint`/`GroundTruthDocument`（真实焊点）、
    `EvalMatch`/`EvalSummary`/`EvaluationDocument`（评测结果）+ 对应 load helper。
  - `src/weld_core/evaluate.py`（新模块，纯 Python/numpy，不依赖 pycatia）：核心是"按距离从近
    到远贪心一对一匹配"（每对真实焊点-候选点在容忍度内就算候选对，按距离排序，从近到远认领，
    任一方被认领后退出后续匹配）——这是点集检测评测里的标准近似算法（类似 COCO 关键点匹配），
    不是精确最优分配，但在这个场景（几百个点，真实焊点间距 ≥20mm 而合理容忍度是几 mm）不会
    和精确解产生分歧，不必为此引入 `scipy`。V1"不漏检为先"的原则决定了 `recall`（真实焊点
    命中率）是首要指标，`precision`（候选点里多少是有效的）次要——多余候选交给人工复核，
    不算失败，这条在模块 docstring 里写明了。CLI 用法同 `pipeline.py` 的 `python -m
    weld_core.xxx` 风格。
  - `scripts/extract_ground_truth.py`（新脚本，纯离线 OCP，不需要 CATIA 运行）：
    `data/SPOT.step` → `ground_truth.json`。
  - 测试：`tests/test_evaluate.py`（8 个用例，纯合成数据，不需要 OCP：完美匹配/漏检/多余候选/
    容忍度边界内外/多个候选选最近的/一对一不会多对一/真实焊点或候选点为空时 recall/precision
    的边界定义）；`tests/test_step_geometry.py` 加了一个 OCP 现场构造两个球（模拟两个真实焊点）
    验证 `parse_step_spheres` 按位置正确合并/不误并的用例。全部 37 个用例（原 27 + 新 10）通过。
  - `docs/json_contract.md` 补充 `ground_truth.json`/`evaluation.json` 契约；`PLAN.md`
    新增 P5 阶段和 M5 里程碑。

**真实数据评测结果**（`data/SPOT.step` 解析出的 286 个真实焊点 vs 同一装配体今天上午
Phase 4 记录里跑出的 `data/component_e2e.candidates.json`，200 个候选点）
- 容忍度扫了几档：5mm → recall 6.6%/precision 9.5%；**10mm → recall 22.7%/precision
  32.5%**（mean/max 匹配误差 6.3mm/10.0mm）；15mm → recall 39.2%/precision 56.0%；
  20mm（逼近 20mm 最小点间距上限，再大就有跨点误匹配风险）→ recall 48.3%/precision 69.0%；
  30mm → recall 54.9%/precision 78.5%。
- **结论：即使把容忍度放宽到接近点间距设计上限，真实焊点的命中率也只能到 ~50%，还有一半
  左右的真实焊点在任何合理容忍度下都找不到邻近的候选点**——这不是容忍度选择的问题，是当前
  V1 配对/布点阈值（法向夹角 ≤5°、面间距 ≤0.1mm、点间距 20-70mm 等）产出的候选点位置和真实
  焊点位置系统性地对不上。和 PLAN.md"V1 不漏检为先"的目标有明显差距。
- 遗留的 `unmatched_ground_truth`（漏检的真实焊点 id 列表）已完整输出在
  `data/component_e2e.evaluation.json` 里，可供后续排查具体漏在哪些零件/区域。

**结论**
- Phase 5（评测能力）完成：现在有了可重复运行的"真实焊点 vs 候选点"评测链路，容忍度可调
  （`--tolerance`），recall 优先于 precision 的取向和 PLAN.md 一致。
- 评测结果本身是一个新发现的、比较严重的产品问题（约一半真实焊点漏检），不是本次改动的
  bug，是评测揭示出的算法现状——是否要回头调整 `WeldParams` 阈值、改进配对/布点算法，还是
  V1 阶段先接受这个 recall 水平继续人工复核兜底，需要产品侧/工程师决策。

**下一步**
- 和用户/产品侧过一遍 `unmatched_ground_truth` 里漏检的真实焊点分布（`label` 字段按零件
  分组能看出漏检是否集中在特定零件/区域），判断是配对阈值太严（法向夹角/面间距）还是布点
  阶段的问题（区域中点位置系统性偏移），再决定要不要调 `WeldParams` 默认值。
- 如果要调参，评测链路已经就位，可以直接在每次调参后重跑
  `scripts/extract_ground_truth.py`（一次性，SPOT.step 不变不用重跑）+
  `python -m weld_core.evaluate` 看 recall/precision 变化，不需要再手工比对。

---

## 2026-07-17 — Phase 4 完成：补齐一键复现脚本，真正端到端跑通原生文件全链路，
过程中发现并修复了候选点 id 跨会话不稳定的问题

**背景**
- 检查发现 CATIA 当前打开的活动文档就是上一条记录 SaveAs 出来的
  `data/component_with_weld_candidates_native.CATProduct`（全部 34 个子文档都绑定了磁盘路径）——
  正是 Phase 4 一直缺的"真正的原生文件"。和用户确认：就用这个文件做端到端验证；本轮不调整
  `WeldParams` 阈值（留给工程师后续反馈）；把一直靠 `python -c` 手动调用的 STEP 导出补成正式脚本。

**新增脚本**
- `catia/export_step.py`：把 `Document.ExportData(path, "stp", overwrite=True)` 这个之前临时用
  `python -c` 调用的操作正式化，风格对齐 `extract_faces.py`/`write_candidates.py`（同样的 `logs/`
  运行日志模式）。**踩坑**：pycatia 的 `export_data` 对相对路径只会打一条 warning（"be explicit and
  use absolute filenames"），不会拦截——但 CATIA COM 侧对相对路径直接报一个无信息量的通用
  `com_error`（`ExportData 失败`），换成绝对路径后立刻成功。脚本内部对传入路径统一做
  `.resolve()`，不依赖调用方传对。
- `scripts/run_full_pipeline.py`：一键串联 extract→export→enrich→core→（`--write` 时）write 五步，
  直接 import 复用四个已有脚本/模块的现成函数（`catia/extract_faces.py::extract_faces`、新的
  `export_step`、`scripts/enrich_faces_with_step.py::enrich_faces_document`、
  `weld_core.pipeline.run`、`catia/write_candidates.py` 的三个函数），没有重新实现任何逻辑；
  `catia/`/`scripts/` 都不是包（没有 `__init__.py`），沿用现有脚本"加 `sys.path` 再 import"的模式。
  `--write` 默认关闭（跑一键脚本默认只读 CATIA、写本地 JSON/STEP，不改动活动文档），显式传才回写。
  先用 `--limit 50` 跑通 smoke test（17/17 平面面匹配成功）确认链路本身没问题，再跑全量。

**真实端到端跑通结果**（对着 `component_with_weld_candidates_native.CATProduct` 跑
`run_full_pipeline.py --write`，`logs/run_full_pipeline_..._20260717-101448.log`）
- 提取：10706 个面（1926 planar），**537s（约 19.9 faces/sec）**——比 DEVLOG 早前记录的
  "3~4 faces/sec、全量要 45~70 分钟" 快了近 6 倍，具体原因未深究（这次读取失败/COM 异常次数可能
  更少），记录下来但不作为可靠估算依据，以后需要预估耗时时以实测为准。
- STEP 导出 35s，STEP+OCP enrich 30s（1903/1926 planar 面匹配成功，比上次全量记录的 1892/1925
  略高，同样未深究、在正常波动范围内），核心算法 0.57s，产出 **200 个候选点**（比 Phase 2 基线的
  192 个多 8 个，同样是因为这次多匹配到的 11 个 planar 面带来的新候选，量级上合理）。

**发现并修复：候选点 id 跨会话不稳定，导致回写时静默把已复核的点挪到错误位置**
- 回写阶段报 `8 created, 192 updated, 0 newly stale`，表面看起来像是"基本幂等、只多了 8 个"，但
  逐个比对新旧 `candidates.json` 发现同一个 `wc_NNN` id 在新旧两次跑里对应的坐标能差出去
  **700+ mm**（如 `wc_058`）——192 个同名 id 里有 **163 个** 关联的 `faces` 字段前后不一致，
  即回写把这些点悄悄挪到了完全不同的物理位置，而不是"多找到 8 个"这么简单。用位置做最近邻比对
  （忽略 id）证实：旧的 192 个候选里 174 个在新结果集里能找到几乎精确重合（<0.01mm）的对应点——
  说明两次跑找到的物理候选点集合本身高度一致，问题出在 **`wc_NNN` 编号本身不稳定**。
- **根因**：`weld_core/pipeline.py::run()` 之前按"配对被发现的顺序"给候选点编号
  （`for i, c in enumerate(candidates, start=1)`），而配对发现顺序由 `pairing.find_mating_pairs`
  遍历输入 `faces` 列表的顺序决定，这个顺序又来自 `faces.json` 里面 face 的原始顺序——**同一个文档
  两次独立 COM 提取，`Selection.Search` 返回 face 的顺序不保证一致**（这次和 Phase 2 基线之间还
  隔着一次 STEP 重新导入，内部顺序更容易变化）。而 `catia/write_candidates.py` 的"原地更新"策略
  是按 id 字符串匹配的（详见该文件 2026-07-16 的设计说明）——**编号不稳定 + 按 id 匹配回写，两者
  叠加，就会把一个物理点在无声无息间移动到另一个物理点曾经的位置**，且不会报错、不会被
  `manual_review`/`STALE` 机制捕捉到（这两个机制防的是"点消失"，不是"同名点被意外改指向"）。这是
  Phase 3 "幂等性验证通过" 结论的一个盲点：Phase 3 只验证过"同一个 `candidates.json` 重复回写"，
  没验证过"独立重新提取一遍再回写"，而这正是 Phase 4 端到端测试要覆盖的场景。
- **修复**（`src/weld_core/pipeline.py`）：编号前按内容（`sorted(faces)` 元组 + `position`）对
  `candidates` 排序，而不是按发现顺序，使编号变成候选点内容的确定性函数，不再依赖遍历顺序。
  新增回归测试 `tests/test_pipeline.py::test_candidate_ids_stable_regardless_of_input_face_order`：
  构造两组独立的贴合面对，分别按正序和逆序喂给 `run()`，断言两次跑出来的 `id -> position` 映射
  完全一致。**28 个用例（含新增这条）全部通过。**

**现场善后**（活动文档在发现问题前已经被那一轮"跳号"结果写坏——163/192 个点被移到了错的位置）
- 先用旧基线 `data/candidates_component_full.json`（Phase 2 那 192 个、已核对过的候选）重跑一次
  `write_candidates.py`：`0 created, 192 updated, 8 newly marked stale`——把被跳号问题错误挪动的
  192 个点位置恢复回 Phase 2 复核过的坐标，同时把这一轮多出的 8 个（`wc_193`~`wc_200`）标记
  stale（符合预期：它们不在这次传入的候选集里）。
- 再用**修复后的 pipeline** 重新跑一遍核心算法（复用同一份已提取好的
  `data/component_e2e.faces.enriched.json`，不需要重新连 CATIA/重新导出 STEP）生成新的
  `data/component_e2e.candidates.json`（仍是 200 个候选，只是编号方式变了），回写：
  `0 created, 200 updated, 0 newly stale`——200 个 id 全部对上（因为这次的 id 从 1 到 200 连续，
  和文档里已存在的 `wc_001`~`wc_200` 恰好全覆盖），之前标的 stale 前缀也随更新一起清掉了。
- **验证**：用 `HybridShapePointCoord.x/y/z`（不是参数缓存值）读回 `wc_001`/`wc_050`/`wc_100`/
  `wc_150`/`wc_192`/`wc_200` 六个点的真实坐标，和 `component_e2e.candidates.json` 逐分量比对，
  **误差全部为 0.0**——确认活动文档现在的状态和修复后的候选集完全一致。

**结论**
- Phase 4 的核心目标——"端到端集成，不像上次因为环境问题中途换了对象"——达成：这次全程只用了一个
  原生 `.CATProduct` 文件，提取/导出/回写都对着同一个活动文档，没有再依赖 STEP 重新导入兜底。
- 顺带发现并修复了一个真实的、之前没测出来的正确性问题（id 跨会话不稳定导致回写静默错位），比
  单纯"跑通一次"更有价值——这也是为什么 DEVLOG 早前"幂等性验证通过"的表述需要修正为"仅验证了
  同输入重复回写幂等，跨会话重新提取的幂等性直到这次才被验证并证明存在缺陷，现已修复"。
- 本轮按约定**没有调整** `WeldParams` 任何阈值（`max_normal_angle_deg`/`max_gap_mm`/
  `min_spacing_mm`/`max_spacing_mm`/`min_point_distance_mm`/`min_face_width_mm` 均为
  `config.py` 里的默认值）——是否需要调参，仍然等工程师看过现在这 200 个候选点后再反馈，Phase 2
  记录里提的这个开放问题依然开放。

**下一步**
- 等工程师/产品侧对 CATIA 里当前这 200 个候选点做一次人工复核，反馈是否需要调整
  `WeldParams` 阈值。
- 三层板自动识别、`body` 字段仍是已知的简化/占位（见 Phase 2 记录），不阻塞。

---

## 2026-07-16 — 发现 STEP 导出会丢失点名/参数；改用原生 Save As；打包给同事看

**做了什么**
- 上一条记录里把 `Weld_Candidates` 导出成了 `data/component_with_weld_candidates.stp`。用户
  重新打开这个 STEP 文件后反馈"`Weld_Candidates` 没有展开的选项"——排查发现 **STEP 是中性交换
  格式，不携带 CATIA 原生的 feature 树/对象名字/参数**：重新导入后 `Weld_Candidates` 这个
  Product 级别的名字还在（PRODUCT 实体的名字保留了），但它引用的实际几何文档被 CATIA 的 STEP
  导入器改成了通用名字（如 `PartNN.CATPart`），192 个点的独立名字（`wc_001`等）和所有
  `_info` 参数都没有随之保留——即"坐标本身是对的，但名字/元数据这层信息在 STEP 往返后丢了"。
- 解决办法：不导出 STEP，改用 **原生 `Document.SaveAs` 存成 `.CATProduct`/`.CATPart`**
  （CATIA 自己的格式，不是中性交换格式，不会有这个丢失问题）。用户确认后重新走了一遍
  "关闭重开 CATIA → 导入 component.step → 跑 write_candidates.py"的干净流程（这次
  `192 created, 0 updated`，全新的一次），然后 `save_as` 到
  `data/component_with_weld_candidates_native.CATProduct`。
  - 验证：`SaveAs` 在顶层 Product 上调用，会级联把所有新增/修改过的子文档（包括之前一直没有
    绑定磁盘路径的 `Weld_Candidates.CATPart`）一起存到同一目录，不需要对每个子文档单独存一次。
  - 最终落盘 35 个文件（1 个 `.CATProduct` + 34 个 `.CATPart`：33 个真实零件 + 1 个
    `Weld_Candidates`），共 90MB。
- 用户要把这个装配体发给同事看，要求打包成一个 zip。用 PowerShell 的
  `Compress-Archive`（Git Bash 没有 `zip` 命令）把这 35 个原生文件（不含两个大 STEP 输入文件，
  同事不需要）打平打包成 `data/component_with_weld_candidates.zip`（71MB），验证了包内是
  平铺结构（没有子目录）——这一点很重要，因为 CATIA 靠"零件文件和装配体文件在同一目录"来自动
  解析组件引用，解压到不同目录会打不开。

**结论**
- **看 Weld_Candidates 里每个点的名字/参数，必须走原生 `.CATProduct`/`.CATPart`，不能用 STEP
  往返**——这是这套 CATIA COM/STEP 环境里一个通用结论，不只是这次的个例，以后任何需要保留
  CATIA 原生对象名字/参数的场景都要记得这条。
- `catia/write_candidates.py` 本身不用改：它一直操作的是内存里的活动文档，问题出在"事后怎么把
  结果存下来给人看"这一步的格式选择上，不是回写逻辑本身的问题。

**新增忽略规则**
- `.gitignore` 加了 `data/*.zip`（71MB 的打包压缩包不应该进仓库，和已有的 `data/*.step`/
  `data/*.stp` 归一类）。

**下一步**
- Phase 4：端到端集成（如果拿到真正的原生 `.CATProduct` 原文件）、调参、文档收尾——同上一条
  记录，还没变。

---

## 2026-07-16 — Phase 3 完成：`catia/write_candidates.py` 回写 CATIA，真实会话验证通过（附带三个 COM 坑）

**做了什么**
- 新增 `catia/write_candidates.py`：在当前活动文档的根 Product 下建（或复用）一个 `Weld_Candidates`
  Part 组件，内含同名 `HybridBody`，每个候选点建成一个 `HybridShapePointCoord`，点名即
  `candidate.id`（如 `wc_001`），并挂一条同名 `_info` 字符串参数记录 `faces`/`layer_type`/
  `spacing_mm`/`reason`（`PLAN.md`"输出"章节要求的字段里，坐标就是点本身，其余塞进这个参数）。

**踩坑过程（这次做了大量真实 CATIA 会话调试，记录下来避免以后重复踩）**
1. **`Selection.Delete()` 在这套 CATIA/pycatia 环境里不可靠**：无论是删整个 `HybridBody` 还是删
   单个点，`selection.add(obj); selection.delete()` 都以一个无信息量的通用 COM 错误失败（连
   `wc_doc.activate()` 之后也一样）。原计划"清空重建"的第一版设计（先删旧点再建新点）走不通。
2. **`Products.remove()` 只解绑树上的引用，不会真正关闭底层文档**：换成"整组件删除重建"
   （`Products.remove()` + 手动 `Document.close()` 旧文档）以为绕开了第 1 条，结果验证时发现
   `Document.close()` 同样不生效——`add_new_component` 再次创建同名组件时，CATIA 会静默复用
   还开着的旧 `Weld_Candidates.CATPart` 文档而不是真正给一个空文档，导致每跑一次
   `hybrid_bodies` 数量 +1、参数数量翻倍地累积。**更意外的是**：让用户在 CATIA UI 里手动删除
   同一个集合，底层文档一样没有被真正清空/关闭——说明这不是 pycatia 或某个 API 调用方式的问题，
   而是这套 CATIA 环境里"删除"这件事本身，无论是编程调用还是手动操作，都无法让一个组件的底层
   文档标识真正被回收复用。
3. **最终方案：不删除，原地更新**——`Weld_Candidates` 组件/几何集在第一次运行后就固定复用，
   之后每次运行按候选点 id 匹配已有点：存在则直接改该点的 `<body>\<point>\X`/`Y`/`Z` 参数值
   （已用 `HybridShapePointCoord.x/y/z`—— 而不是参数缓存值——读回验证，确认改参数真的会移动几何
   点本身）；不存在则新建；新一轮里消失的候选 id（比如调参后候选数变少）不删除，只在其 `_info`
   参数前加 `STALE - not present in latest run:` 前缀标记，可见但不误导。
   - 过程中还踩了一个自己代码的坑：判断"点是否已存在对应的 `_info` 参数"最初用了
     `Parameters.get_item_by_name`，这个方法是按**全限定名**（如 `Weld_Candidates\wc_001_info`）
     做精确比较，而我们一直用短名字 `wc_001_info` 去查，所以永远查不到、永远走"新建"分支——
     实测导致每次重跑都会在已有的 `wc_001_info` 旁边再建一个 `wc_001_info.1`（CATIA 自动加后缀
     去重），参数数量翻倍但没报错，不易察觉。改成包一层 `try: parameters.item(name) except:
     None`（`.item()` 短名字能正确解析，只是没有"找不到返回 None"这个安全语义，需要自己包）后
     解决，并用 `Parameters.remove(name)`（这个删除 API 反而是可靠的，和前面两个不同）清理掉了
     调试过程中产生的 191 个重复参数。

**真实会话验证结果**
- 对着真实的 `component.CATProduct`（这次是从 `data/component.step` 重新导入的，因为原生
  `.CATProduct` 文件在中途被误关闭，详见下方"环境插曲"）连续跑了三轮：
  1. 首次运行：192 个点全部新建，坐标/`_info`参数抽查（`wc_001`/`wc_096`/`wc_192`）和
     `candidates.json` 逐位精确匹配。
  2. 第二次运行（真正的幂等性验证，用的是修复后的版本）：`0 created, 192 updated, 0 newly
     marked stale`，参数总数前后都是 970，没有任何重复对象。
  3. 抽查确认：`Weld_Candidates` 组件的放置矩阵是单位阵（`get_components()` 返回
     `(1,0,0, 0,1,0, 0,0,1, 0,0,0)`），验证了"新 Part 局部坐标系 = Product 全局坐标系"这个
     前提，候选点坐标不需要额外变换。

**环境插曲（记录一下，不是这次改动本身，但解释了为什么最终对象是 STEP 导入而不是原生文件）**
- 调试过程中一度把用户当时打开的 CATIA 会话搞乱（累积了多个孤立的 `Weld_Candidates` 残留文档/
  参数），用户选择直接关闭重开 CATIA、重新导入 `data/component.step` 作为干净起点——这一步之后
  就回不到最初那个原生 `component.CATProduct` 文件了（不知道它在磁盘上的路径，这次会话里也没找）。
- `component.CATProduct`（STEP 导入产物）本身没有绑定磁盘文件路径，`Document.save()` 直接失败
  （需要 Save As）。和用户确认后，改用 `Document.ExportData` 导出（`catia/extract_faces.py`
  之前就验证过这条路径存在），产出 `data/component_with_weld_candidates.stp`
  （214MB，`.stp` 扩展名——试过 `.step`/"step" 参数组合直接报同样的通用 COM 错误，换成
  `.stp`/"stp" 才成功，和 `PLAN.md` 里"`ExportData` 支持 stp/step"这条对上了，但这次环境下
  只有 `.stp` 这个具体组合真正跑通）。文本核对确认导出内容里包含 `Weld_Candidates`。

**结论**
- Phase 3 完成：候选焊点现在能以真实几何 + 可读参数的形式出现在 CATIA 里，工程师可以直接在三维
  视图里检视，不需要再对着 JSON 坐标猜。
- 幂等性验证通过（"原地更新"策略，不依赖任何在这套环境里被证明不可靠的删除类 API）。
- 已知简化：`wc_test`（本次调试期间手滑留下的测试点）留在 `Weld_Candidates` 集合里，已标记
  stale，无需清理；三层板分类、`body` 字段占位等 Phase 2 已知简化原样保留。

**下一步**
- Phase 4：端到端集成（如果用户后续能拿到真正的原生 `.CATProduct` 文件，用
  `catia/extract_faces.py` → `scripts/enrich_faces_with_step.py` → `weld_core.pipeline` →
  `catia/write_candidates.py` 走一遍完整链路，而不是像这次一样中途因为环境问题换了对象）、
  调参、文档收尾。
- 目前 27 个 pytest 用例仍全绿，本次改动没有触碰 `weld_core` 核心逻辑。

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
