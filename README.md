# ml-pipeline — CATIA V5 焊点自动候选识别（V1 原型）

在 CATIA V5 零件上自动粗筛可能的贴合焊接区域并生成候选焊点。

- 业务思路：[`PLAN.md`](PLAN.md)
- 数据契约：[`docs/json_contract.md`](docs/json_contract.md)
- **开发进度：[`DEVLOG.md`](DEVLOG.md)（每次开发前先读）**
- 协作约定：[`CLAUDE.md`](CLAUDE.md)

> 开发环境：Windows + 运行中的 CATIA V5（`catia/` 层的硬依赖；`src/weld_core/` 不需要 CATIA
> 打开，但依赖 `cadquery`/`OCP` 做 STEP 离线解析）。

## 架构（三层解耦）

```
CATIA ──①extract(COM)──▶ faces.json ──②enrich(STEP+OCP,补顶点)──▶ faces.json
                                                                        │
                                                                        ▼
                                                          ③core(纯Python+numpy)
                                                                        │
                                                                        ▼
                                                              candidates.json
                                                                        │
                                                          ④write(COM)──▶ CATIA
```

- `catia/extract_faces.py` — pycatia 逐面提取（面积/法向/零件号），需要 **Windows + 运行中的
  CATIA V5**。`vertices` 字段恒为空（CATIA COM 逐面顶点提取不可靠，见 `DEVLOG.md`）。
- `catia/export_step.py` — 把当前活动文档导出成 STEP（`Document.ExportData`），需要
  **Windows + 运行中的 CATIA V5**，是 ①→② 之间的桥接步骤。
- `scripts/enrich_faces_with_step.py` — 离线解析同一文档的 STEP 导出（`weld_core.step_geometry`，
  基于 `cadquery`/`OCP`，**不需要 CATIA 打开**），按零件名+几何匹配把 `vertices` 补进
  `faces.json`。
- `src/weld_core/` — 纯算法核心（`pairing`/`region`/`points`/`filtering` + `pipeline.py`
  编排），**不依赖 CATIA**，可在不打开 CATIA 的情况下单独跑 `pytest`。`step_geometry.py` 虽然
  在这个包里，但只依赖 `cadquery`/`OCP`（跨平台，非 CATIA 专有），不违反这条约束。
- `catia/write_candidates.py` — pycatia 回写，把 `candidates.json` 建成 CATIA 里真实的
  `Weld_Candidates` 点集合，需要 **Windows + 运行中的 CATIA V5**。重复运行按候选点 id 原地更新
  坐标/参数，不依赖任何删除类 API（这套环境里删除操作不可靠，见 `DEVLOG.md`）。
- `scripts/run_full_pipeline.py` — 一键串联上述①~④，Phase 4 新增，见下方"运行"一节。
- `src/weld_core/data_layout.py` — 原始输入登记、运行目录和 `manifest.json` 的统一约束。
- `scripts/inspect_run.py` — 查看某次运行与其原始零件输入的对应关系。
- `scripts/select_general_planes.py` / `scripts/evaluate_general_plane_selection.py` /
  `scripts/run_general_plane_selection_regression.py` — 通用 CAD face 选面、显式离线参考评测和
  回归串联入口；生产选面只读取 `primary_model`，参考 STEP 只在评测命令中使用。

## 环境

项目本地 `.venv`（本机无 conda，不使用 `environment*.yml`）：
```bash
python -m venv .venv
.venv\Scripts\pip install pycatia pywin32 numpy "pydantic>=2" cadquery pytest
.venv\Scripts\python .venv\Scripts\pywin32_postinstall.py -install   # 注册 COM
.venv\Scripts\pip install -e .
```

- `pytest` / `weld_core` 相关命令不需要打开 CATIA（`step_geometry.py` 只需要 `cadquery`/`OCP`，
  不需要 pycatia/CATIA 运行）。
- `catia/` 下的脚本需要 CATIA V5 已打开：先跑 `python scripts/check_env_catia.py` 确认能连上。
- `.venv` 是项目本地虚拟环境，不影响系统/全局 Python。

## 运行

## 数据目录与追溯

原始零件与每次运行结果严格分离：

```text
raw_data/<part-id>/                         # 原始 CAD、焊点标注、验证参考 + manifest.json
data/<part-id>/<YYYYMMDD-HHMMSS>-<label>/   # 单次运行全部产物 + manifest.json
```

`raw_data/component/` 登记主装配体和 `SPOT.step` 标注；
`raw_data/component-simplify/` 登记小零件及其平面导出参考文件，后者只用于验证平面提取正确性，
不参与焊点评测。运行清单记录输入 SHA-256、参数和产物路径；用以下命令快速查询：

```bash
python scripts/inspect_run.py component [run-id]
```

独立脚本可继续传入显式路径，但其输入应取自 `raw_data/<part-id>/`，输出应写入一个运行目录。

通用选面的跨件默认最大 plane gap 为 1.5 mm，same-part pair 默认始终关闭。此默认仅在
`component-simplify` 的受管离线回归满足 recall≥75%、precision≥80%，并完成 AABB 复核和
same-part 风险隔离后启用；参考 STEP/truth 只由显式离线评测与分析命令读取，绝不会成为生产
selector、pipeline 或候选生成的输入。该证据只限单数据集，不代表未知零件或跨零件泛化。数据集
边界和跨零件门槛见 `docs/dataset_generalization.md`。

## 运行

核心算法（离线，不需要 CATIA）：
```bash
python -m weld_core.pipeline data/component/<run-id>/faces.json data/component/<run-id>/candidates.json
```

CATIA 提取（需 CATIA V5 已打开，目标 Part/Product 为当前 active document）：
```bash
python catia/extract_faces.py data/component/<run-id>/faces.json [--part-number NAME] [--limit N]
```
每次运行会在 `logs/` 生成一份人类可读的耗时/吞吐性能日志。

STEP 顶点补全（离线，不需要 CATIA，STEP 输出位于本次运行目录）：
```bash
python scripts/enrich_faces_with_step.py data/component/<run-id>/faces.json data/component/<run-id>/component.stp data/component/<run-id>/faces.enriched.json
```

STEP 导出（需 CATIA V5 已打开，目标 Product/Part 为当前 active document）：
```bash
python catia/export_step.py data/component/<run-id>/component.stp
```
> 传入路径会被转成绝对路径再调用 `Document.ExportData`——CATIA 的 COM 调用对相对路径会直接报
> 一个无信息量的通用错误，详见 `DEVLOG.md`。

CATIA 回写（需 CATIA V5 已打开，目标 Product 为当前 active document）：
```bash
python catia/write_candidates.py data/component/<run-id>/candidates.json
```
> **保存结果时用原生 `Document.SaveAs`（`.CATProduct`/`.CATPart`），不要导出 STEP** ——
> STEP 是中性交换格式，不携带 CATIA 的对象名字/参数，往返一次会丢掉每个焊点的 `wc_NNN` 名字和
> `_info` 元数据（坐标本身不受影响）。详见 `DEVLOG.md`。

一键跑通全链路（需 CATIA V5 已打开，目标 Product 为当前 active document；串联上面 extract→export→
enrich→core 四步，`--write` 时再加回写）：
```bash
python scripts/run_full_pipeline.py component --run-label full [--write] [--save-native]
```
自动创建 `data/component/<run-id>/`，其中包含 `component.stp`、`faces.json`、
`faces.enriched.json`、`candidates.json`、`run.log` 和 `manifest.json`。默认不加 `--write` 时
只读 CATIA；`--save-native` 必须与 `--write` 一起使用，把原生 CATIA 结果保存到 `native/`。

## 状态
- [x] Phase 0：环境、骨架、数据契约、验证脚本、单测
- [x] Phase 1：CATIA 提取层 `catia/extract_faces.py`，已用真实装配体验证
- [x] Phase 1.5：STEP+OCP 顶点补全（`weld_core/step_geometry.py` +
      `scripts/enrich_faces_with_step.py`），已用真实装配体验证（planar 面 `manual_review`
      100%→1.7%）
- [x] Phase 2：算法核心（`pairing`/`region`/`points`/`filtering`），已用真实装配体验证
      （192 个候选焊点/41 组零件配对，间距全部落在 20-70mm）
- [x] Phase 3：CATIA 回写层 `catia/write_candidates.py`，已用真实 CATIA 会话验证（坐标/参数
      精确匹配、幂等性通过）
- [x] Phase 4：端到端集成（`catia/export_step.py` + `scripts/run_full_pipeline.py` 一键跑通，
      对真正的原生 `.CATProduct` 验证；过程中发现并修复候选点 id 跨会话不稳定的问题，详见
      `DEVLOG.md`）。调参留待工程师人工复核后续反馈，本阶段未改动 `WeldParams` 默认值。
- [x] Phase 5：通用 CAD face 选面回归链路已建立；当前只报告单数据集结果，跨零件能力需要至少
      两个未参与阈值设定的独立验证零件分别达到计划阈值后再声明。
