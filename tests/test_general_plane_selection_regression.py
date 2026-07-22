from __future__ import annotations

from pathlib import Path

from scripts import run_general_plane_selection_regression as regression


def test_regression_command_runs_selection_evaluation_then_pipeline(monkeypatch, tmp_path: Path):
    run_dir = tmp_path / "data" / "part-a" / "20260722-170000-generic-regression"
    calls: list[tuple[str, list[str]]] = []

    def fake_select(part_id: str, **_kwargs):
        calls.append(("select", [part_id]))
        run_dir.mkdir(parents=True)
        return run_dir

    def fake_evaluate(argv: list[str]):
        calls.append(("evaluate", argv))
        return 0

    def fake_pipeline(argv: list[str]):
        calls.append(("pipeline", argv))
        return 0

    monkeypatch.setattr(regression, "run_registered_general_plane_selection", fake_select)
    monkeypatch.setattr(regression, "evaluation_main", fake_evaluate)
    monkeypatch.setattr(regression, "pipeline_main", fake_pipeline)

    assert regression.main(["part-a"]) == 0
    assert calls == [
        ("select", ["part-a"]),
        ("evaluate", ["part-a", "--run-dir", str(run_dir)]),
        ("pipeline", [str(run_dir / "faces.general-selected.json"), str(run_dir / "candidates.json")]),
    ]


def test_regression_command_stops_before_pipeline_when_evaluation_fails(monkeypatch, tmp_path: Path):
    run_dir = tmp_path / "data" / "part-b" / "20260722-170001-generic-regression"
    calls: list[str] = []

    monkeypatch.setattr(regression, "run_registered_general_plane_selection", lambda *_args, **_kwargs: run_dir)

    def fake_evaluate(_argv: list[str]):
        calls.append("evaluate")
        return 1

    def fake_pipeline(_argv: list[str]):
        calls.append("pipeline")
        return 0

    monkeypatch.setattr(regression, "evaluation_main", fake_evaluate)
    monkeypatch.setattr(regression, "pipeline_main", fake_pipeline)

    assert regression.main(["part-b"]) == 1
    assert calls == ["evaluate"]
