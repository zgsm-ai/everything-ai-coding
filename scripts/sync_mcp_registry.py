#!/usr/bin/env python3
"""registry.modelcontextprotocol.io 数据源接入脚本。

用途：
- 主路径：分页拉取 /v0/servers，处理 cursor 翻页与 ETag 缓存
- 过滤：仅保留 _meta.io.modelcontextprotocol.registry/official.status == "active"
  且 isLatest == true 的条目
- 输出：catalog/mcp/mcp_registry_index.json（中间索引），不做与其他源去重
- stars 门槛：registry 没有任何人工筛选，大量 0 star 刷量条目（2026-10 抽样 75% ≤5 star），
  按 GitHub stars 过滤，门槛由 MCP_REGISTRY_MIN_STARS 控制（默认 6，0 = 关闭）
- 增量 diff：与上次输出对比，记录 added / status_changed / version_bumped / removed
  四类，stable 集合不写入文件但日志输出统计数

注意：
- 仅用 Python 标准库
- 错误兜底：网络失败 / 5xx / 缓存损坏 → ERROR 日志 + sys.exit(1)
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import dumps_index, is_plugin_source, load_plugin_sources, logger  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CACHE_DIR = os.path.join(REPO_ROOT, ".mcp_registry_cache")
REGISTRY_CACHE_PATH = os.path.join(CACHE_DIR, "registry.json")
ETAG_PATH = os.path.join(CACHE_DIR, "etag.txt")
DIFF_PATH = os.path.join(CACHE_DIR, "diff.json")
# 持久化 diff 视角的基线（所有 isLatest，含非 active）。compute_diff 在下一次运行时
# 以此为 prev，确保非 active 但 isLatest 的条目不会被反复识别为 added。
DIFF_BASELINE_PATH = os.path.join(CACHE_DIR, "diff_baseline.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "catalog", "mcp", "mcp_registry_index.json")
# stars 查询结果缓存。随 catalog/ 提交，跨周保留（.mcp_registry_cache 只在同一周内有效）
STARS_CACHE_PATH = os.path.join(REPO_ROOT, "catalog", "mcp", "mcp_registry_stars.json")

REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0/servers"
SOURCE_NAME = "registry.modelcontextprotocol.io"
META_KEY = "io.modelcontextprotocol.registry/official"

DEFAULT_LIMIT = 100
# 防死循环上限。不带 version=latest 时（2026-10）已超过 1000 页，带上后约一半
MAX_PAGES = 3000
PAGE_ATTEMPTS = 3  # 单页超时 / 5xx / 网络错误的尝试次数
PAGE_RETRY_BACKOFF = 5  # 秒，第 n 次重试前等 n * BACKOFF

GRAPHQL_URL = "https://api.github.com/graphql"
STARS_BATCH = 100  # 每次 GraphQL 查询的仓库数，实测约 3-4 秒一批
STARS_TTL_DAYS = 28  # 缓存过期天数
STARS_REFRESH_LIMIT = 5000  # 每轮最多刷新的过期仓库数（新仓库不受限），约 3 分钟
DEFAULT_MIN_STARS = 6  # stars <= 5 剔除
# 整个脚本（registry 拉取 + stars 查询）的时间预算，超出后没查的仓库留到下一轮。
# 实测拉取约 21 分钟，stars 查询约 1100 仓库/分钟（含二级限流等待）
DEFAULT_BUDGET_MINUTES = 40
# GitHub owner / repo 合法字符；不匹配的 github.com URL 视为无效仓库
_GITHUB_REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?:/.*)?$")

TODAY = date.today().isoformat()


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[sync_mcp_registry] {msg}", file=sys.stderr)


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _read_etag() -> str:
    if not os.path.exists(ETAG_PATH):
        return ""
    try:
        with open(ETAG_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _write_etag(etag: str) -> None:
    if not etag:
        return
    with open(ETAG_PATH, "w", encoding="utf-8") as f:
        f.write(etag)


def _load_local_registry_cache() -> list:
    """从本地缓存读 servers 列表；不存在或损坏返回空列表。"""
    if not os.path.exists(REGISTRY_CACHE_PATH):
        return []
    try:
        with open(REGISTRY_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError) as e:
        _log(f"ERROR: local registry cache corrupted: {e}")
        return []


def _save_local_registry_cache(servers: list) -> None:
    _ensure_cache_dir()
    with open(REGISTRY_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(servers, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# fetch_registry: 分页拉取（generator 风格但内部聚合返回 list）
# ---------------------------------------------------------------------------

def fetch_registry(limit: int = DEFAULT_LIMIT, timeout: int = 30):
    """分页拉取 v0/servers，yield 每条 raw server entry。

    - 首页带 If-None-Match（用上次 ETag）；304 时 yield 本地缓存条目
    - 200 时聚合所有页 + 落盘 + 保存新 ETag
    - 5xx / 网络失败 / 解析失败 → 抛 RuntimeError
    """
    _ensure_cache_dir()
    last_etag = _read_etag()

    cursor = ""
    page_idx = 0
    aggregated: list = []
    new_etag = ""
    used_cache = False

    while True:
        page_idx += 1
        if page_idx > MAX_PAGES:
            _log(f"ERROR: exceeded MAX_PAGES={MAX_PAGES}, abort")
            raise RuntimeError("registry pagination exceeded MAX_PAGES")

        # version=latest：服务端只返回每个 server 的最新版本（含非 active），
        # 与下面 is_latest 的客户端过滤一致，页数减半
        params = {"limit": str(limit), "version": "latest"}
        if cursor:
            params["cursor"] = cursor
        url = f"{REGISTRY_BASE}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, method="GET")
        # 仅首页带 If-None-Match（cursor 翻页是有状态序列，304 仅对全量集合有意义）
        if page_idx == 1 and last_etag:
            req.add_header("If-None-Match", last_etag)
        req.add_header("User-Agent", "everything-ai-coding-mcp-registry-sync")

        # 单页重试：2026-10 连续几周分别死在第 46 页超时、第 109 页 500，整轮放弃
        for attempt in range(1, PAGE_ATTEMPTS + 1):
            retry_reason = ""
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    etag = ""
                    try:
                        etag = resp.headers.get("ETag", "") or ""
                    except AttributeError:
                        etag = ""
                    body = resp.read()
                    try:
                        data = json.loads(body.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        _log(f"ERROR: page={page_idx} JSON parse error: {e}")
                        raise RuntimeError("registry JSON parse error") from e
            except urllib.error.HTTPError as e:
                if e.code == 304 and page_idx == 1:
                    _log("INFO: registry 304 Not Modified, using local cache")
                    cached = _load_local_registry_cache()
                    if not cached:
                        _log("ERROR: 304 received but local cache missing/corrupted")
                        raise RuntimeError("304 with no local cache")
                    used_cache = True
                    for item in cached:
                        yield item
                    return
                if not 500 <= e.code < 600:
                    _log(f"ERROR: page={page_idx} HTTP {e.code} {e.reason}")
                    raise RuntimeError(f"registry HTTP {e.code}") from e
                if attempt == PAGE_ATTEMPTS:
                    _log(f"ERROR: page={page_idx} HTTP 5xx: {e.code} {e.reason}")
                    raise RuntimeError(f"registry 5xx {e.code}") from e
                retry_reason = f"HTTP {e.code}"
            except urllib.error.URLError as e:
                if attempt == PAGE_ATTEMPTS:
                    _log(f"ERROR: page={page_idx} URL error: {e.reason}")
                    raise RuntimeError(f"registry URL error: {e.reason}") from e
                retry_reason = f"URL error: {e.reason}"
            except TimeoutError as e:
                # urllib.request.urlopen(timeout=N) 触发的 socket.timeout 在新 Python 里
                # 是 TimeoutError 的别名，不是 URLError 子类，必须单独捕获否则会逃逸出
                # main()，产生不友好的 traceback 与错误退出码。
                if attempt == PAGE_ATTEMPTS:
                    _log(f"ERROR: page={page_idx} timeout after {timeout}s: {e}")
                    raise RuntimeError(f"registry timeout after {timeout}s") from e
                retry_reason = f"timeout after {timeout}s"
            if not retry_reason:
                break
            _log(f"WARNING: page={page_idx} {retry_reason}, retry {attempt}/{PAGE_ATTEMPTS - 1}")
            time.sleep(PAGE_RETRY_BACKOFF * attempt)

        if page_idx == 1 and etag:
            new_etag = etag

        if not isinstance(data, dict) or "servers" not in data:
            _log(f"ERROR: page={page_idx} unexpected schema: missing 'servers' key")
            raise RuntimeError("registry response missing 'servers' key")
        servers = data.get("servers") or []
        if not isinstance(servers, list):
            _log(f"ERROR: page={page_idx} 'servers' is not a list")
            raise RuntimeError("registry 'servers' is not a list")
        aggregated.extend(servers)
        for item in servers:
            yield item

        metadata = data.get("metadata") or {}
        next_cursor = metadata.get("nextCursor") or ""
        _log(
            f"INFO: page={page_idx} fetched {len(servers)} entries "
            f"(total={len(aggregated)}, nextCursor={next_cursor[:32] + '...' if next_cursor else 'None'})"
        )
        if not next_cursor:
            break
        cursor = next_cursor

    # 落盘整页缓存 + 新 ETag
    if not used_cache:
        _save_local_registry_cache(aggregated)
        if new_etag:
            _write_etag(new_etag)
        _log(f"INFO: cached {len(aggregated)} entries, etag={new_etag[:16]}...")


# ---------------------------------------------------------------------------
# 过滤
# ---------------------------------------------------------------------------

def _get_official_meta(raw: dict) -> dict:
    meta = (raw or {}).get("_meta") or {}
    return meta.get(META_KEY) or {}


def is_active_and_latest(raw: dict) -> bool:
    """检查 status==active 且 isLatest==true。"""
    official = _get_official_meta(raw)
    if not official:
        return False
    return official.get("status") == "active" and official.get("isLatest") is True


def is_latest(raw: dict) -> bool:
    """检查 isLatest==true（不限制 status）。

    diff 计算需要更广的视角（包含 deprecated 等非 active 但 isLatest 的条目），
    才能正确捕获 active→deprecated 的 status_changed 转移；否则这类 entry 会被
    过滤后误判为 removed。
    """
    official = _get_official_meta(raw)
    if not official:
        return False
    return official.get("isLatest") is True


# ---------------------------------------------------------------------------
# 转换
# ---------------------------------------------------------------------------

_ID_INVALID_RE = re.compile(r"[^a-z0-9-]+")


def _kebab(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[\s_./]+", "-", s)
    s = _ID_INVALID_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _make_id(server_name: str) -> str:
    """基于 server.name 生成稳定 kebab-case id。

    server.name 形如 io.github.<owner>/<repo> 或 com.example/product。
    同一 name 多次 sync 必须产出同一 id。

    为避免 kebab 化后冲突（例如 io.github.foo/bar-baz 与 io.github.foo-bar/baz
    都会 kebab 成 io-github-foo-bar-baz），始终追加 8 位 SHA-1 短哈希后缀。
    哈希基于原始 server_name，保证：
    - 同一 server_name 永远得到同一 id（稳定）
    - 不同 server_name 即使 kebab 一致也不会碰撞
    """
    sk = _kebab(server_name)
    if not sk:
        sk = "mcp-server"
    h = hashlib.sha1((server_name or "").encode("utf-8")).hexdigest()[:8]
    return f"{sk}-{h}"


def _registry_fallback_url(server_name: str) -> str:
    """无 GitHub repository 时的 fallback：registry URL + URL-encoded name。"""
    encoded = urllib.parse.quote(server_name or "", safe="")
    return f"{REGISTRY_BASE}/{encoded}"


def _build_source_url(server: dict, registry_name: str) -> str:
    """优先使用 server.repository.url（GitHub 真实仓库），fallback 到 registry URL。

    规则（§14 修复 A）：
    - server.repository.source == "github" 且 url 非空 → 用 repo URL
    - 含 subfolder（monorepo）→ 拼接 ``/tree/HEAD/<subfolder>``
    - 否则（SaaS / 商业 server 无 GitHub repo）→ registry URL fallback

    这样去重 / health 信号 / LLM 评估都能拿到真实 GitHub 链接，避免所有 entry
    的 source_url 都落在 registry.modelcontextprotocol.io 上。
    """
    repo = (server or {}).get("repository") or {}
    if isinstance(repo, dict) and (repo.get("source") or "").lower() == "github":
        url = (repo.get("url") or "").rstrip("/")
        if url:
            subfolder = (repo.get("subfolder") or "").strip("/")
            if subfolder:
                return f"{url}/tree/HEAD/{subfolder}"
            return url
    return _registry_fallback_url(registry_name)


def _build_install(server: dict) -> dict:
    """根据 server.packages[] 构建 install 字典；无 packages 时退化为 manual。

    §14 修复 B：把 npm/pypi/cargo/oci 等真实安装信息塞入 install.config，
    供消费者 / LLM 看到具体命令而非空 manual。catalog schema 仍要求
    install.method ∈ {mcp_config|mcp_config_template|manual|git_clone|download_file}，
    所以保持 "manual" 不变；config 是任意 object，安全嵌入扩展字段。
    """
    packages = server.get("packages") or []
    remotes_raw = server.get("remotes") or []

    # mcp_remotes 字段：array of {type, url}
    mcp_remotes: list = []
    for r in remotes_raw:
        if not isinstance(r, dict):
            continue
        rtype = r.get("type") or ""
        rurl = r.get("url") or ""
        if not rtype and not rurl:
            continue
        mcp_remotes.append({"type": rtype, "url": rurl})

    if isinstance(packages, list) and packages:
        pkg = packages[0] if isinstance(packages[0], dict) else {}
        registry_type = (pkg.get("registryType") or "").lower()
        ident = pkg.get("identifier") or ""
        ver = pkg.get("version") or ""

        if registry_type == "npm":
            cmd = f"npx -y {ident}@{ver}" if ver else f"npx -y {ident}"
        elif registry_type == "pypi":
            cmd = f"pipx run {ident}=={ver}" if ver else f"pipx run {ident}"
        elif registry_type == "cargo":
            cmd = f"cargo install {ident}@{ver}" if ver else f"cargo install {ident}"
        elif registry_type == "oci":
            cmd = f"docker run {ident}:{ver}" if ver else f"docker run {ident}"
        elif registry_type and ident:
            cmd = f"{registry_type}: {ident}@{ver}" if ver else f"{registry_type}: {ident}"
        else:
            cmd = ""

        config: dict = {
            "registry_type": registry_type,
            "identifier": ident,
            "version": ver,
        }
        if cmd:
            config["command"] = cmd

        return {
            "method": "manual",
            "config": config,
            "remotes": mcp_remotes,
        }

    return {"method": "manual", "remotes": mcp_remotes}


def normalize_entry(raw: dict) -> dict:
    """将 registry server entry 转换为 catalog mcp schema。"""
    server = (raw or {}).get("server") or {}
    official = _get_official_meta(raw)

    server_name = server.get("name") or ""
    title = server.get("title") or server_name
    description = server.get("description") or ""
    version = server.get("version") or ""
    website_url = server.get("websiteUrl") or ""

    install = _build_install(server)
    mcp_remotes = install.get("remotes") or []

    entry: dict = {
        "id": _make_id(server_name),
        "name": title,
        "type": "mcp",
        "description": description,
        "source_url": _build_source_url(server, server_name),
        "stars": None,
        "category": "tooling",
        "tags": [],
        "tech_stack": [],
        "install": install,
        "source": SOURCE_NAME,
        "last_synced": TODAY,
        # 三个新字段
        "version": version,
        "mcp_registry_status": official.get("status") or "",
        "mcp_registry_published_at": official.get("publishedAt") or "",
        "mcp_remotes": mcp_remotes,
    }
    if website_url:
        entry["website_url"] = website_url
    return entry


# ---------------------------------------------------------------------------
# stars 门槛
# ---------------------------------------------------------------------------

def _min_stars() -> int:
    raw = os.environ.get("MCP_REGISTRY_MIN_STARS", str(DEFAULT_MIN_STARS))
    try:
        return max(0, int(raw))
    except ValueError:
        _log(f"WARNING: invalid MCP_REGISTRY_MIN_STARS={raw!r}, using {DEFAULT_MIN_STARS}")
        return DEFAULT_MIN_STARS


def _budget_seconds() -> float:
    raw = os.environ.get("MCP_REGISTRY_BUDGET_MINUTES", str(DEFAULT_BUDGET_MINUTES))
    try:
        return max(0.0, float(raw)) * 60
    except ValueError:
        _log(f"WARNING: invalid MCP_REGISTRY_BUDGET_MINUTES={raw!r}, using {DEFAULT_BUDGET_MINUTES}")
        return DEFAULT_BUDGET_MINUTES * 60


def _github_repo(source_url: str):
    """github.com URL → (owner, repo) 小写；非 github.com → None；github.com 但不合法 → ("", "")。"""
    url = (source_url or "").strip()
    if not url.lower().startswith("https://github.com/"):
        return None
    m = _GITHUB_REPO_RE.match(url)
    if not m:
        return ("", "")
    return (m.group(1).lower(), m.group(2).lower())


def _retry_after_seconds(headers, default: int) -> int:
    try:
        return min(300, max(1, int(headers.get("Retry-After") or "")))
    except (TypeError, ValueError):
        pass
    # X-RateLimit-Reset 每个响应都带，只有额度真用完时才按它等，否则普通 5xx 会白等几分钟
    if headers.get("X-RateLimit-Remaining") == "0":
        try:
            reset = int(headers.get("X-RateLimit-Reset") or "")
            return min(300, max(1, reset - int(time.time())))
        except (TypeError, ValueError):
            pass
    return default


def _graphql(query: str, token: str, timeout: int = 60) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "everything-ai-coding-sync",
        },
    )
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            # 403 只有带限流头时才重试；token 无效之类的 403 重试没有意义
            limited = e.code == 429 or (
                e.code == 403
                and (e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Remaining") == "0")
            )
            if attempt < 3 and (limited or e.code >= 500):
                wait = _retry_after_seconds(e.headers, 30 * (attempt + 1))
                _log(f"WARNING: GitHub GraphQL HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GitHub GraphQL failed: {last_err}")


def fetch_repo_stars(repos: list, token: str) -> dict:
    """批量查 stargazerCount。返回 {(owner, repo): stars}，仓库不存在为 None。

    挂在单个仓库上的其它错误（如所属 org 开了 IP 白名单 → FORBIDDEN）只让该仓库不出现在
    结果里，由调用方按「未知」处理；不挂在仓库上的错误（限流、语法、data 为空）抛 RuntimeError。
    串行请求：实测 4 路并发没有提速（GitHub 按 token 串行处理），还更容易撞二级限流。
    """
    result: dict = {}
    for i in range(0, len(repos), STARS_BATCH):
        chunk = repos[i:i + STARS_BATCH]
        fields = "\n".join(
            f"r{j}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{ stargazerCount }}"
            for j, (o, n) in enumerate(chunk)
        )
        payload = _graphql("query {\n" + fields + "\n}", token)
        aliases = {f"r{j}" for j in range(len(chunk))}
        unknown: dict = {}
        for err in payload.get("errors") or []:
            if err.get("type") == "NOT_FOUND":
                continue
            alias = (err.get("path") or [None])[0]
            if alias not in aliases:
                raise RuntimeError(f"GitHub GraphQL error: {err}")
            unknown[alias] = err
        data = payload.get("data")
        if data is None:
            raise RuntimeError(f"GitHub GraphQL returned no data: {payload.get('errors')}")
        for j, key in enumerate(chunk):
            if f"r{j}" in unknown:
                err = unknown[f"r{j}"]
                _log(f"WARNING: stars unknown for {key[0]}/{key[1]}: {err.get('type')} {err.get('message', '')[:120]}")
                continue
            node = data.get(f"r{j}")
            result[key] = node.get("stargazerCount") if node else None
    return result


def _load_stars_cache() -> dict:
    try:
        with open(STARS_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        _log(f"WARNING: stars cache unreadable, starting empty: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _save_stars_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(STARS_CACHE_PATH), exist_ok=True)
    lines = [
        f"{json.dumps(k)}:{json.dumps(v, separators=(',', ':'))}" for k, v in sorted(cache.items())
    ]
    with open(STARS_CACHE_PATH, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(lines) + "\n}\n" if lines else "{}\n")


def resolve_repo_stars(repos: list, cache: dict, fetch, today: str,
                       ttl_days: int = STARS_TTL_DAYS,
                       refresh_limit: int = STARS_REFRESH_LIMIT,
                       deadline: float = None) -> tuple:
    """用缓存 + 增量查询得到 repos 的 stars。

    缓存格式 {"owner/repo": {"stars": int | None, "checked": "YYYY-MM-DD"}}，None 表示仓库不存在。
    新仓库全部查询；过期（checked 早于 today - ttl_days）的按最旧优先刷新，每轮最多
    refresh_limit 个，其余沿用旧值。按 STARS_BATCH 分批查，到 deadline（time.monotonic()）
    或某批失败就停，已查到的照样进缓存，下一轮接着查。

    返回 (stars, new_cache, stats)。stars 里没有的 key = 未知（没来得及查 / 查询失败 / 单仓错误），
    由调用方决定去留。new_cache 只保留本轮 repos，不在 registry 里的仓库自然淘汰。
    """
    def valid(v):
        return isinstance(v, dict) and "stars" in v

    cutoff = (date.fromisoformat(today) - timedelta(days=ttl_days)).isoformat()
    missing, stale = [], []
    for k in repos:
        v = cache.get(f"{k[0]}/{k[1]}")
        if not valid(v):
            missing.append(k)
        elif (v.get("checked") or "") < cutoff:
            stale.append(k)
    stale.sort(key=lambda k: cache[f"{k[0]}/{k[1]}"].get("checked") or "")
    to_query = missing + stale[:refresh_limit]

    fetched: dict = {}
    error = ""
    for i in range(0, len(to_query), STARS_BATCH):
        if deadline is not None and time.monotonic() >= deadline:
            _log(f"WARNING: stars time budget used up at {i}/{len(to_query)}, rest left for next run")
            break
        try:
            fetched.update(fetch(to_query[i:i + STARS_BATCH]))
        except RuntimeError as e:
            error = str(e)
            _log(f"ERROR: stars lookup stopped at {i}/{len(to_query)}: {error}")
            break
        if (i // STARS_BATCH) % 20 == 19:
            _log(f"INFO: stars fetched {min(i + STARS_BATCH, len(to_query))}/{len(to_query)}")

    new_cache: dict = {}
    for k in repos:
        ks = f"{k[0]}/{k[1]}"
        if k in fetched:
            new_cache[ks] = {"stars": fetched[k], "checked": today}
        elif valid(cache.get(ks)):
            new_cache[ks] = cache[ks]
    stars = {k: new_cache[f"{k[0]}/{k[1]}"]["stars"] for k in repos if f"{k[0]}/{k[1]}" in new_cache}
    stats = {
        "repos": len(repos),
        "queried": len(to_query),
        "new": len(missing),
        "refreshed": len(to_query) - len(missing),
        "stale_left": max(0, len(stale) - refresh_limit),
        "unknown": len(repos) - len(stars),
        "error": error,
    }
    return stars, new_cache, stats


def apply_stars_gate(entries: list, min_stars: int, fetch_stars, prev_ids=frozenset()) -> tuple:
    """按 GitHub stars 过滤 registry 条目，返回 (kept, stats)。

    - 非 github.com source_url（纯 remote / SaaS）→ 保留，无法判断
    - github.com 但仓库不存在或 URL 不合法 → 剔除
    - stars < min_stars → 剔除；保留的条目写入 entry["stars"]
    - stars 未知（fetch_stars 结果里没有该仓库）→ id 在 prev_ids（上次产物）里的保留，
      新条目先不收录：没查完时放行新条目，index.json 会直接涨破 100 MB
    - min_stars <= 0 → 原样返回，不发请求
    """
    stats = {"no_repo": 0, "not_found": 0, "below_min": 0, "unknown_kept": 0, "unknown_dropped": 0, "kept": 0}
    if min_stars <= 0:
        stats["kept"] = len(entries)
        return list(entries), stats

    repos = sorted({k for k in (_github_repo(e.get("source_url")) for e in entries) if k and k[0]})
    stars = fetch_stars(repos) if repos else {}

    kept: list = []
    for e in entries:
        key = _github_repo(e.get("source_url"))
        if key is None:
            stats["no_repo"] += 1
            kept.append(e)
            continue
        if key[0] and key not in stars:
            if e.get("id") in prev_ids:
                stats["unknown_kept"] += 1
                kept.append(e)
            else:
                stats["unknown_dropped"] += 1
            continue
        n = stars.get(key)
        if n is None:
            stats["not_found"] += 1
            continue
        e["stars"] = n
        if n < min_stars:
            stats["below_min"] += 1
            continue
        kept.append(e)
    stats["kept"] = len(kept)
    return kept, stats


def _run_stars_gate(entries: list, min_stars: int, prev_ids, deadline: float) -> tuple:
    """对 entries 应用 stars 门槛，返回 (kept, new_stars_cache, error)。

    查询中途失败或超出 deadline 不抛异常：已查到的照常过滤，error 非空表示本轮有查询失败。
    没有 GITHUB_TOKEN 抛 RuntimeError。
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("stars gate needs GITHUB_TOKEN (set MCP_REGISTRY_MIN_STARS=0 to disable)")
    stars_cache = _load_stars_cache()
    resolved: dict = {}

    def lookup(repos):
        stars, resolved["cache"], resolved["stats"] = resolve_repo_stars(
            repos, stars_cache, lambda rs: fetch_repo_stars(rs, token), TODAY, deadline=deadline
        )
        return stars

    kept, stats = apply_stars_gate(entries, min_stars, lookup, prev_ids)
    cstats = resolved.get("stats") or {}
    _log(
        f"INFO: stars lookup: repos={cstats.get('repos', 0)} queried={cstats.get('queried', 0)} "
        f"(new={cstats.get('new', 0)} refreshed={cstats.get('refreshed', 0)}) "
        f"stale_left={cstats.get('stale_left', 0)} unknown={cstats.get('unknown', 0)}"
    )
    _log(
        f"INFO: stars gate (min={min_stars}): kept={stats['kept']} "
        f"below_min={stats['below_min']} not_found={stats['not_found']} "
        f"unknown_kept={stats['unknown_kept']} unknown_dropped={stats['unknown_dropped']} "
        f"no_github_repo={stats['no_repo']}"
    )
    return kept, resolved.get("cache", stars_cache), cstats.get("error", "")


def _gate_previous_output(deadline: float) -> None:
    """registry 拉取失败时，仍对上次产物应用 stars 门槛并写回。

    registry 2026-10 起几乎每周都拉取失败（超时 / 5xx / 页数上限），产物停在 08-31；
    门槛要是只挂在拉取成功之后，就一次都生效不了。上次产物的条目 stars 未知时一律保留。
    diff 基线不动，main 仍返回 1。
    """
    min_stars = _min_stars()
    if min_stars <= 0:
        return
    prev = _load_prev_output()
    if not prev:
        return
    try:
        kept, stars_cache, _ = _run_stars_gate(prev, min_stars, {e.get("id") for e in prev}, deadline)
    except RuntimeError as e:
        _log(f"ERROR: stars gate on previous output failed, left unchanged: {e}")
        return
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(dumps_index(kept))
    _save_stars_cache(stars_cache)
    _log(f"INFO: fetch failed; re-gated previous output {len(prev)} -> {len(kept)} entries")


# ---------------------------------------------------------------------------
# 增量 diff
# ---------------------------------------------------------------------------

def _diff_signature(entry: dict) -> tuple:
    """diff 比较签名：(version, mcp_registry_status, statusChangedAt 替代用 published_at)。

    R5 要求按 (server.version, _meta.statusChangedAt) 比较。statusChangedAt 不映射到
    catalog entry，因此 diff 直接消费 raw entry 的 _meta；当我们仅有 normalized
    entry 时（如本地上次输出），用 (version, status, published_at) 替代——published_at
    在 status 改变或 version 变更时也会刷新。
    """
    return (
        entry.get("version") or "",
        entry.get("mcp_registry_status") or "",
        entry.get("mcp_registry_published_at") or "",
    )


def compute_diff(prev_entries: list, new_entries: list) -> dict:
    """对比上次与本次输出。

    四类：added / status_changed / version_bumped / removed；stable 仅记数。
    """
    prev_map = {e.get("id"): e for e in prev_entries if e.get("id")}
    new_map = {e.get("id"): e for e in new_entries if e.get("id")}

    added = sorted(set(new_map) - set(prev_map))
    removed = sorted(set(prev_map) - set(new_map))
    common = set(prev_map) & set(new_map)

    status_changed: list = []
    version_bumped: list = []
    stable = 0
    for sid in common:
        old = prev_map[sid]
        new = new_map[sid]
        old_v = old.get("version") or ""
        new_v = new.get("version") or ""
        old_s = old.get("mcp_registry_status") or ""
        new_s = new.get("mcp_registry_status") or ""
        if old_s != new_s:
            status_changed.append({"id": sid, "old": old_s, "new": new_s})
        elif old_v != new_v:
            version_bumped.append({"id": sid, "old": old_v, "new": new_v})
        else:
            # 即使 published_at 变了，只要 version+status 一致仍视作 stable
            stable += 1

    return {
        "added": added,
        "status_changed": sorted(status_changed, key=lambda x: x["id"]),
        "version_bumped": sorted(version_bumped, key=lambda x: x["id"]),
        "removed": removed,
        "stable": stable,
    }


def _load_prev_output() -> list:
    if not os.path.exists(OUTPUT_PATH):
        return []
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError) as e:
        _log(f"WARNING: previous output corrupted: {e}")
        return []


def _load_diff_baseline() -> list:
    """加载上次的 diff 基线（所有 isLatest，含非 active）。

    与 OUTPUT_PATH（仅 active+isLatest）不同：diff 视角的基线在更广的集合上工作，
    保证非 active 但 isLatest 的条目不会在每次 run 都被报告为 added。
    文件不存在时回退到 OUTPUT_PATH（首次升级路径），保留原有行为。
    """
    if not os.path.exists(DIFF_BASELINE_PATH):
        # 首次启用基线：以现有 OUTPUT 作为兼容回退，避免一上来全部条目刷成 added
        return _load_prev_output()
    try:
        with open(DIFF_BASELINE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError) as e:
        _log(f"WARNING: diff baseline corrupted: {e}")
        return []


def _save_diff_baseline(entries: list) -> None:
    _ensure_cache_dir()
    with open(DIFF_BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    deadline = time.monotonic() + _budget_seconds()
    load_plugin_sources()  # warm cache; warns once if missing/unparseable
    _log(f"INFO: fetching {REGISTRY_BASE} (limit={DEFAULT_LIMIT})")

    try:
        raw_iter = fetch_registry(limit=DEFAULT_LIMIT)
        all_raw = list(raw_iter)
    except RuntimeError as e:
        _log(f"ERROR: fetch_registry failed: {e}")
        _gate_previous_output(deadline)
        return 1

    _log(f"INFO: total raw entries fetched: {len(all_raw)}")

    # 第一层：仅按 isLatest 过滤（保留所有 status，含 deprecated/inactive）
    # 这是 diff 的输入集，确保 active→deprecated 这类 status 转移不会被误判为 removed
    latest_raw = [r for r in all_raw if is_latest(r)]
    _log(
        f"INFO: filtered isLatest (any status): {len(latest_raw)} "
        f"(from {len(all_raw)})"
    )

    def _normalize_with_dedup(raw_list: list) -> list:
        out: list = []
        seen: set = set()
        for r in raw_list:
            entry = normalize_entry(r)
            # source_url 现在可能是 GitHub URL（修复 A 后），仅校验非空 + 有 id
            if not entry["id"] or not entry.get("source_url"):
                _log(f"WARNING: skipped invalid entry id={entry.get('id')}")
                continue
            if entry["id"] in seen:
                _log(
                    f"WARNING: duplicate id={entry['id']} (server.name={r.get('server', {}).get('name')}), skipping"
                )
                continue
            # plugin_sources.json skip — match either the (possibly GitHub)
            # source_url or the reverse-DNS server name `io.github.owner/repo`
            # (is_plugin_source rewrites the latter to canonical GitHub form).
            server_name = (r.get("server") or {}).get("name") or ""
            if (
                is_plugin_source(entry.get("source_url", ""))
                or is_plugin_source(server_name)
            ):
                logger.debug(
                    f"skipping {entry.get('id', '<unknown>')}: in plugin_sources.json"
                )
                continue
            seen.add(entry["id"])
            out.append(entry)
        out.sort(key=lambda e: e["id"])
        return out

    # diff 视角：所有 isLatest 条目（含 deprecated 等），用来正确识别 status_changed
    diff_entries = _normalize_with_dedup(latest_raw)

    # 输出视角：仅 active + isLatest（行为不变，写盘集合保持精简）
    active_raw = [r for r in latest_raw if is_active_and_latest(r)]
    entries = _normalize_with_dedup(active_raw)
    _log(
        f"INFO: filtered active+isLatest: {len(entries)} "
        f"(from {len(latest_raw)} isLatest)"
    )

    # stars 门槛只作用于输出视角；diff 视角保持全集，避免门槛造成 added/removed 抖动
    min_stars = _min_stars()
    stars_cache = None
    gate_error = ""
    if min_stars > 0:
        prev_ids = {e.get("id") for e in _load_prev_output()}
        try:
            entries, stars_cache, gate_error = _run_stars_gate(entries, min_stars, prev_ids, deadline)
        except RuntimeError as e:
            _log(f"ERROR: stars gate failed, previous output kept: {e}")
            return 1

    # diff: 上次「diff 基线」 vs 本次「diff 视角」全集
    # 基线持久化所有 isLatest 条目（含非 active），与 diff_entries 同集合范畴；
    # 否则非 active 条目会在 prev 中缺席、在 diff_entries 中常驻，被反复识别为
    # added。首次运行 baseline 文件不存在时回退到 OUTPUT_PATH 兼容旧仓库状态。
    prev = _load_diff_baseline()
    diff = compute_diff(prev, diff_entries)
    _log(
        f"INFO: diff vs previous: +{len(diff['added'])} added, "
        f"~status={len(diff['status_changed'])}, "
        f"~version={len(diff['version_bumped'])}, "
        f"-{len(diff['removed'])} removed, "
        f"={diff['stable']} stable"
    )

    # 写盘
    _ensure_cache_dir()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(dumps_index(entries))
    _log(f"INFO: wrote {len(entries)} entries to {OUTPUT_PATH}")

    if stars_cache is not None:
        _save_stars_cache(stars_cache)
        _log(f"INFO: wrote stars cache ({len(stars_cache)} repos) to {STARS_CACHE_PATH}")

    with open(DIFF_PATH, "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2, ensure_ascii=False)
    _log(f"INFO: wrote diff to {DIFF_PATH}")

    # 持久化本次「diff 视角」全集为下次 run 的基线
    _save_diff_baseline(diff_entries)
    _log(f"INFO: wrote diff baseline ({len(diff_entries)} entries) to {DIFF_BASELINE_PATH}")

    # 查询失败时产物已按「未知只留旧条目」写盘，非零退出只为在日志里标红
    return 1 if gate_error else 0


if __name__ == "__main__":
    sys.exit(main())
