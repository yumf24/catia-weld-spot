# CLAUDE.md — Agent 指南

> 本文件为 **ml-pipeline** 项目唯一 Agent 指南。`AGENTS.md` 仅链接本文件，不维护独立内容。

## Agents-first 模式
- 本仓库采用 Agents-first 开发模式。
- 人类仅负责高层算法、架构与设计决策。
- Agents 负责所有具体实现、修改、重构、测试和维护。

## Session 初始化（强制）
- 每次 fresh session 开始时，必须先阅读 `DEVLOG.md` 中最近的项目进展。
- 每次 fresh session 开始时，必须查看最近的 Git commit 信息。
- 每次 fresh session 开始时，必须先启用仓库内 `.venv`；命令使用 `.venv\Scripts\python`，环境安装和开发都使用`.venv`环境。
- 业务算法思路见 `docs/PLAN.md`，数据契约见 `docs/json_contract.md`。

## 任务完成（强制）
- 每次完成任务后，必须更新 `DEVLOG.md`。
- 每次完成任务后，必须提交 Git commit。
- 每次完成任务后，必须确保 working tree 保持干净。

## DEVLOG 维护规范
- 内容保持精炼、准确、简短。
- 按时间倒序排列，最新在前。
- 每条记录必须包含完整日期和时间。
- 仅保留近期且仍有价值的项目进展。
- 当文件超过 500 行时，必须删除过时记录并压缩至合理长度。

## 文档结构
- 长期项目文档统一放在 `docs/` 下。
- 当前长期文档包括 `docs/PLAN.md`、`docs/ARCHITECTURE.md`、`docs/json_contract.md`。

## 项目要点
- 目标：CATIA V5 零件上自动粗筛贴合区域并生成候选焊点（V1 不漏检为先，人工复核）。
- 架构：三层解耦 —— `catia/`(Windows/pycatia 提取+回写) ↔ JSON 契约 ↔ `src/weld_core/`(纯 Python 算法核心)。
- **`weld_core` 严禁 import pycatia/pywin32**，须保持跨平台可测。
- 开发机：现阶段 Mac（离线开发核心）；后续迁到装有 CATIA 的 Windows 机做集成。

## 验证
- 改动 `weld_core` 后跑 `pytest`（须全绿）。
- CATIA 侧改动在 Windows 上用 `scripts/check_env_catia.py` + 真实零件验证。
