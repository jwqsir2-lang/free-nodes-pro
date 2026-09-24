# -*- coding: utf-8 -*-
"""统一解析：clash yaml / base64 订阅 / 分享链接 -> 统一的 proxy 字典。"""

import base64
import binascii
import json
import re
import urllib.parse

import yaml

SS_CIPHERS = {
    "aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305", "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305",
    "none", "plain", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "chacha20", "chacha20-ietf",
    "rc4-md5", "rc4", "aes-128-ccm", "aes-256-ccm", "aes-128-gcm-siv",
    "aes-256-gcm-siv", "chacha20-poly1305", "xchacha20-poly1305",
}
VMESS_CIPHERS = {"auto", "aes-128-gcm", "chacha20-poly1305", "none"}
UDP_TYPES = {"hysteria", "hysteria2", "tuic"}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _b64_bytes(s, n):
    try:
        return len(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))) == n
    except Exception:
        return False


def _b64_text(s):
    """宽容的 base64 解码，失败返回原文。"""
    if not s:
        return s
    try:
        d = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        return d.decode("utf-8", "replace")
    except Exception:
        return s


# ------------------------------------------------------------------ clash yaml
def parse_clash_yaml(text):
    try:
        d = yaml.safe_load(text)
    except Exception:
        return []
    if not isinstance(d, dict):
        return []
    out = []
    for p in d.get("proxies") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        out.append(dict(p))
    return out


# ------------------------------------------------------------------ base64 订阅
def parse_base64_sub(text):
    """v2rayN/Karing 的 base64 订阅：整段是 base64，里面一行一条分享链接。"""
    body = text.strip()
    # 整段 base64？
    if not body or "\n" not in body.replace("\r\n", "\n").strip() or ":" not in body:
        body = _b64_text(body)
    links = [l.strip() for l in body.splitlines() if l.strip()]
    return [parse_share_link(l) for l in links]


# ------------------------------------------------------------------ 分享链接
def _b64url_json(payload):
    s = payload.split("?", 1)[1] if "?" in payload else ""
    if not s:
        return {}
    q = dict(urllib.parse.parse_qsl(s, keep_blank_values=True))
    for k in ("obfsParam", "path", "host", "sni", "alpn", "peer"):
        if k in q:
            q[k] = _b64_text(q[k])
    if "alpn" in q and q["alpn"]:
        q["alpn"] = [x for x in str(q["alpn"]).split(",") if x]
    return q


def parse_share_link(link):
    """vmess:// / vless:// / ss:// / trojan:// / hysteria2:// / hy2:// -> proxy dict"""
    link = (link or "").strip()
    try:
        if link.startswith("vmess://"):
            raw = base64.urlsafe_b64decode(link[8:] + "=" * (-len(link[8:]) % 4))
            o = json.loads(raw.decode("utf-8", "replace"))
            return {
                "name": o.get("ps") or o.get("remarks") or "",
                "type": "vmess", "server": str(o.get("add", "")),
                "port": int(o.get("port", 0) or 0),
                "uuid": str(o.get("id", "")), "alterId": int(o.get("aid", 0) or 0),
                "cipher": o.get("scy") or "auto",
                **({"network": o["net"]} if o.get("net") else {}),
                **({"tls": True} if str(o.get("tls", "")).lower() == "tls" else {}),
                **({"servername": o["sni"]} if o.get("sni") else {}),
                **({"skip-cert-verify": True} if o.get("verify_cert") is False else {}),
                **({"ws-opts": {"path": o["path"], "headers": {"Host": o["host"]}}}
                   if o.get("net") == "ws" else {}),
                **({"grpc-opts": {"grpc-service-name": o["path"]}}
                   if o.get("net") == "grpc" and o.get("path") else {}),
            }
        if link.startswith("vless://"):
            u = urllib.parse.urlparse(link)
            q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
            if not UUID_RE.match(u.username or ""):
                return None
            p = {"name": urllib.parse.unquote(u.fragment or ""),
                 "type": "vless", "server": u.hostname or "",
                 "port": u.port or 0, "uuid": u.username}
            if q.get("flow"):
                p["flow"] = q["flow"]
            if q.get("encryption") and q["encryption"] != "none":
                return None
            if q.get("security") in ("tls", "reality"):
                p["tls"] = True
                if q.get("sni"):
                    p["servername"] = q["sni"]
                if q.get("fp"):
                    p["client-fingerprint"] = q["fp"]
                if q["security"] == "reality":
                    p["reality-opts"] = {
                        "public-key": q.get("pbk", ""),
                        **({"short-id": q["sid"]} if q.get("sid") else {})}
                    if not q.get("sni"):
                        return None
            if q.get("type") == "ws":
                p["network"] = "ws"
                p["ws-opts"] = {"path": _b64_text(q.get("path", "/")) or "/",
                                "headers": {"Host": q.get("host", "")} if q.get("host") else {}}
            elif q.get("type") == "grpc":
                p["network"] = "grpc"
                p["grpc-opts"] = {"grpc-service-name": q.get("serviceName", "")}
            return p
        if link.startswith("ss://"):
            body = link[5:]
            userinfo, _, after = body.partition("@")
            if not after:
                # ss://base64(method:pass@host:port)
                dec = _b64_text(userinfo)
                userinfo, _, after = dec.partition("@")
            method, _, password = userinfo.split(":", 2) if userinfo.count(":") >= 2 \
                else (userinfo.split(":", 1) + [""])
            hp, _, frag = after.partition("#")
            host, _, port = hp.rpartition(":")
            port = port.split("/", 1)[0].split("?", 1)[0]
            p = {"name": urllib.parse.unquote(frag),
                 "type": "ss", "server": host.strip("[]"),
                 "port": int(port or 0),
                 "cipher": method, "password": password}
            return p
        if link.startswith("trojan://"):
            u = urllib.parse.urlparse(link)
            q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
            p = {"name": urllib.parse.unquote(u.fragment or ""),
                 "type": "trojan", "server": u.hostname or "",
                 "port": u.port or 443, "password": urllib.parse.unquote(u.username or ""),
                 "sni": q.get("sni") or (u.hostname or "")}
            if q.get("allowInsecure", "0") in ("1", "true"):
                p["skip-cert-verify"] = True
            if q.get("type") == "ws":
                p["network"] = "ws"
                p["ws-opts"] = {"path": _b64_text(q.get("path", "/")) or "/"}
            return p
        if link.startswith("hysteria2://") or link.startswith("hy2://"):
            u = urllib.parse.urlparse(link.replace("hy2://", "hysteria2://"))
            q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
            p = {"name": urllib.parse.unquote(u.fragment or ""),
                 "type": "hysteria2", "server": u.hostname or "",
                 "port": u.port or 443,
                 "password": urllib.parse.unquote(u.username or "")}
            if q.get("sni"):
                p["sni"] = q["sni"]
            if q.get("insecure") in ("1", "true"):
                p["skip-cert-verify"] = True
            if q.get("obfs") == "salamander" and q.get("obfs-password"):
                p["obfs"] = "salamander"
                p["obfs-password"] = q["obfs-password"]
            return p
        if link.startswith("tuic://"):
            u = urllib.parse.urlparse(link)
            q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
            return {"name": urllib.parse.unquote(u.fragment or ""),
                    "type": "tuic", "server": u.hostname or "",
                    "port": u.port or 443, "uuid": u.username or "",
                    "password": urllib.parse.unquote(u.password or ""),
                    "sni": q.get("sni") or (u.hostname or ""),
                    "congestion-controller": q.get("congestion_control", "bbr")}
    except Exception:
        return None
    return None


# ------------------------------------------------------------------ ip:port 文本
IPPORT_RE = re.compile(
    r"^\s*(?:https?://)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})\s*$")


def parse_iplist(text, tls_hint=False):
    """TheSpeedX / proxifly 那种一行一个 ip:port 的纯 HTTP 代理列表。"""
    out = []
    for line in (text or "").splitlines():
        m = IPPORT_RE.match(line)
        if not m:
            continue
        out.append({"name": f"http-{m.group(1)}:{m.group(2)}",
                    "type": "http", "server": m.group(1),
                    "port": int(m.group(2)),
                    **({"_tls_hint": True} if tls_hint else {})})
    return out


def to_share_link(p):
    """proxy dict -> 分享链接（用于 base64 订阅）"""
    try:
        t = p.get("type")
        if t == "vmess":
            o = {"v": "2", "ps": p.get("name", ""), "add": p["server"],
                 "port": str(p["port"]), "id": p.get("uuid", ""),
                 "aid": str(p.get("alterId", 0)), "scy": p.get("cipher", "auto"),
                 "net": p.get("network", "tcp"), "tls": "tls" if p.get("tls") else "",
                 "sni": p.get("servername", ""), "host": "", "path": ""}
            ws = p.get("ws-opts") or {}
            if ws:
                o["path"] = ws.get("path", "/")
                o["host"] = (ws.get("headers") or {}).get("Host", "")
            return "vmess://" + base64.urlsafe_b64encode(
                json.dumps(o, separators=(",", ":")).encode()).decode()
        if t == "vless":
            q = {"encryption": "none"}
            if p.get("flow"):
                q["flow"] = p["flow"]
            if p.get("tls"):
                q["security"] = "reality" if p.get("reality-opts") else "tls"
                if p.get("servername"):
                    q["sni"] = p["servername"]
                if p.get("client-fingerprint"):
                    q["fp"] = p["client-fingerprint"]
                ro = p.get("reality-opts") or {}
                if ro.get("public-key"):
                    q["pbk"] = ro["public-key"]
                if ro.get("short-id"):
                    q["sid"] = ro["short-id"]
            if p.get("network") == "ws":
                q["type"] = "ws"
                ws = p.get("ws-opts") or {}
                q["path"] = base64.urlsafe_b64encode(
                    (ws.get("path") or "/").encode()).decode().rstrip("=")
                if (ws.get("headers") or {}).get("Host"):
                    q["host"] = ws["headers"]["Host"]
            elif p.get("network") == "grpc":
                q["type"] = "grpc"
                q["serviceName"] = (p.get("grpc-opts") or {}).get("grpc-service-name", "")
            url = (f"vless://{p.get('uuid')}@{p['server']}:{p['port']}"
                   f"?{urllib.parse.urlencode(q)}")
            return url + "#" + urllib.parse.quote(p.get("name", ""))
        if t == "ss":
            userinfo = f"{p.get('cipher')}:{p.get('password')}"
            b64 = base64.urlsafe_b64encode(userinfo.encode()).decode().rstrip("=")
            return (f"ss://{b64}@{p['server']}:{p['port']}"
                    f"#{urllib.parse.quote(p.get('name', ''))}")
        if t == "trojan":
            return (f"trojan://{urllib.parse.quote(str(p.get('password','')))}"
                    f"@{p['server']}:{p['port']}?sni={p.get('sni') or p['server']}"
                    f"&allowInsecure=1#{urllib.parse.quote(p.get('name',''))}")
        if t == "hysteria2":
            return (f"hysteria2://{urllib.parse.quote(str(p.get('password','')))}"
                    f"@{p['server']}:{p['port']}?sni={p.get('sni') or p['server']}"
                    f"&insecure=1#{urllib.parse.quote(p.get('name',''))}")
    except Exception:
        return None
    return None


# ------------------------------------------------------------------ 清洗
def clean(p):
    """丢弃结构性非法的节点；字段补默认值。返回 None 表示丢弃。"""
    if not isinstance(p, dict):
        return None
    typ = str(p.get("type", "")).lower()
    if typ not in ("ss", "vmess", "vless", "trojan", "hysteria", "hysteria2",
                   "tuic", "http", "socks5"):
        return None
    p = dict(p)
    p["type"] = typ
    try:
        p["port"] = int(p.get("port") or 0)
    except Exception:
        return None
    p["server"] = str(p.get("server") or "").strip().strip("[]")
    if not p["server"] or not (1 <= p["port"] <= 65535):
        return None
    if not p.get("name"):
        p["name"] = f"{typ}-{p['server']}:{p['port']}"
    p["name"] = str(p["name"])[:60]
    if p.get("udp") not in (True, False):
        p["udp"] = False

    if typ == "vmess":
        if not UUID_RE.match(str(p.get("uuid", ""))):
            return None
        p["cipher"] = p.get("cipher") if p.get("cipher") in VMESS_CIPHERS else "auto"
    if typ == "vless":
        if not UUID_RE.match(str(p.get("uuid", ""))):
            return None
        ro = p.get("reality-opts")
        if isinstance(ro, dict):
            pk, sid = str(ro.get("public-key", "")), str(ro.get("short-id", "") or "")
            if not _b64_bytes(pk, 32) or (sid and not (HEX_RE.match(sid) and len(sid) % 2 == 0)):
                return None
    if typ == "ss":
        if str(p.get("cipher", "")).lower() not in SS_CIPHERS:
            return None
        p["cipher"] = str(p["cipher"]).lower()
        if not p.get("password"):
            return None
        if p.get("plugin"):
            return None
    if typ in ("trojan", "hysteria2", "tuic") and not (p.get("password") or p.get("uuid")):
        return None
    if typ == "tuic" and not UUID_RE.match(str(p.get("uuid", ""))):
        return None
    if typ == "hysteria2":
        if p.get("obfs") not in (None, "salamander"):
            p.pop("obfs", None); p.pop("obfs-password", None)
        elif p.get("obfs") == "salamander" and not p.get("obfs-password"):
            p.pop("obfs", None)
    if typ in ("http", "socks5"):
        for k in ("username", "password"):
            if k in p and not isinstance(p[k], str):
                p[k] = str(p[k])
        if p.get("username") == "":
            p.pop("username", None); p.pop("password", None)
    for k in ("ws-opts", "grpc-opts", "h2-opts"):
        if k in p and not isinstance(p[k], dict):
            p.pop(k, None)
    return p


def dedupe(proxies):
    seen, out = set(), []
    for p in proxies:
        k = (p.get("type"), p["server"], p["port"],
             str(p.get("uuid") or p.get("password") or ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out
