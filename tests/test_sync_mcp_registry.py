"""scripts/sync_mcp_registry.py 单元测试。

覆盖：
- 分页（多个 cursor）聚合
- ETag 304 走本地缓存
- active 过滤 / isLatest 过滤
- normalize_entry 字段映射（source_url / mcp_remotes / status / published_at）
- id 唯一性 + source_url distinct
- compute_diff 四类：added / status_changed / version_bumped / removed + stable
- 5xx 异常退出
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
import urllib.error

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import sync_mcp_registry as smr  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_response(body: bytes, etag: str = ""):
    class _Headers(dict):
        def get(self, name, default=""):
            return super().get(name, default)

    class _Resp:
        def __init__(self, body, headers):
            self._body = body
            self.headers = headers

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    h = _Headers()
    if etag:
        h["ETag"] = etag
    return _Resp(body, h)


def _raw_entry(name, version="1.0.0", status="active", is_latest=True,
               title=None, description="desc", remotes=None,
               published_at="2026-04-01T00:00:00Z",
               repository=None, packages=None, website_url=None):
    """构造一条 registry raw entry。"""
    server: dict = {
        "name": name,
        "title": title or name,
        "description": description,
        "version": version,
        "remotes": remotes or [],
    }
    if repository is not None:
        server["repository"] = repository
    if packages is not None:
        server["packages"] = packages
    if website_url is not None:
        server["websiteUrl"] = website_url
    return {
        "server": server,
        "_meta": {
            smr.META_KEY: {
                "status": status,
                "isLatest": is_latest,
                "publishedAt": published_at,
                "statusChangedAt": published_at,
                "updatedAt": published_at,
            }
        },
    }


class _CacheSandbox:
    """切换 sync_mcp_registry 模块的缓存路径常量到临时目录。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._patches = []

    def __enter__(self):
        cache_dir = os.path.join(self.tmp.name, ".mcp_registry_cache")
        os.makedirs(cache_dir, exist_ok=True)
        catalog_dir = os.path.join(self.tmp.name, "catalog", "mcp")
        os.makedirs(catalog_dir, exist_ok=True)
        self._patches = [
            mock.patch.object(smr, "CACHE_DIR", cache_dir),
            mock.patch.object(smr, "REGISTRY_CACHE_PATH",
                              os.path.join(cache_dir, "registry.json")),
            mock.patch.object(smr, "ETAG_PATH", os.path.join(cache_dir, "etag.txt")),
            mock.patch.object(smr, "DIFF_PATH", os.path.join(cache_dir, "diff.json")),
            mock.patch.object(smr, "DIFF_BASELINE_PATH",
                              os.path.join(cache_dir, "diff_baseline.json")),
            mock.patch.object(smr, "OUTPUT_PATH",
                              os.path.join(catalog_dir, "mcp_registry_index.json")),
            # stars 门槛会发 GraphQL 请求，这里测的是拉取 / diff；门槛见
            # test_sync_mcp_registry_stars.py
            mock.patch.dict(os.environ, {"MCP_REGISTRY_MIN_STARS": "0"}),
            mock.patch.object(smr, "PAGE_RETRY_BACKOFF", 0),
        ]
        for p in self._patches:
            p.start()
        self.cache_dir = cache_dir
        self.catalog_dir = catalog_dir
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()
        return False


# ---------------------------------------------------------------------------
# fetch_registry: pagination
# ---------------------------------------------------------------------------

class TestFetchRegistryPagination(unittest.TestCase):
    def test_multi_page_cursor_aggregation(self):
        """两页响应聚合后总条数 = 两页 servers 之和。"""
        page1 = {
            "servers": [
                _raw_entry("io.github.foo/bar"),
                _raw_entry("io.github.baz/qux"),
            ],
            "metadata": {"nextCursor": "cur1", "count": 2},
        }
        page2 = {
            "servers": [
                _raw_entry("com.example/svc"),
            ],
            "metadata": {"count": 1},
        }
        responses = [
            _make_response(json.dumps(page1).encode("utf-8"), etag="etag-v1"),
            _make_response(json.dumps(page2).encode("utf-8")),
        ]

        with _CacheSandbox():
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=responses):
                out = list(smr.fetch_registry(limit=2))
            self.assertEqual(len(out), 3)
            names = [r["server"]["name"] for r in out]
            self.assertEqual(names, ["io.github.foo/bar",
                                     "io.github.baz/qux",
                                     "com.example/svc"])
            # ETag 已落盘（首页）
            with open(smr.ETAG_PATH, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "etag-v1")
            # 本地缓存包含全部 3 条
            with open(smr.REGISTRY_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            self.assertEqual(len(cached), 3)

    def test_single_page_no_cursor(self):
        page = {
            "servers": [_raw_entry("a.b/c")],
            "metadata": {"count": 1},
        }
        with _CacheSandbox():
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                out = list(smr.fetch_registry())
            self.assertEqual(len(out), 1)


# ---------------------------------------------------------------------------
# ETag 304
# ---------------------------------------------------------------------------

class TestETag304(unittest.TestCase):
    def test_etag_304_uses_local_cache(self):
        """304 时 fetch_registry 直接 yield 本地缓存条目。"""
        with _CacheSandbox():
            cached = [_raw_entry("io.github.x/y", version="2.0.0")]
            with open(smr.REGISTRY_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cached, f)
            with open(smr.ETAG_PATH, "w", encoding="utf-8") as f:
                f.write("old-etag")
            err = urllib.error.HTTPError(
                url=smr.REGISTRY_BASE, code=304, msg="Not Modified",
                hdrs=None, fp=None,
            )
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=err):
                out = list(smr.fetch_registry())
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["server"]["name"], "io.github.x/y")

    def test_304_no_cache_raises(self):
        """304 但本地无缓存 → 抛 RuntimeError。"""
        with _CacheSandbox():
            with open(smr.ETAG_PATH, "w", encoding="utf-8") as f:
                f.write("old-etag")
            err = urllib.error.HTTPError(
                url=smr.REGISTRY_BASE, code=304, msg="Not Modified",
                hdrs=None, fp=None,
            )
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=err):
                with self.assertRaises(RuntimeError):
                    list(smr.fetch_registry())


class TestNetworkErrors(unittest.TestCase):
    def test_5xx_raises_runtime_error(self):
        with _CacheSandbox():
            err = urllib.error.HTTPError(
                url=smr.REGISTRY_BASE, code=503, msg="Service Unavailable",
                hdrs=None, fp=None,
            )
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=err):
                with self.assertRaises(RuntimeError):
                    list(smr.fetch_registry())

    def test_url_error_raises_runtime_error(self):
        with _CacheSandbox():
            err = urllib.error.URLError(reason="connection refused")
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=err):
                with self.assertRaises(RuntimeError):
                    list(smr.fetch_registry())

    def test_page_timeout_retried_then_succeeds(self):
        """单页超时重试后成功，不再整轮放弃（10-19 定时运行死在第 46 页超时）。"""
        with _CacheSandbox():
            page = _make_response(json.dumps({
                "servers": [_raw_entry("io.github.x/y")], "metadata": {},
            }).encode())
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=[TimeoutError("timed out"), page]) as u:
                out = list(smr.fetch_registry())
            self.assertEqual(len(out), 1)
            self.assertEqual(u.call_count, 2)

    def test_5xx_gives_up_after_page_attempts(self):
        with _CacheSandbox():
            err = urllib.error.HTTPError(
                url=smr.REGISTRY_BASE, code=500, msg="Internal Server Error",
                hdrs=None, fp=None,
            )
            with mock.patch.object(smr.urllib.request, "urlopen", side_effect=err) as u:
                with self.assertRaises(RuntimeError):
                    list(smr.fetch_registry())
            self.assertEqual(u.call_count, smr.PAGE_ATTEMPTS)

    def test_request_asks_for_latest_versions_only(self):
        with _CacheSandbox():
            page = _make_response(json.dumps({"servers": [], "metadata": {}}).encode())
            with mock.patch.object(smr.urllib.request, "urlopen", return_value=page) as u:
                list(smr.fetch_registry())
            self.assertIn("version=latest", u.call_args[0][0].full_url)

    def test_main_returns_1_on_fetch_failure(self):
        """主流程 main() 在 fetch 失败时返回 exit code 1。"""
        with _CacheSandbox():
            err = urllib.error.URLError(reason="net down")
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=err):
                rc = smr.main()
            self.assertEqual(rc, 1)

    def test_timeout_raises_runtime_error(self):
        """urlopen 抛 TimeoutError 必须被转成 RuntimeError，不能逃逸。

        覆盖 Finding E：urllib.request.urlopen(timeout=N) 触发的超时在新 Python
        是 TimeoutError（socket.timeout 别名），不是 URLError 的子类。
        """
        with _CacheSandbox():
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=TimeoutError("timed out")):
                with self.assertRaises(RuntimeError):
                    list(smr.fetch_registry())

    def test_main_returns_1_on_timeout(self):
        """main() 必须把 TimeoutError 当成失败正常退出码 1。"""
        with _CacheSandbox():
            with mock.patch.object(smr.urllib.request, "urlopen",
                                   side_effect=TimeoutError("timed out")):
                rc = smr.main()
            self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# active + isLatest filter
# ---------------------------------------------------------------------------

class TestActiveLatestFilter(unittest.TestCase):
    def test_active_latest_passes(self):
        r = _raw_entry("a/b", status="active", is_latest=True)
        self.assertTrue(smr.is_active_and_latest(r))

    def test_inactive_filtered(self):
        r = _raw_entry("a/b", status="inactive", is_latest=True)
        self.assertFalse(smr.is_active_and_latest(r))

    def test_deprecated_filtered(self):
        r = _raw_entry("a/b", status="deprecated", is_latest=True)
        self.assertFalse(smr.is_active_and_latest(r))

    def test_not_latest_filtered(self):
        r = _raw_entry("a/b", status="active", is_latest=False)
        self.assertFalse(smr.is_active_and_latest(r))

    def test_missing_meta_filtered(self):
        self.assertFalse(smr.is_active_and_latest({"server": {"name": "a/b"}}))

    def test_main_filters_inactive_and_outdated(self):
        """端到端：main() 仅写入 active+isLatest 条目。"""
        page = {
            "servers": [
                _raw_entry("io.github.keep/a", status="active", is_latest=True),
                _raw_entry("io.github.drop/b", status="inactive", is_latest=True),
                _raw_entry("io.github.drop/c", status="active", is_latest=False),
                _raw_entry("io.github.keep/d", status="active", is_latest=True),
            ],
            "metadata": {"count": 4},
        }
        with _CacheSandbox():
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                rc = smr.main()
            self.assertEqual(rc, 0)
            with open(smr.OUTPUT_PATH, "r", encoding="utf-8") as f:
                out = json.load(f)
            ids = {e["id"] for e in out}
            self.assertEqual(len(out), 2)
            self.assertTrue(any("keep-a" in i for i in ids))
            self.assertTrue(any("keep-d" in i for i in ids))


# ---------------------------------------------------------------------------
# normalize_entry: field mapping
# ---------------------------------------------------------------------------

class TestNormalizeEntry(unittest.TestCase):
    def test_field_mapping_basic(self):
        raw = _raw_entry(
            "io.github.foo/bar",
            version="1.2.3",
            title="Foo Bar Server",
            description="A test MCP server",
            remotes=[
                {"type": "streamable-http", "url": "https://foo.example/mcp"},
                {"type": "sse", "url": "https://foo.example/sse"},
            ],
            published_at="2026-04-15T10:00:00Z",
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["name"], "Foo Bar Server")
        self.assertEqual(e["description"], "A test MCP server")
        self.assertEqual(e["version"], "1.2.3")
        self.assertEqual(e["type"], "mcp")
        self.assertEqual(e["source"], smr.SOURCE_NAME)
        self.assertEqual(e["mcp_registry_status"], "active")
        self.assertEqual(e["mcp_registry_published_at"], "2026-04-15T10:00:00Z")
        self.assertEqual(len(e["mcp_remotes"]), 2)
        self.assertEqual(e["mcp_remotes"][0]["type"], "streamable-http")
        self.assertEqual(e["mcp_remotes"][0]["url"], "https://foo.example/mcp")

    def test_source_url_uses_registry_base(self):
        """无 repository 字段 → 退回 registry URL fallback。"""
        raw = _raw_entry("io.github.foo/bar")
        e = smr.normalize_entry(raw)
        self.assertTrue(e["source_url"].startswith(smr.REGISTRY_BASE + "/"))
        self.assertIn("io.github.foo", e["source_url"])

    # --- §14 修复 A：source_url 优先用 server.repository.url ---

    def test_source_url_uses_github_when_repository_present(self):
        """含 repository.source=github + url → 直接落到 GitHub URL，不走 registry。"""
        raw = _raw_entry(
            "io.github.foo/bar",
            repository={
                "source": "github",
                "url": "https://github.com/foo/bar",
            },
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["source_url"], "https://github.com/foo/bar")
        self.assertNotIn("registry.modelcontextprotocol.io", e["source_url"])

    def test_source_url_includes_subfolder_for_monorepo(self):
        """monorepo: repository.subfolder 存在 → URL 含 ``/tree/HEAD/<subfolder>``。"""
        raw = _raw_entry(
            "io.github.foo/bar",
            repository={
                "source": "github",
                "url": "https://github.com/foo/bar",
                "subfolder": "packages/lona-mcp-server",
            },
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(
            e["source_url"],
            "https://github.com/foo/bar/tree/HEAD/packages/lona-mcp-server",
        )

    def test_source_url_falls_back_to_registry_when_no_github_repo(self):
        """无 repository（典型 SaaS / 商业 server）→ source_url 退回 registry URL。"""
        raw = _raw_entry("ac.inference.sh/mcp")
        e = smr.normalize_entry(raw)
        self.assertTrue(e["source_url"].startswith(smr.REGISTRY_BASE + "/"))

    def test_source_url_falls_back_when_repository_source_not_github(self):
        """repository.source != github（如 gitlab）→ 走 fallback。"""
        raw = _raw_entry(
            "com.example/svc",
            repository={
                "source": "gitlab",
                "url": "https://gitlab.com/foo/bar",
            },
        )
        e = smr.normalize_entry(raw)
        self.assertTrue(e["source_url"].startswith(smr.REGISTRY_BASE + "/"))

    def test_source_url_strips_trailing_slash(self):
        """repository.url 末尾 / 应被去掉，避免 ``//tree/HEAD/...``。"""
        raw = _raw_entry(
            "io.github.foo/bar",
            repository={
                "source": "github",
                "url": "https://github.com/foo/bar/",
            },
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["source_url"], "https://github.com/foo/bar")

    # --- §14 修复 B：install.config 解析 server.packages[] ---

    def test_install_config_for_npm_package(self):
        raw = _raw_entry(
            "io.github.foo/bar",
            packages=[{
                "registryType": "npm",
                "identifier": "@foo/bar-mcp",
                "version": "1.5.2",
                "transport": {"type": "stdio"},
            }],
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["install"]["method"], "manual")
        cfg = e["install"]["config"]
        self.assertEqual(cfg["registry_type"], "npm")
        self.assertEqual(cfg["identifier"], "@foo/bar-mcp")
        self.assertEqual(cfg["version"], "1.5.2")
        self.assertEqual(cfg["command"], "npx -y @foo/bar-mcp@1.5.2")

    def test_install_config_for_pypi_package(self):
        raw = _raw_entry(
            "io.github.foo/bar",
            packages=[{
                "registryType": "pypi",
                "identifier": "foo-mcp",
                "version": "0.3.0",
            }],
        )
        e = smr.normalize_entry(raw)
        cfg = e["install"]["config"]
        self.assertEqual(cfg["command"], "pipx run foo-mcp==0.3.0")

    def test_install_config_for_npm_package_no_version(self):
        """无 version 字段 → 命令省略版本号，不留 trailing @。"""
        raw = _raw_entry(
            "io.github.foo/bar",
            packages=[{
                "registryType": "npm",
                "identifier": "@foo/bar-mcp",
            }],
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["install"]["config"]["command"], "npx -y @foo/bar-mcp")

    def test_install_falls_back_to_manual_when_no_packages(self):
        """无 packages → install 不含 config 字段，行为保持原样。"""
        raw = _raw_entry("io.github.foo/bar")
        e = smr.normalize_entry(raw)
        self.assertEqual(e["install"]["method"], "manual")
        self.assertNotIn("config", e["install"])
        self.assertEqual(e["install"]["remotes"], [])

    def test_website_url_preserved_when_present(self):
        raw = _raw_entry(
            "io.github.foo/bar",
            website_url="https://foo.example.com",
        )
        e = smr.normalize_entry(raw)
        self.assertEqual(e["website_url"], "https://foo.example.com")

    def test_source_url_url_encodes_special_chars(self):
        """server.name 的 / 等字符 SHALL 被 URL-encoded。"""
        raw = _raw_entry("io.github.foo/bar baz")
        e = smr.normalize_entry(raw)
        # space → %20, / → %2F
        self.assertIn("%20", e["source_url"])
        self.assertIn("%2F", e["source_url"])

    def test_id_stable_for_same_name(self):
        """同一 server.name → 同一 id。"""
        a = smr.normalize_entry(_raw_entry("io.github.foo/bar"))
        b = smr.normalize_entry(_raw_entry("io.github.foo/bar", version="2.0.0"))
        self.assertEqual(a["id"], b["id"])

    def test_id_unique_for_different_names(self):
        a = smr.normalize_entry(_raw_entry("io.github.foo/bar"))
        b = smr.normalize_entry(_raw_entry("io.github.foo/baz"))
        c = smr.normalize_entry(_raw_entry("com.microsoft/azure"))
        self.assertEqual(len({a["id"], b["id"], c["id"]}), 3)

    def test_id_kebab_case(self):
        e = smr.normalize_entry(_raw_entry("io.github.Foo_BAR/Some_Repo"))
        # 全小写 + - 分隔
        self.assertRegex(e["id"], r"^[a-z0-9-]+$")
        # id 末尾追加 8 位 hex hash（防 kebab 碰撞）
        self.assertRegex(e["id"], r"-[0-9a-f]{8}$")

    def test_id_disambiguates_kebab_collisions(self):
        """kebab 后字面相同的两个 server.name 必须产生不同 id（hash 后缀消歧）。

        io.github.foo/bar-baz 和 io.github.foo-bar/baz kebab 后均为
        io-github-foo-bar-baz，必须靠 hash 后缀区分。
        """
        a = smr.normalize_entry(_raw_entry("io.github.foo/bar-baz"))
        b = smr.normalize_entry(_raw_entry("io.github.foo-bar/baz"))
        # kebab 前缀部分相同
        self.assertTrue(a["id"].startswith("io-github-foo-bar-baz-"))
        self.assertTrue(b["id"].startswith("io-github-foo-bar-baz-"))
        # 整 id 不同（hash 后缀不同）
        self.assertNotEqual(a["id"], b["id"])

    def test_main_source_url_distinct(self):
        """端到端：所有 entry 的 source_url 唯一。"""
        names = [f"io.github.org{i}/repo" for i in range(5)]
        page = {
            "servers": [_raw_entry(n) for n in names],
            "metadata": {"count": 5},
        }
        with _CacheSandbox():
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                rc = smr.main()
            self.assertEqual(rc, 0)
            with open(smr.OUTPUT_PATH, "r", encoding="utf-8") as f:
                out = json.load(f)
            urls = [e["source_url"] for e in out]
            self.assertEqual(len(urls), len(set(urls)))


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------

class TestComputeDiff(unittest.TestCase):
    def _entry(self, eid, version="1.0.0", status="active",
               published_at="2026-04-01T00:00:00Z"):
        return {
            "id": eid,
            "version": version,
            "mcp_registry_status": status,
            "mcp_registry_published_at": published_at,
        }

    def test_added(self):
        prev = []
        new = [self._entry("a"), self._entry("b")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(diff["added"], ["a", "b"])
        self.assertEqual(diff["removed"], [])

    def test_removed(self):
        prev = [self._entry("a"), self._entry("b")]
        new = [self._entry("a")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(diff["removed"], ["b"])
        self.assertEqual(diff["added"], [])

    def test_status_changed(self):
        prev = [self._entry("a", status="active")]
        new = [self._entry("a", status="deprecated")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(len(diff["status_changed"]), 1)
        self.assertEqual(diff["status_changed"][0]["id"], "a")
        self.assertEqual(diff["status_changed"][0]["old"], "active")
        self.assertEqual(diff["status_changed"][0]["new"], "deprecated")
        self.assertEqual(diff["version_bumped"], [])

    def test_version_bumped(self):
        prev = [self._entry("a", version="1.0.0")]
        new = [self._entry("a", version="1.1.0")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(len(diff["version_bumped"]), 1)
        self.assertEqual(diff["version_bumped"][0]["id"], "a")
        self.assertEqual(diff["version_bumped"][0]["old"], "1.0.0")
        self.assertEqual(diff["version_bumped"][0]["new"], "1.1.0")
        self.assertEqual(diff["status_changed"], [])

    def test_stable_when_version_status_unchanged(self):
        prev = [self._entry("a", version="1.0.0", status="active",
                            published_at="2026-04-01T00:00:00Z")]
        # published_at 改变但 version/status 一致 → 仍 stable
        new = [self._entry("a", version="1.0.0", status="active",
                           published_at="2026-04-15T00:00:00Z")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(diff["stable"], 1)
        self.assertEqual(diff["version_bumped"], [])
        self.assertEqual(diff["status_changed"], [])

    def test_status_change_takes_precedence_over_version(self):
        """同时 status + version 变 → 归入 status_changed（避免双重计数）。"""
        prev = [self._entry("a", version="1.0.0", status="active")]
        new = [self._entry("a", version="2.0.0", status="deprecated")]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(len(diff["status_changed"]), 1)
        self.assertEqual(diff["version_bumped"], [])

    def test_full_four_categories(self):
        prev = [
            self._entry("stable-1"),
            self._entry("status-1", status="active"),
            self._entry("ver-1", version="1.0.0"),
            self._entry("removed-1"),
        ]
        new = [
            self._entry("stable-1"),
            self._entry("status-1", status="deprecated"),
            self._entry("ver-1", version="2.0.0"),
            self._entry("added-1"),
        ]
        diff = smr.compute_diff(prev, new)
        self.assertEqual(diff["added"], ["added-1"])
        self.assertEqual(diff["removed"], ["removed-1"])
        self.assertEqual(diff["stable"], 1)
        self.assertEqual([c["id"] for c in diff["status_changed"]], ["status-1"])
        self.assertEqual([c["id"] for c in diff["version_bumped"]], ["ver-1"])


# ---------------------------------------------------------------------------
# Main flow integration
# ---------------------------------------------------------------------------

class TestMainIntegration(unittest.TestCase):
    def test_main_status_transition_active_to_deprecated_diff(self):
        """server 从 active 翻转为 deprecated，diff 必须归入 status_changed 而非 removed。

        覆盖 Finding B：之前 main() 在 compute_diff 之前就把非 active 条目过滤掉，
        导致这类 status 转移被误标记为 removed。
        """
        with _CacheSandbox():
            # 第一次 sync: server 处于 active 状态，写入 prev 输出
            page1 = {
                "servers": [
                    _raw_entry("io.github.foo/bar", status="active"),
                ],
                "metadata": {"count": 1},
            }
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page1).encode("utf-8")),
            ):
                rc1 = smr.main()
            self.assertEqual(rc1, 0)

            # 第二次 sync: server 翻转为 deprecated（仍 isLatest）
            page2 = {
                "servers": [
                    _raw_entry("io.github.foo/bar", status="deprecated"),
                ],
                "metadata": {"count": 1},
            }
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page2).encode("utf-8")),
            ):
                rc2 = smr.main()
            self.assertEqual(rc2, 0)

            with open(smr.DIFF_PATH, "r", encoding="utf-8") as f:
                diff = json.load(f)

            # 必须出现在 status_changed，且 NOT 在 removed
            sids = [c["id"] for c in diff["status_changed"]]
            self.assertEqual(len(diff["status_changed"]), 1)
            self.assertEqual(diff["status_changed"][0]["old"], "active")
            self.assertEqual(diff["status_changed"][0]["new"], "deprecated")
            self.assertEqual(diff["removed"], [])
            self.assertEqual(diff["added"], [])
            # 输出文件本身仍只含 active 条目（即此次 deprecated 不会被写入）
            with open(smr.OUTPUT_PATH, "r", encoding="utf-8") as f:
                out = json.load(f)
            self.assertEqual(out, [])
            # status_changed 的 id 与上次 active 写入的 id 一致
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page1).encode("utf-8")),
            ):
                # 复用同样的 server name 计算 expected id
                expected_entry = smr.normalize_entry(
                    _raw_entry("io.github.foo/bar", status="active")
                )
            self.assertEqual(sids, [expected_entry["id"]])

    def test_non_active_islatest_not_re_added_each_run(self):
        """非 active 但 isLatest 的条目在两次连续 run 中只能 added 一次。

        覆盖 Finding D：之前 prev 是 active-only 的 OUTPUT_PATH，所以
        diff_entries 里的非 active 条目永远不在 prev 中，每次 run 都会被
        识别为 added。修复后改为持久化 diff_baseline.json（含所有 isLatest），
        第二次 run 它应当落入 stable，而非再次出现在 added。
        """
        with _CacheSandbox():
            page = {
                "servers": [
                    _raw_entry("io.github.foo/bar", status="active"),
                    _raw_entry("io.github.dep/old", status="deprecated"),
                ],
                "metadata": {"count": 2},
            }
            # 第一次 run：两条都 added（dep/old 是 deprecated 但 isLatest）
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                rc1 = smr.main()
            self.assertEqual(rc1, 0)
            with open(smr.DIFF_PATH, "r", encoding="utf-8") as f:
                diff1 = json.load(f)
            # 首次 run 视乎 baseline 是否存在；新仓库 baseline 不存在 → 回退到
            # OUTPUT_PATH（空），所以两条都视为 added
            self.assertEqual(len(diff1["added"]), 2)
            # baseline 文件应当被写出
            self.assertTrue(os.path.exists(smr.DIFF_BASELINE_PATH))

            # 第二次 run：相同输入。基线已包含 deprecated 条目，所以两条都应 stable
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                rc2 = smr.main()
            self.assertEqual(rc2, 0)
            with open(smr.DIFF_PATH, "r", encoding="utf-8") as f:
                diff2 = json.load(f)
            self.assertEqual(diff2["added"], [])
            self.assertEqual(diff2["removed"], [])
            self.assertEqual(diff2["status_changed"], [])
            self.assertEqual(diff2["version_bumped"], [])
            self.assertEqual(diff2["stable"], 2)
            # OUTPUT_PATH 仍只含 active 条目（行为不变）
            with open(smr.OUTPUT_PATH, "r", encoding="utf-8") as f:
                out = json.load(f)
            self.assertEqual(len(out), 1)
            self.assertTrue(any("foo-bar" in e["id"] for e in out))

    def test_main_writes_output_and_diff(self):
        page = {
            "servers": [
                _raw_entry("io.github.foo/bar", version="1.0.0"),
                _raw_entry("io.github.foo/bar", version="0.9.0",
                           is_latest=False),  # 旧版本应被过滤
            ],
            "metadata": {"count": 2},
        }
        with _CacheSandbox():
            with mock.patch.object(
                smr.urllib.request, "urlopen",
                return_value=_make_response(json.dumps(page).encode("utf-8")),
            ):
                rc = smr.main()
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(smr.OUTPUT_PATH))
            self.assertTrue(os.path.exists(smr.DIFF_PATH))
            with open(smr.OUTPUT_PATH, "r", encoding="utf-8") as f:
                out = json.load(f)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
