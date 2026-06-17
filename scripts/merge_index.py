#!/usr/bin/env python3
"""Merge all type-specific indexes and curated files into catalog/index.json."""

import argparse
import hashlib
import json
import os
import sys
from typing import Any
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
try:
    from .utils import (
        load_index,
        save_index,
        deduplicate,
        categorize,
        extract_tags,
        normalize_source_url,
        get_repo_meta,
        to_kebab_case,
        is_localized_skill_path,
        logger,
    )
    from .enrichment_orchestrator import enrich_entries
    from .scoring_governor import apply_governance
    from .catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
        overlay_preserved_fields,
    )
except ImportError:
    from utils import (
        load_index,
        save_index,
        deduplicate,
        categorize,
        extract_tags,
        normalize_source_url,
        get_repo_meta,
        to_kebab_case,
        is_localized_skill_path,
        logger,
    )
    from enrichment_orchestrator import enrich_entries
    from scoring_governor import apply_governance
    from catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
        overlay_preserved_fields,
    )

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
# Resource-type sub-directories under catalog/. Entry-level `type` values are
# singular (mcp / skill / rule / prompt / plugin); these directory names are
# plural to match the on-disk layout (catalog/<dir>/index.json + curated.json).
TYPES = ["mcp", "skills", "rules", "prompts", "plugins"]
TODAY = date.today().isoformat()


def _synthetic_skill_id(plugin_id: str, skill_name: str, existing_ids: set[str]) -> str:
    """Build a kebab-safe, collision-free id for a synthesized orphan sub-skill.

    The id MUST be idempotent under ``to_kebab_case`` (i.e.
    ``to_kebab_case(id) == id``). The downstream pipeline derives the on-disk
    folder name via ``download_catalog._kebab_name`` (= ``to_kebab_case(id)``)
    while costrict-web ingest and ``download_catalog._filter_top_index_to_downloaded``
    look up the SKILL.md by the **raw** entry id. Any character that
    ``to_kebab_case`` rewrites (notably ``_`` / ``__``) would make the written
    folder name differ from the raw id → ENOENT → the entry gets dropped.

    Strategy: kebab-case both halves independently, then join with a single
    ``-`` (so ``<plugin-id>-<skill-name>``). On collision with an existing id,
    append ``-<shorthash>`` where the hash is lowercase hex (still kebab-safe).
    """
    base = f"{to_kebab_case(plugin_id)}-{to_kebab_case(skill_name)}"
    base = to_kebab_case(base)  # collapse any double hyphen from empty halves
    if base not in existing_ids:
        return base
    digest = hashlib.sha1(f"{plugin_id}:{skill_name}".encode("utf-8")).hexdigest()
    for length in (8, 12, 40):
        candidate = f"{base}-{digest[:length]}"
        if candidate not in existing_ids:
            return candidate
    # Extremely unlikely fallthrough; widen with a counter.
    counter = 2
    while f"{base}-{digest[:8]}-{counter}" in existing_ids:
        counter += 1
    return f"{base}-{digest[:8]}-{counter}"


def _synthetic_mcp_id(plugin_id: str, server_name: str, existing_ids: set[str]) -> str:
    """Build a kebab-safe id for a synthesized plugin-bundled MCP entry."""
    base = f"{to_kebab_case(plugin_id)}-mcp-{to_kebab_case(server_name)}"
    base = to_kebab_case(base)
    if base not in existing_ids:
        return base
    digest = hashlib.sha1(f"{plugin_id}:mcp:{server_name}".encode("utf-8")).hexdigest()
    for length in (8, 12, 40):
        candidate = f"{base}-{digest[:length]}"
        if candidate not in existing_ids:
            return candidate
    counter = 2
    while f"{base}-{digest[:8]}-{counter}" in existing_ids:
        counter += 1
    return f"{base}-{digest[:8]}-{counter}"


# ---------------------------------------------------------------------------
# Generic plugin-bundled child kinds
#
# Every functional component a plugin ships (beyond skills + MCP) is synthesized
# into a standalone, path-faithful catalog entry via the same machinery the
# orphan-skill / bundled-mcp paths already use. The table below is the single
# source of truth tying together: the bundle fields the sync stage emits
# (``<ns_field>`` / ``<paths_field>``), the catalog entry ``type``, the
# ``source`` provenance tag (used by score-backfill / prune / type-index sync),
# whether the on-disk component is a DIRECTORY (skill-style, all sibling files
# travel) or a single FILE, and the per-type download dir.
#
# NOTE: ``type`` values MUST stay aligned with three other layers (or children
# get dropped / mistyped):
#   - catalog/schema.json  ``type`` enum  (mcp/skill/rule/prompt/plugin + template/command/subagent)
#   - download_catalog.py  DOWNLOADERS / _PRIMARY_FILE_BY_TYPE
#   - costrict-web         parser_service.InferItemType + catalog_ingest_service.typeDirAndFile
# ---------------------------------------------------------------------------

class _ChildKind:
    __slots__ = ("kind", "ns_field", "paths_field", "type", "source", "is_dir", "type_dir")

    def __init__(self, kind, ns_field, paths_field, type, source, is_dir, type_dir):
        self.kind = kind
        self.ns_field = ns_field
        self.paths_field = paths_field
        self.type = type
        self.source = source
        self.is_dir = is_dir
        self.type_dir = type_dir


# Skills keep their dedicated match-or-synthesize path (they can match an
# existing catalog skill). The kinds below are ALWAYS synthesized fresh from
# the plugin bundle — they have no standalone catalog source to match against.
_BUNDLED_CHILD_KINDS: list[_ChildKind] = [
    # evaluators ship as a skill (directory with SKILL.md + siblings).
    _ChildKind("evaluator", "evaluators_namespaces", "evaluator_paths",
               "skill", "plugin-bundled-evaluator", True, "skills"),
    _ChildKind("command", "commands_namespaces", "command_paths",
               "command", "plugin-bundled-command", False, "commands"),
    _ChildKind("agent", "agents_namespaces", "agent_paths",
               "subagent", "plugin-bundled-subagent", False, "subagents"),
    _ChildKind("rule", "rules_namespaces", "rule_paths",
               "rule", "plugin-bundled-rule", False, "rules"),
    _ChildKind("template", "templates_namespaces", "template_paths",
               "template", "plugin-bundled-template", False, "templates"),
]

# All synthesized child provenance tags (skill + mcp + the generic kinds).
# Anything that filters/keys on "is this a synthesized plugin child" must use
# this set so a newly-added kind is picked up everywhere automatically.
_PLUGIN_BUNDLED_SOURCES: set[str] = {"plugin-bundled-skill", "plugin-bundled-mcp"} | {
    k.source for k in _BUNDLED_CHILD_KINDS
}

# source tag → per-type catalog dir, for _sync_synthesized_children_to_type_indexes.
# Skills (incl. evaluators) land in skills/, mcp in mcp/, and each new kind in
# its own dir. MISSING A BUCKET HERE = synthesized children never reach a type
# index → download_catalog skips them → bundle drops them as orphans (silent).
_SOURCE_TO_TYPE_DIR: dict[str, str] = {
    "plugin-bundled-skill": "skills",
    "plugin-bundled-mcp": "mcp",
    **{k.source: k.type_dir for k in _BUNDLED_CHILD_KINDS},
}


def _synthetic_child_id(
    plugin_id: str, kind: str, name: str, existing_ids: set[str]
) -> str:
    """Build a kebab-safe, collision-free id for a synthesized plugin child.

    Mirrors ``_synthetic_skill_id`` (idempotent under ``to_kebab_case`` so the
    on-disk download folder == the raw id the web hub looks up) but namespaces
    the id with ``-<kind>-`` so a command and a rule of the same name don't
    collide. ``name`` may carry a nested ``<group>/<file>`` prefix (rules);
    ``to_kebab_case`` flattens the slash into a hyphen.
    """
    base = f"{to_kebab_case(plugin_id)}-{kind}-{to_kebab_case(name)}"
    base = to_kebab_case(base)
    if base not in existing_ids:
        return base
    digest = hashlib.sha1(f"{plugin_id}:{kind}:{name}".encode("utf-8")).hexdigest()
    for length in (8, 12, 40):
        candidate = f"{base}-{digest[:length]}"
        if candidate not in existing_ids:
            return candidate
    counter = 2
    while f"{base}-{digest[:8]}-{counter}" in existing_ids:
        counter += 1
    return f"{base}-{digest[:8]}-{counter}"


def _plugin_root_relative(repo_path: str | None, plugin_root: str | None) -> str | None:
    """Strip the ``<plugin_root>/`` prefix from a repo-relative path.

    The outward ``source_path`` (consumed by costrict-web as item.SourcePath and
    used by the frontend to build the work tree) MUST be **plugin-root relative**
    so it matches the archive-upload path root exactly (e.g. ``rules/dfx/安全.md``,
    ``skills/<n>/SKILL.md``). Otherwise the tree gains a spurious top-level
    plugin-dir layer and catalog ↔ archive children diverge.

    Download/content fetch still uses the FULL repo-relative path (install.path /
    install.files); only this outward field is rebased. Defensive: if the path
    does not start with the plugin_root prefix, it is returned unchanged.
    """
    if not isinstance(repo_path, str) or not repo_path:
        return repo_path
    root = (plugin_root or "").strip().strip("/")
    if root:
        prefix = root + "/"
        if repo_path.startswith(prefix):
            return repo_path[len(prefix):]
    return repo_path


def _synthesize_bundled_child_entry(
    plugin: dict,
    spec: "_ChildKind",
    child_name: str,
    child_path: str,
    source_repo: str | None,
    source_ref: str | None,
    synthetic_id: str,
    plugin_root: str | None = None,
) -> dict:
    """Construct a standalone catalog entry of ``spec.type`` for one plugin-bundled
    component (command / subagent / evaluator / rule / template).

    The entry carries an ``install.git_clone`` block whose ``path`` is the
    FULL repo-relative path of the component (``<plugin_root>/...``) so
    ``download_catalog`` fetches the right raw URL; ``files=[<path>]`` is set for
    single-file kinds so it fetches just that file; directory kinds (evaluators)
    set ``path`` to the directory so all siblings travel (skill-style download).

    ``source_path`` (the OUTWARD field downstream web ingest stores as
    item.SourcePath and the frontend builds the work tree from) is rebased to be
    **plugin-root relative** — identical to the archive-upload path root — so the
    GitHub-style tree has no spurious plugin-dir layer and the catalog/archive
    children agree.
    """
    plugin_id = plugin.get("id") or ""
    repo = (source_repo or "").strip()
    branch = (source_ref or "").strip() or "HEAD"

    install: dict[str, Any] = {"method": "git_clone"}
    install_path = child_path
    if spec.is_dir and isinstance(child_path, str) and child_path:
        # Directory kind: install.path is the parent dir (drop /SKILL.md).
        install_path = child_path.rsplit("/SKILL.md", 1)[0].strip("/")
    if repo:
        install["repo"] = f"https://github.com/{repo}.git"
        install["branch"] = branch
    if install_path:
        install["path"] = install_path
    if not spec.is_dir and child_path:
        # Single-file kind: pin the exact (full repo-relative) file so download
        # fetches just it.
        install["files"] = [child_path]

    if repo and install_path:
        source_url = f"https://github.com/{repo}/tree/{branch}/{install_path}"
    else:
        source_url = plugin.get("source_url") or _PLACEHOLDER_SOURCE_URL

    display_name = child_name.rsplit("/", 1)[-1]
    description = (
        f"Bundled {spec.kind} {display_name} from plugin "
        f"{plugin.get('name') or plugin_id}"
    ).strip()
    tags = extract_tags(display_name, description)
    category = categorize(display_name, description, tags)

    entry: dict[str, Any] = {
        "id": synthetic_id,
        "name": display_name,
        "type": spec.type,
        "description": description,
        "source_url": source_url,
        "stars": plugin.get("stars"),
        "pushed_at": plugin.get("pushed_at"),
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "install": install,
        "bundled_in": plugin_id,
        # Plugin-root-relative (NOT repo-relative): matches the archive-upload
        # path root so the work tree mirrors the real layout WITHOUT a spurious
        # <plugin_root>/ level, and catalog ↔ archive children stay identical.
        "source_path": _plugin_root_relative(child_path, plugin_root),
        "final_score": plugin.get("final_score", 0) or 0,
        "source": spec.source,
        "last_synced": TODAY,
    }
    return entry


def _synthesize_orphan_skill_entry(
    plugin: dict,
    skill_name: str,
    skill_path: str | None,
    source_repo: str | None,
    source_ref: str | None,
    synthetic_id: str,
    plugin_root: str | None = None,
) -> dict:
    """Construct a standalone ``type=skill`` catalog entry for an orphan
    sub-skill bundled by ``plugin`` but absent from the catalog (the common
    cospower case — their 9–15 skills live only inside the plugin).

    The entry carries an ``install.git_clone`` block pointing at the skill's
    directory (FULL repo-relative) so ``download_catalog._download_skill`` can
    fetch SKILL.md (and siblings) into ``catalog-download/skills/<synthetic_id>/SKILL.md``.

    The OUTWARD ``source_path`` is set to the **plugin-root-relative real path**
    (e.g. ``skills/<name>/SKILL.md`` / ``evaluators/<name>/SKILL.md``) — identical
    to the archive-upload root and to the generic child kinds — so the web hub
    work tree mirrors GitHub at the real path, not a synthetic-id stub. This
    only affects BUNDLED sub-skills (the entry always carries ``bundled_in`` +
    ``source=plugin-bundled-skill``); independent catalog skills are never touched
    by this factory.

    ``final_score`` is inherited from the parent later (after governance promotes
    it); here it is initialized so the field is present even if backfill is skipped.
    """
    plugin_id = plugin.get("id") or ""
    repo = (source_repo or "").strip()
    # skill_path is repo-relative, e.g. "<plugin_root>/skills/<name>/SKILL.md".
    # The install dir is its parent directory (drop the trailing /SKILL.md).
    skill_dir = ""
    if isinstance(skill_path, str) and skill_path:
        skill_dir = skill_path.rsplit("/SKILL.md", 1)[0].strip("/")

    branch = (source_ref or "").strip()
    # Keep HEAD when the sync layer used it. GitHub tree/raw endpoints accept
    # HEAD and resolve it to the repository default branch; forcing "main"
    # breaks repositories whose default branch has another name.
    if not branch:
        branch = "HEAD"

    install: dict[str, Any] = {"method": "git_clone"}
    if repo:
        install["repo"] = f"https://github.com/{repo}.git"
        install["branch"] = branch
    if skill_dir:
        install["path"] = skill_dir

    if repo and skill_dir:
        source_url = f"https://github.com/{repo}/tree/{branch}/{skill_dir}"
    else:
        source_url = plugin.get("source_url") or _PLACEHOLDER_SOURCE_URL

    description = f"Bundled skill {skill_name} from plugin {plugin.get('name') or plugin_id}".strip()
    tags = extract_tags(skill_name, description)
    category = categorize(skill_name, description, tags)

    entry: dict[str, Any] = {
        "id": synthetic_id,
        "name": skill_name,
        "type": "skill",
        "description": description,
        "source_url": source_url,
        "stars": plugin.get("stars"),
        "pushed_at": plugin.get("pushed_at"),
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "install": install,
        "bundled_in": plugin_id,
        # Plugin-root-relative real path (matches archive root + generic kinds),
        # so the work tree shows skills/<name>/SKILL.md not skills/<synthetic-id>/.
        "source_path": _plugin_root_relative(skill_path, plugin_root),
        # Inherited from the parent plugin after governance promotes its
        # top-level final_score (see merge() final_score backfill). Seeded to 0
        # so the field is always present and schema-valid.
        "final_score": plugin.get("final_score", 0) or 0,
        "source": "plugin-bundled-skill",
        "last_synced": TODAY,
    }
    return entry


def _synthesize_bundled_mcp_entry(
    plugin: dict,
    server_name: str,
    config: dict,
    synthetic_id: str,
) -> dict:
    """Construct a standalone ``type=mcp`` entry for a plugin-bundled server.

    The entry carries ``install.config`` directly so download_catalog._download_mcp
    can write a valid ``catalog-download/mcp/<id>/.mcp.json`` without cloning the
    full plugin repository.

    NOTE: deliberately NO ``source_path``. An MCP child is a server keyed inside a
    shared ``.mcp.json`` (``mcpServers.<name>``), not a faithful single file —
    downstream costrict-web identifies it as ``<path>#<server-key>`` (synthetic,
    capability_item.go:2874), and the frontend tree normalizes that ``#key`` form
    specially. Forcing a plain path-faithful source_path here would be wrong.
    """
    plugin_id = plugin.get("id") or ""
    description = f"Bundled MCP server {server_name} from plugin {plugin.get('name') or plugin_id}".strip()
    tags = extract_tags(server_name, description)
    category = categorize(server_name, description, tags)

    return {
        "id": synthetic_id,
        "name": server_name,
        "type": "mcp",
        "description": description,
        "source_url": plugin.get("source_url") or _PLACEHOLDER_SOURCE_URL,
        "stars": plugin.get("stars"),
        "pushed_at": plugin.get("pushed_at"),
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "install": {
            "method": "mcp_config",
            "config": config,
        },
        "bundled_in": plugin_id,
        "final_score": plugin.get("final_score", 0) or 0,
        "source": "plugin-bundled-mcp",
        "last_synced": TODAY,
    }


_PLACEHOLDER_SOURCE_URL = "https://github.com/zgsm-ai/everything-ai-coding"


def _apply_bundled_in_annotations(entries: list[dict], log=logger) -> list[dict]:
    """Soft-annotate plugin-bundled children and write reverse mappings.

    For each entry whose ``type == "plugin"``, scan ``bundle.skills_namespaces``
    (a list of ``"<plugin-name>:<skill-name>"`` strings, per the plugin manifest
    contract). For every namespace string, locate a matching skill entry and
    set ``bundled_in: <plugin-id>`` on it.

    Match resolution (first hit wins, in this order):
      1. Skill ``namespace`` field equals the namespace string verbatim
         (e.g. ``superpowers:brainstorming``). This is the canonical match.
      2. Skill ``id`` equals the namespace string verbatim.
      3. Slugified fallback: skill ``id`` equals ``<plugin-name>-<skill-name>``
         derived by replacing ``:`` with ``-`` (handles the common case where
         skills are stored as ``superpowers-brainstorming``).

    In the same pass, populate ``plugin["bundle"]["bundled_skill_ids"]`` — a
    list **position-aligned** with ``bundle.skills_namespaces``: element[i] is
    the matched skill's catalog ``id``, or ``None`` if no skill matched (orphan).
    Plugins whose ``skills_namespaces`` is missing or empty do NOT get the
    field written (it stays absent rather than being set to ``[]``).

    Mutates ``entries`` in place and also returns it. Logs a single summary
    line per spec plugin-bundle-dedup §"Dedup correctness logging" and a
    WARNING per orphan namespace.
    """
    plugin_entries = [e for e in entries if (e.get("type") or "") == "plugin"]
    skill_entries = [e for e in entries if (e.get("type") or "") == "skill"]
    mcp_entries = [e for e in entries if (e.get("type") or "") == "mcp"]

    skills_by_namespace: dict[str, dict] = {}
    skills_by_id: dict[str, dict] = {}
    # Index skills by the trailing path segment of their source_url so we can
    # match plugin namespaces like "superpowers:brainstorming" against catalog
    # skills mirrored under different repos (e.g. sickn33/...) whose
    # source_url ends in /skills/brainstorming. Many skills share names — so
    # we keep a list and pick the first hit per (plugin_repo, skill_name) pair
    # below to avoid arbitrary cross-plugin attribution.
    skills_by_source_skill_name: dict[str, list[dict]] = {}
    for s in skill_entries:
        ns = s.get("namespace")
        if isinstance(ns, str) and ns:
            skills_by_namespace.setdefault(ns, s)
        sid = s.get("id")
        if isinstance(sid, str) and sid:
            skills_by_id.setdefault(sid, s)
        url = s.get("source_url")
        if isinstance(url, str) and "/skills/" in url:
            # Trailing component after /skills/ — strip /SKILL.md or trailing /
            tail = url.rstrip("/").rsplit("/skills/", 1)[-1].split("/")[0]
            if tail and tail != "skills":
                skills_by_source_skill_name.setdefault(tail, []).append(s)

    bundled_mcp_by_parent_name: dict[tuple[str, str], dict] = {}
    for m in mcp_entries:
        parent_id = m.get("bundled_in")
        name = m.get("name")
        if isinstance(parent_id, str) and parent_id and isinstance(name, str) and name:
            bundled_mcp_by_parent_name.setdefault((parent_id, name), m)

    def _plugin_source_repo(plugin: dict) -> str:
        url = plugin.get("source_url") or ""
        if "github.com" not in url:
            return ""
        path = url.replace("https://github.com/", "").replace("http://github.com/", "")
        # Remove trailing /tree/<ref>/... and .git suffix
        path = path.split("/tree/")[0].split("/blob/")[0]
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else ""

    # All catalog ids (including skills synthesized in earlier plugin
    # iterations of this same pass) so synthetic ids stay globally unique.
    existing_ids: set[str] = {
        s for s in (e.get("id") for e in entries) if isinstance(s, str) and s
    }
    synthesized: list[dict] = []
    synthesized_mcp_count = 0

    annotated = 0
    orphan_count = 0
    synthesized_count = 0
    for plugin in plugin_entries:
        plugin_id = plugin.get("id") or ""
        bundle = plugin.get("bundle") or {}
        namespaces = bundle.get("skills_namespaces")
        # Repo-relative SKILL.md paths + source coordinates, written by
        # sync_plugins_official._build_bundle_from_layout (position-aligned
        # with skills_namespaces). Used to synthesize orphan skill entries with
        # a working install block. May be absent for legacy / manifest-only
        # bundles → orphan synthesis is skipped for those (no usable path).
        skill_paths = bundle.get("skill_paths")
        if not isinstance(skill_paths, list):
            skill_paths = []
        bundle_source_repo = bundle.get("source_repo")
        bundle_source_ref = bundle.get("source_ref")
        bundle_plugin_root = bundle.get("plugin_root")
        if not namespaces:
            log.debug(
                "post-merge: plugin %s has no skills_namespaces; skipping",
                plugin_id or "<unknown>",
            )
            continue
        if not isinstance(namespaces, list):
            log.debug(
                "post-merge: plugin %s skills_namespaces is not a list (%s); skipping",
                plugin_id or "<unknown>",
                type(namespaces).__name__,
            )
            continue
        # Drop localized/translated bundled skills (e.g. ECC's 519
        # docs/<locale>/skills/.../SKILL.md copies) before any matching /
        # synthesis. namespaces and skill_paths are position-aligned (both from
        # the layout detector); we only drop a position when its aligned
        # skill_path is present AND classified localized — absent paths are
        # never dropped (high-precision bias, keeps canonical / legacy bundles).
        # When we drop, persist the filtered lists + corrected skills_count back
        # onto the bundle so skills_namespaces / skill_paths / bundled_skill_ids
        # stay position-aligned (downstream chips + counts).
        if skill_paths:
            kept_ns: list = []
            kept_paths: list = []
            dropped_localized = 0
            for i, ns in enumerate(namespaces):
                sp = skill_paths[i] if i < len(skill_paths) else None
                if sp and is_localized_skill_path(sp):
                    dropped_localized += 1
                    continue
                kept_ns.append(ns)
                kept_paths.append(sp if i < len(skill_paths) else None)
            if dropped_localized:
                log.info(
                    "post-merge: plugin %s — dropped %d localized bundled SKILL.md "
                    "copies, kept %d canonical",
                    plugin_id or "<unknown>",
                    dropped_localized,
                    len(kept_ns),
                )
                namespaces = kept_ns
                skill_paths = kept_paths
                bundle["skills_namespaces"] = list(kept_ns)
                bundle["skill_paths"] = list(kept_paths)
                bundle["skills_count"] = len(kept_ns)
                plugin["bundle"] = bundle
        plugin_repo = _plugin_source_repo(plugin)
        # Position-aligned reverse mapping: one element per namespace entry
        # (None for orphans). Written back to plugin["bundle"]["bundled_skill_ids"]
        # after the namespace loop completes.
        bundled_skill_ids: list = []
        for i, ns in enumerate(namespaces):
            if not isinstance(ns, str) or not ns:
                # Non-string / empty namespace entries can't be matched; keep
                # alignment with the input list by recording None.
                bundled_skill_ids.append(None)
                continue
            target = skills_by_namespace.get(ns) or skills_by_id.get(ns)
            if target is None and ":" in ns:
                slug_id = ns.replace(":", "-")
                target = skills_by_id.get(slug_id)
            if target is None and ":" in ns:
                # Source-url-path fallback: look for any catalog skill whose
                # source_url ends in /skills/<skill-name>. Prefer one whose
                # source_url contains the plugin's GitHub repo path
                # (highest-confidence: same-repo mirror); if no same-repo
                # match exists, fall back to any catalog skill with that
                # trailing skill-name segment.
                _, skill_name = ns.split(":", 1)
                candidates = skills_by_source_skill_name.get(skill_name) or []
                if candidates:
                    same_repo = [
                        c for c in candidates
                        if plugin_repo and plugin_repo in (c.get("source_url") or "")
                    ]
                    target = same_repo[0] if same_repo else candidates[0]
            if target is None:
                # Orphan: no matching catalog skill. Synthesize a standalone
                # type=skill entry so the bundled sub-skill becomes a
                # first-class, separately-installable item. Requires the
                # repo-relative skill path + source coordinates carried in the
                # bundle (sync_plugins_official); without them we fall back to
                # the legacy "warn + None" behaviour.
                orphan_count += 1
                skill_name = ns.split(":", 1)[1] if ":" in ns else ns
                skill_path = skill_paths[i] if i < len(skill_paths) else None
                if plugin_id and skill_path and bundle_source_repo:
                    synthetic_id = _synthetic_skill_id(
                        plugin_id, skill_name, existing_ids
                    )
                    existing_ids.add(synthetic_id)
                    synthetic_entry = _synthesize_orphan_skill_entry(
                        plugin,
                        skill_name,
                        skill_path,
                        bundle_source_repo,
                        bundle_source_ref,
                        synthetic_id,
                        bundle_plugin_root,
                    )
                    synthesized.append(synthetic_entry)
                    bundled_skill_ids.append(synthetic_id)
                    synthesized_count += 1
                    log.info(
                        "post-merge: synthesized standalone skill %s for orphan "
                        "namespace %r bundled by plugin %s",
                        synthetic_id,
                        ns,
                        plugin_id,
                    )
                else:
                    bundled_skill_ids.append(None)
                    log.warning(
                        "post-merge: plugin %s declares orphan namespace %r "
                        "(no matching skill in catalog; cannot synthesize — "
                        "missing skill_path/source_repo in bundle)",
                        plugin_id or "<unknown>",
                        ns,
                    )
                continue
            target_id = target.get("id") or None
            bundled_skill_ids.append(target_id)
            if plugin_id:
                target["bundled_in"] = plugin_id
                annotated += 1
                # Backfill the plugin-root-relative real source_path on the
                # MATCHED/REUSED skill from THIS bundle's skill_paths, even if the
                # existing entry already had a (None/stale) source_path. Without
                # this, cospower skills already present in catalog/skills/index.json
                # from an earlier (pre-P3) synthesis keep source_path=None and the
                # web work tree never mirrors their real path. install/source_url
                # on the existing entry are left untouched.
                skill_path = skill_paths[i] if i < len(skill_paths) else None
                if isinstance(skill_path, str) and skill_path:
                    target["source_path"] = _plugin_root_relative(
                        skill_path, bundle_plugin_root
                    )
        # Write reverse mapping back onto the plugin entry. We only reach this
        # point when ``namespaces`` was a non-empty list (the earlier guards
        # ``continue`` for empty/missing/non-list cases), so per-spec we are
        # safe to set the field unconditionally here.
        plugin.setdefault("bundle", {})["bundled_skill_ids"] = bundled_skill_ids

    for plugin in plugin_entries:
        plugin_id = plugin.get("id") or ""
        bundle = plugin.get("bundle") or {}
        configs = bundle.get("mcp_server_configs")
        if not plugin_id or not isinstance(configs, dict) or not configs:
            continue
        bundled_mcp_ids: list[str | None] = []
        names = bundle.get("mcp_server_names")
        ordered_names = names if isinstance(names, list) and names else sorted(configs)
        for raw_name in ordered_names:
            if not isinstance(raw_name, str) or not raw_name:
                bundled_mcp_ids.append(None)
                continue
            config = configs.get(raw_name)
            if not isinstance(config, dict):
                bundled_mcp_ids.append(None)
                continue
            command = config.get("command")
            url = config.get("url")
            has_command = isinstance(command, str) and command.strip()
            has_url = isinstance(url, str) and url.strip()
            if not has_command and not has_url:
                bundled_mcp_ids.append(None)
                continue
            existing_mcp = bundled_mcp_by_parent_name.get((plugin_id, raw_name))
            if existing_mcp is not None:
                existing_id = existing_mcp.get("id")
                if existing_mcp.get("source") == "plugin-bundled-mcp":
                    existing_mcp["install"] = {
                        "method": "mcp_config",
                        "config": config,
                    }
                    existing_mcp["last_synced"] = TODAY
                bundled_mcp_ids.append(existing_id if isinstance(existing_id, str) else None)
                continue
            synthetic_id = _synthetic_mcp_id(plugin_id, raw_name, existing_ids)
            existing_ids.add(synthetic_id)
            synthetic_entry = _synthesize_bundled_mcp_entry(
                plugin, raw_name, config, synthetic_id
            )
            synthesized.append(synthetic_entry)
            bundled_mcp_by_parent_name[(plugin_id, raw_name)] = synthetic_entry
            bundled_mcp_ids.append(synthetic_id)
            synthesized_mcp_count += 1
            log.info(
                "post-merge: synthesized standalone MCP %s for server %r bundled by plugin %s",
                synthetic_id,
                raw_name,
                plugin_id,
            )
        if bundled_mcp_ids:
            plugin.setdefault("bundle", {})["bundled_mcp_ids"] = bundled_mcp_ids

    # --- Generic plugin-bundled children: commands / subagents / evaluators /
    # rules / templates. Unlike skills these never match a STANDALONE catalog
    # entry, but a prior merge run may have already synthesized them (they get
    # re-loaded from their type index into this pass). To stay idempotent we
    # REUSE the existing synthesized child (keyed by parent + source + repo
    # path) instead of minting a colliding duplicate. ---
    # Path-keyed index: matches re-loaded children that already carry the
    # correct plugin-root-relative source_path.
    existing_child_by_key: dict[tuple[str, str, str], dict] = {}
    # Id-keyed index: also matches re-loaded children whose source_path is
    # None/missing/stale (e.g. pre-P3 synthesized cospower children). Their id
    # is deterministic, so we re-derive the prospective id and reuse + backfill.
    existing_child_by_id: dict[str, dict] = {}
    for e in entries:
        src = e.get("source")
        parent = e.get("bundled_in")
        sp = e.get("source_path")
        eid = e.get("id")
        if src in _PLUGIN_BUNDLED_SOURCES and isinstance(parent, str) and parent:
            if isinstance(sp, str) and sp:
                existing_child_by_key.setdefault((parent, src, sp), e)
            if isinstance(eid, str) and eid:
                existing_child_by_id.setdefault(eid, e)

    synthesized_child_counts: dict[str, int] = {}
    for plugin in plugin_entries:
        plugin_id = plugin.get("id") or ""
        bundle = plugin.get("bundle") or {}
        if not plugin_id:
            continue
        source_repo = bundle.get("source_repo")
        source_ref = bundle.get("source_ref")
        plugin_root = bundle.get("plugin_root")
        for spec in _BUNDLED_CHILD_KINDS:
            namespaces = bundle.get(spec.ns_field)
            paths = bundle.get(spec.paths_field)
            if not isinstance(namespaces, list) or not namespaces:
                continue
            if not isinstance(paths, list):
                paths = []
            reverse_ids: list[str | None] = []
            for i, ns in enumerate(namespaces):
                child_path = paths[i] if i < len(paths) else None
                child_name = ns.split(":", 1)[1] if isinstance(ns, str) and ":" in ns else ns
                if not isinstance(child_name, str) or not child_name or not child_path or not source_repo:
                    # No usable path/repo → cannot materialize content; record
                    # None to keep position alignment (matches skill behaviour).
                    reverse_ids.append(None)
                    if not (isinstance(child_name, str) and child_name and child_path and source_repo):
                        log.warning(
                            "post-merge: plugin %s declares %s %r but cannot "
                            "synthesize (missing path/source_repo in bundle)",
                            plugin_id, spec.kind, ns,
                        )
                    continue
                # Idempotent reuse: a prior run already synthesized this exact
                # child → keep its id, don't duplicate. Match first by the OUTWARD
                # (plugin-root-relative) source_path; then fall back to the
                # deterministic synthetic id so we ALSO catch re-loaded children
                # whose persisted source_path is None/stale (pre-P3 entries).
                outward_path = _plugin_root_relative(child_path, plugin_root)
                existing_child = existing_child_by_key.get(
                    (plugin_id, spec.source, outward_path)
                )
                if existing_child is None:
                    prospective_id = _synthetic_child_id(
                        plugin_id, spec.kind, child_name, set()
                    )
                    candidate = existing_child_by_id.get(prospective_id)
                    if candidate is not None and candidate.get("source") == spec.source:
                        existing_child = candidate
                if existing_child is not None:
                    # ALWAYS backfill the plugin-root-relative source_path from
                    # the current bundle (even if the existing entry's was
                    # None/stale) so re-used children stay path-faithful.
                    existing_child["source_path"] = outward_path
                    existing_id = existing_child.get("id")
                    reverse_ids.append(existing_id if isinstance(existing_id, str) else None)
                    # Keep both indexes consistent for subsequent lookups.
                    existing_child_by_key[(plugin_id, spec.source, outward_path)] = existing_child
                    continue
                synthetic_id = _synthetic_child_id(
                    plugin_id, spec.kind, child_name, existing_ids
                )
                existing_ids.add(synthetic_id)
                synthetic_entry = _synthesize_bundled_child_entry(
                    plugin, spec, child_name, child_path,
                    source_repo, source_ref, synthetic_id, plugin_root,
                )
                synthesized.append(synthetic_entry)
                existing_child_by_key[(plugin_id, spec.source, outward_path)] = synthetic_entry
                existing_child_by_id[synthetic_id] = synthetic_entry
                reverse_ids.append(synthetic_id)
                synthesized_child_counts[spec.kind] = (
                    synthesized_child_counts.get(spec.kind, 0) + 1
                )
            plugin.setdefault("bundle", {})[f"bundled_{spec.kind}_ids"] = reverse_ids

    # Append synthesized child entries last so they don't participate in this
    # pass's matching indexes (they already carry bundled_in; re-matching them
    # against plugins would be redundant and could double-attribute).
    if synthesized:
        entries.extend(synthesized)

    log.info(
        "post-merge: scanned %d plugins, annotated %d skills with bundled_in, "
        "found %d orphan namespaces, synthesized %d standalone skills, "
        "synthesized %d standalone MCP servers, synthesized children by kind %s",
        len(plugin_entries),
        annotated,
        orphan_count,
        synthesized_count,
        synthesized_mcp_count,
        synthesized_child_counts,
    )
    return entries


def _backfill_bundled_child_final_scores(entries: list[dict], log=logger) -> None:
    """Backfill ``final_score`` on synthesized plugin children from their
    parent plugin (resolved via ``bundled_in``).

    Runs after governance has promoted ``final_score`` to the top level on all
    entries, so the parent plugin's score is now available. Only touches
    entries we synthesized (any ``source`` in ``_PLUGIN_BUNDLED_SOURCES``) so a
    real standalone child that happens to carry ``bundled_in`` keeps its own
    score. Survives parent plugins that were filtered out by governance (no
    parent → leave the seeded score unchanged).
    """
    plugin_score_by_id: dict[str, Any] = {}
    for e in entries:
        if (e.get("type") or "") == "plugin":
            pid = e.get("id")
            if isinstance(pid, str) and pid:
                plugin_score_by_id[pid] = e.get("final_score", 0)

    backfilled = 0
    for e in entries:
        if e.get("source") not in _PLUGIN_BUNDLED_SOURCES:
            continue
        parent_id = e.get("bundled_in")
        if not isinstance(parent_id, str) or parent_id not in plugin_score_by_id:
            continue
        e["final_score"] = plugin_score_by_id[parent_id]
        backfilled += 1

    if backfilled:
        log.info(
            "post-merge: inherited final_score for %d synthesized plugin children "
            "from parent plugins",
            backfilled,
        )


def _prune_invalid_plugin_child_refs(entries: list[dict], log=logger) -> list[dict]:
    """Drop synthesized children whose parent plugin was filtered out, then
    clear plugin reverse mappings that point at missing children.

    ``bundle.bundled_*_ids`` is written before governance so the merge pass can
    keep position alignment with the source bundle. Governance may later filter
    out either a parent plugin or a child entry. This cleanup makes the final
    catalog internally consistent before it is written.
    """
    existing_ids: set[str] = {
        e["id"] for e in entries if isinstance(e.get("id"), str) and e.get("id")
    }
    plugin_ids: set[str] = {
        e["id"]
        for e in entries
        if e.get("type") == "plugin" and isinstance(e.get("id"), str) and e.get("id")
    }

    kept: list[dict] = []
    dropped_children = 0
    for entry in entries:
        if entry.get("source") in _PLUGIN_BUNDLED_SOURCES:
            parent_id = entry.get("bundled_in")
            if not isinstance(parent_id, str) or parent_id not in plugin_ids:
                dropped_children += 1
                continue
        kept.append(entry)

    if dropped_children:
        existing_ids = {
            e["id"] for e in kept if isinstance(e.get("id"), str) and e.get("id")
        }

    # Reverse-ref fields written by the synthesis pass: the original two plus
    # one per generic kind (bundled_command_ids / bundled_rule_ids / ...).
    reverse_ref_fields = ["bundled_skill_ids", "bundled_mcp_ids"] + [
        f"bundled_{k.kind}_ids" for k in _BUNDLED_CHILD_KINDS
    ]
    cleared_refs = 0
    for plugin in kept:
        if plugin.get("type") != "plugin":
            continue
        bundle = plugin.get("bundle")
        if not isinstance(bundle, dict):
            continue
        for field in reverse_ref_fields:
            ids = bundle.get(field)
            if not isinstance(ids, list):
                continue
            cleaned: list[Any] = []
            for item in ids:
                if item is None:
                    cleaned.append(None)
                elif isinstance(item, str) and item in existing_ids:
                    cleaned.append(item)
                else:
                    cleaned.append(None)
                    cleared_refs += 1
            bundle[field] = cleaned

    if dropped_children or cleared_refs:
        log.info(
            "post-merge: dropped %d plugin children with missing parent and "
            "cleared %d stale plugin child refs",
            dropped_children,
            cleared_refs,
        )
    return kept


def _sync_synthesized_children_to_type_indexes(entries: list[dict], log=logger) -> None:
    """Write final synthesized plugin children back to type indexes.

    download_catalog.py downloads from catalog/<type-dir>/index.json, then
    reconciles catalog/index.json against files on disk. Synthetic children are
    created during merge, so they must be present in the type indexes as final
    entries before the download step runs.

    CRITICAL: every synthesized child ``source`` MUST map to a type-dir bucket
    via ``_SOURCE_TO_TYPE_DIR``. A missing bucket silently strands its children
    OUT of every type index → download_catalog never fetches them → the bundle
    drops them as orphans. ``_SOURCE_TO_TYPE_DIR`` is derived from
    ``_BUNDLED_CHILD_KINDS`` so a new kind is wired here automatically.
    """
    # Seed all known type-dir buckets so a dir with zero synthesized children
    # this run still gets its stale prior children scrubbed.
    children_by_dir: dict[str, list[dict]] = {
        td: [] for td in set(_SOURCE_TO_TYPE_DIR.values())
    }
    for entry in entries:
        type_dir = _SOURCE_TO_TYPE_DIR.get(entry.get("source"))
        if type_dir is not None:
            children_by_dir.setdefault(type_dir, []).append(entry)

    for type_dir, children in children_by_dir.items():
        index_path = os.path.join(CATALOG_DIR, type_dir, "index.json")
        original = load_index(index_path)
        existing = [
            e for e in original
            if e.get("source") not in _PLUGIN_BUNDLED_SOURCES
        ]
        if not children:
            if len(existing) != len(original):
                save_index(existing, index_path)
            continue

        child_ids = {
            e.get("id") for e in children if isinstance(e.get("id"), str) and e.get("id")
        }
        merged = [e for e in existing if e.get("id") not in child_ids]
        merged.extend(children)
        save_index(merged, index_path)
        log.info(
            "post-merge: synced %d synthesized plugin children into %s/index.json",
            len(children),
            type_dir,
        )


def overlay_curated_fields(entries: list) -> list:
    """Merge supplementary fields from curated.json files into deduped entries.

    For each entry in the deduped list, if a matching curated entry exists
    (matched by id, with fallback to normalized source_url):
      - tech_stack: union of curated + existing (curated values first, deduplicated)
      - tags: append curated tags (deduplicated)
      - Non-supplementary fields (name, description, stars, source_url, install,
        evaluation) are NOT overwritten.

    Curated entries with no match are appended as new entries.

    This function is idempotent: calling it multiple times produces the same result.
    """
    # Build lookup maps over the deduped entries
    id_to_entry: dict[str, Any] = {}
    url_to_entry: dict[str, Any] = {}
    for entry in entries:
        eid = entry.get("id", "")
        if eid:
            id_to_entry[eid] = entry
        surl = entry.get("source_url", "")
        if surl:
            url_to_entry[normalize_source_url(surl)] = entry

    appended: list = []

    for resource_type in TYPES:
        curated_path = os.path.join(CATALOG_DIR, resource_type, "curated.json")
        curated_entries = load_index(curated_path)
        for curated in curated_entries:
            cid = curated.get("id", "")
            curl = curated.get("source_url", "")
            norm_curl = normalize_source_url(curl) if curl else ""

            # Find match: id first, then normalized source_url
            target = None
            if cid and cid in id_to_entry:
                target = id_to_entry[cid]
            elif norm_curl and norm_curl in url_to_entry:
                target = url_to_entry[norm_curl]

            if target is None:
                # No match — append as new entry, track to prevent
                # duplicates from subsequent curated entries in the loop
                appended.append(curated)
                if cid:
                    id_to_entry[cid] = curated
                if norm_curl:
                    url_to_entry[norm_curl] = curated
                continue

            # Merge tech_stack: curated first, then existing, deduplicated
            curated_ts = curated.get("tech_stack") or []
            existing_ts = target.get("tech_stack") or []
            merged_ts_seen: set = set()
            merged_ts: list = []
            for item in curated_ts + existing_ts:
                if item not in merged_ts_seen:
                    merged_ts_seen.add(item)
                    merged_ts.append(item)
            target["tech_stack"] = merged_ts

            # Merge tags: append curated tags (deduplicated)
            curated_tags = curated.get("tags") or []
            existing_tags = target.get("tags") or []
            existing_tags_set = set(existing_tags)
            for tag in curated_tags:
                if tag not in existing_tags_set:
                    existing_tags.append(tag)
                    existing_tags_set.add(tag)
            target["tags"] = existing_tags

    return entries + appended


def _load_queue_state(queue_state_path: str) -> dict[str, Any]:
    try:
        with open(queue_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {}


def merge(skip_enrichment: bool = False):
    """Merge all source indexes into catalog/index.json.

    Args:
        skip_enrichment: When True, skip the LLM enrichment + evaluation step
            (``enrich_entries``) and produce a "data-only" catalog where every
            entry has ``evaluation == {}`` (empty dict, not missing key) so
            downstream aggregate jobs can distinguish a deferred-evaluation
            placeholder from a missing field. Governance still runs in
            health-only mode (no LLM-derived final_score), assigning safe
            defaults (final_score=0, decision="review").
    """
    all_entries = []

    for resource_type in TYPES:
        type_dir = os.path.join(CATALOG_DIR, resource_type)

        # Load auto-synced index (includes Tier 1 + Tier 2 for skills)
        index_path = os.path.join(type_dir, "index.json")
        entries = load_index(index_path)
        logger.info(f"Loaded {len(entries)} entries from {resource_type}/index.json")
        all_entries.extend(entries)

        # Load skills.sh sub-index (Tier 1 sibling source for skills only).
        # Skill identity-aware dedup in utils.deduplicate() collapses these
        # against the main index by source_priority, merging install_count /
        # skills_sh_url / skills_sh_scraped_at onto the winning entry.
        if resource_type == "skills":
            skills_sh_path = os.path.join(type_dir, "skills_sh_index.json")
            skills_sh_entries = load_index(skills_sh_path)
            if skills_sh_entries:
                logger.info(
                    f"Loaded {len(skills_sh_entries)} entries from "
                    f"{resource_type}/skills_sh_index.json"
                )
                all_entries.extend(skills_sh_entries)

        # Load mcp_registry sub-index (Tier 1 sibling source for mcp only).
        # mcp identity-aware dedup in utils.deduplicate() collapses registry
        # entries against GitHub URL sources by mcp_identity_key, merging
        # mcp_registry_status / mcp_registry_published_at / mcp_remotes onto
        # the winning entry. Sidecar absence is tolerated (logged at INFO).
        if resource_type == "mcp":
            mcp_registry_path = os.path.join(type_dir, "mcp_registry_index.json")
            if os.path.exists(mcp_registry_path):
                registry_entries = load_index(mcp_registry_path)
                if registry_entries:
                    logger.info(
                        f"Loaded {len(registry_entries)} entries from "
                        f"{resource_type}/mcp_registry_index.json"
                    )
                    all_entries.extend(registry_entries)
            else:
                logger.info(
                    f"No {resource_type}/mcp_registry_index.json sidecar; "
                    "skipping registry source"
                )

        # Load awesome-windsurfrules sub-index (Tier 1 sibling source for rules
        # only). Currently no rule_identity_key — entries are deduped by id /
        # source_url in Pass 2. Sidecar absence is tolerated.
        if resource_type == "rules":
            windsurfrules_path = os.path.join(type_dir, "windsurfrules_index.json")
            if os.path.exists(windsurfrules_path):
                wr_entries = load_index(windsurfrules_path)
                if wr_entries:
                    logger.info(
                        f"Loaded {len(wr_entries)} entries from "
                        f"{resource_type}/windsurfrules_index.json"
                    )
                    all_entries.extend(wr_entries)
            else:
                logger.info(
                    f"No {resource_type}/windsurfrules_index.json sidecar; "
                    "skipping windsurfrules source"
                )

        # Load curated entries (Tier 3 — lowest priority in dedup)
        curated_path = os.path.join(type_dir, "curated.json")
        curated = load_index(curated_path)
        if curated:
            logger.info(
                f"Loaded {len(curated)} entries from {resource_type}/curated.json"
            )
            all_entries.extend(curated)

    # Deduplicate by source_url + id (earlier entries take priority: Tier 1 > Tier 2 > Tier 3)
    pre_dedup_counts = {}
    for entry in all_entries:
        t = entry.get("type", "unknown")
        pre_dedup_counts[t] = pre_dedup_counts.get(t, 0) + 1

    deduped = deduplicate(all_entries)

    # Plugin schema validation: drop entries missing the marketplace fields
    # required by the install command (added by fix-plugin-marketplace-fields).
    # `marketplace_name` may be null (manifest had no `name` field), so it's not
    # required here — `marketplace_verified=False` covers that case.
    plugin_validated: list = []
    plugin_dropped = 0
    for entry in deduped:
        if entry.get("type") == "plugin":
            install = entry.get("install") or {}
            missing = []
            if not isinstance(install.get("marketplace_repo"), str) or not install.get("marketplace_repo"):
                missing.append("marketplace_repo")
            if not isinstance(install.get("marketplace_verified"), bool):
                missing.append("marketplace_verified")
            if missing:
                logger.warning(
                    "Dropping plugin entry id=%s (missing install fields: %s)",
                    entry.get("id"), ", ".join(missing),
                )
                plugin_dropped += 1
                continue
        plugin_validated.append(entry)
    if plugin_dropped:
        logger.info(
            "Plugin schema validator dropped %d entries missing required install fields",
            plugin_dropped,
        )
    deduped = plugin_validated

    post_dedup_counts = {}
    for entry in deduped:
        t = entry.get("type", "unknown")
        post_dedup_counts[t] = post_dedup_counts.get(t, 0) + 1
    for t, pre in pre_dedup_counts.items():
        post = post_dedup_counts.get(t, 0)
        drop_pct = (1 - post / pre) * 100 if pre > 0 else 0
        if drop_pct > 50:
            logger.warning(
                f"Dedup integrity: type={t} dropped {drop_pct:.0f}% ({pre} → {post})"
            )
        else:
            logger.info(f"Dedup stats: type={t} {pre} → {post} (-{drop_pct:.0f}%)")

    # Overlay supplementary fields (tech_stack, tags) from curated.json files
    deduped = overlay_curated_fields(deduped)

    # Fix invalid categories
    VALID_CATEGORIES = {
        "frontend",
        "backend",
        "fullstack",
        "mobile",
        "devops",
        "database",
        "testing",
        "security",
        "ai-ml",
        "tooling",
        "documentation",
    }
    fixed_cats = 0
    for entry in deduped:
        if entry.get("category") not in VALID_CATEGORIES:
            tags = entry.get("tags") or []
            entry["category"] = categorize(
                entry.get("name", ""), entry.get("description", ""), tags
            )
            fixed_cats += 1
    if fixed_cats:
        logger.info(f"Fixed {fixed_cats} entries with invalid category")

    # --- Overlay prior evaluation from existing output ---
    # Per-type source indexes don't carry evaluation data. Store the full
    # prior evaluation under _prior_evaluation so populate_signals() can
    # use it as a fallback when cache/LLM are unavailable, preventing
    # unchanged entries from losing their scores. Only overlay timestamps
    # into evaluation{} to avoid blocking enrich_quality() re-evaluation.
    existing_output = load_index(os.path.join(CATALOG_DIR, "index.json"))
    _TIMESTAMP_KEYS = ("evaluated_at", "model_id")
    _SCORE_KEYS = ("coding_relevance", "doc_completeness", "specificity")
    existing_eval_map = {}
    for entry in existing_output:
        eid = entry.get("id")
        ev = entry.get("evaluation")
        if eid and ev and (ev.get("evaluated_at") or any(ev.get(k) for k in _SCORE_KEYS)):
            existing_eval_map[eid] = ev
    for entry in deduped:
        eid = entry.get("id")
        if eid and eid in existing_eval_map and not entry.get("evaluation"):
            prior_ev = existing_eval_map[eid]
            entry["_prior_evaluation"] = dict(prior_ev)
            entry["evaluation"] = {k: prior_ev[k] for k in _TIMESTAMP_KEYS if k in prior_ev}

    # --- Preserve security block across rebuilds ---
    # Spec security-risk-eval "catalog_lifecycle 保留 security 字段": old entries'
    # `security` blocks SHALL survive rebuilds where the security stage is
    # skipped (SECURITY_SCAN_ENABLED=false) or fails for that entry. Overlay
    # happens BEFORE enrichment so a fresh security_scan result naturally wins
    # (it writes into entry["security"] later).
    overlay_preserved_fields(deduped, existing_output)

    # --- Backfill pushed_at: overlay from prior output, API only for new entries ---
    existing_pushed_at = {}
    for entry in existing_output:
        eid = entry.get("id")
        pa = entry.get("pushed_at")
        if eid and pa:
            existing_pushed_at[eid] = pa
    overlayed = 0
    for entry in deduped:
        if not entry.get("pushed_at"):
            pa = existing_pushed_at.get(entry.get("id"))
            if pa:
                entry["pushed_at"] = pa
                overlayed += 1

    # mcp_registry 派生条目复用 mcp_registry_published_at 作为 pushed_at，
    # 避免对 6000+ registry 条目逐个打 GitHub API（首次接入时 6h CI 超时根因）。
    # registry publishedAt 是 registry 端打包时间，对 freshness 信号是合理近似。
    registry_overlayed = 0
    for entry in deduped:
        if not entry.get("pushed_at"):
            rpa = entry.get("mcp_registry_published_at")
            if rpa:
                entry["pushed_at"] = rpa
                registry_overlayed += 1
    if registry_overlayed:
        logger.info(
            f"Overlayed pushed_at for {registry_overlayed} entries "
            f"from mcp_registry_published_at"
        )

    skip_pushed_at_backfill = (
        os.environ.get("MERGE_INDEX_SKIP_PUSHED_AT_BACKFILL", "").strip().lower()
        == "true"
    )
    still_missing = [e for e in deduped if not e.get("pushed_at") and e.get("source_url", "").startswith("https://github.com/")]
    if still_missing and not skip_pushed_at_backfill:
        logger.info(f"Backfilling pushed_at for {len(still_missing)} new entries via GitHub API (overlayed {overlayed} from prior output)")
        filled = 0
        for entry in still_missing:
            meta = get_repo_meta(entry["source_url"])
            if meta and meta.get("pushed_at"):
                entry["pushed_at"] = meta["pushed_at"]
                filled += 1
        logger.info(f"Backfilled pushed_at for {filled}/{len(still_missing)} entries")
    elif still_missing and skip_pushed_at_backfill:
        logger.info(
            "MERGE_INDEX_SKIP_PUSHED_AT_BACKFILL=true: skipped pushed_at "
            "GitHub API backfill for %d entries (overlayed %d from prior output)",
            len(still_missing),
            overlayed,
        )
    elif overlayed:
        logger.info(f"Overlayed pushed_at for {overlayed} entries from prior output, 0 new API calls")

    # --- Post-merge soft annotation: bundled_in on skills bundled by plugins ---
    # Runs AFTER deduplicate()/overlay_curated_fields() and BEFORE enrichment so
    # downstream stages (governance / lifecycle / featured / readme) can read the
    # bundled_in field. Per spec plugin-bundle-dedup §"Post-merge bundled_in
    # soft annotation" (`openspec/changes/add-plugins-category`).
    _apply_bundled_in_annotations(deduped)

    # --- Layer 2: Enrichment (tags, translation, LLM evaluation, signals) ---
    if skip_enrichment:
        logger.info(
            "--skip-enrichment: skipping LLM evaluation; "
            "entries will have evaluation={}"
        )
        # Reset evaluation to an empty dict on every entry so downstream
        # aggregate jobs can distinguish "data layer wrote skip-enrichment
        # placeholder" from "missing key entirely". Drop _prior_evaluation
        # too — that overlay is only meaningful when enrichment runs.
        for entry in deduped:
            entry["evaluation"] = {}
            entry.pop("_prior_evaluation", None)
    else:
        enrich_entries(deduped)
        logger.info(f"Enrichment complete for {len(deduped)} entries")

    # --- Layer 3: Scoring & Governance (final_score, decision, health, reject filter) ---
    # Only pass health_only when set, so legacy mocks of apply_governance that
    # accept a single positional arg continue to work.
    if skip_enrichment:
        deduped = apply_governance(deduped, health_only=True)
    else:
        deduped = apply_governance(deduped)
    logger.info(f"Governance complete: {len(deduped)} entries after filtering")

    deduped = _prune_invalid_plugin_child_refs(deduped)

    # Promote scoring fields to top level for easy consumption by search/browse/recommend.
    # In skip_enrichment mode, evaluation stays empty ({}) so final_score=0,
    # decision="review" — aggregate_enrichment will fill these in later.
    for entry in deduped:
        ev = entry.get("evaluation") or {}
        if skip_enrichment:
            entry["evaluation"] = {}
            entry["final_score"] = 0
            entry["decision"] = "review"
        else:
            entry["final_score"] = ev.get("final_score", 0)
            entry["decision"] = ev.get("decision", "review")

    # Inherit final_score from the parent plugin for synthesized plugin
    # children. This MUST run AFTER the promotion loop above: at synthesis
    # time (_apply_bundled_in_annotations, pre-governance) the parent plugin's
    # top-level final_score is not computed yet, so the field would be 0/stale.
    # MVP: bundled children display the parent plugin's score (no separate
    # eval). Identified by source == plugin-bundled-* + bundled_in.
    _backfill_bundled_child_final_scores(deduped)

    # --- Lifecycle ---
    existing_output = backfill_missing_added_at(existing_output, today=TODAY)
    prior_entries = deduped + existing_output
    deduped = overlay_added_at(deduped, prior_entries, today=TODAY)

    maintenance_dir = os.path.join(CATALOG_DIR, "maintenance")
    queue_path = os.path.join(maintenance_dir, "incremental_recrawl_candidates.json")
    queue_state_path = os.path.join(maintenance_dir, "incremental_recrawl_state.json")
    queue_state = _load_queue_state(queue_state_path)
    candidates, queue_state = build_incremental_recrawl_candidates(
        deduped,
        queue_state,
        now=datetime.combine(
            date.fromisoformat(TODAY), datetime.min.time(), tzinfo=timezone.utc
        ),
        threshold_days=365,
        cooldown_days=30,
        max_candidates=500,
    )
    save_index(candidates, queue_path)
    os.makedirs(os.path.dirname(queue_state_path), exist_ok=True)
    with open(queue_state_path, "w", encoding="utf-8") as f:
        json.dump(queue_state, f, indent=2, ensure_ascii=False)

    # Sort by final_score descending, then health.score, then stars (nulls last)
    deduped.sort(
        key=lambda x: (
            x.get("final_score", 0),
            x.get("health", {}).get("score", 0),
            x.get("stars") if x.get("stars") is not None else -1,
        ),
        reverse=True,
    )

    output_path = os.path.join(CATALOG_DIR, "index.json")
    _sync_synthesized_children_to_type_indexes(deduped)
    save_index(deduped, output_path)

    # Generate lightweight search index (subset of fields for search/browse/recommend)
    SEARCH_INDEX_FIELDS = (
        "id", "name", "type", "category", "tags", "tech_stack",
        "stars", "description", "description_zh", "source_url",
        "final_score", "decision", "freshness_label", "bundled_in",
        # source 透传：让 Detail fallback / 客户端搜索结果也能渲染
        # github-trending 等 source 角标（per-type JSON 已带，这里补上 search-index）。
        "source",
    )
    search_entries = []
    for entry in deduped:
        se = {k: entry.get(k) for k in SEARCH_INDEX_FIELDS}
        install_obj = entry.get("install")
        se["install_method"] = install_obj.get("method") if isinstance(install_obj, dict) else None
        # For plugin entries, carry the marketplace_verified flag in a minimal
        # install sub-object so list-view cards can render the "unverified"
        # badge without re-fetching the per-entry JSON.
        if entry.get("type") == "plugin" and isinstance(install_obj, dict):
            verified = install_obj.get("marketplace_verified")
            if isinstance(verified, bool):
                se["install"] = {"marketplace_verified": verified}
        # Build search_text: merged field for semantic keyword matching
        parts = [
            entry.get("name", ""),
            entry.get("description", ""),
            entry.get("description_zh", ""),
            " ".join(entry.get("tags") or []),
            " ".join(entry.get("tech_stack") or []),
            " ".join(entry.get("search_terms") or []),
        ]
        se["search_text"] = " ".join(p for p in parts if p)
        search_entries.append(se)

    search_index_path = os.path.join(CATALOG_DIR, "search-index.json")
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(search_entries, f, ensure_ascii=False, separators=(",", ":"))

    full_size = os.path.getsize(output_path)
    search_size = os.path.getsize(search_index_path)
    ratio = search_size / full_size * 100 if full_size else 0
    logger.info(
        f"Search index: {len(search_entries)} entries, "
        f"{search_size / 1024:.0f} KB ({ratio:.1f}% of full index)"
    )

    # Print summary by type and category
    by_type = {}
    by_category = {}
    for entry in deduped:
        t = entry.get("type", "unknown")
        c = entry.get("category", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_category[c] = by_category.get(c, 0) + 1

    logger.info(f"\nTotal: {len(deduped)} entries")
    logger.info(f"By type: {by_type}")
    logger.info(f"By category: {by_category}")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Parses argv and dispatches to merge()."""
    parser = argparse.ArgumentParser(
        description=(
            "Merge type-specific indexes and curated files into "
            "catalog/index.json."
        )
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        default=False,
        help=(
            "Skip the LLM enrichment + evaluation step. Produces a "
            "'data-only' catalog where every entry has evaluation={} "
            "so a downstream aggregate job can fill it in."
        ),
    )
    args = parser.parse_args(argv)
    merge(skip_enrichment=args.skip_enrichment)


if __name__ == "__main__":
    main()
