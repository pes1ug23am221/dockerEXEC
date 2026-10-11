"""
tests/test_runner_polyglot.py
-----------------------------
Unit tests for polyglot image auto-detection logic in executor/runner.py.
Does NOT require Docker to be running — tests only the detect_image() and
_build_bash_command() helper functions.
"""

import tempfile
from pathlib import Path

import pytest

from executor.runner import detect_image, _build_bash_command, IMAGE_BASE, IMAGE_POLYGLOT


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path):
    """Returns a fresh empty temp directory acting as a workspace."""
    return tmp_path


# ── detect_image ───────────────────────────────────────────────────────────────

def test_detect_image_base_for_python_only(tmp_workspace):
    """Python-only workspace (requirements.txt but no JS/C files) → base image."""
    (tmp_workspace / "requirements.txt").write_text("numpy\n")
    assert detect_image(tmp_workspace) == IMAGE_BASE


def test_detect_image_base_for_empty_workspace(tmp_workspace):
    """Empty workspace → base image (safest default)."""
    assert detect_image(tmp_workspace) == IMAGE_BASE


def test_detect_image_polyglot_for_package_json(tmp_workspace):
    """package.json present → Node.js needed → polyglot."""
    (tmp_workspace / "package.json").write_text('{"name":"test"}')
    assert detect_image(tmp_workspace) == IMAGE_POLYGLOT


def test_detect_image_polyglot_for_makefile(tmp_workspace):
    """Makefile present → C/C++ needed → polyglot."""
    (tmp_workspace / "Makefile").write_text("all:\n\tgcc -o main main.c\n")
    assert detect_image(tmp_workspace) == IMAGE_POLYGLOT


def test_detect_image_polyglot_for_cmake(tmp_workspace):
    """CMakeLists.txt present → C++ build needed → polyglot."""
    (tmp_workspace / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\n")
    assert detect_image(tmp_workspace) == IMAGE_POLYGLOT


def test_detect_image_polyglot_takes_priority_over_requirements(tmp_workspace):
    """Mixed workspace (Python + Node.js) → polyglot wins."""
    (tmp_workspace / "requirements.txt").write_text("numpy\n")
    (tmp_workspace / "package.json").write_text('{"name":"test"}')
    assert detect_image(tmp_workspace) == IMAGE_POLYGLOT


# ── _build_bash_command ────────────────────────────────────────────────────────

def test_bash_command_always_has_run_sh(tmp_workspace):
    script = _build_bash_command(tmp_workspace)
    assert "bash run.sh" in script


def test_bash_command_includes_pip_for_requirements(tmp_workspace):
    (tmp_workspace / "requirements.txt").write_text("numpy\n")
    script = _build_bash_command(tmp_workspace)
    assert "pip install" in script


def test_bash_command_includes_npm_for_package_json(tmp_workspace):
    (tmp_workspace / "package.json").write_text('{"name":"t"}')
    script = _build_bash_command(tmp_workspace)
    assert "npm install" in script


def test_bash_command_has_set_e(tmp_workspace):
    """set -e must always be present so failures abort early."""
    script = _build_bash_command(tmp_workspace)
    assert script.startswith("set -e")
