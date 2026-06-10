#!/usr/bin/env python3
"""Validate MCP install config shape and install readiness.

This script is intentionally read-only by default. It computes candidate catalog
fields for MCP entries so we can sample the effect before writing them back:

  mcp_schema_valid: bool
  mcp_install_state: ready | needs_config | manual | invalid
  mcp_validation_tags: list[str]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DEFAULT_INDEX = os.path.join(REPO_ROOT, "catalog", "mcp", "index.json")

INSTALL_STATES = {"ready", "needs_config", "manual", "invalid"}

_ANGLE_PLACEHOLDER_RE = re.compile(r"<[^>]+>")
_YOUR_PLACEHOLDER_RE = re.compile(r"\b(?:your|YOUR)(?:[-_\s]?[A-Za-z0-9]+)*\b")
_PATH_PLACEHOLDER_RE = re.compile(
    r"(^|[\s:=])(?:/|\.?/)?(?:absolute/)?path/to(?:/|\b)|/path/to/your/",
    re.IGNORECASE,
)
_BRACKET_PLACEHOLDER_RE = re.compile(
    r"\[(?:absolute[-_ ]?)?(?:path|your)[^\]]*\]",
    re.IGNORECASE,
)
_WINDOWS_SAMPLE_PATH_RE = re.compile(
    r"\b[A-Za-z]:\\(?:Projects|path|your)[^,\s]*",
    re.IGNORECASE,
)
_REPLACE_PLACEHOLDER_RE = re.compile(
    r"\b(?:replace[_-]?me|changeme|insert[-_ ]?your|paste\s+.*command)\b",
    re.IGNORECASE,
)
_SHELL_VARIABLE_RE = re.compile(r"(?<!\\)\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")
_SHELL_ENV_PREFIX_RE = re.compile(r"^env\s+\w+=", re.IGNORECASE)


def _walk_strings(value: Any, path: str = ""):
    """Yield (path, string_value) pairs from nested dict/list structures."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_strings(child, child_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{idx}]")
    elif isinstance(value, str):
        yield path, value


def _add_placeholder_tags(tags: set[str], path: str, value: str) -> None:
    if _ANGLE_PLACEHOLDER_RE.search(value):
        tags.add("placeholder_angle")
    if _YOUR_PLACEHOLDER_RE.search(value):
        tags.add("placeholder_your")
    if _PATH_PLACEHOLDER_RE.search(value):
        tags.add("placeholder_path")
    if _BRACKET_PLACEHOLDER_RE.search(value):
        tags.add("placeholder_bracket")
    if _WINDOWS_SAMPLE_PATH_RE.search(value):
        tags.add("placeholder_path")
    if _REPLACE_PLACEHOLDER_RE.search(value):
        tags.add("placeholder_replace")
    if _SHELL_VARIABLE_RE.search(value):
        tags.add("placeholder_variable")
    if _SHELL_ENV_PREFIX_RE.search(value):
        tags.add("shell_env_prefix")
    if path.startswith("env.") and value == "":
        tags.add("placeholder_empty_env")


def _validate_claude_mcp_schema(config: Any) -> list[str]:
    """Return schema issue tags for Claude-style MCP server config."""
    issues: list[str] = []

    if config is None:
        return ["missing_config"]
    if not isinstance(config, dict):
        return ["config_not_object"]
    if not config:
        return ["empty_config"]

    url = config.get("url")
    if isinstance(url, str) and url.strip():
        headers = config.get("headers")
        if "headers" in config and not isinstance(headers, dict):
            issues.append("headers_not_object")
        elif isinstance(headers, dict) and any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in headers.items()
        ):
            issues.append("headers_non_string")
        return issues

    command = config.get("command")
    if not isinstance(command, str) or not command.strip():
        issues.append("missing_or_blank_command")
    elif re.search(r"\s", command.strip()):
        issues.append("command_contains_whitespace")

    args = config.get("args")
    if "args" in config and not isinstance(args, list):
        issues.append("args_not_list")
    elif isinstance(args, list) and any(not isinstance(item, str) for item in args):
        issues.append("args_item_not_string")

    env = config.get("env")
    if "env" in config and not isinstance(env, dict):
        issues.append("env_not_object")
    elif isinstance(env, dict) and any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()
    ):
        issues.append("env_non_string")

    return issues


def classify_mcp_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Classify one catalog MCP entry."""
    install = entry.get("install") or {}
    config = install.get("config")

    schema_issues = _validate_claude_mcp_schema(config)
    schema_valid = not schema_issues
    tags: set[str] = set(schema_issues)

    if isinstance(config, dict):
        for path, value in _walk_strings(config):
            _add_placeholder_tags(tags, path, value)

    placeholder_tags = {
        tag
        for tag in tags
        if tag.startswith("placeholder_") or tag == "shell_env_prefix"
    }

    if not schema_valid:
        state = "manual" if tags == {"missing_config"} else "invalid"
    elif placeholder_tags:
        state = "needs_config"
    else:
        state = "ready"

    return {
        "mcp_schema_valid": schema_valid,
        "mcp_install_state": state,
        "mcp_validation_tags": sorted(tags),
    }


def _load_entries(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return [entry for entry in data if isinstance(entry, dict)]


def _sample_rows(
    entries: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    sample_per_state: int,
) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry, validation in zip(entries, validations):
        state = validation["mcp_install_state"]
        if len(samples[state]) >= sample_per_state:
            continue
        samples[state].append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "source_url": entry.get("source_url"),
                "install_method": (entry.get("install") or {}).get("method"),
                "install_config": (entry.get("install") or {}).get("config"),
                **validation,
            }
        )
    return {state: samples.get(state, []) for state in sorted(INSTALL_STATES)}


def build_report(
    entries: list[dict[str, Any]],
    sample_per_state: int,
) -> dict[str, Any]:
    validations = [classify_mcp_entry(entry) for entry in entries]
    state_counts = Counter(v["mcp_install_state"] for v in validations)
    schema_counts = Counter(str(v["mcp_schema_valid"]).lower() for v in validations)
    tag_counts = Counter(
        tag for validation in validations for tag in validation["mcp_validation_tags"]
    )

    return {
        "total": len(entries),
        "schema_valid_counts": dict(sorted(schema_counts.items())),
        "install_state_counts": {
            state: state_counts.get(state, 0) for state in sorted(INSTALL_STATES)
        },
        "validation_tag_counts": dict(tag_counts.most_common()),
        "samples": _sample_rows(entries, validations, sample_per_state),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify MCP install configs for schema validity and readiness."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INDEX,
        help="Path to catalog MCP index JSON.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write JSON report.",
    )
    parser.add_argument(
        "--sample-per-state",
        type=int,
        default=8,
        help="Number of sample entries to include for each install state.",
    )
    args = parser.parse_args()

    entries = _load_entries(args.input)
    entries = [entry for entry in entries if entry.get("type") == "mcp"]
    report = build_report(entries, args.sample_per_state)

    print(f"total: {report['total']}")
    print(f"schema_valid_counts: {report['schema_valid_counts']}")
    print(f"install_state_counts: {report['install_state_counts']}")
    print(f"validation_tag_counts: {report['validation_tag_counts']}")

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"report written: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
