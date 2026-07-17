# CLAUDE.md — 项目约定

## 会话流程（强制）
- **每次 fresh session 开始，先阅读 `DEVLOG.md`** 熟悉当前进度与未决问题，再动手。
- **每推进一步（完成任务/阶段/重要决策）后，立刻更新 `DEVLOG.md`**：追加带日期的条目，记录做了什么、结论、下一步。
- 业务算法思路见 `PLAN.md`，数据契约见 `docs/json_contract.md`。

## 项目要点
- 目标：CATIA V5 零件上自动粗筛贴合区域并生成候选焊点（V1 不漏检为先，人工复核）。
- 架构：三层解耦 —— `catia/`(pycatia 提取+回写) ↔ JSON 契约 ↔ `src/weld_core/`(纯 Python 算法核心)。
- **`weld_core` 严禁 import pycatia/pywin32**：即使现在开发和运行都在同一台 Windows 机上，
  这条也保留——保证核心算法能脱离运行中的 CATIA 单独跑 `pytest`，不与提取/回写层耦合。
- 开发环境：Windows + 运行中的 CATIA V5（`catia/` 层的硬依赖）。

## 环境
- 项目本地 `.venv`（本机无 conda，不用 `environment*.yml`）：
  `python -m venv .venv` → `pip install pycatia pywin32 numpy "pydantic>=2"` → `pip install -e .`。
- 装完 pywin32 需跑一次 `python .venv/Scripts/pywin32_postinstall.py -install` 注册 COM。
- 不改动系统/全局 Python。

## 验证
- 改动 `weld_core` 后跑 `pytest`（须全绿），不需要 CATIA 打开。
- CATIA 侧改动先用 `scripts/check_env_catia.py`（需 CATIA 已打开）确认能连上，再用真实零件验证。
- `catia/extract_faces.py` 每次运行会在 `logs/` 生成耗时/吞吐性能日志（已在 `.gitignore`）。

## Git
- 仓库已 `git init` 并有提交历史。大体积 CAD 输入（`.step`/`.CATPart`/`.CATProduct`）和运行产物
  （`logs/`）已在 `.gitignore`，不会误入库；无需为此重新初始化或调整忽略规则。
