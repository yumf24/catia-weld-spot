# DEVLOG — 开发进度记录

> 每次 fresh session 先读本文件；每推进一步后立即在顶部追加带日期的条目。
> 最新在上。日期格式 YYYY-MM-DD。

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
