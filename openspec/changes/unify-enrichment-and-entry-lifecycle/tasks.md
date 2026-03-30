## 1. Schema and validation groundwork

- [x] 1.1 Update `catalog/schema.json` to define the new lifecycle field for `mcp` / `skill` entries and the governance-oriented `evaluation` sub-object without removing existing top-level publish fields
- [x] 1.2 Update validation and helper logic that assumes the old schema shape (including curated/index validation paths) so new fields are accepted consistently
- [x] 1.3 Decide and document the canonical identity rule used to preserve lifecycle metadata across full index rebuilds (`id` first, normalized `source_url` fallback)

## 2. Preserve `added_at` across full sync rebuilds

- [x] 2.1 Add a shared helper that loads the previous type-specific index and overlays historical `added_at` onto regenerated `mcp` / `skill` entries
- [x] 2.2 Integrate the overlay helper into `scripts/sync_mcp.py` so existing MCP entries keep their original `added_at` and only brand-new entries receive today’s date
- [x] 2.3 Integrate the overlay helper into `scripts/sync_skills.py` so existing Skill entries keep their original `added_at` and only brand-new entries receive today’s date
- [x] 2.4 Backfill missing `added_at` values for the existing `catalog/mcp/index.json` and `catalog/skills/index.json` in a repeatable way that does not overwrite preserved values

## 3. Land the unified enrichment contract

- [x] 3.1 Extract or introduce a shared enrichment orchestration layer that defines the normalized `evaluation` output contract described in docs 4.5
- [x] 3.2 Refactor the current Skill enrichment flow so translation, LLM evaluation, and tag normalization are coordinated through the shared enrichment contract instead of separate ad-hoc outputs
- [x] 3.3 Update downstream publish/merge logic to populate top-level `category`, `tags`, and `description_zh` from the unified enrichment result while remaining backward-compatible with legacy fields during migration
- [x] 3.4 Update health / scoring code paths to read semantic-quality inputs from the new governance layer with fallback to existing fields where needed

## 4. Generate and maintain the incremental recrawl queue

- [x] 4.1 Create a dedicated maintenance artifact (and companion state if needed) for cross-run incremental recrawl candidates instead of overloading source-specific crawl caches
- [x] 4.2 Implement queue generation rules for `mcp` / `skill` entries based on `added_at`, configurable age threshold, and recrawl cooldown / dedup semantics
- [x] 4.3 Record enough candidate metadata for later processing, including resource type, stable identifier, enqueue reason, enqueue time, and priority inputs
- [x] 4.4 Prioritize stale-risk entries in the queue without making queue membership itself dependent on automatic catalog deletion

## 5. Wire the queue into the sync pipeline safely

- [x] 5.1 Define where the queue generation step runs in the existing sync/merge flow so it executes after fresh catalog data is available
- [x] 5.2 Ensure existing source-specific incremental mechanisms (`catalog/mcp/crawl_state.json`, `catalog/skills/.repo_cache.json`) keep their current responsibilities and only consume the new queue through explicit integration points
- [x] 5.3 Add CI or local command coverage for generating the maintenance artifacts and verifying they remain deterministic across repeated runs

## 6. Verification and documentation

- [x] 6.1 Add or update tests for schema compatibility, `added_at` preservation across rebuilds, and queue dedup / threshold behavior
- [x] 6.2 Run the relevant sync / merge / validation commands to prove the new schema and generated artifacts work end to end
- [x] 6.3 Update README / docs / operator notes to explain the unified enrichment governance layer and how `added_at` plus the incremental recrawl queue keep catalog freshness maintainable
