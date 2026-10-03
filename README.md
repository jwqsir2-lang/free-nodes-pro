# 

### 1️⃣ jk 节点
已按出口 IP 节点少但省心。

| 客户端 | 订阅地址 |
|---|---|
| Clash Verge / mihomo | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/clash.yaml` |
| GUI.for.SingBox | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/singbox.json` |
| V2Ray / base64 通用 | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/v2ray.txt` |

### 2️⃣ jk 节点 · 全量档（手动挑节点用）

**不筛选**，全部 jk节点都在里面，节点多、美国节点多，适合自己逐个测速挑选。

| 客户端 | 订阅地址 |
|---|---|
| Clash Verge / mihomo | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential-all/clash.yaml` |
| GUI.for.SingBox | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential-all/singbox.json` |
| V2Ray / base64 通用 | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential-all/v2ray.txt` |

### 3️⃣ 全部节点（不分 IP 类型）

上表之外的全部节点，不区分 IP 类型，什么线路都有。

| 客户端 | 订阅地址 |
|---|---|
| Clash Verge / mihomo | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/clash.yaml` |
| GUI.for.SingBox | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/singbox.json` |

> raw 地址：把 `https://cdn.jsdelivr.net/gh/` 换成 `https://raw.githubusercontent.com/` 即可，无缓存延迟，但部分地区无法直连。

## 客户端说明

- **Clash Verge**：订阅对应档位的 `clash.yaml`。已开启 geodata-mode 并配置 geox-url，GEOSITE / GEOIP 规则集可直接使用
- **GUI.for.SingBox**：订阅对应档位的 `singbox.json`（sing-box 原生格式）。不要用 clash.yaml，Clash 的 TLS 写法转换到 sing-box 内核会丢 TLS，导入后测速全部为 0
- **V2RayN / Shadowrocket 等**：用 `v2ray.txt`（base64 通用格式）

