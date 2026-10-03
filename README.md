# FreeNodesPro

每天 **10:00（北京时间，UTC 02:00）** 自动抓取 / 测速 / 检测 IP 类型并发布，发布后自动刷新 jsDelivr 缓存，订阅客户端点「更新」即可拿到当天新节点。

## 订阅地址

### 1️⃣ jk 节点 · 精选档（推荐日常使用）

已按出口 IP 类型筛选，只保留质量较高的节点，节点少但省心。

| 客户端 | 订阅地址 |
|---|---|
| Clash Verge / mihomo | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/clash.yaml` |
| GUI.for.SingBox | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/singbox.json` |
| V2Ray / base64 通用 | `https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/v2ray.txt` |

### 2️⃣ jk 节点 · 全量档（手动挑节点用）

**不筛选**，全部 jk 节点都在里面，节点多、美国节点多，适合自己逐个测速挑选。

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

## 各档区别

| 档位 | 节点数 | 说明 |
|---|---|---|
| jk 精选档 | 少（个位数） | 筛选后留下的高质量节点，直接用 |
| jk 全量档 | 多（90+） | 不筛选，自己测速挑好用的 |
| 全部节点 | 最多 | 所有线路，不区分类型 |

三档的分流规则完全相同，都带完整的国内直连规则。

## 客户端说明

- **Clash Verge**：订阅对应档位的 `clash.yaml`。已开启 geodata-mode 并配置 geox-url，GEOSITE / GEOIP 规则集可直接使用
- **GUI.for.SingBox**：订阅对应档位的 `singbox.json`（sing-box 原生格式）。不要用 clash.yaml，Clash 的 TLS 写法转换到 sing-box 内核会丢 TLS，导入后测速全部为 0
- **V2RayN / Shadowrocket 等**：用 `v2ray.txt`（base64 通用格式）

## IP 类型检测

- **jk**：ISP 为住宅宽带运营商（如 Comcast、KDDI、Deutsche Telekom、Chunghwa），或反向 DNS 命中对应 PTR 特征（如 `resi.`、`hsd1.`、`cpe.`）
- **机房**：命中 IDC / 托管商特征（如 SAKURA、Equinix、UK Dedicated Servers、阿里云），或 hosting 标记为真
- **移动**：mobile 标记为真（移动运营商蜂窝 IP）
- **未知**：无法判定（教育网、混合型线路等），保守归类不强行标记
- 数据来自 ip-api.com 免费 API（hosting / mobile / proxy / reverse / as / isp）+ 反向 DNS 双重验证，只检测延迟测速存活的节点（ip-api 免费版限速 45 次/分钟）

## 其它

- 节点名带国旗和国家代码前缀（如 `🇺🇸 US http-1.2.3.4:443|T`），只改显示名字，连接参数不动
- 订阅每天 10:00 自动更新，无需手动操作
