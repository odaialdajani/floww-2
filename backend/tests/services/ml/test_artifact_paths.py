from pathlib import Path

import pytest

from services.ml.artifact_paths import resolve_artifact_path


def test_windows_git_link_uses_the_existing_real_artifact(tmp_path):
    target = tmp_path / "trained.joblib"
    target.write_bytes(b"binary-model-data")
    link = tmp_path / "production.joblib"
    link.write_text("trained.joblib", encoding="utf-8")
    assert resolve_artifact_path(link) == target
    assert resolve_artifact_path(target) == target


def test_link_cannot_escape_its_model_directory_or_cycle(tmp_path):
    link = tmp_path / "production.joblib"
    link.write_text("../other.joblib", encoding="utf-8")
    with pytest.raises(ValueError, match="directory"):
        resolve_artifact_path(link)
    link.write_text("production.joblib", encoding="utf-8")
    with pytest.raises(ValueError, match="cycle"):
        resolve_artifact_path(link)


def test_missing_target_is_not_a_model(tmp_path):
    link = tmp_path / "production.joblib"
    link.write_text("missing.joblib", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        resolve_artifact_path(link)
