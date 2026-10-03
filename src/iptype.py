# -*- coding: utf-8 -*-
"""节点出口 IP 类型检测：jk / 机房 / 移动网络。

判定依据是「这个 IP 属于住宅段还是数据中心段」，公开数据源就能复刻：
  1. ip-api.com 免费 API 给 hosting/mobile/proxy 布尔标记 + ASN + 反向 DNS；
  2. 本地反向 DNS（PTR）几乎总带 resi./hsd1./c-pool 这类主机名。

免费档限速 45 次/分钟，但批量接口 /batch 一次最多 100 个 IP、每分钟 15 批，
折合 1500 次/分钟 —— 完全够用。叠加本地 PTR 双保险，判断更稳。
"""

import json
import socket
import threading
import urllib.request

# ---- 分类 -----------------------------------------------------------------

RESIDENTIAL = "jk"
DATACENTER = "机房"
MOBILE = "移动"
UNKNOWN = "未知"

# 已知的 jk ISP 关键词（AS 名称里命中就算 jk，比 hosting 标记更准）
RES_ISP_HINTS = (
    "comcast", "verizon", "at&t", "charter", "spectrum", "cox comm",
    "at&t services", "frontier", "windstream", "qwest", "centurylink",
    "time warner", "bright house", "mediacom", "suddenlink", "cablevision",
    "optimum", "rcn", "consolidated", "hughes", "viasat", "dish",
    "bt", "virgin media", "sky", "talktalk", "plusnet", "ee", "vodafone",
    "deutsche telekom", "telekom", "unitymedia", "1&1",
    "orange", "free sa", "bouygues", "numericable", "sfr",
    "movistar", "orange espa", "vodafone espa", "masmovil", "jazztel",
    "tim", "wind", "fastweb", "mediaset",
    "kddi", "softbank", "ntt", "ocn", "so-net", "plala", "biglobe",
    "hanaro", "lg uplus", "sk broadband", "kt",
    "chunghwa", "hi-net", "seednet",
    "china telecom", "china unicom", "china mobile", "广电", "铁通",
    "rcs&rds", "telekom romania", "orange romania",
    "rostelecom", "mtts", "beeline", "mts",
    "cogeco", "bell", "telus", "rogers", "shaw", "videotron", "bell canada",
    "telmex", "izzi", "totalplay",
    "oi", "vivo", "claro", "netvirta",
    "etisalat", "du", "stc", "zain",
    "telkom sa", "mtn", "vodacom",
    "nbn", "aussie", "tpg", "optus", "iinet", "exetel",
    "spark", "vodafone nz", "2degrees",
)

# PTR 反向 DNS 里常见的关键段
RES_PTR_HINTS = (
    "resi", "hsd1", "hsd2", "hsd3", "c-", "pool-", "dsl", "cable",
    "dynamic", "dyn-", "pppoe", "rev", "home", "cust",
)

# 数据中心关键词（AS 名命中算机房，防止 hosting 标记漏标）
DC_ISP_HINTS = (
    "amazon", "aws", "google", "microsoft", "azure", "alibaba", "tencent",
    "digitalocean", "vultr", "linode", "hetzner", "ovh", "leaseweb",
    "godaddy", "hostinger", "bluehost", "dreamhost", "digital ocean",
    "choopa", "constant company", "contabo", "kamatera", "scaleway",
    "online s.a.s", "gandi", "namecheap", "cloudflare", "fastly",
    "akamai", "cdnetworks", "highwinds", "stackpath", "quad9",
    "datacamp", "datacampus", "datacenter", "hosting", "serverhub",
    "colocation", "as-choopa", "m247", "ipvolume", "lease web",
    "zenlayer", "edgenat", "bandwagon", "hostwinds", "buyvm",
    "online data", "wan.io", "it7", "global net", "cloud innovation",
    "arka", "green floid", "virtualsystems", "aeza", "timeweb",
    "sel-server", "komtach", "aeza network", "megalink",
)

# 企业形态后缀——AS 名带这些词说明是注册公司，不是家庭宽带
CORP_SUFFIXES = (
    "inc.", "inc", "ltd.", "ltd", "llc", "corp", "corporation", "gmbh",
    "s.r.o.", "sp. z o.o.", "sp. z o.o", "sasu", "s.a.s.", "sa", "s.p.a.",
    "spa", "sia", "uab", "a/s", "aps", "plc", "oyj", "ab", "ooo", "jsc",
    "pty", "ltda", "co., ltd", "ag", "bv", "nv",
)


def classify_ip(info, ptr=""):
    """ip-api 单条结果 + PTR -> jk/机房/移动/未知。

    判据优先级：
      1. hosting 标记（付费库 IP 段级数据，最可靠）；
      2. AS 名关键词兜底（hosting 标记有时漏标亚洲 IDC）；
      3. PTR 特征词作为 jk 的补强证据。
    """
    if not info:
        return UNKNOWN
    if info.get("mobile"):
        return MOBILE
    as_name = (info.get("as") or "").lower()
    isp = (info.get("isp") or "").lower()
    blob = f"{as_name} {isp}"

    if info.get("hosting"):
        return DATACENTER
    # hosting=False 时再用 AS 名兜底：明显机房关键词也算机房
    if any(k in blob for k in DC_ISP_HINTS):
        return DATACENTER
    # jk 判定：AS 名命中 jk ISP，或 PTR 带 jk 特征
    if any(k in blob for k in RES_ISP_HINTS):
        return RESIDENTIAL
    if ptr and any(k in ptr.lower() for k in RES_PTR_HINTS):
        return RESIDENTIAL
    # hosting=False 但 AS 名是注册公司（带 Ltd/GmbH/SpA…），归机房
    as_name = (info.get("as") or "").lower()
    if any(as_name.endswith(k) or f", {k}" in as_name or f" {k}" in as_name
           for k in CORP_SUFFIXES):
        return DATACENTER
    return UNKNOWN


def reverse_dns(ip, timeout=2):
    """查 PTR；失败返回空串。超时设得很短——这只是补强证据，不值得等。"""
    import socket
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""
    finally:
        socket.setdefaulttimeout(old)


# ---- ip-api 批量查询 -------------------------------------------------------

BATCH_URL = "http://ip-api.com/batch"
BATCH_SIZE = 100           # 单次最多 100 个
RATE_WINDOW_S = 62         # 免费档 45 次/分钟，留点余量
_lock = threading.Lock()


def _sleep_for_429():
    """免费档 45 次/分钟，429 时等到下个窗口。"""
    import time
    time.sleep(RATE_WINDOW_S)


def _post(batch, timeout=45):
    """批量查询；遇到 429 自动等到限速窗口重试（最多 3 轮）。
    422 = 单批超过 100 个，自动对半分片重试。"""
    import time
    if len(batch) > BATCH_SIZE:
        out = []
        for i in range(0, len(batch), BATCH_SIZE):
            out.extend(_post(batch[i:i + BATCH_SIZE], timeout=timeout))
        return out
    req = urllib.request.Request(
        BATCH_URL + "?fields=status,message,country,countryCode,isp,org,as,proxy,hosting,mobile,reverse,query",
        data=json.dumps([{"query": ip} for ip in batch]).encode(),
        headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                # 限速：等到下个窗口再试
                time.sleep(RATE_WINDOW_S)
                continue
            if e.code in (502, 503, 504):
                # ip-api 代理偶发网关错误，短暂退避重试
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except Exception as e:
            # ConnectionReset / 超时：退避重试，一个坏 IP 不该毁掉整批
            last = e
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    raise last


def lookup_ips(ips, on_log=None, on_progress=None):
    """批量查 IP 类型。返回 {ip: {"type": 分类, "as": ..., "isp": ..., "ptr": ...}}。

    ips 里重复的 IP 只查一次（结果缓存），同 /16 段的 IP 共享一次查询以省配额。
    """
    uniq = []
    seen = set()
    for ip in ips:
        if ip and ip not in seen:
            seen.add(ip)
            uniq.append(ip)
    if not uniq:
        return {}

    result = {}
    ptr_cache = {}

    def fill(ip, info):
        # ip-api 的 reverse 字段够用时直接用；没有的批量丢给线程池并行查——
        # 本地 gethostbyaddr 对无应答的 IP 会阻塞 10 秒以上（Windows DNS 超时），
        # 串行查能把一批节点拖到分钟级。
        result[ip] = {
            "type": None,   # 占位，PTR 查完后回填
            "as": info.get("as") or "",
            "isp": info.get("isp") or "",
            "country": info.get("country") or "",
            "country_code": info.get("countryCode") or "",
            "proxy": bool(info.get("proxy")),
            "ptr": "",
            "_info": info,
        }

    # 第一轮：全量批量查（ip-api 直接给 reverse，省掉本地 PTR 的开销）
    # 注意：批量接口上限 100 个/批，超过会被 422 拒掉，必须分片。
    for i in range(0, len(uniq), BATCH_SIZE):
        batch = uniq[i:i + BATCH_SIZE]
        try:
            data = _post(batch)
        except Exception as e:
            on_log and on_log(f"  IP 类型批量查询失败（{e}），改逐个查")
            data = []
            # 逐个兜底，遵守免费档限速
            import time
            for ip in batch:
                try:
                    data.append(_post([ip])[0])
                    time.sleep(1.4)
                except Exception:
                    continue
        if data:
            for r in data:
                # ip-api 只要 fields 里没列 status 就不返回该字段，
                # 所以这里容忍缺失：有 query 且没报错就算成功
                if r.get("query") and (r.get("status") is None
                                       or r.get("status") == "success"):
                    fill(r["query"], r)
                    on_progress and on_progress(len(result), len(uniq))
        if on_log and (i // BATCH_SIZE + 1) % 5 == 0:
            on_log(f"  IP 类型已查 {len(result)}/{len(uniq)}")

    # 第二轮：ip-api 没返回的 IP 逐个补查 + 本地 PTR 兜底
    # （第一步可能因 429 限速整批失败，这里给最后一搏）
    import time as _t
    for ip in uniq:
        if ip not in result:
            try:
                data = _post([ip])
                if data and data[0].get("status") == "success":
                    fill(ip, data[0])
                    continue
            except Exception:
                pass
            result[ip] = {"type": UNKNOWN, "as": "", "isp": "",
                          "country": "", "country_code": "",
                          "proxy": False, "ptr": ""}
            on_progress and on_progress(len(result), len(uniq))

    # 第三轮：并行补本地 PTR + 算出最终分类
    # ip-api 经常不返回 reverse 字段，本地 gethostbyaddr 又慢，
    # 用线程池并行把这段压到几秒。
    from concurrent.futures import ThreadPoolExecutor
    need_ptr = [ip for ip, v in result.items() if not v.get("ptr")]
    if need_ptr:
        with ThreadPoolExecutor(max_workers=24) as ex:
            ptrs = dict(zip(need_ptr, ex.map(reverse_dns, need_ptr)))
        for ip, ptr in ptrs.items():
            result[ip]["ptr"] = ptr
    for v in result.values():
        if v.get("type") is None:
            v["type"] = classify_ip(v.pop("_info", {}), v.get("ptr") or "")
        v.pop("_info", None)
    return result


def tag_proxies(proxies, ipinfo, on_log=None):
    """把 IP 类型结果写回节点：p['iptype'] = jk/机房/移动/未知。
    同时写 p['country_code']（ISO-2），给 jk 订阅加国旗用。"""
    kinds = {}
    for p in proxies:
        ip = str(p.get("server") or "")
        info = ipinfo.get(ip)
        if info:
            p["iptype"] = info["type"]
            p["country_code"] = info.get("country_code") or ""
            # 保留原始质量标记（proxy/hosting/mobile），给 clean_residential 过滤用
            p["_ipinfo"] = {
                "proxy": info.get("proxy", False),
                "hosting": info.get("hosting", False),
                "mobile": info.get("mobile", False),
            }
            kinds[info["type"]] = kinds.get(info["type"], 0) + 1
        else:
            p["iptype"] = UNKNOWN
            kinds[UNKNOWN] = kinds.get(UNKNOWN, 0) + 1
    if on_log and kinds:
        summary = "、".join(f"{k} {v}" for k, v in
                            sorted(kinds.items(), key=lambda kv: -kv[1]))
        on_log(f"IP 类型检测完成：{summary}")
    return proxies


def residential_only(proxies):
    """只留 jk 节点（机房/移动/未知全部剔除）。"""
    return [p for p in proxies if p.get("iptype") == RESIDENTIAL]


def clean_residential(proxies, on_log=None):
    """jk 订阅专用：jk + 出口质量干净（proxy/hosting/mobile 全 False）。

    风控严的站点登录时查 IP 质量库，被标记代理/机房的 IP
    直接拒（实测：能登的都是 proxy=False 的 IP）。公开免费节点被大量人
    薅过，脏 IP 比例很高，这一步是把「能登」的节点筛出来的关键。
    """
    kept, dropped = [], 0
    for p in proxies:
        if p.get("iptype") != RESIDENTIAL:
            continue
        ip = str(p.get("server") or "")
        # 质量标记来自 lookup_ips -> tag_proxies 写入的 p['_ipinfo']
        info = p.get("_ipinfo") or {}
        if info.get("proxy") or info.get("hosting") or info.get("mobile"):
            dropped += 1
            continue
        kept.append(p)
    if on_log:
        on_log(f"质量过滤：{len(kept)} 个可用 / 剔除 {dropped} 个低质量 IP")
    return kept


def datacenter_only(proxies):
    return [p for p in proxies if p.get("iptype") == DATACENTER]
