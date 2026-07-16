# CLAUDE.md — 项目约定

> 本文件为 **ml-pipeline** 项目级指令，配合用户全局 `~/.claude/CLAUDE.md` 使用。

## 会话流程（强制）
- **每次 fresh session 开始，先阅读 `DEVLOG.md`** 熟悉当前进度与未决问题，再动手。
- **每推进一步（完成任务/阶段/重要决策）后，立刻更新 `DEVLOG.md`**：追加带日期的条目，记录做了什么、结论、下一步。
- 业务算法思路见 `PLAN.md`，数据契约见 `docs/json_contract.md`。

## 项目要点
- 目标：CATIA V5 零件上自动粗筛贴合区域并生成候选焊点（V1 不漏检为先，人工复核）。
- 架构：三层解耦 —— `catia/`(Windows/pycatia 提取+回写) ↔ JSON 契约 ↔ `src/weld_core/`(纯 Python 算法核心)。
- **`weld_core` 严禁 import pycatia/pywin32**，须保持跨平台可测。
- 开发机：现阶段 Mac（离线开发核心）；后续迁到装有 CATIA 的 Windows 机做集成。

## 环境
- 核心：conda env `weld-core`（Python 3.11，numpy/pydantic/pytest，无 CATIA）。
- CATIA：conda env `weld-catia`（Windows，pycatia+pywin32，需运行中的 CATIA V5）。
- 不改动系统/全局 Python。

## 验证
- 改动 `weld_core` 后跑 `pytest`（须全绿）。
- CATIA 侧改动在 Windows 上用 `scripts/check_env_catia.py` + 真实零件验证。
