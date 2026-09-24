# -*- coding: utf-8 -*-
"""输出 Clash / sing-box / base64 三种订阅格式。"""

import base64
import json
import os
import random
import string
import urllib.parse

import yaml

from parsers import to_share_link
from version import SIGNATURE

# 国家/地区旗标
FLAG = {
    "HK": "🇭🇰", "TW": "🇹🇼", "JP": "🇯🇵", "SG": "🇸🇬", "US": "🇺🇸", "KR": "🇰🇷",
    "DE": "🇩🇪", "GB": "🇬🇧", "FR": "🇫🇷", "CA": "🇨🇦", "AU": "🇦🇺", "TR": "🇹🇷",
    "IN": "🇮🇳", "RU": "🇷🇺", "NL": "🇳🇱", "MY": "🇲🇾", "PH": "🇵🇭", "TH": "🇹🇭",
    "VN": "🇻🇳", "ID": "🇮🇩", "ZA": "🇿🇦", "BR": "🇧🇷", "MX": "🇲🇽", "ES": "🇪🇸",
    "IT": "🇮🇹", "SE": "🇸🇪", "CH": "🇨🇭", "UA": "🇺🇦", "PL": "🇵🇱", "FI": "🇫🇮",
    "CN": "🇨🇳",
}

# 从 server 名/域名里猜地区
REGION_HINTS = [
    ("HK", ("香港", "Hong Kong", "hkg", "hk")),
    ("TW", ("台湾", "Taiwan", "twn", "tw")),
    ("JP", ("日本", "Japan", "tokyo", "osa", "jp")),
    ("SG", ("新加坡", "Singapore", "sgp", "sg")),
    ("US", ("美国", "United States", "UnitedStates", "us")),
    ("KR", ("韩国", "Korea", "kor", "kr")),
    ("DE", ("德国", "Germany", "fra", "de")),
    ("GB", ("英国", "United Kingdom", "uk")),
    ("FR", ("法国", "France", "fra", "fr")),
    ("CA", ("加拿大", "Canada", "ca")),
    ("AU", ("澳大利亚", "Australia", "au")),
    ("TR", ("土耳其", "Turkey", "tr")),
    ("IN", ("印度", "India", "ind", "in")),
    ("RU", ("俄罗斯", "Russia", "rus", "ru")),
]


def guess_region(p):
    """先从名字里的域名/地区关键词猜，猜不到再用 IP 前缀库。"""
    parts = [str(p.get(k, "")) for k in ("name", "server", "sni", "ws-opts", "peer")]
    blob = " ".join(parts).lower()
    for code, keys in REGION_HINTS:
        for k in keys:
            if k.lower() in blob:
                return code
    # 名字猜不到，就按 IP 前缀库
    ip_region = guess_region_ip(p.get("server"))
    if ip_region:
        return ip_region
    return ""


def _public(p):
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _fmt_name(p, i):
    r = guess_region(p)
    kind = p.get("type", "?")
    if kind == "http":
        kind = "https" if p.get("tls") else "http"
    sp = p.get("_kbps")
    if sp and sp >= 1024:
        speed = f"{sp/1024:.1f}MB/s"
    elif sp:
        speed = f"{sp:.0f}KB/s"
    else:
        speed = f"{p['_delay']}ms"
    # 国旗 + 地区码，对齐 gist 标签风格（🇿🇦ZA_1|3.5MB/s|...）
    flag = FLAG.get(r, "")
    rtxt = f"{flag}{r}_{i+1}" if r else f"NODE_{i+1}"
    tags = []
    for short, key in (("GPT", "openai"), ("YT", "youtube"), ("GM", "google")):
        if key in (p.get("_unlock") or {}):
            tags.append(short)
    tail = ("|" + "|".join(tags)) if tags else ""
    return f"{rtxt}|{speed}{tail}"[:60]


# /16 前缀 → 国家（精确匹配，优先查）
IP_PREFIX_16 = [
    ("52.196.", "JP"), ("13.112.", "JP"), ("13.113.", "JP"), ("18.176.", "JP"),
    ("35.77.", "JP"), ("3.112.", "JP"), ("3.109.", "JP"), ("43.154.", "JP"),
    ("124.156.", "JP"), ("133.242.", "JP"), ("175.45.", "JP"),
    ("13.213.", "SG"), ("13.229.", "SG"), ("18.136.", "SG"), ("18.141.", "SG"),
    ("52.221.", "SG"), ("54.179.", "SG"), ("54.254.", "SG"),
    ("103.3.", "SG"), ("43.156.", "SG"),
    ("210.48.", "MY"),
    ("120.232.", "CN"), ("202.79.", "CN"),
    # Azure
    ("20.205.", "US"), ("20.94.", "US"), ("20.190.", "US"), ("52.140.", "US"),
    ("40.112.", "US"), ("13.87.", "US"), ("104.41.", "US"),
    # GCP
    ("35.186.", "US"), ("35.187.", "US"), ("35.188.", "US"), ("35.195.", "US"),
    ("35.196.", "US"), ("35.224.", "US"), ("35.225.", "US"), ("35.226.", "US"),
    ("34.64.", "US"), ("34.65.", "US"), ("34.66.", "US"), ("34.67.", "US"),
    ("34.68.", "US"), ("34.69.", "US"), ("34.70.", "US"), ("34.71.", "US"),
    ("34.72.", "US"), ("34.73.", "US"), ("34.74.", "US"), ("34.75.", "US"),
    ("34.76.", "US"), ("34.77.", "US"), ("34.78.", "US"), ("34.79.", "US"),
    ("34.80.", "US"), ("34.81.", "US"), ("34.82.", "US"), ("34.83.", "US"),
    ("34.84.", "US"), ("34.85.", "US"), ("34.86.", "US"), ("34.87.", "US"),
    ("34.88.", "US"), ("34.89.", "US"), ("34.90.", "US"), ("34.91.", "US"),
    ("34.92.", "US"), ("34.93.", "US"), ("34.94.", "US"), ("34.95.", "US"),
    ("34.96.", "US"), ("34.97.", "US"), ("34.98.", "US"), ("34.99.", "US"),
    ("34.100.", "US"), ("34.101.", "US"), ("34.102.", "US"), ("34.103.", "US"),
    ("34.104.", "US"), ("34.105.", "US"), ("34.106.", "US"), ("34.107.", "US"),
    ("34.108.", "US"), ("34.109.", "US"), ("34.110.", "US"), ("34.111.", "US"),
    ("34.112.", "US"), ("34.113.", "US"), ("34.114.", "US"), ("34.115.", "US"),
    ("34.116.", "US"), ("34.117.", "US"), ("34.118.", "US"), ("34.119.", "US"),
    ("34.120.", "US"), ("34.121.", "US"), ("34.122.", "US"), ("34.123.", "US"),
    ("34.124.", "US"), ("34.125.", "US"), ("34.126.", "US"), ("34.127.", "US"),
    ("34.128.", "US"), ("34.129.", "US"), ("34.130.", "US"), ("34.131.", "US"),
    ("34.132.", "US"), ("34.133.", "US"), ("34.134.", "US"), ("34.135.", "US"),
    ("34.136.", "US"), ("34.137.", "US"), ("34.138.", "US"), ("34.139.", "US"),
    ("34.140.", "US"), ("34.141.", "US"), ("34.142.", "US"), ("34.143.", "US"),
    ("34.144.", "US"), ("34.145.", "US"), ("34.146.", "US"), ("34.147.", "US"),
    ("34.148.", "US"), ("34.149.", "US"), ("34.150.", "US"), ("34.151.", "US"),
    ("34.152.", "US"), ("34.153.", "US"), ("34.154.", "US"), ("34.155.", "US"),
    ("35.232.", "US"), ("35.236.", "US"), ("35.238.", "US"), ("35.240.", "US"),
    ("35.244.", "US"),
    # 欧洲(IDC)
    ("5.9.", "DE"), ("5.255.", "RU"), ("46.29.", "RU"), ("45.145.", "RU"),
    ("78.47.", "DE"), ("85.214.", "DE"), ("188.40.", "DE"), ("136.243.", "DE"),
    ("116.202.", "DE"), ("161.97.", "DE"), ("5.178.", "DE"), ("195.192.", "RU"),
    ("185.216.", "CZ"), ("154.81.", "ZA"), ("164.132.", "FR"), ("46.105.", "FR"),
    ("51.68.", "GB"), ("51.89.", "GB"), ("51.91.", "GB"), ("51.141.", "GB"),
    ("20.4.", "GB"), ("40.120.", "GB"), ("52.56.", "GB"), ("18.169.", "GB"),
    ("35.178.", "GB"), ("3.10.", "GB"), ("13.40.", "GB"), ("13.41.", "GB"),
    ("13.42.", "GB"), ("13.43.", "GB"), ("13.44.", "GB"), ("13.45.", "GB"),
    ("13.46.", "GB"), ("13.47.", "GB"), ("13.48.", "GB"), ("13.49.", "GB"),
    ("16.16.", "GB"), ("18.130.", "GB"), ("18.134.", "GB"), ("18.135.", "GB"),
    ("3.8.", "GB"), ("3.9.", "GB"), ("3.11.", "GB"),
    # DigitalOcean / Linode / Vultr 等
    ("157.230.", "US"), ("165.22.", "US"), ("165.232.", "US"), ("159.89.", "US"),
    ("138.68.", "US"), ("159.203.", "US"), ("165.227.", "US"), ("178.128.", "US"),
    ("46.101.", "US"), ("159.65.", "US"), ("167.71.", "US"), ("161.35.", "US"),
    ("68.183.", "US"), ("64.227.", "US"), ("143.198.", "US"), ("137.184.", "US"),
    ("143.110.", "US"), ("137.220.", "US"), ("142.93.", "US"), ("128.199.", "US"),
    ("188.166.", "US"), ("134.209.", "US"), ("142.4.", "US"), ("178.62.", "US"),
    ("139.59.", "US"), ("139.180.", "US"), ("45.32.", "US"), ("45.55.", "US"),
    ("45.76.", "US"), ("45.77.", "US"), ("45.79.", "US"), ("45.63.", "US"),
    ("104.207.", "US"), ("104.238.", "US"), ("104.131.", "US"),
    ("172.104.", "US"), ("172.105.", "US"), ("172.232.", "US"), ("170.187.", "US"),
    ("139.144.", "US"), ("172.234.", "US"),
]

# /8 前缀 → 国家（粗，只有 /16 没命中时才用）
IP_PREFIX_8 = [
    ("3.", "US"), ("4.", "US"), ("13.", "US"), ("15.", "US"), ("18.", "US"),
    ("20.", "US"), ("34.", "US"), ("35.", "US"), ("43.", "US"), ("44.", "US"),
    ("46.", "US"), ("47.", "US"), ("50.", "US"), ("52.", "US"), ("54.", "US"),
    ("63.", "US"), ("65.", "US"), ("67.", "US"), ("69.", "US"), ("72.", "US"),
    ("75.", "US"), ("79.", "US"), ("87.", "US"), ("99.", "US"), ("100.", "US"),
    ("107.", "US"), ("108.", "US"), ("122.", "US"), ("123.", "US"), ("133.", "US"),
    ("134.", "US"), ("135.", "US"), ("142.", "US"), ("146.", "US"), ("148.", "US"),
    ("151.", "US"), ("157.", "US"), ("160.", "US"), ("162.", "US"), ("163.", "US"),
    ("164.", "US"), ("171.", "US"), ("172.", "US"), ("174.", "US"), ("175.", "US"),
    ("176.", "US"), ("185.", "US"), ("192.", "US"), ("198.", "US"), ("203.", "US"),
    ("205.", "US"), ("207.", "US"), ("208.", "US"), ("210.", "US"), ("211.", "US"),
    ("212.", "US"), ("213.", "US"), ("216.", "US"),
]


def guess_region_ip(server):
    """纯 IP 节点按前缀猜国家。先查 /16（精确），再回退 /8（粗）。"""
    s = str(server or "").strip()
    if not s or not s[0].isdigit() or "." not in s:
        return ""
    b = s.split(".")
    if len(b) < 2 or not b[0].isdigit() or not b[1].isdigit():
        return ""
    # /16 优先
    p16 = f"{b[0]}.{b[1]}."
    for pfx, code in IP_PREFIX_16:
        if s.startswith(pfx):
            return code
    # /8 回退
    p8 = f"{b[0]}."
    for pfx, code in IP_PREFIX_8:
        if s.startswith(pfx):
            return code
    return ""


SINGBOX_PLAIN_OK = {"http", "socks5", "vmess", "vless", "trojan", "shadowsocks", "hysteria2"}


def _rid():
    return "ID_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def to_singbox_outbound(p):
    """clash 格式的 proxy -> sing-box outbound。

    原则：抓到什么字段就带什么字段过去，只做字段名翻译，不猜测、不补值。
    传输层（ws-opts/grpc-opts/h2-opts/reality-opts）必须完整带过去，
    少了它们节点必死（GUI.for.SingBox 里表现为延迟 -1）。
    返回 None 表示这个协议导不了。
    """
    t = p.get("type")
    if t not in ("http", "socks5", "vmess", "vless", "trojan", "ss",
                 "hysteria2", "tuic", "hysteria", "naive"):
        return None
    ob = {"tag": p["name"],
          "type": "shadowsocks" if t == "ss" else
                  ("http" if t in ("http", "socks5") else t),
          "server": p["server"],
          "server_port": int(p["port"])}

    # ---- TLS：有 tls 标记或强 TLS 协议才写，且只写抓到的字段
    needs_tls = t in ("trojan", "hysteria2", "tuic", "hysteria", "naive")
    if p.get("tls") or needs_tls:
        tls = {"enabled": True}
        sni = p.get("sni") or p.get("servername") or p.get("server-name")
        if sni:
            tls["server_name"] = sni
        if p.get("skip-cert-verify") or p.get("skip_cert_verify"):
            tls["insecure"] = True
        alpn = p.get("alpn")
        if alpn:
            tls["alpn"] = alpn if isinstance(alpn, list) else [alpn]
        ob["tls"] = tls

    # ---- reality（vless/xray）：原样搬
    ro = p.get("reality-opts")
    if isinstance(ro, dict):
        r = {}
        if ro.get("public-key"):
            r["public_key"] = ro["public-key"]
        if ro.get("short-id"):
            r["short_id"] = ro["short-id"]
        if r:
            ob["tls"] = ob.get("tls", {})
            ob["tls"].update({"enabled": True, "reality": r})
            if ro.get("spider-x"):
                ob["tls"]["reality"]["spider_x"] = ro["spider-x"]

    # ---- 传输层：clash 用 *-opts，sing-box 用 transport
    tr = None
    net = p.get("network")
    if p.get("ws-opts"):
        w = p["ws-opts"]
        tr = {"type": "ws"}
        if w.get("path"):
            # clash 的 path 偶尔是列表（多路径），sing-box 只收字符串，取第一个
            pw = w["path"]
            tr["path"] = pw[0] if isinstance(pw, list) and pw else pw
        if w.get("headers"):
            tr["headers"] = dict(w["headers"])
        if w.get("max-early-data") is not None:
            tr["max_early_data"] = w["max-early-data"]
        if w.get("early-data-header-name"):
            tr["early_data_header_name"] = w["early-data-header-name"]
    elif p.get("grpc-opts"):
        tr = {"type": "grpc", "service_name": p["grpc-opts"].get("grpc-service-name", "")}
        if p["grpc-opts"].get("grpc-mode") == "multi":
            tr["stream_multiplexing"] = True
    elif p.get("h2-opts"):
        h = p["h2-opts"]
        tr = {"type": "h2"}
        if h.get("host"):
            tr["host"] = h["host"] if isinstance(h["host"], list) else [h["host"]]
        if h.get("path"):
            ph = h["path"]
            tr["path"] = ph[0] if isinstance(ph, list) and ph else ph
    elif net == "http" or p.get("http-opts"):
        h = p.get("http-opts") or {}
        tr = {"type": "http"}
        if h.get("path"):
            ph = h["path"]
            tr["path"] = ph[0] if isinstance(ph, list) and ph else ph
        if h.get("headers"):
            tr["headers"] = dict(h["headers"])
    if tr:
        ob["transport"] = tr

    # ---- 凭证（只在有值时写，不写空串）
    if p.get("uuid"):
        ob["uuid"] = p["uuid"]
    if p.get("password"):
        ob["password"] = p["password"]
    if p.get("username"):
        ob["username"] = p["username"]
    if t == "ss":
        if p.get("cipher"):
            ob["method"] = p["cipher"]
    if t == "vmess":
        ob["alter_id"] = int(p.get("alterId", 0) or 0)
        if p.get("cipher"):
            ob["security"] = p["cipher"]
    if t == "tuic":
        cc = p.get("congestion-controller") or p.get("congestion_control")
        if cc:
            ob["congestion_control"] = cc
        if p.get("udp-relay-mode"):
            ob["udp_relay_mode"] = p["udp-relay-mode"]
    if t in ("hysteria2", "hysteria"):
        if p.get("obfs") == "salamander" and p.get("obfs-password"):
            ob["obfs"] = {"type": "salamander", "password": p["obfs-password"]}
        if p.get("up") is not None:
            ob["up_mbps"] = p["up"]
        if p.get("down") is not None:
            ob["down_mbps"] = p["down"]
    if p.get("flow"):
        # xtls-rprx-vision-udp443 是 xray 专属值，sing-box 不收（它自动处理 udp/443）
        ob["flow"] = "xtls-rprx-vision" if p["flow"] == "xtls-rprx-vision-udp443" else p["flow"]
    if p.get("client-fingerprint"):
        fp = p["client-fingerprint"]
        ob["tls"] = ob.get("tls", {})
        ob["tls"].setdefault("enabled", True)
        ob["tls"]["utls"] = {"enabled": True, "fingerprint": fp}
    return ob


def is_http(p):
    return p.get("type") == "http"


def build_all(ok, out_dir, meta=None):
    """ok: 已排序的节点列表（含 _delay/_kbps/_unlock）。写全套订阅。

    节点名（tag）保持抓到时的原样，不重命名、不加国旗不加速度后缀。
    只在重名时加序号去重（sing-box 重名会崩）。
    """
    os.makedirs(out_dir, exist_ok=True)
    meta = meta or {}
    seen = {}
    for p in ok:
        base = p.get("name") or f"{p.get('server')}:{p.get('port')}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            p["name"] = f"{base}#{n + 1}"

    # clash 代理组用的名字列表（= 节点原始名）
    names = [p["name"] for p in ok]

    # （必须在 _public 之前，否则 clash 配置漏 TLS）
    ok = [p for p in ok if p.get("server")]
    for p in ok:
        if p.get("type") in ("trojan", "hysteria2", "tuic", "naive", "hysteria"):
            p.setdefault("tls", True)
            if not p.get("sni") and not p.get("server-name"):
                p["sni"] = p.get("server", "")
            if p.get("sni") and not p.get("server-name"):
                p["server-name"] = p["sni"]

    pub = [_public(p) for p in ok]

    # ---------------- Clash / mihomo
    clash = {
        "mixed-port": 7890,
        "mode": "rule",
        "log-level": "warning",
        "external-controller": "127.0.0.1:9090",
        "ipv6": False,
        "proxies": pub,
        "proxy-groups": [
            {"name": "🚀 节点选择", "type": "select",
             "proxies": ["⚡ 精选速度", "♻️ 自动测速", "DIRECT"] + names},
            {"name": "⚡ 精选速度", "type": "url-test",
             "url": "https://www.gstatic.com/generate_204",
             "interval": 300, "tolerance": 50,
             "proxies": [n for p, n in zip(ok, names) if p.get("_kbps")] or names[:10]},
            {"name": "♻️ 自动测速", "type": "url-test",
             "url": "https://www.gstatic.com/generate_204",
             "interval": 300, "tolerance": 50,
             "proxies": names or ["DIRECT"]},
            {"name": "🤖 ChatGPT", "type": "select",
             "proxies": [n for p, n in zip(ok, names)
                         if p.get("_unlock", {}).get("GPT")] or ["DIRECT"]},
            {"name": "▶️ YouTube", "type": "select",
             "proxies": [n for p, n in zip(ok, names)
                         if p.get("_unlock", {}).get("YT")] or ["DIRECT"]},
            {"name": "🌐 落地分流", "type": "select", "proxies": ["🚀 节点选择", "DIRECT"]},
        ],
        "rules": [
            "GEOSITE,private,DIRECT",
            "GEOSITE,cn,DIRECT",
            "GEOIP,private,DIRECT",
            "GEOIP,cn,DIRECT",
            "GEOSITE,openai,🤖 ChatGPT",
            "GEOSITE,category-ads-all,REJECT",
            "MATCH,🚀 节点选择",
        ],
    }
    with open(os.path.join(out_dir, "clash.yaml"), "w", encoding="utf-8") as f:
        f.write(f"# 由 FreeNodesPro 生成（本机实测）\n"
                f"# 生成时间：{meta.get('at','')} | 节点：{len(ok)}\n"
                + yaml.safe_dump(clash, allow_unicode=True, sort_keys=False, width=10000))

    # ---------------- sing-box（扁平节点数组，GUI.for.SingBox 等客户端直接导入）
    # 注意：GUI.for.SingBox 的"订阅"导入的是纯节点数组，不是完整配置。
    # outbounds 放全部协议；http 节点的 type 统一写成 "http"。
    # sing-box 对 trojan/hysteria2/tuic/naive/hysteria 强制要求显式 TLS 块，
    # 缺失会 "TLS required" 整个启动失败 —— TLS 在下面循环里统一补
    # 先给这些协议的 proxy 本体补 TLS（mihomo 也要用，_public 会带上）
    for p in ok:
        if p.get("type") in ("trojan", "hysteria2", "tuic", "naive", "hysteria"):
            p.setdefault("tls", True)
            if not p.get("sni") and not p.get("server-name"):
                p["sni"] = p.get("server", "")
            if p.get("sni") and not p.get("server-name"):
                p["server-name"] = p["sni"]

    outbounds = [to_singbox_outbound(p) for p in ok]
    outbounds = [o for o in outbounds if o]

    tags = [o["tag"] for o in outbounds]

    # 顶层 singbox.json = GUI.for.SingBox 手动导入格式：纯节点数组 [{...}]
    # 它的 Manual 分支是 JSON.parse(body)，要 [ ] 开头结尾；带壳的它不认。
    with open(os.path.join(out_dir, "singbox.json"), "w", encoding="utf-8") as f:
        json.dump(outbounds, f, ensure_ascii=False, indent=2)

    # singbox-full.json = 带 inbounds/route 的完整配置（进阶用户自用）
    # 用 {"outbounds": [...]} 壳格式，sing-box check 能通过
    sb = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [{"type": "mixed", "tag": "mixed-in",
                      "listen": "127.0.0.1", "listen_port": 2080}],
        "outbounds": outbounds + [
            {"type": "selector", "tag": "🚀 节点选择",
             "outbounds": ["⚡ 精选速度", "♻️ 自动测速", "direct"] + tags,
             "default": "⚡ 精选速度"},
            {"type": "urltest", "tag": "⚡ 精选速度",
             "outbounds": [o["tag"] for o, p in zip(outbounds, ok) if p.get("_kbps")] or tags[:10],
             "url": "https://www.gstatic.com/generate_204", "interval": "5m"},
            {"type": "urltest", "tag": "♻️ 自动测速", "outbounds": tags or ["direct"],
             "url": "https://www.gstatic.com/generate_204", "interval": "5m"},
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "rules": [
                {"ip_is_private": True, "outbound": "direct"},
                {"geosite": ["cn"], "outbound": "direct"},
                {"geoip": ["cn", "private"], "outbound": "direct"},
                {"geosite": ["openai"], "outbound": "🚀 节点选择"},
                {"geosite": ["category-ads-all"], "outbound": "block"},
            ],
            "final": "🚀 节点选择",
        },
    }
    with open(os.path.join(out_dir, "singbox-full.json"), "w", encoding="utf-8") as f:
        json.dump(sb, f, ensure_ascii=False, indent=2)

    # ---------------- base64 订阅（v2rayN / Karing / Shadowrocket）
    # 综合订阅包含全部类型（http 走 http(s)://user:pass@host:port 链接）
    links = [l for l in (to_share_link(p) for p in ok) if l]
    with open(os.path.join(out_dir, "v2ray.txt"), "w", encoding="utf-8") as f:
        f.write(base64.b64encode("\n".join(links).encode()).decode() if links else "")

    # ---------------- 纯 HTTP 分类（对应不同客户端）
    http_nodes = [p for p in ok if is_http(p)]
    if http_nodes:
        http_dir = os.path.join(out_dir, "http")
        os.makedirs(http_dir, exist_ok=True)

        # 纯节点数组（GUI.for.SingBox 手动导入 / NekoBox / Karing）
        plain = [o for o in (to_singbox_outbound(p) for p in http_nodes) if o]
        with open(os.path.join(http_dir, "singbox.json"), "w", encoding="utf-8") as f:
            json.dump(plain, f, ensure_ascii=False, indent=2)

        # Clash proxies 片段（proxies 列表，可直接贴进 clash 配置）
        with open(os.path.join(http_dir, "clash.yaml"), "w", encoding="utf-8") as f:
            f.write(yaml.safe_dump({"proxies": [_public(p) for p in http_nodes]},
                                   allow_unicode=True, sort_keys=False, width=10000))

        # base64 订阅：http(s)://user:pass@host:port
        links = []
        for p in http_nodes:
            scheme = "https" if p.get("tls") else "http"
            auth = f"{p['username']}:{p.get('password','')}@" if p.get("username") else ""
            links.append(f"{scheme}://{auth}{p['server']}:{p['port']}")
        with open(os.path.join(http_dir, "base64.txt"), "w", encoding="utf-8") as f:
            f.write(base64.b64encode("\n".join(links).encode()).decode() if links else "")

    # ---------------- 测速结果专档（只放真测过速度的节点，避免"白测"）
    sped = [p for p in ok if p.get("_kbps")]
    if sped and not out_dir.endswith("speedtest"):
        sped.sort(key=lambda p: -(p.get("_kbps") or 0))
        sub = os.path.join(out_dir, "speedtest")
        os.makedirs(sub, exist_ok=True)
        build_all(sped, sub, meta={"at": meta.get("at", "") + " (测速结果)"})

    # ---------------- 元信息
    info = {
        "app": SIGNATURE,
        "at": meta.get("at", ""),
        "total": len(ok),
        "with_speed": sum(1 for p in ok if p.get("_kbps")),
        "unlock": {k: sum(1 for p in ok if (p.get("_unlock") or {}).get(k))
                   for k in ("GPT", "YT", "GM")},
        "regions": {},
        "nodes": [{"name": p["name"], "type": p.get("type"),
                   "server": p["server"], "port": p["port"],
                   "delay": p["_delay"], "kbps": round(p.get("_kbps") or 0),
                   "unlock": {k: v for k, v in (p.get("_unlock") or {}).items() if v}}
                  for p in ok],
    }
    for p in ok:
        r = guess_region(p)
        info["regions"][r or "其他"] = info["regions"].get(r or "其他", 0) + 1
    with open(os.path.join(out_dir, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    return info
