# -*- coding: utf-8 -*-
"""活的源管理：内置源 + 健康度统计 + 自动降级 + GitHub 搜索补位 + 手动加源。

状态保存在用户目录的 sources.json，软件重启后依然记得每个源的成败历史。
"""

import json
import os
import time
import urllib.parse
import urllib.request

# ---- 内置源（匿名 raw，不需要登录 GitHub）------------------------------
# 格式: (名字, 链接, 类型) —— 类型决定怎么解析
BUILTIN = [
    # clash yaml（含 vmess/vless/trojan/ss/hysteria2，质量最高）
    ("anaer/Sub", "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml", "clash"),
    ("peasoft/NoMoreWalls", "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", "base64"),
    ("ermaozi/get_subscribe", "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt", "base64"),
    ("freefq/free", "https://raw.githubusercontent.com/freefq/free/master/v2", "base64"),
    ("Pawdroid/Free-servers", "https://raw.githubusercontent.com/Pawdroid/Free-servers/master/sub", "base64"),
    ("ripaojiedian/freenode", "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub", "base64"),
    ("mahdibland/Eternity", "https://raw.githubusercontent.com/mahdibland/Eternity/main/sub", "base64"),
    ("Barabama/FreeNodes", "https://raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/nodefree.txt", "base64"),
    # 纯 HTTP 代理（量大，国内可用率低，只取一点）
    ("TheSpeedX/http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "iplist"),
    ("monosans/http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "iplist"),
    ("proxifly/https", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/https/data.txt", "iplist_tls"),
    ("zloi-user/https", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt", "iplist_tls"),
]

KINDS = ("clash", "base64", "iplist", "iplist_tls")

# 降级阈值：连续失败这么多次就暂时停用
FAIL_STREAK = 3
# 降级后多久才给机会重试（秒），1 天
COOLDOWN = 86400
# 最多记多少条历史
MAX_HISTORY = 60

# GitHub 搜索补位用的关键词（按优先级）
SEARCH_KEYWORDS = [
    "clash free nodes",
    "free proxy clash yaml",
    "v2ray free nodes subscribe",
    "free node subscribe",
    "https proxy list",
]


def state_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FreeNodesPro", "sources.json")


def load_state():
    """读源状态文件。没有就返回空壳。"""
    empty = {"sources": [], "updated_at": 0}
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and isinstance(st.get("sources"), list):
            return st
    except Exception:
        pass
    return empty


def save_state(st):
    os.makedirs(os.path.dirname(state_path()), exist_ok=True)
    st["updated_at"] = int(time.time())
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_path())


def current_sources():
    """返回当前该用的源列表（合并内置 + 用户加的 + 状态）。

    第一次运行会把内置源播种进状态文件；之后内置源的更新会自动并入
    （按 url 匹配，用户对某个内置源的 启停/删除 会被保留）。
    被用户删除的源保留 removed 标记（墓碑），不会被重新播种。
    """
    st = load_state()
    by_url = {s["url"]: s for s in st["sources"]}
    changed = False

    # 内置源：状态里没有就补进去（保留用户对已有源的修改）
    for n, u, k in BUILTIN:
        s = by_url.get(u)
        if s is None:
            st["sources"].append({
                "name": n, "url": u, "kind": k, "builtin": True,
                "enabled": True, "streak": 0, "ok": 0, "fail": 0,
                "last_check": 0, "last_good": 0, "history": [],
            })
            changed = True
        elif not s.get("removed") and s.get("kind") != k:
            # 内置源的名字/类型以代码里的为准（方便我们更新链接）
            s["kind"] = k
            changed = True

    if changed:
        save_state(st)
    return st


def list_sources():
    """给 GUI 用的完整列表（按内置在前、名字排序）。已删除的不出现。"""
    st = current_sources()
    srcs = [s for s in st["sources"] if not s.get("removed")]
    srcs.sort(key=lambda s: (not s.get("builtin", False), s["name"]))
    return srcs


def _can_retry(s, now):
    """降级中的源是否到了重试时间。"""
    if s.get("enabled", True):
        return True
    return (now - s.get("last_check", 0)) > COOLDOWN


def active_sources():
    """本次实际去抓的源：启用的 + 降级到期的。降级到期会临时给一次机会。"""
    st = current_sources()
    now = int(time.time())
    out = []
    for s in st["sources"]:
        if s.get("removed"):
            continue
        if s.get("enabled", True) or _can_retry(s, now):
            out.append(s)
    return out


def record(name, url, ok, count, note=""):
    """记录一次抓取结果，更新健康度并决定是否降级。"""
    st = current_sources()
    s = next((x for x in st["sources"] if x["url"] == url), None)
    if not s:
        return
    now = int(time.time())
    s["last_check"] = now
    s["history"] = (s.get("history") or [])[-(MAX_HISTORY - 1):] + \
        [int(now) * 1000 + (1 if ok else 0)]
    if ok:
        s["ok"] = s.get("ok", 0) + 1
        s["streak"] = 0
        s["fail"] = 0
        s["last_good"] = now
        s["enabled"] = True
    else:
        s["fail"] = s.get("fail", 0) + 1
        s["streak"] = s.get("streak", 0) + 1
        if s["streak"] >= FAIL_STREAK:
            s["enabled"] = False  # 连续失败 → 降级
    save_state(st)


def add_source(name, url, kind):
    """GUI 手动加源。返回 (ok, 消息)。"""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False, "链接要以 http:// 或 https:// 开头"
    if kind not in KINDS:
        return False, f"类型必须是 {KINDS} 之一"
    st = current_sources()
    if any(s["url"] == url for s in st["sources"]):
        return False, "这个源已经存在了"
    st["sources"].append({
        "name": (name or url)[:60], "url": url, "kind": kind,
        "builtin": False, "enabled": True, "streak": 0, "ok": 0, "fail": 0,
        "last_check": 0, "last_good": 0, "history": [],
    })
    save_state(st)
    return True, "已添加"


def remove_source(url):
    """GUI 删除源：标记 removed，列表立即消失。
    不能真删——current_sources() 每次会把内置源重新播种回来，
    只有用 removed 标记才能让删掉的内置源不再出现。"""
    st = load_state()
    s = next((x for x in st["sources"] if x["url"] == url), None)
    if not s:
        return False, "没有这个源"
    s["removed"] = True
    s["enabled"] = False
    save_state(st)
    return True, "已删除"


def set_enabled(url, enabled):
    st = current_sources()
    s = next((x for x in st["sources"] if x["url"] == url), None)
    if not s:
        return False
    s["enabled"] = bool(enabled)
    if enabled:
        s["streak"] = 0
    save_state(st)
    return True


# ---- GitHub 搜索补位 ----------------------------------------------------
def search_github(keyword, limit=10, timeout=20):
    """匿名搜 GitHub 仓库（不需要登录，走 api.github.com）。"""
    api = "https://api.github.com/search/repositories?q=" + \
        urllib.parse.quote(keyword) + \
        f"&sort=updated&per_page={limit}"
    try:
        req = urllib.request.Request(api, headers={
            "User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except Exception as e:
        return [], f"搜索失败：{e}"
    out = []
    for it in d.get("items", [])[:limit]:
        out.append({
            "name": it["full_name"],
            "desc": (it.get("description") or "")[:120],
            "stars": it.get("stargazers_count", 0),
            "updated": (it.get("updated_at") or "")[:10],
            "url": it["html_url"],
        })
    return out, ""


def guess_raw_url(repo_full, branches=("main", "master")):
    """猜一个仓库最可能的订阅文件 raw 链接（按常见文件名试）。"""
    cand_files = ["clash.yaml", "subscribe/clash.yaml", "list.txt",
                  "v2ray.txt", "sub", "proxies.txt"]
    for br in branches:
        for fn in cand_files:
            yield f"https://raw.githubusercontent.com/{repo_full}/{br}/{fn}"


def find_new_sources(on_log=None, max_add=3):
    """源不够用时，去 GitHub 搜同类仓库补位。

    只在 活跃源少于阈值 或 最近一次抓到的节点太少 时调用。
    """
    st = current_sources()
    n_enabled = sum(1 for s in st["sources"] if s.get("enabled", True))
    if n_enabled >= 6:
        return []  # 源还够多，不折腾

    added = []
    for kw in SEARCH_KEYWORDS:
        if len(added) >= max_add:
            break
        repos, err = search_github(kw, limit=8)
        if err:
            on_log and on_log(f"  搜索「{kw}」失败：{err}")
            continue
        for rp in repos:
            if len(added) >= max_add:
                break
            # 跳过已经在列表里的
            if any(s["name"] == rp["name"] for s in st["sources"]):
                continue
            # 星太少的不靠谱
            if rp["stars"] < 20:
                continue
            ok, msg = add_source(rp["name"], rp["url"], "clash")
            if ok:
                added.append(rp)
                on_log and on_log(f"  ✓ 补位新源：{rp['name']}（{rp['stars']}★）")
    return added
