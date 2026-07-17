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
- `scripts/enrich_faces_with_step.py` — 离线解析同一文档的 STEP 导出（`weld_core.step_geometry`，
  基于 `cadquery`/`OCP`，**不需要 CATIA 打开**），按零件名+几何匹配把 `vertices` 补进
  `faces.json`。
- `src/weld_core/` — 纯算法核心（`pairing`/`region`/`points`/`filtering` + `pipeline.py`
  编排），**不依赖 CATIA**，可在不打开 CATIA 的情况下单独跑 `pytest`。`step_geometry.py` 虽然
  在这个包里，但只依赖 `cadquery`/`OCP`（跨平台，非 CATIA 专有），不违反这条约束。
- `catia/write_candidates.py` — pycatia 回写，把 `candidates.json` 建成 CATIA 里真实的
  `Weld_Candidates` 点集合，需要 **Windows + 运行中的 CATIA V5**。重复运行按候选点 id 原地更新
  坐标/参数，不依赖任何删除类 API（这套环境里删除操作不可靠，见 `DEVLOG.md`）。

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

核心算法（离线，不需要 CATIA）：
```bash
python -m weld_core.pipeline data/faces.json data/candidates.json
```

CATIA 提取（需 CATIA V5 已打开，目标 Part/Product 为当前 active document）：
```bash
python catia/extract_faces.py data/faces.json [--part-number NAME] [--limit N]
```
每次运行会在 `logs/` 生成一份人类可读的耗时/吞吐性能日志。

STEP 顶点补全（离线，不需要 CATIA，`data/*.step` 需先从 CATIA `ExportData` 导出）：
```bash
python scripts/enrich_faces_with_step.py data/faces.json data/component.step data/faces.enriched.json
```

CATIA 回写（需 CATIA V5 已打开，目标 Product 为当前 active document）：
```bash
python catia/write_candidates.py data/candidates.json
```
> **保存结果时用原生 `Document.SaveAs`（`.CATProduct`/`.CATPart`），不要导出 STEP** ——
> STEP 是中性交换格式，不携带 CATIA 的对象名字/参数，往返一次会丢掉每个焊点的 `wc_NNN` 名字和
> `_info` 元数据（坐标本身不受影响）。详见 `DEVLOG.md`。

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
- [ ] Phase 4：端到端集成、调参、日志、文档
