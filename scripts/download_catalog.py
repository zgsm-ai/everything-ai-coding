#!/usr/bin/env python3
"""Download everything-ai-coding catalog entries into a local folder structure.

Format follows awesome-claude-skills-master conventions:
  skills/<kebab-name>/SKILL.md
  mcp/<kebab-name>/.mcp.json
  prompts/<kebab-name>/PROMPT.md
  rules/<kebab-name>/RULE.md   (+ .cursorrules when available)
  plugins/<kebab-name>/.plugin.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import quote

# Reuse project utilities
sys.path.insert(0, os.path.dirname(__file__))
try:
    from .utils import to_kebab_case, fetch_raw_content, logger, github_api
except ImportError:
    from utils import to_kebab_case, fetch_raw_content, logger, github_api

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_DIR = os.path.join(SCRIPT_DIR, "..", "catalog")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "..", "catalog-download")

RAW_CSV_URLS = {
    "prompts-chat": "https://raw.githubusercontent.com/f/prompts.chat/main/prompts.csv",
    "wonderful-prompts": "https://raw.githubusercontent.com/langgptai/wonderful-prompts/main/README.md",
}

# In-memory caches for shared remote resources
_prompt_csv_cache: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quote_repo_path(path: str) -> str:
    """Percent-encode a repo-relative path for use in a raw.githubusercontent URL.

    raw.githubusercontent.com (and urllib/http.client, which require the HTTP
    request line to be ASCII) reject non-ASCII bytes in the path. Cospower rules
    carry CJK filenames (e.g. ``rules/dfx/安全.md``) → without encoding,
    ``request.encode("ascii")`` raises UnicodeEncodeError and the fetch crashes.

    ``safe="/"`` keeps the directory separators literal while percent-encoding
    every path segment (CJK, spaces, etc.). The ENCODED form is only used to
    build the fetch URL; the ORIGINAL path is still used for on-disk basenames so
    files land under their real (non-ASCII) names. Idempotent for already-ASCII
    paths (they pass through unchanged).
    """
    return quote(path, safe="/")


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _file_exists(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _build_frontmatter(**kwargs) -> str:
    lines = ["---"]
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, list):
            val = ", ".join(str(x) for x in v)
        else:
            val = str(v)
        lines.append(f"{k}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _inject_frontmatter(content: str, **kwargs) -> str:
    """Inject YAML frontmatter at the top if not already present."""
    if content.strip().startswith("---"):
        return content
    return _build_frontmatter(**kwargs) + "\n" + content


def _fetch_raw_with_backoff(
    url: str,
    retries: int = 3,
    delay: float = 0.5,
    timeout: float = 30,
) -> Optional[str]:
    """Fetch raw content from an arbitrary URL with simple backoff."""
    # GitHub raw URLs: use project fetch_raw_content if possible
    gh_match = re.match(
        r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.+)", url
    )
    if gh_match:
        repo, branch, path = gh_match.groups()
        # fetch_raw_content doesn't expose timeout; we use our own urlopen below
        # to allow larger timeouts for big files like prompts.csv.
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError, URLError

        req_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        req = Request(req_url, headers={"User-Agent": "everything-ai-coding-download"})
        for attempt in range(retries):
            try:
                with urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except (HTTPError, URLError, TimeoutError, OSError) as e:
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
                logger.warning(f"Failed to fetch {url}: {e}")
                return None
        return None

    # Fallback for non-GitHub URLs
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError, URLError

    req = Request(url, headers={"User-Agent": "everything-ai-coding-download"})
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            logger.warning(f"Failed to fetch {url}: {e}")
            return None
    return None


def _kebab_name(entry: dict) -> str:
    """Determine folder name from entry id or name."""
    return to_kebab_case(entry.get("id", entry.get("name", "unknown")))


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def _repo_branch_and_dir(entry: dict) -> tuple[Optional[str], str, Optional[str]]:
    """Extract raw GitHub repo slug, branch, and directory path from a skill install block."""
    install = entry.get("install", {})
    repo_url = install.get("repo", "")
    branch = install.get("branch", "main")
    files = install.get("files", [])
    path = install.get("path", "")

    if not repo_url:
        return None, branch, None

    # Extract owner/repo from https://github.com/owner/repo.git
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/|$)", repo_url)
    if not match:
        return None, branch, None
    repo = match.group(1)

    if files:
        return repo, branch, files[0].rstrip("/")
    if path:
        return repo, branch, path.rstrip("/")
    return repo, branch, None


def _preload_repo_trees(entries: list[dict]) -> dict[tuple[str, str], list[str]]:
    """Preload GitHub tree for all repos used by skills. Returns {(repo, branch): [paths]}."""
    cache: dict[tuple[str, str], list[str]] = {}
    needed: set[tuple[str, str]] = set()

    for entry in entries:
        if entry.get("type") != "skill":
            continue
        repo, branch, _ = _repo_branch_and_dir(entry)
        if repo:
            needed.add((repo, branch))

    for repo, branch in needed:
        data = github_api(f"repos/{repo}/git/trees/{branch}?recursive=1")
        if not data or "tree" not in data:
            cache[(repo, branch)] = []
            logger.warning(f"Failed to load tree for {repo}@{branch}")
            continue
        paths = [item["path"] for item in data["tree"] if item.get("type") == "blob"]
        cache[(repo, branch)] = paths
        logger.info(f"Loaded tree for {repo}@{branch}: {len(paths)} files")

    return cache


def _download_skill(
    entry: dict,
    output_dir: str,
    force: bool = False,
    repo_tree_cache: Optional[dict] = None,
) -> tuple[str, bool, Optional[str]]:
    """Recursively download a single skill and its attachments.

    Returns (kebab_name, success, error_msg).
    """
    name = _kebab_name(entry)
    skill_dir = os.path.join(output_dir, "skills", name)
    skill_md_path = os.path.join(skill_dir, "SKILL.md")

    repo, branch, dir_path = _repo_branch_and_dir(entry)

    # Determine files to download from preloaded tree
    files_to_download: list[str] = []
    if repo and dir_path and repo_tree_cache:
        tree = repo_tree_cache.get((repo, branch), [])
        prefix = dir_path + "/"
        files_to_download = [p for p in tree if p.startswith(prefix)]

    if files_to_download:
        downloaded = 0
        failed = 0
        for repo_path in files_to_download:
            rel_path = repo_path[len(dir_path) + 1 :]
            local_path = os.path.join(skill_dir, rel_path)

            if not force and _file_exists(local_path):
                downloaded += 1
                continue

            # Percent-encode the repo path for the raw URL — a skill dir may
            # carry non-ASCII sibling filenames; repo_path stays raw for the
            # local_path written above.
            raw = fetch_raw_content(
                repo, _quote_repo_path(repo_path), branch, quiet_404=True
            )
            if raw is not None:
                _write_file(local_path, raw)
                downloaded += 1
            else:
                failed += 1

        # Ensure SKILL.md has frontmatter if it exists
        if os.path.exists(skill_md_path):
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = _inject_frontmatter(
                content,
                name=entry.get("name", name),
                description=entry.get("description", ""),
                category=entry.get("category", ""),
            )
            with open(skill_md_path, "w", encoding="utf-8") as f:
                f.write(content)

        if failed > 0:
            return name, True, f"{failed}/{len(files_to_download)} files failed"
        return name, True, None

    # Fallback: generate minimal SKILL.md when no tree info available
    if not force and _file_exists(skill_md_path):
        return name, True, None

    content = _build_frontmatter(
        name=entry.get("name", name),
        description=entry.get("description", ""),
        category=entry.get("category", ""),
    )
    content += f"\n# {entry.get('name', name)}\n\n{entry.get('description', '')}\n"
    _write_file(skill_md_path, content)
    return name, True, None


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------

def _download_mcp(entry: dict, output_dir: str, force: bool = False) -> tuple[str, bool, Optional[str]]:
    """Generate .mcp.json for a single MCP entry. Returns (kebab_name, success, error_msg).

    Refuses to write a .mcp.json whose server config has neither ``command``
    nor ``url`` — registry.modelcontextprotocol.io commonly lists servers
    with empty install info, and downstream NormalizeMCPMetadata rejects
    them anyway. By returning failure here the entry gets dropped from the
    top-level catalog/index.json during the reconciliation pass, so every
    consumer downstream sees a clean dataset.
    """
    name = _kebab_name(entry)
    mcp_dir = os.path.join(output_dir, "mcp", name)
    mcp_path = os.path.join(mcp_dir, ".mcp.json")

    if not force and _file_exists(mcp_path):
        return name, True, None

    install = entry.get("install", {})
    config = install.get("config", {}) if isinstance(install, dict) else {}
    if not isinstance(config, dict):
        config = {}

    command = config.get("command")
    url = config.get("url")
    has_command = isinstance(command, str) and command.strip()
    has_url = isinstance(url, str) and url.strip()
    if not has_command and not has_url:
        return name, False, "no install info (missing command and url)"

    display_name = entry.get("name", name)

    # Build .mcp.json in the same shape as awesome-claude-skills-master
    mcp_data = {"mcpServers": {display_name: config}}
    _write_file(mcp_path, json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n")
    return name, True, None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _download_rule(entry: dict, output_dir: str, force: bool = False) -> tuple[str, bool, Optional[str]]:
    """Download a single rule. Returns (kebab_name, success, error_msg).

    Two install shapes are supported:
      - Plugin-bundled rule (``install.repo`` + ``install.files=[<repo-path>]``):
        fetched via the repo single-file downloader (path-faithful, frontmatter
        injected) so the work tree mirrors ``rules/<group>/<file>.md``.
      - Legacy rule (``install.files=[<raw-url>]`` only): fetched as a raw URL
        into ``.cursorrules`` + a wrapping RULE.md (original behaviour).
    """
    install = entry.get("install", {}) or {}
    if install.get("repo"):
        td, fn = _SINGLE_FILE_TYPE_SPEC["rule"]
        return _download_repo_single_file(entry, output_dir, td, fn, force)

    name = _kebab_name(entry)
    rule_dir = os.path.join(output_dir, "rules", name)
    rule_md_path = os.path.join(rule_dir, "RULE.md")
    rule_raw_path = os.path.join(rule_dir, ".cursorrules")

    if not force and _file_exists(rule_md_path):
        return name, True, None

    files = install.get("files", [])
    raw_content: Optional[str] = None
    if files:
        raw_content = _fetch_raw_with_backoff(files[0])

    if raw_content:
        _write_file(rule_raw_path, raw_content)
        # Also write a RULE.md with frontmatter for readability
        md_content = _build_frontmatter(
            name=entry.get("name", name),
            description=entry.get("description", ""),
            category=entry.get("category", ""),
        )
        md_content += f"\n# {entry.get('name', name)}\n\n```\n{raw_content}\n```\n"
        _write_file(rule_md_path, md_content)
    else:
        # Minimal RULE.md if download failed
        md_content = _build_frontmatter(
            name=entry.get("name", name),
            description=entry.get("description", ""),
            category=entry.get("category", ""),
        )
        md_content += f"\n# {entry.get('name', name)}\n\n{entry.get('description', '')}\n"
        _write_file(rule_md_path, md_content)

    return name, True, None


# ---------------------------------------------------------------------------
# Single-file plugin children (commands / subagents / templates / repo-based rules)
# ---------------------------------------------------------------------------

# type → (type-dir, primary filename). The primary file mirrors the per-type
# convention costrict-web ingest expects (typeDirAndFile). Keep aligned with
# _PRIMARY_FILE_BY_TYPE / build_catalog_bundle.TYPE_DIR_AND_FILE and the merge
# _SOURCE_TO_TYPE_DIR table.
_SINGLE_FILE_TYPE_SPEC = {
    "command":  ("commands",  "COMMAND.md"),
    "subagent": ("subagents", "AGENT.md"),
    "template": ("templates", "TEMPLATE.md"),
    "rule":     ("rules",     "RULE.md"),
}


def _download_repo_single_file(
    entry: dict, output_dir: str, type_dir: str, filename: str, force: bool = False
) -> tuple[str, bool, Optional[str]]:
    """Fetch one repo-relative file for a synthesized plugin child.

    Writes ``<type_dir>/<id>/<filename>`` with frontmatter injected, plus the
    original file preserved verbatim at its real basename so the work tree
    keeps the authentic content. Returns (kebab_name, success, error_msg).
    """
    name = _kebab_name(entry)
    out_dir = os.path.join(output_dir, type_dir, name)
    primary_path = os.path.join(out_dir, filename)

    if not force and _file_exists(primary_path):
        return name, True, None

    repo, branch, file_path = _repo_branch_and_dir(entry)
    raw_content: Optional[str] = None
    if repo and file_path:
        # Percent-encode the path for the raw URL (CJK rule filenames otherwise
        # crash urllib's ASCII request line). file_path itself stays raw for the
        # on-disk basename below.
        raw_content = fetch_raw_content(
            repo, _quote_repo_path(file_path), branch, quiet_404=True
        )

    if raw_content is None:
        # Minimal placeholder so the entry still materializes (and survives the
        # reconciliation filter) even when the upstream file 404s.
        content = _build_frontmatter(
            name=entry.get("name", name),
            description=entry.get("description", ""),
            category=entry.get("category", ""),
        )
        content += f"\n# {entry.get('name', name)}\n\n{entry.get('description', '')}\n"
        _write_file(primary_path, content)
        return name, True, "source file unavailable; wrote placeholder"

    # Preserve the verbatim file under its real basename (so SKILL.md-style
    # sibling content is faithful), and write the canonical primary file with
    # frontmatter for downstream parsers.
    if file_path:
        basename = file_path.rstrip("/").rsplit("/", 1)[-1]
        if basename and basename != filename:
            _write_file(os.path.join(out_dir, basename), raw_content)

    primary_content = _inject_frontmatter(
        raw_content,
        name=entry.get("name", name),
        description=entry.get("description", ""),
        category=entry.get("category", ""),
    )
    _write_file(primary_path, primary_content)
    return name, True, None


def _download_command(entry, output_dir, force=False):
    td, fn = _SINGLE_FILE_TYPE_SPEC["command"]
    return _download_repo_single_file(entry, output_dir, td, fn, force)


def _download_subagent(entry, output_dir, force=False):
    td, fn = _SINGLE_FILE_TYPE_SPEC["subagent"]
    return _download_repo_single_file(entry, output_dir, td, fn, force)


def _download_template(entry, output_dir, force=False):
    td, fn = _SINGLE_FILE_TYPE_SPEC["template"]
    return _download_repo_single_file(entry, output_dir, td, fn, force)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _load_prompts_csv(source: str) -> list[dict]:
    """Load and parse the shared prompts.csv into a list of dicts. Cached in memory."""
    if source in _prompt_csv_cache:
        return _prompt_csv_cache[source]

    url = RAW_CSV_URLS.get(source)
    if not url:
        return []

    raw = _fetch_raw_with_backoff(url, timeout=120)
    if not raw:
        return []

    try:
        # prompts.csv from f/prompts.chat uses standard CSV with columns like act, prompt
        # Increase field size limit to handle very long prompt cells
        csv.field_size_limit(max(csv.field_size_limit(), 2**20))
        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)
        _prompt_csv_cache[source] = rows
        return rows
    except Exception as e:
        logger.warning(f"Failed to parse prompts CSV from {source}: {e}")
        return []


def _find_prompt_text(rows: list[dict], entry_name: str) -> Optional[str]:
    """Find the prompt text matching a catalog entry name from CSV rows."""
    name_lower = entry_name.lower().strip()
    for row in rows:
        # Common column names in prompts CSV: 'act', 'prompt', 'title'
        act = (row.get("act") or row.get("title") or "").lower().strip()
        if act == name_lower:
            return row.get("prompt", "")
        # Fuzzy match: entry name contained in act or vice versa
        if name_lower in act or act in name_lower:
            return row.get("prompt", "")
    return None


def _download_prompt(entry: dict, output_dir: str, force: bool = False) -> tuple[str, bool, Optional[str]]:
    """Download/generate a single prompt. Returns (kebab_name, success, error_msg)."""
    name = _kebab_name(entry)
    prompt_dir = os.path.join(output_dir, "prompts", name)
    prompt_path = os.path.join(prompt_dir, "PROMPT.md")

    if not force and _file_exists(prompt_path):
        return name, True, None

    source = entry.get("source", "")
    prompt_text: Optional[str] = None

    if source == "prompts-chat":
        rows = _load_prompts_csv("prompts-chat")
        prompt_text = _find_prompt_text(rows, entry.get("name", ""))
    elif source == "wonderful-prompts":
        # For wonderful-prompts, the README.md is shared; we fall back to description
        prompt_text = None

    if prompt_text:
        content = _build_frontmatter(
            name=entry.get("name", name),
            description=entry.get("description", ""),
            category=entry.get("category", ""),
        )
        content += f"\n# {entry.get('name', name)}\n\n{prompt_text}\n"
        _write_file(prompt_path, content)
    else:
        # Minimal PROMPT.md from catalog metadata
        content = _build_frontmatter(
            name=entry.get("name", name),
            description=entry.get("description", ""),
            category=entry.get("category", ""),
        )
        content += f"\n# {entry.get('name', name)}\n\n{entry.get('description', '')}\n"
        _write_file(prompt_path, content)

    return name, True, None


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------

PLUGIN_REQUIRED_INSTALL_FIELDS = ("plugin_name", "marketplace_name", "marketplace_repo")


def _prepare_plugin_entries(entries: list[dict]) -> list[dict]:
    """Filter + deduplicate plugin entries before they reach the downloader.

    Upstream `catalog/plugins/index.json` carries the same plugin twice when
    both `claude-plugins-dev` and `claude-plugins-official` sync sources
    surfaced it (e.g. anthropic-superpowers + anthropics-claude-plugins-
    official-superpowers — same (marketplace_repo, plugin_name) but two
    different `id` values). The merged top-level `catalog/index.json` keeps
    only the highest `source_priority` copy; emitting both per-plugin files
    here would make 174 .plugin.json directories unreachable from backfill
    and leave their security_status / source / experience_score blank.

    This helper mirrors the merge logic so the per-plugin output set lines
    up 1:1 with the merged catalog: drop unverified rows and pick the
    highest-priority entry per (repo, plugin_name) pair (id breaks ties
    deterministically).
    """
    by_key: dict[tuple[str, str], dict] = {}
    for entry in entries:
        install = entry.get("install", {})
        if not install.get("marketplace_verified"):
            continue
        repo = install.get("marketplace_repo")
        name = install.get("plugin_name")
        if not repo or not name:
            continue
        key = (repo, name)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = entry
            continue
        prev_priority = prev.get("source_priority", 0)
        curr_priority = entry.get("source_priority", 0)
        if curr_priority > prev_priority:
            by_key[key] = entry
        elif curr_priority == prev_priority and entry.get("id", "") < prev.get("id", ""):
            by_key[key] = entry
    return list(by_key.values())


def _download_plugin(entry: dict, output_dir: str, force: bool = False) -> tuple[str, bool, Optional[str]]:
    """Emit .plugin.json for a single plugin entry. Returns (kebab_name, success, error_msg).

    Plugins have no remote content to fetch: the file is just a stable, canonical
    serialization of the catalog's install + bundle blocks so downstream ingest
    (costrict-web SyncService) can consume it like the other 4 capability types.

    Filtering + deduplication is handled upstream by _prepare_plugin_entries;
    this function only validates the required install fields as a defense in
    depth.
    """
    name = _kebab_name(entry)
    plugin_dir = os.path.join(output_dir, "plugins", name)
    plugin_path = os.path.join(plugin_dir, ".plugin.json")

    install = entry.get("install", {})
    missing = [f for f in PLUGIN_REQUIRED_INSTALL_FIELDS if not install.get(f)]
    if missing:
        return name, False, f"missing required install fields: {','.join(missing)}"

    if not force and _file_exists(plugin_path):
        return name, True, None

    # Mirror SKILL.md frontmatter shape: name/description/category/tags live at
    # the top level so ParserService can populate ParsedItem fields directly
    # (sync phase), independent of the catalog/index.json backfill phase.
    payload: dict = {
        "name": entry.get("name") or install.get("plugin_name", ""),
        "description": entry.get("description", ""),
        "category": entry.get("category", ""),
        "tags": entry.get("tags", []) or [],
        "install": install,
    }
    bundle = entry.get("bundle")
    if bundle:
        payload["bundle"] = bundle

    _write_file(plugin_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return name, True, None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

DOWNLOADERS = {
    "skill": _download_skill,
    "mcp": _download_mcp,
    "rule": _download_rule,
    "prompt": _download_prompt,
    "plugin": _download_plugin,
    # Plugin-bundled single-file children (commands/agents/templates). evaluators
    # are synthesized as type=skill and reuse _download_skill (directory fetch).
    "command": _download_command,
    "subagent": _download_subagent,
    "template": _download_template,
}


def _download_batch(
    entries: list[dict],
    output_dir: str,
    force: bool = False,
    max_workers: int = 8,
    repo_tree_cache: Optional[dict] = None,
) -> tuple[list[str], list[str]]:
    """Download a batch of entries using thread pool. Returns (success_names, error_names)."""
    successes: list[str] = []
    errors: list[str] = []

    def _task(entry: dict) -> tuple[str, bool, Optional[str]]:
        entry_type = entry.get("type", "")
        downloader = DOWNLOADERS.get(entry_type)
        if not downloader:
            return _kebab_name(entry), False, f"Unknown type: {entry_type}"
        # Small sleep to avoid hammering GitHub raw
        time.sleep(0.15)
        if entry_type == "skill":
            return downloader(entry, output_dir, force, repo_tree_cache)
        return downloader(entry, output_dir, force)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {executor.submit(_task, e): _kebab_name(e) for e in entries}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                name, ok, err = future.result()
            except Exception as exc:
                # Backstop: a downloader must never crash the whole batch. Any
                # unexpected exception (e.g. a transient network error that
                # slipped past fetch_raw_content's retry loop) is downgraded to
                # a per-entry failure so the other ~12k downloads still finish.
                errors.append(f"{name}: {exc!r}")
                logger.warning(f"Download crashed for {name}: {exc!r}")
                continue
            if ok:
                successes.append(name)
            else:
                errors.append(f"{name}: {err}")
                logger.warning(f"Download failed for {name}: {err}")

    return successes, errors


# Mapping from index.json `type` to the per-entry primary file under
# catalog-download/. Mirrors TYPE_DIR_AND_FILE in scripts/build_catalog_bundle.py
# — keep the two in sync if either changes.
_PRIMARY_FILE_BY_TYPE = {
    "skill":    ("skills",    "SKILL.md"),
    "mcp":      ("mcp",       ".mcp.json"),
    "rule":     ("rules",     "RULE.md"),
    "prompt":   ("prompts",   "PROMPT.md"),
    "plugin":   ("plugins",   ".plugin.json"),
    "command":  ("commands",  "COMMAND.md"),
    "subagent": ("subagents", "AGENT.md"),
    "template": ("templates", "TEMPLATE.md"),
}


def _filter_top_index_to_downloaded(output_dir: str) -> tuple[int, int]:
    """Rewrite catalog/index.json to drop entries whose primary file did
    not survive the download pass.

    Why: ``merge_index.py`` writes the top-level catalog/index.json from
    upstream source listings (mcp registry, mastra, antigravity, …). Those
    listings advertise more entries than ``download_catalog.py`` can
    actually fetch — repos get deleted, raw 404s, registry stubs without
    install info, etc. Without this filter the on-disk catalog-download/
    tree is a strict subset of index.json, and every downstream consumer
    (build_catalog_bundle.py, aggregate_enrichment.py, costrict-web
    ingest) has to re-discover the same orphan set independently.

    Returns (kept_count, dropped_count). Best-effort: silently no-ops if
    the top-level index does not exist (e.g. running download in isolation
    against a private catalog snapshot).
    """
    top_index_path = os.path.normpath(os.path.join(CATALOG_DIR, "index.json"))
    if not os.path.isfile(top_index_path):
        return 0, 0

    try:
        with open(top_index_path, "r", encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, json.JSONDecodeError) as err:
        logger.warning(f"could not read {top_index_path} for filter pass: {err}")
        return 0, 0

    kept: list[dict] = []
    dropped = 0
    for entry in entries:
        etype = entry.get("type") or ""
        eid = entry.get("id") or ""
        spec = _PRIMARY_FILE_BY_TYPE.get(etype)
        if not spec or not eid:
            # Unknown type or malformed entry — preserve verbatim so we
            # don't accidentally drop schema additions made elsewhere.
            kept.append(entry)
            continue
        type_dir, filename = spec
        primary_path = os.path.join(output_dir, type_dir, eid, filename)
        if os.path.isfile(primary_path):
            kept.append(entry)
        else:
            dropped += 1

    if dropped == 0:
        return len(kept), 0

    # Atomic write: tmp file then rename, so a concurrent reader never
    # observes a half-written index.
    tmp_path = top_index_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp_path, top_index_path)
    return len(kept), dropped


def run(
    output_dir: str,
    types: Optional[list[str]] = None,
    force: bool = False,
    max_workers: int = 8,
) -> None:
    """Main entry point."""
    os.makedirs(output_dir, exist_ok=True)
    # Plugin-bundled single-file children live in their own type dirs
    # (commands/subagents/templates); evaluators ride inside skills/ as
    # type=skill, rules inside the existing rules/ dir.
    types = types or [
        "skills", "mcp", "rules", "prompts", "plugins",
        "commands", "subagents", "templates",
    ]

    all_successes: list[str] = []
    all_errors: list[str] = []

    for typ in types:
        index_path = os.path.join(CATALOG_DIR, typ, "index.json")
        if not os.path.exists(index_path):
            logger.warning(f"Index not found: {index_path}")
            continue

        with open(index_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        # Plugins need de-duplication + verified gating before download so the
        # output set lines up 1:1 with the merged catalog/index.json (see
        # _prepare_plugin_entries doc for why).
        if typ == "plugins":
            before = len(entries)
            entries = _prepare_plugin_entries(entries)
            logger.info(f"plugins: filtered {before} → {len(entries)} after verified gate + (repo, plugin_name) dedupe")

        # Preload repo trees for skills to avoid duplicate API calls
        repo_tree_cache: Optional[dict] = None
        if typ == "skills":
            repo_tree_cache = _preload_repo_trees(entries)

        logger.info(f"Downloading {len(entries)} {typ}...")
        successes, errors = _download_batch(
            entries, output_dir, force, max_workers, repo_tree_cache
        )
        all_successes.extend(successes)
        all_errors.extend(errors)
        logger.info(f"{typ}: {len(successes)} succeeded, {len(errors)} failed")

    # Write error log
    if all_errors:
        log_path = os.path.join(output_dir, "download_errors.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(all_errors) + "\n")
        logger.info(f"Error log written to {log_path}")

    logger.info(f"Done. Total: {len(all_successes)} succeeded, {len(all_errors)} failed.")

    # Final reconciliation pass: drop orphan entries from the top-level
    # catalog/index.json so the on-disk tree and the manifest stay in
    # sync. See _filter_top_index_to_downloaded() for why.
    kept, dropped = _filter_top_index_to_downloaded(output_dir)
    if dropped > 0:
        logger.info(
            f"Reconciled catalog/index.json: kept {kept} entries with "
            f"on-disk files, dropped {dropped} orphan entries."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download everything-ai-coding catalog entries to local folders."
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help="Output directory (default: catalog-download/)",
    )
    parser.add_argument(
        "--types", "-t",
        default="skills,mcp,rules,prompts,plugins,commands,subagents,templates",
        help="Comma-separated list of types to download (default: all)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=8,
        help="Max concurrent download workers (default: 8)",
    )
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    run(args.output, types=types, force=args.force, max_workers=args.workers)


if __name__ == "__main__":
    main()
