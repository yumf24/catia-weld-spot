# component-simplify 平面算法测试报告

**测试时间**：2026-07-22 15:36 +08:00
**运行目录**：`data/component-simplify/20260722-153636-result-analysis/`
**结论**：当前冻结模板选面算法在其唯一受支持的注册主 STEP 输入上通过精确 CAD 面验收：40 个
目标 face 全部选中，无额外选面，precision 和 recall 均为 **100.00%**。

## 1. 测试范围与判定口径

本次测试覆盖当前 `component-simplify` 的冻结模板选面路径：

1. 运行时仅解析注册的主 STEP，并校验其 SHA-256、冻结 face 的零件号、稳定 STEP face index
   与边界指纹；生成 `faces.selected.json` 和完整 `selection_audit.json`。
2. 仅在评测阶段读取人工 `surface_reference` STEP，使用 OCCT `BRepAlgoAPI_Common` 计算 CAD
   修剪面边界的公共面积与覆盖率。投影 AABB 不参与最终通过判定。
3. 将选中的 face 送入当前核心候选生成流程，确认模板输入可被下游消费。

正式选面验收阈值如下：

| 指标 | 阈值 |
|---|---:|
| 无向法向夹角 | `<= 0.5°` |
| 平面距离 | `<= 0.05 mm` |
| source face 覆盖率 | `>= 0.95` |
| precision | `> 0.90` |
| recall | `> 0.95` |

## 2. 输入与可追溯性

| 项目 | 值 |
|---|---|
| 主 STEP | `raw_data/component-simplify/component_simplify.step` |
| 主 STEP SHA-256 | `8c79d3364640245c035702cd382aad0022a0740280f74f72212a5b6c15287856` |
| 人工参考 STEP（只供构建/评测） | `raw_data/component-simplify/component_simplify_surface.step` |
| 参考 STEP SHA-256 | `d035d1f9106d870b2bbe21c0aacf7e09bd05250baefe66bf788e677728d6a2ff` |
| 冻结模板 | `templates/component-simplify/plane-selection-template.json` |
| 冻结模板 SHA-256 | `2c83bc2105ed87d4fec4756127f6933d2f49976f87126297a52b96782e0f0aca` |
| 主 STEP 面数 / 平面数 | 2834 / 525 |
| 参考 STEP 面数 / 平面数 | 89 / 40 |

该模板按 SHA-256 精确绑定上述主 STEP。主 STEP 改版、face index 改变或边界指纹不一致时，运行
会以非零退出并且不写出部分选面结果；不能以放宽几何容差绕过，必须重新构建并验收模板。

## 3. 执行的命令

```powershell
.venv\Scripts\python scripts\select_template_planes.py component-simplify --run-label result-analysis
.venv\Scripts\python scripts\evaluate_template_plane_selection.py component-simplify --run-dir data\component-simplify\20260722-153636-result-analysis
.venv\Scripts\python -m weld_core.pipeline data\component-simplify\20260722-153636-result-analysis\faces.selected.json data\component-simplify\20260722-153636-result-analysis\candidates.json
.venv\Scripts\python -m pytest --basetemp .pytest_cache\result-full
```

## 4. 运行时选面结果

| 指标 | 结果 |
|---|---:|
| 主 STEP 平面数 | 525 |
| 冻结模板选中 | 40 |
| 明确排除 | 485 |
| 选面审计状态 | 通过 |

每个主 STEP 平面均出现在 `selection_audit.json` 中。40 个目标面记录为
`template_identity_and_fingerprint_verified`；其余 485 个均以 `not_in_frozen_template` 明确排除。
这避免了旧的“同平面远处小面”或“擦边 AABB 相交”被当作匹配的情况。

## 5. 精确 CAD 面验收结果

| 指标 | 结果 | 验收条件 | 判定 |
|---|---:|---:|---|
| 选中 face 数 | 40 | — | 通过 |
| 参考 face 数 | 40 | — | 通过 |
| TP / FP / FN | 40 / 0 / 0 | — | 通过 |
| precision | 1.0000（100.00%） | `> 0.90` | 通过 |
| recall | 1.0000（100.00%） | `> 0.95` | 通过 |
| 最大法向夹角 | 0.0003008° | `<= 0.5°` | 通过 |
| 最大平面距离 | 0.0000005584 mm | `<= 0.05 mm` | 通过 |
| 最低 source 覆盖率 | 0.9997845（99.978%） | `>= 0.95` | 通过 |
| source 覆盖率范围 | 0.9997845–1.0000000 | `>= 0.95` | 通过 |
| 公共面积范围 | 233.0929–4497.5929 mm² | 正面积 | 通过 |

参考覆盖率范围为 0.9968224–1.0021963。略高于 1 的数值来自独立 STEP 导出面在 OCCT 布尔运算的
微小几何容差；它不影响正式判定，正式判定以 source 覆盖率、法向与平面距离为准。

## 6. 下游候选生成结果

核心流程成功消费本运行目录的 `faces.selected.json`，生成 `candidates.json`：

| 指标 | 结果 |
|---|---:|
| 候选数 | 13 |
| layer type | 13 个 `two_layer` |
| selected face 来源 | `faces.selected.json` |
| 模板 SHA / 主 STEP SHA | 已写入候选元数据 |
| 运行清单状态 | `completed` |

该结果证明冻结选面产物已接入下游流程。它**不**代表焊点位置的真实召回率或精确率：本报告的
100% 指标仅针对“人工参考表面映射为单个 CAD face”的选面问题。焊点效果需要另行用真实焊点
`ground_truth.json` 对候选点进行 3D 距离评测。

## 7. 回归测试

`.venv\Scripts\python -m pytest --basetemp .pytest_cache\result-full`：**72 passed**（23.84 秒）。

该套件包含精确公共面积、边/点接触拒绝、非共面/超容差拒绝、多参考面覆盖去重、标签歧义拒绝、
模板 SHA/index/指纹失配拒绝、运行时不读取参考 STEP，以及受管模板输入接入核心流程的回归用例。

## 8. 产物索引

- `data/component-simplify/20260722-153636-result-analysis/faces.selected.json`
- `data/component-simplify/20260722-153636-result-analysis/selection_audit.json`
- `data/component-simplify/20260722-153636-result-analysis/plane_selection_evaluation.json`
- `data/component-simplify/20260722-153636-result-analysis/plane_selection_evaluation.md`
- `data/component-simplify/20260722-153636-result-analysis/candidates.json`
- `data/component-simplify/20260722-153636-result-analysis/manifest.json`

## 9. 适用边界

本结论仅适用于上述精确 SHA-256 的 `component-simplify` 主 STEP，不能外推到新零件、重新导出或
修改后的 STEP。人工参考 STEP 在日常选面运行中不被读取；它只能用于模板构建和独立验收。若源
模型变化，应重新构建标签、冻结模板、执行精确评测，并以新的受管运行目录记录结果。
