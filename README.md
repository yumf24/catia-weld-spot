# ml-pipeline — CATIA V5 焊点自动候选识别（V1 原型）

在 CATIA V5 零件上自动粗筛可能的贴合焊接区域并生成候选焊点。

- 业务思路：[`PLAN.md`](PLAN.md)
- 数据契约：[`docs/json_contract.md`](docs/json_contract.md)
- **开发进度：[`DEVLOG.md`](DEVLOG.md)（每次开发前先读）**
- 协作约定：[`CLAUDE.md`](CLAUDE.md)

> 开发机：现阶段在 Mac 上离线开发算法核心；集成阶段迁移到装有 CATIA V5 的
> Windows 机（提取/回写只能在 Windows 运行）。

## 架构（三层解耦）

```
CATIA(Win) ──extract──▶ faces.json ──core(Mac)──▶ candidates.json ──write──▶ CATIA(Win)
  pycatia                中间契约      纯Python+numpy    中间契约          pycatia
```

- `src/weld_core/` — 纯算法核心，**不依赖 CATIA**，可在 Mac 上开发/测试。
- `catia/` — pycatia 适配（提取 / 回写），**仅 Windows** 且需运行中的 CATIA V5。

## 环境

### 核心环境（Mac / 跨平台，无 CATIA）
```bash
conda env create -f environment.yml
conda activate weld-core
pytest                       # 运行单元测试
python scripts/check_env_core.py
```

### CATIA 环境（Windows，需 CATIA V5 运行）
```bash
conda env create -f environment-catia.yml
conda activate weld-catia
pip install -e .
python scripts/check_env_catia.py   # 打开 CATIA 后运行
```

> conda 创建的是独立命名环境，不影响系统/全局 Python。

## 运行（离线核心，Mac 可用）
```bash
python -m weld_core.pipeline tests/fixtures/two_layer.json data/candidates.json
```

## 状态
- [x] Phase 0：环境、骨架、数据契约、验证脚本、单测
- [ ] Phase 1：CATIA 提取层（`catia/extract_faces.py`）
- [ ] Phase 2：算法核心（pairing / region / points / filtering）
- [ ] Phase 3：CATIA 回写层（`catia/write_candidates.py`）
- [ ] Phase 4：端到端集成、调参、日志、文档
