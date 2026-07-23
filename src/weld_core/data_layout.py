"""Managed on-disk layout for raw CAD inputs and pipeline runs.

``raw_data/<part-id>`` contains registered, immutable source assets and
``data/<part-id>/<run-id>`` contains all artifacts produced by one run.  The
manifests are deliberately plain JSON so they remain useful outside Python.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_ROOT = REPO_ROOT / "raw_data"
DATA_ROOT = REPO_ROOT / "data"
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9]+)?$")


class DataLayoutError(ValueError):
    """Raised when a requested managed-data path or manifest is invalid."""


def validate_identifier(value: str, kind: str = "identifier") -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise DataLayoutError(
            f"invalid {kind} {value!r}; use lowercase letters, digits, and "
            "single hyphens between words"
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataLayoutError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataLayoutError(f"manifest {path} must contain a JSON object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _portable_path(path: Path) -> str:
    """Prefer repository-relative paths, retaining a useful value for tests."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def raw_part_dir(part_id: str, root: Path = RAW_DATA_ROOT) -> Path:
    return root / validate_identifier(part_id, "part-id")


def data_part_dir(part_id: str, root: Path = DATA_ROOT) -> Path:
    return root / validate_identifier(part_id, "part-id")


def load_raw_manifest(part_id: str, root: Path = RAW_DATA_ROOT) -> dict[str, Any]:
    part_dir = raw_part_dir(part_id, root)
    manifest = _read_json(part_dir / "manifest.json")
    if manifest.get("part_id") != part_id:
        raise DataLayoutError(
            f"raw manifest part_id must be {part_id!r}, got {manifest.get('part_id')!r}"
        )
    if not isinstance(manifest.get("inputs"), dict) or not manifest["inputs"]:
        raise DataLayoutError(f"raw manifest {part_dir / 'manifest.json'} has no inputs")
    return manifest


def verify_raw_inputs(
    part_id: str, root: Path = RAW_DATA_ROOT, roles: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Verify registered raw input files and return portable input records."""
    part_dir = raw_part_dir(part_id, root)
    manifest = load_raw_manifest(part_id, root)
    requested_roles = set(roles) if roles is not None else None
    if requested_roles is not None:
        unknown = requested_roles - manifest["inputs"].keys()
        if unknown:
            raise DataLayoutError(f"raw manifest has no requested inputs: {', '.join(sorted(unknown))}")
    records: list[dict[str, Any]] = []
    for role, info in manifest["inputs"].items():
        if requested_roles is not None and role not in requested_roles:
            continue
        if not isinstance(info, dict) or not isinstance(info.get("path"), str):
            raise DataLayoutError(f"raw input {role!r} must contain a relative path")
        path = (part_dir / info["path"]).resolve()
        try:
            path.relative_to(part_dir.resolve())
        except ValueError as exc:
            raise DataLayoutError(f"raw input {role!r} escapes {part_dir}") from exc
        if not path.is_file():
            raise DataLayoutError(f"raw input {role!r} is missing: {path}")
        actual_hash = sha256_file(path)
        if info.get("sha256") and actual_hash != info["sha256"]:
            raise DataLayoutError(f"raw input {role!r} SHA-256 differs from its manifest")
        if info.get("size_bytes") is not None and path.stat().st_size != info["size_bytes"]:
            raise DataLayoutError(f"raw input {role!r} size differs from its manifest")
        records.append(
            {
                "role": role,
                "path": _portable_path(path),
                "sha256": actual_hash,
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def _next_run_dir(
    part_id: str, label: str, now: datetime, root: Path, run_parent: Path | None = None
) -> tuple[str, Path]:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{validate_identifier(label, 'run label')}"
    parent = run_parent if run_parent is not None else data_part_dir(part_id, root)
    candidate = parent / base
    index = 2
    while candidate.exists():
        candidate = parent / f"{base}-{index:02d}"
        index += 1
    return candidate.name, candidate


def create_run(
    part_id: str,
    label: str,
    *,
    parameters: dict[str, Any] | None = None,
    active_document: str = "",
    now: datetime | None = None,
    raw_root: Path = RAW_DATA_ROOT,
    data_root: Path = DATA_ROOT,
    run_parent: Path | None = None,
    input_roles: Iterable[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Create one empty managed run after validating its raw inputs."""
    raw_inputs = verify_raw_inputs(part_id, raw_root, input_roles)
    run_id, run_dir = _next_run_dir(part_id, label, now or datetime.now(), data_root, run_parent)
    run_dir.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "format_version": 1,
        "part_id": part_id,
        "run_id": run_id,
        "created_at": (now or datetime.now()).astimezone().isoformat(timespec="seconds"),
        "status": "running",
        "active_document": active_document,
        "raw_manifest": _portable_path(raw_part_dir(part_id, raw_root) / "manifest.json"),
        "raw_inputs": raw_inputs,
        "parameters": parameters or {},
        "artifacts": {},
    }
    _write_json(run_dir / "manifest.json", manifest)
    return run_dir, manifest


def update_run_manifest(run_dir: Path, **changes: Any) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    manifest = _read_json(path)
    manifest.update(changes)
    _write_json(path, manifest)
    return manifest


def register_artifact(run_dir: Path, name: str, path: Path, **metadata: Any) -> dict[str, Any]:
    """Register an existing artifact that must be located inside ``run_dir``."""
    path = path.resolve()
    try:
        relative = path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise DataLayoutError(f"artifact {path} is outside run directory {run_dir}") from exc
    manifest = _read_json(run_dir / "manifest.json")
    artifacts = manifest.setdefault("artifacts", {})
    artifacts[name] = {"path": str(relative), **metadata}
    _write_json(run_dir / "manifest.json", manifest)
    return manifest


def register_managed_artifact(path: Path, name: str, **metadata: Any) -> bool:
    """Register an artifact when its parent chain is a managed run directory.

    Standalone commands remain useful with arbitrary paths, so callers use
    this best-effort helper rather than requiring every output to be managed.
    """
    candidate = path.resolve().parent
    while candidate != candidate.parent:
        manifest_path = candidate / "manifest.json"
        if manifest_path.is_file():
            manifest = _read_json(manifest_path)
            if "run_id" in manifest and "part_id" in manifest:
                register_artifact(candidate, name, path, **metadata)
                return True
        candidate = candidate.parent
    return False


def find_run(part_id: str, run_id: str | None = None, root: Path = DATA_ROOT) -> Path:
    parent = data_part_dir(part_id, root)
    if not parent.is_dir():
        raise DataLayoutError(f"no runs found for part-id {part_id!r}")
    if run_id is not None:
        validate_identifier(run_id, "run-id")
        candidate = parent / run_id
        if not candidate.is_dir() or not (candidate / "manifest.json").is_file():
            raise DataLayoutError(f"run {run_id!r} not found for {part_id!r}")
        return candidate
    runs = sorted(p for p in parent.iterdir() if p.is_dir() and (p / "manifest.json").is_file())
    if not runs:
        raise DataLayoutError(f"no runs found for part-id {part_id!r}")
    return runs[-1]
