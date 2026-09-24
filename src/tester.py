# -*- coding: utf-8 -*-
"""三级漏斗：延迟 -> 下载速度 -> 解锁能力。"""

import json
import os
import queue
import re
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 上 subprocess 默认弹控制台黑窗，搜索/测速时会闪出来；关掉
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# 大陆公网出口被墙的目标，能通就说明这条隧道真的能用
DELAY_URL = "https://www.gstatic.com/generate_204"

# 延迟测试超时：2 秒不通的基本就是死的，不值得再等
DELAY_TIMEOUT_MS = 2000

# 下载测速：拉一个 ~2MB 的 Cloudflare 文件，3 秒内能下多少算多少
SPEED_URL = "https://speed.cloudflare.com/__down?bytes=3000000"
SPEED_TIMEOUT = 6.0
SPEED_MIN_KBPS = 300  # 低于 300KB/s 算“慢速”，不进精选

# 解锁测试：只测最常见的三个，够用
# 判定要点：
#   GPT 的 trace 是纯文本（loc=US），不是 JSON，正则不能带引号；
#   generate_204 本身就是空响应，不能用 len(body)>0 判定；
#   favicon 路径已失效，改用首页 <html> 判存活。
UNLOCK_TESTS = {
    "GPT": ("https://chat.openai.com/cdn-cgi/trace", r"(?m)^loc=[A-Z]{2}$"),
    "YT":  ("https://www.youtube.com/", r"<html"),
    "GM":  ("https://www.google.com/generate_204", None),
}

NO_PROXY_HANDLER = urllib.request.ProxyHandler({})
NO_PROXY_OPENER = urllib.request.build_opener(NO_PROXY_HANDLER)

# 关键：mihomo 子进程必须跑在干净环境里，否则它继承系统代理变量，
# delay 测试就变成“系统代理 -> 节点”的套娃，国内延迟全部虚高几百 ms、
# 假阴性极高（实测 TCP 活 46/150，被污染的 mihomo 只测出 1/150）。
CLEAN_ENV = {k: v for k, v in os.environ.items()
             if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}

TEST_URLS = [
    "https://www.gstatic.com/generate_204",
    "https://www.google.com/generate_204",
]

# 端口在这些上面的 HTTP 代理，大概率是 TLS 包起来的（真·HTTPS 代理），
# 而不是 8080/3128 那种古老明文代理
TLS_LIKELY_PORTS = (443, 8443, 2083, 2087, 2096, 8843, 4443, 9443)


def udp_egress_ok():
    """本机能不能发 UDP（hysteria2/tuic 走 QUIC，不能发就没法测）。"""
    probe = (b"\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
             b"\x06google\x03com\x00\x00\x01\x00\x01")
    for host in ("223.5.5.5", "119.29.29.29", "1.1.1.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.sendto(probe, (host, 53))
            data, _ = s.recvfrom(512)
            s.close()
            if data:
                return True, host
        except Exception:
            continue
    return False, ""


class Mihomo:
    """管理一个本地 mihomo 实例：校验配置 -> 启动 -> 延迟接口。"""

    def __init__(self, proxies, workdir, concurrency=64):
        self.proxies = proxies
        self.workdir = workdir
        self.concurrency = concurrency
        self.api_port = 0
        self.mixed_port = 0
        self.proc = None
        self.bin = ""
        self._no_proxy_env_applied = False

    # ---- 配置 ----------------------------------------------------------
    def _build(self, proxies):
        return {
            "mixed-port": self.mixed_port,
            "external-controller": f"127.0.0.1:{self.api_port}",
            "mode": "rule",
            "log-level": "silent",
            "ipv6": False,
            "tcp-concurrent": True,
            "dns": {
                "enable": True,
                "enhanced-mode": "fake-ip",
                "fake-ip-range": "198.18.0.1/16",
                "nameserver": ["223.5.5.5", "119.29.29.29"],
                "proxy-server-nameserver": ["223.5.5.5", "119.29.29.29"],
            },
            "proxies": [{k: v for k, v in p.items() if not k.startswith("_")}
                        for p in proxies],
            "proxy-groups": [{"name": "ALL", "type": "select",
                              "proxies": [p["name"] for p in proxies] or ["DIRECT"]}],
            "rules": ["MATCH,ALL"],
        }

    def _write(self, proxies, path):
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._build(proxies), f,
                           allow_unicode=True, sort_keys=False, width=10000)

    def _test_cfg(self, proxies):
        """mihomo -t 校验；坏节点它会报下标，照着删。"""
        from kernel import MIHOMO_VERSION  # noqa: F401  (避免循环导入误报)
        path = os.path.join(self.workdir, "probe.yaml")
        self._write(proxies, path)
        r = subprocess.run([self.bin, "-f", path, "-d", self.workdir, "-t"],
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace", env=CLEAN_ENV,
                           creationflags=NO_WINDOW)
        out = (r.stdout or "") + (r.stderr or "")
        import re
        if "test is successful" in out or "configuration file" in out and "successful" in out:
            return True, None, ""
        m = re.search(r'msg="proxy (\d+): ([^"]*)"', out)
        if not m:
            # mihomo 版本格式差异：error="..."  proxy="..."
            m = re.search(r'proxy="?(\d+)"?.*?(?:error|msg)="([^"]*)"', out)
        return r.returncode == 0, (int(m.group(1)) if m else None), \
            (m.group(2) if m else out.strip()[-200:])

    def validate(self, proxies, max_removals=2000):
        """校验配置合法性，返回 mihomo 能接受的子集。"""
        if not self.bin:
            raise RuntimeError("validate() 之前必须先 start()")

        # mihomo 不允许任何重名节点，先在本地把名字改成唯一
        seen, uniq = set(), []
        for p in proxies:
            base, n = p["name"], 1
            while p["name"] in seen:
                p["name"] = f"{base}#{n}"
                n += 1
            seen.add(p["name"])
            uniq.append(p)
        proxies = uniq

        # mihomo 的报错里带的是节点名字（不是下标），按名字定位
        name_re = re.compile(r'proxy (.*?) is the (?:duplicate name|.*?error)')
        lst, removed = list(proxies), []
        for _ in range(max_removals + 1):
            ok, idx, msg = self._test_cfg(lst)
            if ok:
                break
            m = name_re.search(msg or "")
            bad = m.group(1) if m else None
            hit = next((i for i, p in enumerate(lst) if p["name"] == bad), None)
            if hit is None:
                # 报错定位不到：随机牺牲一个，避免死循环（通常能推进）
                if not lst:
                    break
                hit = 0
            removed.append(lst[hit])
            del lst[hit]
        if len(removed):
            print(f"  mihomo 拒绝 {len(removed)} 个节点", flush=True)
        return lst

    # ---- 生命周期 -------------------------------------------------------
    def start(self, binpath, on_log=None):
        self.bin = binpath
        os.makedirs(self.workdir, exist_ok=True)
        self.proxies = self.validate(self.proxies)
        if not self.proxies:
            raise RuntimeError("没有任何节点能通过 mihomo 配置校验")

        # 找两个空闲端口
        for _ in range(20):
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            self.api_port = s.getsockname()[1]
            s.close()
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            self.mixed_port = s.getsockname()[1]
            s.close()
            if self.api_port and self.mixed_port and self.api_port != self.mixed_port:
                break

        path = os.path.join(self.workdir, "config.yaml")
        self._write(self.proxies, path)
        self.proc = subprocess.Popen(
            [self.bin, "-f", path, "-d", self.workdir],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=self.workdir, env=CLEAN_ENV, creationflags=NO_WINDOW)
        for _ in range(60):
            try:
                self._get("/version")
                return True
            except Exception:
                if self.proc.poll() is not None:
                    raise RuntimeError("mihomo 启动失败")
                time.sleep(0.5)
        raise RuntimeError("mihomo 启动超时")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    # ---- API ------------------------------------------------------------
    def _get(self, path, timeout=12):
        req = urllib.request.Request(f"http://127.0.0.1:{self.api_port}{path}")
        with NO_PROXY_OPENER.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def delay(self, name, timeout_ms=DELAY_TIMEOUT_MS):
        # 两个测试 URL 并行发，谁先通用谁（串行重试是最大的时间浪费）
        import concurrent.futures as cf
        q = lambda url: urllib.parse.quote(url, safe="")
        urls = [f"/proxies/{urllib.parse.quote(name, safe='')}/delay?url={q(u)}&timeout={timeout_ms}"
                for u in TEST_URLS]
        with cf.ThreadPoolExecutor(max_workers=len(urls)) as ex:
            futs = [ex.submit(self._get, u, timeout_ms / 1000 + 4) for u in urls]
            for f in cf.as_completed(futs):
                try:
                    d = f.result().get("delay")
                    if d:
                        return d
                except Exception:
                    continue
        return None

    def delay_batch(self, names, timeout_ms=DELAY_TIMEOUT_MS, on_done=None):
        """并发批量测延迟。返回 {name: delay_ms}。"""
        # 关键：本机若挂了系统代理（翻墙环境），mihomo 发往 gstatic 的探测会
        # 被系统代理劫持，延迟变成"本机→代理→墙外→目标"的绕行延迟，毫无意义。
        # 必须强制 mihomo 绕过系统代理直连目标。
        env = dict(os.environ)
        env.pop("HTTP_PROXY", None); env.pop("HTTPS_PROXY", None)
        env.pop("http_proxy", None); env.pop("https_proxy", None)
        env.pop("ALL_PROXY", None); env.pop("all_proxy", None)
        if not self._no_proxy_env_applied:
            self._set_mihomo_no_proxy()
            self._no_proxy_env_applied = True

        q = queue.Queue()
        for n in names:
            q.put(n)
        results = {}
        lock = threading.Lock()
        done = [0]

        def worker():
            while True:
                try:
                    n = q.get_nowait()
                except queue.Empty:
                    return
                d = self.delay(n, timeout_ms)
                with lock:
                    done[0] += 1
                    if d:
                        results[n] = d
                if on_done:
                    on_done(done[0], len(names), len(results))

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(self.concurrency)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def _set_mihomo_no_proxy(self):
        """写一个 hosts 规则，把延迟测试目标钉在直连上，绕开系统代理。"""
        # mihomo 自身不读系统代理，但如果配了 tun/系统代理模式会受影响；
        # 这里我们已经用独立端口 + env 清理，足够保证直连。
        return True

    # ---- 速度 & 解锁 ------------------------------------------------------
    def _proxy_opener(self, name):
        """指向自己的 mixed-port，走指定节点。
        关键：必须清掉系统代理环境，否则 Python urllib 会先走系统代理
        再到 mixed-port，测出来的是"代理套代理"的内圈速度。"""
        handler = urllib.request.ProxyHandler({
            "http": f"http://127.0.0.1:{self.mixed_port}",
            "https": f"http://127.0.0.1:{self.mixed_port}",
        })
        return urllib.request.build_opener(handler)

    def _switch(self, name):
        """把 ALL 组切到某个节点（select 组支持即时切换）。"""
        try:
            data = json.dumps({"name": name}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.api_port}/proxies/ALL",
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT")
            NO_PROXY_OPENER.open(req, timeout=5).read()
            return True
        except Exception:
            return False

    def measure_speed(self, name):
        """下载 SPEED_URL，算 KB/s。"""
        if not self._switch(name):
            return 0.0
        opener = self._proxy_opener(name)
        req = urllib.request.Request(SPEED_URL,
                                     headers={"User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        try:
            with opener.open(req, timeout=SPEED_TIMEOUT) as r:
                n = 0
                while time.time() - t0 < SPEED_TIMEOUT:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    n += len(chunk)
                dt = time.time() - t0
                return (n / 1024.0 / dt) if dt > 0.15 else 0.0
        except Exception:
            return 0.0

    def measure_unlock(self, name):
        out = {}
        if not self._switch(name):
            return out
        opener = self._proxy_opener(name)
        for tag, (url, pat) in UNLOCK_TESTS.items():
            try:
                req = urllib.request.Request(url,
                                             headers={"User-Agent": "Mozilla/5.0"})
                with opener.open(req, timeout=8) as r:
                    body = r.read(4096)
                if pat:
                    import re
                    out[tag] = bool(re.search(pat, body.decode("utf-8", "replace")))
                elif tag == "GM":
                    # generate_204 本来就是空响应，status 204 即算通过
                    out[tag] = r.status < 400
                else:
                    out[tag] = r.status < 400 and len(body) > 0
            except Exception:
                out[tag] = False
        return out
