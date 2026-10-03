# FreeNodesPro

 10:00（UTC 02:00）自动更新，更新后自动刷新 jsDelivr 缓存，订阅客户端点更新即可拿到当天新节点。

jk节点专用订阅（已按出口 IP 类型筛选，流媒体不易识别封锁）：

```
Clash Verge:
https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/clash.yaml
```

```
GUI.for.SingBox（sing-box 原生格式，实测可用）:
https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/singbox.json
```

```
V2Ray / base64 通用:
https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/residential/v2ray.txt
```

全量节点订阅（不分 IP 类型）：

```
https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/clash.yaml
https://cdn.jsdelivr.net/gh/jwqsir2-lang/free-nodes-pro@master/dist/singbox.json
```

说明：
- 节点名带国旗和国家代码前缀（如 `🇺🇸 US http-1.2.3.4:443|T`），只改名字，连接参数不动
- clash.yaml 已开启 geodata-mode 并配置 geox-url，GEOSITE/GEOIP 规则集可直接使用
- jk判定：ip-api.com 免费 API（hosting/mobile/proxy/reverse/as/isp）+ 反向 DNS 双重验证
- raw.githubusercontent.com 在部分网络下无法访问，故使用 jsDelivr 镜像

## 客户端说明

- **Clash Verge**：订阅 clash.yaml
- **GUI.for.SingBox**：订阅 singbox.json。注意：虽然订阅支持解析 YAML，但 clash.yaml 导入后测速全部为 0（Clash 的 TLS 写法转换到 sing-box 内核会丢 TLS），必须用 sing-box 原生格式的 singbox.json
- **sing-box 内核订阅**：需完整配置，顶层纯节点数组只能用于手动导入

## IP 类型检测

- jk：ISP 为住宅宽带运营商（如 Comcast、KDDI、Deutsche Telekom、Chunghwa），或反向 DNS 命中对应 PTR 特征（如 `resi.`、`hsd1.`、`cpe.`）
- 机房：命中 IDC / 托管商特征（如 SAKURA、Equinix、UK Dedicated Servers、阿里云），或 hosting 标记为真
- 移动：mobile 标记为真（移动运营商蜂窝 IP）
- 未知：无法判定（教育网、混合型线路等），保守归类不强行标记
- 只检测延迟测速存活的节点（ip-api 免费版限速 45 次/分钟）
