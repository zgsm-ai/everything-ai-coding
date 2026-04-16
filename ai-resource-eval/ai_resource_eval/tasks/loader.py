"""YAML task configuration loader.

Loads task YAML files from the package data directory or arbitrary paths,
parses them with PyYAML, and validates them with the TaskConfig Pydantic model.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ai_resource_eval.api.types import TaskConfig

# Directory containing bundled YAML task configs (sibling to this module).
_TASKS_DIR = Path(__file__).parent


def load_task_config(task_name: str) -> TaskConfig:
    """Load a built-in task configuration by name.

    Parameters
    ----------
    task_name:
        Task name matching a YAML file in the tasks directory
        (e.g. ``"skill"`` loads ``tasks/skill.yaml``).

    Returns
    -------
    TaskConfig
        Validated task configuration.

    Raises
    ------
    FileNotFoundError
        If no YAML file exists for the given task name.
    ValueError
        If the YAML content fails Pydantic validation.
    """
    path = _TASKS_DIR / f"{task_name}.yaml"
    if not path.exists():
        available = [p.stem for p in _TASKS_DIR.glob("*.yaml")]
        raise FileNotFoundError(
            f"No task config found for {task_name!r}. "
            f"Available tasks: {available}"
        )
    return load_task_config_from_path(path)


def load_task_config_from_path(path: str | Path) -> TaskConfig:
    """Load a task configuration from an arbitrary file path.

    Parameters
    ----------
    path:
        Path to a YAML task configuration file.

    Returns
    -------
    TaskConfig
        Validated task configuration.

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    ValueError
        If the YAML content fails Pydantic validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Task config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping, got {type(raw).__name__}")

    return TaskConfig(**raw)


def list_available_tasks() -> list[str]:
    """Return names of all built-in task configurations.

    Returns
    -------
    list[str]
        Sorted list of task names (without ``.yaml`` extension).
    """
    return sorted(p.stem for p in _TASKS_DIR.glob("*.yaml"))
