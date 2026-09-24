# -*- coding: utf-8 -*-
"""抓取 + 清洗 + 三级漏斗的主流程。可单独跑（CLI），也被 GUI 调用。"""

import datetime
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kernel as kernel_mod
import sources as sources_mod
from exporters import build_all
from parsers import (clean, dedupe, parse_base64_sub, parse_clash_yaml,
                     parse_iplist)
from tester import Mihomo, TLS_LIKELY_PORTS, udp_egress_ok

# ---- 预算上限（保证轻量、不打扰电脑）------------------------------------
MAX_CANDIDATES = 2000     # 总候选上限
HTTP_MAX = 400            # HTTP 代理上限（国内可用率极低，测多了浪费）
CONCURRENCY = 128         # 并发延迟测试线程（第一轮筛选要快）
SPEED_TOPN = 30           # 只有延迟最低的 N 个才进入真测速 + 解锁


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def expand_variants(proxies):
    """HTTP 代理有两种形态：明文 HTTP，或被 TLS 包起来的 HTTPS 代理。
    公开 ip:port 列表不会标，所以同一个 host:port 生成两个变体都真测一遍，
    按端口决定先试哪个（443/8443 优先 TLS）。其余协议原样保留。"""
    out = []
    n_http = 0
    for p in proxies:
        if p.get("type") != "http":
            out.append(p)
            continue
        n_http += 1
        base = {k: v for k, v in p.items()
                if k not in ("tls", "servername", "sni", "skip-cert-verify")}
        plain = dict(base, name=base["name"] + "|P")
        tls = dict(base, name=base["name"] + "|T", tls=True,
                   skip_cert_verify=True,
                   servername=str(p.get("servername") or p.get("sni") or p["server"]))
        if p.get("port") in TLS_LIKELY_PORTS:
            out += [tls, plain]
        else:
            out += [plain, tls]
    if n_http:
        log(f"HTTP 代理展开为明文/TLS 变体：{n_http} → {n_http * 2}")
    return out


def fetch_text(url, timeout=25):
    """raw.githubusercontent.com 在国内不稳，先走 jsdelivr 镜像再回源。

    jsdelivr 镜像把 /branch/ 换成 @branch：user/repo@branch/path。
    main / master / 其他分支名都要处理，否则 master 分支的源镜像拼成空串被跳过。
    """
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.*)", url)
    mirrors = []
    if m:
        repo, branch, rest = m.groups()
        for host in ("cdn.jsdelivr.net", "fastly.jsdelivr.net", "testingcf.jsdelivr.net"):
            mirrors.append(f"https://{host}/gh/{repo}@{branch}/{rest}")
    for u in mirrors + [url]:
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            continue
    return ""


def collect(on_log=log):
    """抓所有源 -> 清洗 -> 去重。源是活的：带健康度、自动降级、不够还会去 GitHub 补位。"""
    # 活跃源（启用的 + 降级到期的），不够 6 个就去 GitHub 搜同类仓库补位
    srcs = sources_mod.active_sources()
    if len([s for s in srcs if s.get("enabled")]) < 6:
        on_log("活跃源太少，去 GitHub 搜同类仓库补位…")
        sources_mod.find_new_sources(on_log)
        srcs = sources_mod.active_sources()
    on_log(f"共 {len(srcs)} 个源待抓")

    allp = []
    for s in srcs:
        name, url, kind = s["name"], s["url"], s["kind"]
        text = fetch_text(url)
        if not text:
            on_log(f"  ✗ {name} 抓取失败")
            sources_mod.record(name, url, ok=False, count=0, note="抓取失败")
            continue
        try:
            if kind == "clash":
                got = parse_clash_yaml(text)
            elif kind == "base64":
                got = [p for p in parse_base64_sub(text) if p]
            elif kind in ("iplist", "iplist_tls"):
                got = parse_iplist(text, tls_hint=kind == "iplist_tls")
            else:
                got = []
        except Exception as e:
            on_log(f"  ✗ {name} 解析失败：{e}")
            sources_mod.record(name, url, ok=False, count=0, note=f"解析失败: {e}")
            got = []
        got = [p for p in (clean(x) for x in got) if p]
        ok = len(got) > 0
        sources_mod.record(name, url, ok=ok, count=len(got))
        if not ok:
            on_log(f"  ✗ {name}：0 个有效节点")
            continue
        on_log(f"  ✓ {name}：{len(got)} 个有效节点")
        for p in got:
            p["_src"] = name
        allp.extend(got)

    allp = dedupe(allp)

    # HTTP 代理限量
    http = [p for p in allp if p.get("type") == "http"]
    other = [p for p in allp if p.get("type") != "http"]
    if len(http) > HTTP_MAX:
        # 优先 TLS 可能性高的（443/8443 端口、https 来源）
        from tester import DELAY_TIMEOUT_MS  # noqa: F401
        from parsers import _b64_bytes  # noqa: F401
        http.sort(key=lambda p: (not p.get("_tls_hint"), p["port"] not in
                                 (443, 8443, 2053, 2083, 2087, 2096)))
        http = http[:HTTP_MAX]
    allp = other + http
    if len(allp) > MAX_CANDIDATES:
        allp = allp[:MAX_CANDIDATES]
    on_log(f"去重后候选：{len(allp)} 个（http {len(http)} / 其他 {len(other)}）")
    return allp


def speed_test(final, workdir, kernel_path, topn=None, on_log=log, on_progress=None,
               stop_flag=None):
    """下载测速 + 流媒体解锁（GUI 的「手动测速」按钮调用）。
    final 必须是按延迟排好的列表，只测最快的 topn 个；返回按速度重排后的列表。
    stop_flag: 传入一个返回 bool 的函数，返回 True 就在当前节点测完后停止。"""
    if not final:
        raise RuntimeError("没有可测速的节点")
    topn = topn or SPEED_TOPN
    top = final[:topn]
    on_log(f"对最快的 {len(top)} 个测下载速度 + 解锁…")
    m2 = Mihomo(top, workdir, concurrency=8)
    try:
        m2.start(kernel_path)
        for i, p in enumerate(top, 1):
            if stop_flag and stop_flag():
                on_log(f"收到停止信号，已完成 {i - 1}/{len(top)}")
                break
            p["_kbps"] = m2.measure_speed(p["name"])
            p["_unlock"] = m2.measure_unlock(p["name"])
            on_progress and on_progress(f"测速 {i}/{len(top)}")
            on_log(f"  {p['name'][:40]:40} {p['_delay']:4}ms "
                   f"{p['_kbps']:7.0f}KB/s "
                   f"{''.join(k for k, v in p['_unlock'].items() if v)}")
    finally:
        m2.stop()
    # 有实测速度的排前面，同档按速度/延迟
    top.sort(key=lambda p: (-(p.get("_kbps") or 0), p["_delay"]))
    return top + [p for p in final if p not in top]


def run(on_log=log, on_progress=None, workdir=None, kernel_path=None, quick=True):
    """完整流程：搜集 -> 延迟筛选 -> 导出。
    quick=True（默认）：只做延迟筛选，立刻可导出。
    quick=False：额外对最快的 N 个真测速 + 解锁（慢，一般用界面里的手动测速按钮）。"""
    t0 = time.time()
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    data_dir = os.path.join(base, "FreeNodesPro")
    workdir = workdir or os.path.join(data_dir, "work")
    out_dir = os.path.join(data_dir, "out")
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    # 0. 内核
    k = kernel_path or kernel_mod.find_kernel()
    if not k:
        on_log("首次运行：正在下载 mihomo 内核（约 20MB，只需一次）…")
        k = kernel_mod.download_kernel(
            on_progress=lambda g, t: on_progress and on_progress(
                f"下载内核 {g // 1048576}MB / {t // 1048576}MB"))
    on_log(f"内核：{kernel_mod.version(k)}")

    # 1. 搜集
    on_log("开始搜集节点源…")
    cands = collect(on_log)
    if not cands:
        raise RuntimeError("一个候选都没抓到，检查网络")

    # 2. UDP 能力
    udp_ok, udp_host = udp_egress_ok()
    on_log(f"本机 UDP 出站：{'可用（' + udp_host + '）' if udp_ok else '不可用'}")
    if not udp_ok:
        drop = {p["type"] for p in cands if p["type"] in
                {"hysteria", "hysteria2", "tuic"}}
        if drop:
            on_log(f"  跳过 UDP 协议（本机发不了 UDP 就没法测）：{sorted(drop)}")
            cands = [p for p in cands if p["type"] not in drop]

    # 2.5 HTTP 代理展开为明文 / TLS 两个变体
    #     公开列表不会告诉你这个 http 代理是不是 TLS 包起来的，
    #     443/8443 等端口优先试 TLS，其余优先试明文，两个都真测一遍
    cands = expand_variants(cands)
    on_log(f"展开 HTTP 变体后 {len(cands)} 个待测")
    m = Mihomo(cands, workdir, concurrency=CONCURRENCY)
    try:
        on_log(f"校验配置并启动 mihomo（{len(cands)} 个节点）…")
        m.start(k)
        on_log(f"开始延迟测试（并发 {CONCURRENCY}，超时 3 秒）…")
        delays = m.delay_batch([p["name"] for p in m.proxies],
                               on_done=lambda done, total, ok: on_progress and on_progress(
                                   f"延迟测试 {done}/{total}，可用 {ok}"))
    finally:
        m.stop()

    alive = [p for p in m.proxies if p["name"] in delays]
    for p in alive:
        p["_delay"] = delays[p["name"]]
    alive.sort(key=lambda p: p["_delay"])
    on_log(f"延迟测试完成：{len(alive)}/{len(m.proxies)} 可用，"
           f"最快 {alive[0]['_delay']}ms" if alive else "延迟测试完成：0 个可用")

    if not alive:
        raise RuntimeError("没有任何节点通过延迟测试")

    # 4. 真测速 + 解锁（默认跳过，用 speed_test() 手动触发）
    if not quick:
        final = speed_test(alive, workdir, k, on_log=on_log, on_progress=on_progress)
    else:
        final = alive
        for p in final:
            p.setdefault("_kbps", None)
            p.setdefault("_unlock", {})

    info = build_all(final, out_dir, meta={
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    # GUI 导出按钮要用：保留原始代理配置，能直接重新导出三种格式
    info["nodes_raw"] = final
    on_log(f"完成！{len(final)} 个节点已写入 {out_dir}，"
           f"总耗时 {time.time() - t0:.0f}s")
    return info, out_dir


if __name__ == "__main__":
    run()
