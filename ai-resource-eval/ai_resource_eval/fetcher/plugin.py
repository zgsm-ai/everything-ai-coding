"""Plugin content fetcher — assembles full plugin bundle content from a GitHub repo.

Identifies plugin boundary by ``.claude-plugin/plugin.json`` (uniform rule across
L1 marketplace subdir / L2 root plugin / L3 root with many SKILLs / L4 dev
monorepo) and concatenates ``plugin.json`` + ``SKILL.md`` + ``agents/*.md`` +
``commands/*.md`` into a single normalized blob suitable for LLM evaluation.

Two instance caches:

* ``_tree_cache``: ``(repo, ref) → tree json`` so a marketplace monorepo with
  50+ plugins triggers exactly one GitHub Tree API call.
* ``_raw_cache``: ``url → text|None`` mirrors the GitHubFetcher pattern so
  retries / re-evaluations skip HTTP.

When a target sub-path lacks ``.claude-plugin/plugin.json``, ``fetch`` returns
``None`` and the caller falls back to ``GitHubFetcher`` (README mode).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

# Matches "https://github.com/owner/repo" with optional /tree|blob/ref/subpath.
_GITHUB_REPO_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)"
    r"(?:/(?:tree|blob)/([^/]+)(?:/(.+))?)?"
)

_API_BASE = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"
_PLUGIN_JSON_MARKER = ".claude-plugin/plugin.json"
_HOOKS_JSON_PATH = "hooks/hooks.json"
_DOT_MCP_JSON_PATH = ".mcp.json"
_TIMEOUT = 30.0

# Dot-prefixed directories that are real Claude-Code component containers,
# allow-listed past the shadow-directory filter. Anything else starting with
# "." is treated as a non-Claude shadow (e.g., .codex/, .gemini/).
_COMPONENT_DOT_DIRS_ALLOWLIST: frozenset[str] = frozenset({
    ".claude-plugin",
    ".agents",
    ".commands",
})

# Threshold for the marketplace detection heuristic when the repo has both a
# ``plugins/`` subdir AND its own ``.claude-plugin/plugin.json``. When ``plugins/``
# contains this many or more child dirs each owning their own plugin.json, the
# top-level entry is treated as a marketplace shell.
_MARKETPLACE_NESTED_PLUGINS_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Layout dataclass
# ---------------------------------------------------------------------------


@dataclass
class PluginLayout:
    """Result of ``detect_plugin_layout`` — paths of files comprising a plugin.

    Attributes
    ----------
    is_plugin
        True when ``.claude-plugin/plugin.json`` was found at the target root.
    plugin_root
        Plugin root relative to repo root (``""`` for repo-root plugins).
    plugin_json_path
        Repo-relative path to ``plugin.json`` (empty when ``is_plugin=False``).
    skill_paths / agent_paths / command_paths
        Repo-relative paths to plugin content files, sorted alphabetically.
    skills_namespaces
        ``"<plugin-name>:<skill-name>"`` strings, one per ``SKILL.md``.
    """

    is_plugin: bool
    plugin_root: str = ""
    plugin_json_path: str = ""
    skill_paths: list[str] = field(default_factory=list)
    agent_paths: list[str] = field(default_factory=list)
    command_paths: list[str] = field(default_factory=list)
    skills_namespaces: list[str] = field(default_factory=list)
    fetch_error: str | None = None  # Tree API failure reason (HTTP code / exception); is_plugin=False with this set means "could not detect" (transient), not "no plugin.json"
    # Hook signals (deep-tier extraction from hooks/hooks.json)
    hook_events: list[str] = field(default_factory=list)
    hooks_count: int = 0
    # MCP server names (union of plugin.json inline mcpServers and .mcp.json)
    mcp_server_names: list[str] = field(default_factory=list)
    # MCP server configs keyed by server name. Only configs with a usable
    # command or url are included; name-only declarations remain visible in
    # mcp_server_names but are not enough to synthesize installable children.
    mcp_server_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # True when the repo at this plugin_root looks like a marketplace shell
    # (contains a plugins/ subdir with multiple nested plugins) rather than a
    # single plugin. Sync layer SHALL skip writing an entry when this is True.
    is_marketplace_repo: bool = False


# ---------------------------------------------------------------------------
# PluginContentFetcher
# ---------------------------------------------------------------------------


class PluginContentFetcher:
    """Fetch and normalize plugin bundle content from a GitHub repository.

    Parameters
    ----------
    github_token
        GitHub PAT used as ``Authorization: token …`` for Tree API calls.
        Falls back to ``GITHUB_TOKEN`` env var. Without a token the API allows
        only 60 unauthenticated requests/hour, which is fine for tests but not
        production CI.
    size_cap
        Soft byte limit for the concatenated content. When the running total
        exceeds this, files beyond the first 5 of each category are truncated
        to ``frontmatter + first 800 chars``. Default 600,000 bytes
        (~150k tokens, ~15% of MiMo 1M context window).
    http_client
        Optional pre-built ``httpx.Client`` (mainly for tests). When omitted the
        fetcher creates its own client with a 30 s timeout.
    """

    DEFAULT_SIZE_CAP = 600_000
    _SHORT_FALLBACK_CHARS = 800

    def __init__(
        self,
        github_token: str | None = None,
        size_cap: int = DEFAULT_SIZE_CAP,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = (
            github_token
            if github_token is not None
            else os.environ.get("GITHUB_TOKEN", "")
        ).strip()
        self._size_cap = size_cap
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=_TIMEOUT)
        # Standard CPython GIL serialises dict mutations; no extra locking
        # needed for the usage pattern here (read-then-set with at-most-once
        # write per key).
        self._tree_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._raw_cache: dict[str, str | None] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_plugin_layout(
        self, repo: str, plugin_root: str = "", ref: str = "HEAD"
    ) -> PluginLayout:
        """Detect which files belong to the plugin at ``plugin_root``.

        Calls the GitHub Tree API once per ``(repo, ref)`` and walks the path
        list in-memory. Does **not** fetch any file content.

        Returns ``PluginLayout(is_plugin=False, …)`` when no
        ``.claude-plugin/plugin.json`` exists at the target root — caller is
        expected to fall back to README mode.
        """
        plugin_root = plugin_root.strip("/")

        tree_data = self._fetch_tree(repo, ref=ref)
        fetch_error = tree_data.get("error")
        tree_entries = [
            item
            for item in tree_data.get("tree", [])
            if isinstance(item.get("path"), str)
        ]
        tree_paths = [
            item["path"] for item in tree_entries if item.get("type") == "blob"
        ]

        # Discover all plugin roots in this repo.  A path equal to
        # ".claude-plugin/plugin.json" → root is "".  A path ending in
        # "/.claude-plugin/plugin.json" → root is everything before that
        # suffix.  Skip roots whose path contains a dot-prefixed segment
        # (shadow plugins like ``.codex/...``) — but allow component
        # allow-list entries (.claude-plugin itself is the marker, no segments
        # before it).
        all_plugin_roots: set[str] = set()
        for path in tree_paths:
            root: str | None = None
            if path == _PLUGIN_JSON_MARKER:
                root = ""
            elif path.endswith("/" + _PLUGIN_JSON_MARKER):
                root = path[: -len("/" + _PLUGIN_JSON_MARKER)]
            else:
                continue
            if any(seg.startswith(".") for seg in root.split("/") if seg):
                continue
            all_plugin_roots.add(root)

        # Marketplace heuristic — runs even when no plugin.json is present
        # at this plugin_root (a marketplace shell may lack one). Inspected
        # before short-circuiting the "not a plugin" path.
        is_marketplace = self._detect_marketplace(
            tree_paths=tree_paths,
            plugin_root=plugin_root,
            all_plugin_roots=all_plugin_roots,
        )

        if plugin_root not in all_plugin_roots:
            return PluginLayout(
                is_plugin=False,
                plugin_root=plugin_root,
                fetch_error=str(fetch_error) if fetch_error is not None else None,
                is_marketplace_repo=is_marketplace,
            )

        plugin_json_path = (
            (plugin_root + "/" if plugin_root else "") + _PLUGIN_JSON_MARKER
        )

        # When this plugin_root is itself a marketplace, do NOT enumerate its
        # children as direct components — the sync layer is expected to walk
        # plugins/<name>/ subdirectories separately. Returning empty
        # component lists prevents false-positive bundle counts (e.g., a
        # marketplace shell shipping 2857 skills via its `skills/` subdir
        # that actually belong to nested plugins).
        if is_marketplace:
            return PluginLayout(
                is_plugin=True,
                plugin_root=plugin_root,
                plugin_json_path=plugin_json_path,
                is_marketplace_repo=True,
            )

        # Roots strictly deeper than ``plugin_root`` (nested plugins inside
        # this one).  Their files belong to that nested plugin, not us.
        prefix = plugin_root + "/" if plugin_root else ""
        deeper_roots = sorted(
            (
                r
                for r in all_plugin_roots
                if r != plugin_root and r.startswith(prefix) and r != ""
            ),
            key=len,
        )

        skill_paths: list[str] = []
        agent_paths: list[str] = []
        command_paths: list[str] = []

        for path in tree_paths:
            if not path.startswith(prefix):
                continue
            # Skip files that belong to a deeper (nested) plugin.
            if any(path.startswith(d + "/") for d in deeper_roots):
                continue

            relative = path[len(prefix):]
            # Shadow-directory exclusion: any non-allowlisted segment that
            # starts with "." is a platform-specific artifact.
            segments = relative.split("/")
            if any(
                seg.startswith(".") and seg not in _COMPONENT_DOT_DIRS_ALLOWLIST
                for seg in segments[:-1]
            ):
                continue

            # Component classification — also considers allow-listed dot-prefixed
            # variants ``.agents/`` / ``.commands/``.
            if path.endswith("SKILL.md") and "skills" in segments:
                skill_paths.append(path)
            elif path.endswith(".md") and (
                "agents" in segments or ".agents" in segments
            ):
                agent_paths.append(path)
            elif path.endswith(".md") and (
                "commands" in segments or ".commands" in segments
            ):
                command_paths.append(path)

        skill_paths = sorted(set(skill_paths))
        agent_paths = sorted(set(agent_paths))
        command_paths = sorted(set(command_paths))

        plugin_name = self._derive_plugin_name(repo, plugin_root, plugin_json_path)
        skills_namespaces = [
            f"{plugin_name}:{self._extract_skill_name(p, plugin_root)}"
            for p in skill_paths
        ]

        # Hook + MCP signals — content fetches via raw URLs (cached).
        hook_events, hooks_count = self._extract_hooks(repo, ref, plugin_root)
        mcp_server_names, mcp_server_configs = self._extract_mcp_servers(
            repo, ref, plugin_root, plugin_json_path
        )

        return PluginLayout(
            is_plugin=True,
            plugin_root=plugin_root,
            plugin_json_path=plugin_json_path,
            skill_paths=skill_paths,
            agent_paths=agent_paths,
            command_paths=command_paths,
            skills_namespaces=skills_namespaces,
            hook_events=hook_events,
            hooks_count=hooks_count,
            mcp_server_names=mcp_server_names,
            mcp_server_configs=mcp_server_configs,
            is_marketplace_repo=False,
        )

    def fetch(self, source_url: str) -> tuple[str, str] | None:
        """Fetch and normalize plugin bundle content.

        Steps:

        1. Parse ``source_url`` → (repo, ref, plugin_root).
        2. Detect plugin layout (Tree API + path classification).
        3. If no ``plugin.json`` at target → return ``None`` (caller falls back).
        4. Otherwise fetch each file, concatenate with ``## <path>`` headings,
           apply size_cap fallback for large bundles.

        Returns
        -------
        tuple[str, str] | None
            ``(content, content_hash)`` on success.  ``None`` when the URL is
            not GitHub or no plugin marker exists at the target.
        """
        parsed = self._parse_source_url(source_url)
        if parsed is None:
            return None
        repo, ref, plugin_root = parsed

        layout = self.detect_plugin_layout(repo, plugin_root, ref=ref)
        if not layout.is_plugin:
            return None

        content = self._normalize_content(repo, ref, layout)
        if not content:
            return None
        return content, self._content_hash(content)

    def close(self) -> None:
        """Close the underlying ``httpx.Client`` if owned by this instance."""
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_source_url(source_url: str) -> tuple[str, str, str] | None:
        """Return ``(repo, ref, plugin_root)`` or ``None`` for non-GitHub URLs.

        ``repo`` is ``"owner/name"``.  ``ref`` defaults to ``"HEAD"`` when the
        URL has no ``/tree/<ref>/…`` segment.  ``plugin_root`` is the trailing
        sub-path (empty string for repo-root plugins).
        """
        m = _GITHUB_REPO_RE.match(source_url)
        if m is None:
            return None
        owner = m.group(1)
        repo_name = m.group(2)
        if repo_name.endswith(".git"):
            repo_name = repo_name[: -len(".git")]
        ref = m.group(3) or "HEAD"
        plugin_root = (m.group(4) or "").rstrip("/")
        return f"{owner}/{repo_name}", ref, plugin_root

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ------------------------------------------------------------------
    # GitHub I/O
    # ------------------------------------------------------------------

    def _fetch_tree(self, repo: str, ref: str = "HEAD") -> dict[str, Any]:
        """Fetch ``/repos/<repo>/git/trees/<ref>?recursive=1``, cached by ``(repo, ref)``."""
        key = (repo, ref)
        if key in self._tree_cache:
            return self._tree_cache[key]

        url = f"{_API_BASE}/repos/{repo}/git/trees/{ref}?recursive=1"
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"

        try:
            response = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("Tree API %s exception: %s", repo, exc)
            data: dict[str, Any] = {"tree": [], "truncated": False, "error": str(exc)}
            self._tree_cache[key] = data
            return data

        if response.status_code != 200:
            log.warning(
                "Tree API %s: HTTP %d %s",
                repo,
                response.status_code,
                response.text[:200],
            )
            data = {
                "tree": [],
                "truncated": False,
                "error": response.status_code,
            }
            self._tree_cache[key] = data
            return data

        try:
            data = response.json()
        except ValueError as exc:
            log.warning("Tree API %s: malformed JSON: %s", repo, exc)
            data = {"tree": [], "truncated": False, "error": "invalid_json"}
            self._tree_cache[key] = data
            return data

        if data.get("truncated") is True:
            # GitHub caps the recursive tree at ~100k entries.  Plugins listed
            # past the cap will be silently missed; warn so callers can
            # diagnose under-counts in monorepos.
            log.warning(
                "Tree API %s: response truncated — plugin detection may be "
                "incomplete for this repo (large monorepo).",
                repo,
            )

        self._tree_cache[key] = data
        return data

    def _fetch_raw(self, repo: str, ref: str, path: str) -> str | None:
        """Fetch ``raw.githubusercontent.com/<repo>/<ref>/<path>``, cached by URL."""
        url = f"{_RAW_BASE}/{repo}/{ref}/{path}"
        if url in self._raw_cache:
            return self._raw_cache[url]

        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            log.debug("raw fetch %s failed: %s", url, exc)
            self._raw_cache[url] = None
            return None

        if response.status_code == 200:
            text = response.text
            self._raw_cache[url] = text
            return text

        self._raw_cache[url] = None
        return None

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def _derive_plugin_name(
        self, repo: str, plugin_root: str, plugin_json_path: str
    ) -> str:
        """Pick a stable plugin name for ``skills_namespaces``.

        * For sub-directory plugins, use the last segment of ``plugin_root``.
        * For repo-root plugins, parse ``plugin.json`` and use its ``name``
          field; fall back to the repo's basename when the field is missing.
        """
        if plugin_root:
            return plugin_root.rsplit("/", 1)[-1]

        # Repo-root plugin: try plugin.json's `name` field.
        raw = self._fetch_raw(repo, "HEAD", plugin_json_path)
        if raw:
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                name = payload.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        # Final fallback: repo basename.
        return repo.rsplit("/", 1)[-1]

    # ------------------------------------------------------------------
    # Hook / MCP / marketplace extraction
    # ------------------------------------------------------------------

    def _extract_hooks(
        self, repo: str, ref: str, plugin_root: str
    ) -> tuple[list[str], int]:
        """Parse ``hooks/hooks.json`` → ``(sorted_unique_events, total_entries)``.

        Returns ``([], 0)`` when the file is absent, malformed, or has no
        ``hooks`` top-level key. Logs WARNING on malformed JSON.
        """
        path = self._plugin_relative(plugin_root, _HOOKS_JSON_PATH)
        raw = self._fetch_raw(repo, ref, path)
        if raw is None:
            return [], 0
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            log.warning("Malformed %s in %s: %s", _HOOKS_JSON_PATH, repo, exc)
            return [], 0
        hooks_obj = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks_obj, dict):
            return [], 0
        events: list[str] = []
        total = 0
        for event_name, entries in hooks_obj.items():
            if not isinstance(event_name, str):
                continue
            if isinstance(entries, list):
                events.append(event_name)
                total += len(entries)
        return sorted(set(events)), total

    def _extract_mcp_servers(
        self,
        repo: str,
        ref: str,
        plugin_root: str,
        plugin_json_path: str,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        """Merge MCP servers from plugin.json + .mcp.json.

        Source A — ``plugin.json.mcpServers`` when its value is a dict (string
        path values are treated as references and ignored; an empty dict
        contributes zero servers).

        Source B — ``.mcp.json`` at the plugin root. Schema mirrors
        ``{"mcpServers": {"<name>": {...}}}``.
        """
        names: set[str] = set()
        configs: dict[str, dict[str, Any]] = {}

        def add_servers(value: Any) -> None:
            if not isinstance(value, dict):
                return
            for name, config in value.items():
                if not isinstance(name, str) or not name:
                    continue
                names.add(name)
                if not isinstance(config, dict):
                    continue
                command = config.get("command")
                url = config.get("url")
                has_command = isinstance(command, str) and command.strip()
                has_url = isinstance(url, str) and url.strip()
                if has_command or has_url:
                    configs[name] = config

        # Source A — plugin.json inline mcpServers (dict only).
        plugin_json_raw = self._fetch_raw(repo, ref, plugin_json_path)
        if plugin_json_raw:
            try:
                payload = json.loads(plugin_json_raw)
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                inline = payload.get("mcpServers")
                add_servers(inline)

        # Source B — .mcp.json at plugin root.
        dot_mcp_path = self._plugin_relative(plugin_root, _DOT_MCP_JSON_PATH)
        dot_mcp_raw = self._fetch_raw(repo, ref, dot_mcp_path)
        if dot_mcp_raw:
            try:
                payload = json.loads(dot_mcp_raw)
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                servers = payload.get("mcpServers", payload)
                add_servers(servers)

        return sorted(names), {k: configs[k] for k in sorted(configs)}

    def _detect_marketplace(
        self,
        *,
        tree_paths: list[str],
        plugin_root: str,
        all_plugin_roots: set[str],
    ) -> bool:
        """Return True when this plugin_root looks like a marketplace shell.

        Two conditions either of which triggers marketplace classification:

        1. The plugin_root has a ``plugins/`` subdir AND no own ``.claude-plugin/plugin.json``
        2. The plugin_root has a ``plugins/`` subdir AND that subdir contains
           ``_MARKETPLACE_NESTED_PLUGINS_THRESHOLD`` or more children that are
           themselves plugins (own ``.claude-plugin/plugin.json``).

        Single plugins without a ``plugins/`` subdir always return False.
        """
        prefix = plugin_root + "/" if plugin_root else ""
        plugins_subdir_prefix = prefix + "plugins/"

        # Has plugins/ subdir at all? (any blob path under it counts)
        has_plugins_subdir = any(
            p.startswith(plugins_subdir_prefix) for p in tree_paths
        )
        if not has_plugins_subdir:
            return False

        has_own_marker = plugin_root in all_plugin_roots

        if not has_own_marker:
            # plugins/ exists, no plugin.json here → marketplace shell.
            return True

        # Both exist — count nested plugin roots under plugins/<*>/.
        nested_count = sum(
            1
            for r in all_plugin_roots
            if r != plugin_root and r.startswith(plugins_subdir_prefix)
        )
        return nested_count >= _MARKETPLACE_NESTED_PLUGINS_THRESHOLD

    @staticmethod
    def _plugin_relative(plugin_root: str, rel_path: str) -> str:
        """Join plugin_root and rel_path with a single '/' separator."""
        if plugin_root:
            return f"{plugin_root}/{rel_path}"
        return rel_path

    @staticmethod
    def _extract_skill_name(skill_path: str, plugin_root: str) -> str:
        """Extract ``<skill-name>`` from ``<plugin_root>/skills/<skill>/SKILL.md``."""
        rel = (
            skill_path[len(plugin_root) + 1:]
            if plugin_root and skill_path.startswith(plugin_root + "/")
            else skill_path
        )
        parts = rel.split("/")
        if len(parts) >= 3 and parts[0] == "skills":
            return parts[1]
        return parts[-2] if len(parts) >= 2 else "unknown"

    # ------------------------------------------------------------------
    # Content normalisation
    # ------------------------------------------------------------------

    def _normalize_content(
        self, repo: str, ref: str, layout: PluginLayout
    ) -> str:
        """Concatenate plugin files into a single LLM-ready string.

        Files are ordered ``plugin.json → skills (alphabetical) → agents
        (alphabetical) → commands (alphabetical)`` with each preceded by a
        ``## <path>`` markdown heading.  When the running total exceeds
        ``size_cap``, files beyond the first 5 of each category are reduced to
        ``frontmatter + first 800 chars``.
        """
        parts: list[str] = []

        # plugin.json — always full.
        plugin_json_text = self._fetch_raw(repo, ref, layout.plugin_json_path)
        if plugin_json_text:
            parts.append(
                f"## {layout.plugin_json_path}\n```json\n{plugin_json_text}\n```\n"
            )

        # hooks/hooks.json + .mcp.json — included for content_hash coverage so
        # changes invalidate the incremental cache. Always full (small files).
        hooks_path = self._plugin_relative(layout.plugin_root, _HOOKS_JSON_PATH)
        hooks_text = self._fetch_raw(repo, ref, hooks_path)
        if hooks_text:
            parts.append(f"## {hooks_path}\n```json\n{hooks_text}\n```\n")

        dot_mcp_path = self._plugin_relative(layout.plugin_root, _DOT_MCP_JSON_PATH)
        dot_mcp_text = self._fetch_raw(repo, ref, dot_mcp_path)
        if dot_mcp_text:
            parts.append(f"## {dot_mcp_path}\n```json\n{dot_mcp_text}\n```\n")

        def running_total() -> int:
            return sum(len(p) for p in parts)

        def add_file(path: str, full: bool) -> None:
            text = self._fetch_raw(repo, ref, path)
            if text is None:
                return
            if not full:
                text = self._abbreviate(text)
            parts.append(f"## {path}\n{text}\n")

        for i, path in enumerate(layout.skill_paths):
            full = running_total() < self._size_cap or i < 5
            add_file(path, full)

        for i, path in enumerate(layout.agent_paths):
            full = running_total() < self._size_cap or i < 5
            add_file(path, full)

        for i, path in enumerate(layout.command_paths):
            full = running_total() < self._size_cap or i < 5
            add_file(path, full)

        return "\n".join(parts)

    @classmethod
    def _abbreviate(cls, text: str) -> str:
        """Return YAML frontmatter (if any) + first paragraph truncated to 800 chars."""
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if m:
            front = m.group(1)
            after = text[m.end():]
            first_para = after.split("\n\n", 1)[0] if after else ""
            return f"---\n{front}\n---\n\n{first_para[: cls._SHORT_FALLBACK_CHARS]}"
        return text[: cls._SHORT_FALLBACK_CHARS]
