# ml-pipeline — CATIA V5 焊点自动候选识别（V1 原型）

在 CATIA V5 零件上自动粗筛可能的贴合焊接区域并生成候选焊点。

- 业务思路：[`PLAN.md`](PLAN.md)
- 数据契约：[`docs/json_contract.md`](docs/json_contract.md)
- **开发进度：[`DEVLOG.md`](DEVLOG.md)（每次开发前先读）**
- 协作约定：[`CLAUDE.md`](CLAUDE.md)

> 开发环境：Windows + 运行中的 CATIA V5（`catia/` 层的硬依赖；`src/weld_core/` 不需要 CATIA）。

## 架构（三层解耦）

```
CATIA ──extract──▶ faces.json ──core──▶ candidates.json ──write──▶ CATIA
pycatia            中间契约      纯Python+numpy   中间契约         pycatia
```

- `src/weld_core/` — 纯算法核心，**不依赖 CATIA**，可在不打开 CATIA 的情况下单独跑 `pytest`。
- `catia/` — pycatia 适配（提取 / 回写），需要 **Windows + 运行中的 CATIA V5**。

## 环境

项目本地 `.venv`（本机无 conda，不使用 `environment*.yml`）：
```bash
python -m venv .venv
.venv\Scripts\pip install pycatia pywin32 numpy "pydantic>=2"
.venv\Scripts\python .venv\Scripts\pywin32_postinstall.py -install   # 注册 COM
.venv\Scripts\pip install -e .
```

- `pytest` / `weld_core` 相关命令不需要打开 CATIA（纯 Python，无 pycatia 依赖）。
- `catia/` 下的脚本需要 CATIA V5 已打开：先跑 `python scripts/check_env_catia.py` 确认能连上。
- `.venv` 是项目本地虚拟环境，不影响系统/全局 Python。

## 运行

核心算法（离线，不需要 CATIA）：
```bash
python -m weld_core.pipeline tests/fixtures/two_layer.json data/candidates.json
```

CATIA 提取（需 CATIA V5 已打开，目标 Part/Product 为当前 active document）：
```bash
python catia/extract_faces.py data/faces.json [--part-number NAME] [--limit N]
```
每次运行会在 `logs/` 生成一份人类可读的耗时/吞吐性能日志。

## 状态
- [x] Phase 0：环境、骨架、数据契约、验证脚本、单测
- [x] Phase 1：CATIA 提取层 `catia/extract_faces.py`，已用真实装配体验证；
      顶点/边界提取有已知限制（`faces[].vertices` 恒为空），详见 `DEVLOG.md`
- [ ] Phase 2：算法核心（pairing / region / points / filtering）
- [ ] Phase 3：CATIA 回写层（`catia/write_candidates.py`）
- [ ] Phase 4：端到端集成、调参、日志、文档
