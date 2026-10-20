"""scripts/sync_mcp_registry.py stars 门槛单元测试。

覆盖：
- _github_repo 解析（monorepo 子目录 / .git 后缀 / 非 github / 非法字符）
- apply_stars_gate：低于门槛剔除、404 剔除、非 github 保留、stars 回写、门槛 0 关闭、
  stars 未知时只保留上次产物里已有的条目
- fetch_repo_stars：分批、NOT_FOUND → None、单仓错误（FORBIDDEN）→ 未知、
  不挂在仓库上的错误抛 RuntimeError
- _graphql：限流按 Retry-After 重试、普通 403 不重试
- resolve_repo_stars：缓存命中 / 新仓库 / 过期刷新上限 / 淘汰不在 registry 的仓库 /
  中途失败或超出时间预算时保留已查到的部分
- main：无 token 返回 1 且不写盘；查询失败返回 1 但按「未知只留旧条目」写盘并落缓存；
  预算为 0 时只用缓存；门槛生效后写盘为一行一条并落缓存；registry 拉取失败时仍对上次产物过滤写回
"""

import io
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


def _entry(source_url, id_=None):
    return {"id": id_ or source_url.rsplit("/", 1)[-1], "source_url": source_url, "stars": None}


class TestGithubRepo(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(smr._github_repo("https://github.com/Owner/Repo"), ("owner", "repo"))

    def test_git_suffix(self):
        self.assertEqual(smr._github_repo("https://github.com/o/r.git"), ("o", "r"))

    def test_monorepo_subfolder(self):
        self.assertEqual(
            smr._github_repo("https://github.com/o/mono/tree/HEAD/servers/x"), ("o", "mono")
        )

    def test_dotted_repo_name(self):
        self.assertEqual(smr._github_repo("https://github.com/o/a.b-c_d"), ("o", "a.b-c_d"))

    def test_non_github_is_none(self):
        self.assertIsNone(
            smr._github_repo("https://registry.modelcontextprotocol.io/v0/servers/x")
        )

    def test_invalid_github_url(self):
        self.assertEqual(smr._github_repo('https://github.com/o/r"x'), ("", ""))
        self.assertEqual(smr._github_repo("https://github.com/only-owner"), ("", ""))


class TestApplyStarsGate(unittest.TestCase):
    def test_filters_by_threshold_and_writes_stars(self):
        entries = [
            _entry("https://github.com/o/zero"),
            _entry("https://github.com/o/five"),
            _entry("https://github.com/o/six"),
            _entry("https://github.com/o/many/tree/HEAD/sub"),
        ]
        stars = {("o", "zero"): 0, ("o", "five"): 5, ("o", "six"): 6, ("o", "many"): 900}
        kept, stats = smr.apply_stars_gate(entries, 6, lambda repos: stars)
        self.assertEqual([e["id"] for e in kept], ["six", "sub"])
        self.assertEqual([e["stars"] for e in kept], [6, 900])
        self.assertEqual(stats["below_min"], 2)
        self.assertEqual(stats["kept"], 2)

    def test_not_found_dropped_and_non_github_kept(self):
        entries = [
            _entry("https://github.com/o/gone"),
            _entry("https://registry.modelcontextprotocol.io/v0/servers/remote-only", "remote"),
            _entry('https://github.com/o/bad"name', "bad"),
        ]
        kept, stats = smr.apply_stars_gate(entries, 6, lambda repos: {("o", "gone"): None})
        self.assertEqual([e["id"] for e in kept], ["remote"])
        self.assertIsNone(kept[0]["stars"])
        self.assertEqual(stats["not_found"], 2)
        self.assertEqual(stats["no_repo"], 1)

    def test_invalid_url_not_queried(self):
        seen = []
        smr.apply_stars_gate(
            [_entry('https://github.com/o/bad"name'), _entry("https://github.com/o/ok")],
            6,
            lambda repos: seen.extend(repos) or {},
        )
        self.assertEqual(seen, [("o", "ok")])

    def test_repos_deduplicated_case_insensitive(self):
        seen = []

        def fetch(repos):
            seen.extend(repos)
            return {("o", "r"): 10}

        kept, _ = smr.apply_stars_gate(
            [_entry("https://github.com/O/R", "a"), _entry("https://github.com/o/r/tree/HEAD/x", "b")],
            6,
            fetch,
        )
        self.assertEqual(seen, [("o", "r")])
        self.assertEqual(len(kept), 2)

    def test_unknown_stars_kept_only_if_previously_listed(self):
        entries = [
            _entry("https://github.com/o/old", "old"),
            _entry("https://github.com/o/new", "new"),
            _entry("https://github.com/o/known", "known"),
        ]
        kept, stats = smr.apply_stars_gate(
            entries, 6, lambda repos: {("o", "known"): 30}, prev_ids={"old", "gone"}
        )
        self.assertEqual([e["id"] for e in kept], ["old", "known"])
        self.assertIsNone(kept[0]["stars"])
        self.assertEqual(stats["unknown_kept"], 1)
        self.assertEqual(stats["unknown_dropped"], 1)

    def test_zero_threshold_disables_gate(self):
        def fetch(repos):
            raise AssertionError("must not query when gate is off")

        entries = [_entry("https://github.com/o/zero")]
        kept, stats = smr.apply_stars_gate(entries, 0, fetch)
        self.assertEqual(kept, entries)
        self.assertEqual(stats["kept"], 1)


class TestFetchRepoStars(unittest.TestCase):
    def test_batches_and_not_found(self):
        repos = [("o", f"r{i}") for i in range(150)]
        calls = []

        def fake_graphql(query, token, timeout=30):
            calls.append(query)
            n = query.count("repository(")
            data = {f"r{j}": {"stargazerCount": j} for j in range(n)}
            data["r0"] = None
            return {"data": data, "errors": [{"type": "NOT_FOUND", "path": ["r0"]}]}

        with mock.patch.object(smr, "_graphql", side_effect=fake_graphql):
            got = smr.fetch_repo_stars(repos, "tok")
        self.assertEqual(len(calls), 2)  # 100 + 50
        self.assertIsNone(got[("o", "r0")])
        self.assertIsNone(got[("o", "r100")])  # r0 of the second batch
        self.assertEqual(got[("o", "r1")], 1)
        self.assertEqual(got[("o", "r149")], 49)

    def test_other_errors_raise(self):
        payload = {"data": None, "errors": [{"type": "RATE_LIMITED", "message": "slow down"}]}
        with mock.patch.object(smr, "_graphql", return_value=payload):
            with self.assertRaises(RuntimeError):
                smr.fetch_repo_stars([("o", "r")], "tok")

    def test_per_repo_error_left_unknown(self):
        # 2026-10-19 实测：debridge-finance org 开了 IP 白名单，单仓 FORBIDDEN，同批其它仓库正常返回
        payload = {
            "data": {"r0": {"stargazerCount": 8}, "r1": None, "r2": None},
            "errors": [
                {"type": "FORBIDDEN", "path": ["r1"], "message": "IP allow list enabled"},
                {"type": "NOT_FOUND", "path": ["r2"]},
            ],
        }
        with mock.patch.object(smr, "_graphql", return_value=payload):
            got = smr.fetch_repo_stars([("o", "a"), ("debridge-finance", "b"), ("o", "c")], "tok")
        self.assertEqual(got, {("o", "a"): 8, ("o", "c"): None})

    def test_error_not_on_a_repo_raises(self):
        payload = {
            "data": {"r0": {"stargazerCount": 8}},
            "errors": [{"type": "FORBIDDEN", "path": ["rateLimit"], "message": "x"}],
        }
        with mock.patch.object(smr, "_graphql", return_value=payload):
            with self.assertRaises(RuntimeError):
                smr.fetch_repo_stars([("o", "a")], "tok")

    def test_null_data_raises(self):
        payload = {"data": None, "errors": [{"type": "FORBIDDEN", "path": ["r0"], "message": "x"}]}
        with mock.patch.object(smr, "_graphql", return_value=payload):
            with self.assertRaises(RuntimeError):
                smr.fetch_repo_stars([("o", "a")], "tok")

    def test_failure_in_any_batch_raises(self):
        repos = [("o", f"r{i}") for i in range(350)]

        def fake_graphql(query, token, timeout=30):
            if '"r200"' in query:
                raise RuntimeError("GitHub GraphQL failed after 3 attempts: 502")
            n = query.count("repository(")
            return {"data": {f"r{j}": {"stargazerCount": 1} for j in range(n)}}

        with mock.patch.object(smr, "_graphql", side_effect=fake_graphql):
            with self.assertRaises(RuntimeError):
                smr.fetch_repo_stars(repos, "tok")

    def test_query_escapes_names(self):
        captured = []

        def fake_graphql(query, token, timeout=30):
            captured.append(query)
            return {"data": {"r0": {"stargazerCount": 1}}}

        with mock.patch.object(smr, "_graphql", side_effect=fake_graphql):
            smr.fetch_repo_stars([("o", 'r"x')], "tok")
        self.assertIn('name: "r\\"x"', captured[0])


def _http_error(code, headers=None):
    return urllib.error.HTTPError(smr.GRAPHQL_URL, code, "err", headers or {}, io.BytesIO(b""))


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestGraphqlRetry(unittest.TestCase):
    def test_rate_limited_retries_with_retry_after(self):
        responses = [_http_error(403, {"Retry-After": "7"}), _Resp({"data": {}})]
        with mock.patch.object(smr.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(smr.time, "sleep") as sleep:
            self.assertEqual(smr._graphql("query{}", "tok"), {"data": {}})
        sleep.assert_called_once_with(7)

    def test_plain_403_not_retried(self):
        with mock.patch.object(smr.urllib.request, "urlopen", side_effect=[_http_error(403)]) as u, \
                mock.patch.object(smr.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                smr._graphql("query{}", "tok")
        self.assertEqual(u.call_count, 1)
        sleep.assert_not_called()

    def test_5xx_ignores_ratelimit_reset_when_quota_left(self):
        far = str(int(smr.time.time()) + 3000)
        responses = [
            _http_error(502, {"X-RateLimit-Remaining": "4000", "X-RateLimit-Reset": far}),
            _Resp({"data": {}}),
        ]
        with mock.patch.object(smr.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(smr.time, "sleep") as sleep:
            smr._graphql("query{}", "tok")
        sleep.assert_called_once_with(30)

    def test_exhausted_quota_waits_for_reset_capped(self):
        far = str(int(smr.time.time()) + 3000)
        responses = [
            _http_error(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": far}),
            _Resp({"data": {}}),
        ]
        with mock.patch.object(smr.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(smr.time, "sleep") as sleep:
            smr._graphql("query{}", "tok")
        sleep.assert_called_once_with(300)

    def test_gives_up_after_four_attempts(self):
        errors = [_http_error(502)] * 4
        with mock.patch.object(smr.urllib.request, "urlopen", side_effect=errors) as u, \
                mock.patch.object(smr.time, "sleep"):
            with self.assertRaises(RuntimeError):
                smr._graphql("query{}", "tok")
        self.assertEqual(u.call_count, 4)


class TestResolveRepoStars(unittest.TestCase):
    TODAY = "2026-10-19"

    def test_fresh_cache_hit_not_queried(self):
        cache = {"o/a": {"stars": 9, "checked": "2026-10-10"}}

        def fetch(repos):
            raise AssertionError("fresh cache must not be queried")

        stars, new_cache, stats = smr.resolve_repo_stars([("o", "a")], cache, fetch, self.TODAY)
        self.assertEqual(stars, {("o", "a"): 9})
        self.assertEqual(new_cache, cache)
        self.assertEqual(stats["queried"], 0)

    def test_new_and_stale_queried_oldest_first_with_limit(self):
        cache = {
            "o/old": {"stars": 1, "checked": "2026-08-01"},
            "o/older": {"stars": 2, "checked": "2026-07-01"},
            "o/fresh": {"stars": 3, "checked": "2026-10-18"},
            "o/gone-from-registry": {"stars": 4, "checked": "2026-10-18"},
        }
        asked = []

        def fetch(repos):
            asked.extend(repos)
            return {k: 100 for k in repos}

        repos = [("o", "new"), ("o", "old"), ("o", "older"), ("o", "fresh")]
        stars, new_cache, stats = smr.resolve_repo_stars(
            repos, cache, fetch, self.TODAY, ttl_days=28, refresh_limit=1
        )
        self.assertEqual(asked, [("o", "new"), ("o", "older")])
        self.assertEqual(stars[("o", "old")], 1)  # stale but over the refresh limit
        self.assertEqual(stars[("o", "older")], 100)
        self.assertEqual(new_cache["o/new"], {"stars": 100, "checked": self.TODAY})
        self.assertNotIn("o/gone-from-registry", new_cache)
        self.assertEqual(stats, {
            "repos": 4, "queried": 2, "new": 1, "refreshed": 1, "stale_left": 1, "unknown": 0, "error": "",
        })

    def test_not_found_cached_as_none(self):
        stars, new_cache, _ = smr.resolve_repo_stars(
            [("o", "x")], {}, lambda repos: {("o", "x"): None}, self.TODAY
        )
        self.assertIsNone(stars[("o", "x")])
        self.assertEqual(new_cache["o/x"], {"stars": None, "checked": self.TODAY})

    def test_malformed_cache_entry_requeried(self):
        stars, _, stats = smr.resolve_repo_stars(
            [("o", "x")], {"o/x": 5}, lambda repos: {("o", "x"): 7}, self.TODAY
        )
        self.assertEqual(stars[("o", "x")], 7)
        self.assertEqual(stats["new"], 1)


    def test_batch_failure_keeps_earlier_batches(self):
        repos = [("o", f"r{i:03d}") for i in range(250)]
        cache = {"o/r249": {"stars": 3, "checked": "2026-01-01"}}  # stale, refresh would come last

        def fetch(chunk):
            if chunk[0] == ("o", "r100"):
                raise RuntimeError("GitHub GraphQL failed: 502")
            return {k: 10 for k in chunk}

        stars, new_cache, stats = smr.resolve_repo_stars(repos, cache, fetch, self.TODAY)
        self.assertEqual(len(stars), 101)  # first batch + stale cache value
        self.assertEqual(stars[("o", "r249")], 3)
        self.assertNotIn(("o", "r100"), stars)
        self.assertEqual(new_cache["o/r000"], {"stars": 10, "checked": self.TODAY})
        self.assertNotIn("o/r100", new_cache)
        self.assertEqual(stats["unknown"], 149)
        self.assertIn("502", stats["error"])

    def test_deadline_stops_before_next_batch(self):
        repos = [("o", f"r{i:03d}") for i in range(250)]
        asked = []

        def fetch(chunk):
            asked.extend(chunk)
            return {k: 10 for k in chunk}

        with mock.patch.object(smr.time, "monotonic", side_effect=[0, 100]):
            stars, new_cache, stats = smr.resolve_repo_stars(
                repos, {}, fetch, self.TODAY, deadline=50
            )
        self.assertEqual(len(asked), 100)
        self.assertEqual(len(new_cache), 100)
        self.assertEqual(stats["unknown"], 150)
        self.assertEqual(stats["error"], "")

    def test_repo_missing_from_fetch_result_not_cached(self):
        stars, new_cache, stats = smr.resolve_repo_stars(
            [("o", "a"), ("o", "b")], {}, lambda repos: {("o", "a"): 7}, self.TODAY
        )
        self.assertEqual(stars, {("o", "a"): 7})
        self.assertNotIn("o/b", new_cache)
        self.assertEqual(stats["unknown"], 1)


class TestStarsCacheFile(unittest.TestCase):
    def test_roundtrip_one_repo_per_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mcp", "stars.json")
            cache = {"o/b": {"stars": None, "checked": "2026-10-19"}, "o/a": {"stars": 3, "checked": "2026-10-19"}}
            with mock.patch.object(smr, "STARS_CACHE_PATH", path):
                smr._save_stars_cache(cache)
                self.assertEqual(smr._load_stars_cache(), cache)
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[1], '"o/a":{"stars":3,"checked":"2026-10-19"},')
            self.assertEqual(len(lines), 4)

    def test_missing_or_corrupt_cache_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stars.json")
            with mock.patch.object(smr, "STARS_CACHE_PATH", path):
                self.assertEqual(smr._load_stars_cache(), {})
                with open(path, "w") as f:
                    f.write("{not json")
                self.assertEqual(smr._load_stars_cache(), {})


def _registry_raw(name, repo_url):
    return {
        "server": {
            "name": name,
            "description": "d",
            "version": "1.0.0",
            "repository": {"source": "github", "url": repo_url},
        },
        "_meta": {
            smr.META_KEY: {"status": "active", "isLatest": True, "publishedAt": "2026-10-01T00:00:00Z"}
        },
    }


class TestMainWithGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cache = os.path.join(self.tmp.name, "cache")
        os.makedirs(cache)
        self.out = os.path.join(self.tmp.name, "mcp_registry_index.json")
        self.stars_cache = os.path.join(self.tmp.name, "mcp_registry_stars.json")
        raws = [
            _registry_raw("io.github.o/popular", "https://github.com/o/popular"),
            _registry_raw("io.github.o/spam", "https://github.com/o/spam"),
        ]
        self.patches = [
            mock.patch.object(smr, "CACHE_DIR", cache),
            mock.patch.object(smr, "REGISTRY_CACHE_PATH", os.path.join(cache, "registry.json")),
            mock.patch.object(smr, "ETAG_PATH", os.path.join(cache, "etag.txt")),
            mock.patch.object(smr, "DIFF_PATH", os.path.join(cache, "diff.json")),
            mock.patch.object(smr, "DIFF_BASELINE_PATH", os.path.join(cache, "baseline.json")),
            mock.patch.object(smr, "OUTPUT_PATH", self.out),
            mock.patch.object(smr, "STARS_CACHE_PATH", self.stars_cache),
            mock.patch.object(smr, "fetch_registry", return_value=iter(raws)),
            mock.patch.object(smr, "load_plugin_sources"),
            mock.patch.object(smr, "is_plugin_source", return_value=False),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_no_token_returns_1_without_writing(self):
        with mock.patch.dict(os.environ, {"MCP_REGISTRY_MIN_STARS": "6"}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            self.assertEqual(smr.main(), 1)
        self.assertFalse(os.path.exists(self.out))

    def test_lookup_failure_returns_1_and_admits_only_previous_entries(self):
        with open(self.out, "w", encoding="utf-8") as f:
            json.dump([{"id": "io-github-o-popular-296a18e8", "source_url": "https://github.com/o/popular"}], f)
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_repo_stars", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(smr.main(), 1)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual([e["source_url"] for e in json.load(f)], ["https://github.com/o/popular"])
        self.assertTrue(os.path.exists(smr.DIFF_BASELINE_PATH))
        self.assertTrue(os.path.exists(self.stars_cache))

    def test_zero_budget_uses_cache_only(self):
        with open(self.stars_cache, "w", encoding="utf-8") as f:
            json.dump({"o/popular": {"stars": 50, "checked": "2026-01-01"}}, f)
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok", "MCP_REGISTRY_BUDGET_MINUTES": "0"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_repo_stars", side_effect=AssertionError("no budget, must not query")
        ):
            self.assertEqual(smr.main(), 0)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual([e["stars"] for e in json.load(f)], [50])
        with open(self.stars_cache, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"o/popular": {"stars": 50, "checked": "2026-01-01"}})

    def test_gate_filters_and_writes_one_entry_per_line(self):
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok"}
        stars = {("o", "popular"): 120, ("o", "spam"): 0}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_repo_stars", return_value=stars
        ):
            self.assertEqual(smr.main(), 0)
        with open(self.out, encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text)
        self.assertEqual([e["source_url"] for e in data], ["https://github.com/o/popular"])
        self.assertEqual(data[0]["stars"], 120)
        self.assertEqual(text.count("\n"), 3)  # "[", one entry, "]"
        # diff baseline keeps the full set so the gate doesn't cause added/removed churn
        with open(smr.DIFF_BASELINE_PATH, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 2)
        with open(self.stars_cache, encoding="utf-8") as f:
            cache = json.load(f)
        self.assertEqual(cache["o/popular"]["stars"], 120)
        self.assertEqual(cache["o/spam"]["stars"], 0)

    def test_fetch_failure_still_gates_previous_output(self):
        prev = [
            {"id": "popular", "source_url": "https://github.com/o/popular", "stars": None},
            {"id": "spam", "source_url": "https://github.com/o/spam", "stars": None},
        ]
        with open(self.out, "w", encoding="utf-8") as f:
            json.dump(prev, f)
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_registry", side_effect=RuntimeError("registry 5xx 500")
        ), mock.patch.object(
            smr, "fetch_repo_stars", return_value={("o", "popular"): 40, ("o", "spam"): 0}
        ):
            self.assertEqual(smr.main(), 1)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual([e["id"] for e in json.load(f)], ["popular"])
        with open(self.stars_cache, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["o/spam"]["stars"], 0)
        self.assertFalse(os.path.exists(smr.DIFF_BASELINE_PATH))

    def test_fetch_failure_and_lookup_failure_keep_previous_entries(self):
        prev = [{"id": "x", "source_url": "https://github.com/o/x", "stars": None}]
        with open(self.out, "w", encoding="utf-8") as f:
            json.dump(prev, f)
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_registry", side_effect=RuntimeError("timeout")
        ), mock.patch.object(smr, "fetch_repo_stars", side_effect=RuntimeError("graphql down")):
            self.assertEqual(smr.main(), 1)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(json.load(f), prev)

    def test_second_run_uses_cache(self):
        env = {"MCP_REGISTRY_MIN_STARS": "6", "GITHUB_TOKEN": "tok"}
        with open(self.stars_cache, "w", encoding="utf-8") as f:
            json.dump({
                "o/popular": {"stars": 50, "checked": smr.TODAY},
                "o/spam": {"stars": 1, "checked": smr.TODAY},
            }, f)
        with mock.patch.dict(os.environ, env), mock.patch.object(
            smr, "fetch_repo_stars", side_effect=AssertionError("cache should be used")
        ):
            self.assertEqual(smr.main(), 0)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual([e["stars"] for e in json.load(f)], [50])


if __name__ == "__main__":
    unittest.main()
