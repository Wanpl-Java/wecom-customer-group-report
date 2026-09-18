# 企微外部客户群 · 会话存档 → 月/季/年 HTML 报表

Linux 可部署服务：通过企业微信官方「会话内容存档」Finance SDK 拉取群消息，识别外部客户群后，按 **月度 / 季度 / 年度** 生成 HTML 报表（问题数、满意度、核心模块 Top3）。

> 不读取本机企微客户端。只使用官方会话存档 SDK 和客户联系 REST 接口。  
> 官方文档：[获取会话记录](https://developer.work.weixin.qq.com/document/path/91774)、[会话内容存档概述](https://developer.work.weixin.qq.com/document/path/91360)。

## 功能

1. **同步存档消息**（Linux x86_64 + `libWeWorkFinanceSdk_C.so`）
2. **解析外部客户群**（`roomid` + 客户群详情 API 补全群名）
3. **从聊天文本抽取支持问题**（状态 / 满意度 / 模块）
4. **按群批量输出 HTML**（索引 + 单群页）
5. **Web 控制台**（触发同步、出报表）
6. **演示模式**（无 SDK 时用样例消息跑通全流程）

## 报表指标（每个外部客户群一份）

- 问题数：本期相关 / 新增 / 完结 / 完结率 / 遗留 / 超 SLA
- 满意度：均值、1–5 分布、样本量
- 核心关注模块 Top3
- 未闭环清单 + 明细

输出目录：`output/customer_groups_<周期>_<时间戳>/`

- `index.html`：全部客户群一览
- `<群名>.html`：单群报告
- `bundle.json`：机器可读汇总

---

## 部署文档

### 1. 环境要求

| 项 | 要求 |
|----|------|
| 操作系统 | Linux x86_64（官方 SDK 仅提供 Linux `.so`；Windows 只能跑演示模式） |
| Python | 3.11+（源码部署） |
| Docker | 24+ 与 Compose v2（容器部署，可选） |
| 出网 | 服务器能访问 `qyapi.weixin.qq.com`，以及 SDK 拉档所需地址 |
| 企微 | 已开通「会话内容存档」，并配置公钥、可信 IP、存档成员 |

演示模式不需要 SDK、私钥和企业 Secret。

### 2. 企微后台准备（生产必做）

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/) → **管理工具** → **会话内容存档**。
2. 在本机生成 RSA 密钥对（2048 位即可）：

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

3. 把 `keys/public.pem` 的内容粘贴到后台「消息加密公钥」。**私钥只留在服务器**，不要提交 Git。
4. 记录：
   - 企业 ID（`ww...`）
   - 会话存档 **Secret**
5. 把部署机器的出口 IP 加入会话存档「可信 IP」。
6. 确认需要出报表的支持同事已在「开启存档的成员」里，客户群消息才会被存档。
7. （可选）若要自动补全外部群名，再准备「客户联系」应用 Secret，并给应用「客户联系」权限。没有这项时，报表群名回退为 `群:<roomid>`，不影响问题统计。

### 3. 下载官方 SDK

从企微开发者中心「会话内容存档」下载 **Linux** SDK，把下面文件放到仓库 `lib/`：

```text
lib/libWeWorkFinanceSdk_C.so
```

仓库不附带该二进制。确认架构：

```bash
file lib/libWeWorkFinanceSdk_C.so
# 期望：ELF 64-bit LSB shared object, x86-64
ldd lib/libWeWorkFinanceSdk_C.so
```

### 4. 获取代码

```bash
git clone https://github.com/Wanpl-Java/wecom-customer-group-report.git
cd wecom-customer-group-report
```

### 5. 填写配置

```bash
cp config.example.yaml config.yaml
```

生产最小配置：

```yaml
mode: sdk          # demo | sdk | json

server:
  host: "0.0.0.0"
  port: 8088

wecom:
  corp_id: "wwxxxxxxxx"
  archive_secret: "会话存档 Secret"
  contact_secret: ""                 # 可选
  private_key_path: "./keys/private.pem"
  room_allowlist: []                 # 空=全部外部群；可填 roomid 白名单
  external_only: true

sdk:
  library_path: "./lib/libWeWorkFinanceSdk_C.so"
  batch_size: 200
  timeout_seconds: 10
  proxy: ""                          # 需要 HTTP 代理时填写
  proxy_password: ""

analyze:
  staff_userids: []                  # 员工 userid；空则非 wm/wo 开头视为员工
  default_product: "JS"
  sla_hours: 48
```

也可用环境变量覆盖（容器场景同样有效）：

| 变量 | 作用 |
|------|------|
| `WECOM_REPORT_CONFIG` | 配置文件路径，默认 `config.yaml` |
| `WECOM_MODE` | 覆盖 `mode` |
| `WECOM_CORP_ID` | 覆盖企业 ID |
| `WECOM_ARCHIVE_SECRET` | 覆盖存档 Secret |
| `WECOM_CONTACT_SECRET` | 覆盖客户联系 Secret |

`config.yaml`、`keys/*.pem`、`lib/*.so` 已在 `.gitignore` 中，不要提交。

### 6. 方式 A：Docker 部署（推荐）

宿主机需已放好 `config.yaml`、`keys/private.pem`、`lib/libWeWorkFinanceSdk_C.so`。

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f wecom-report
```

控制台：`http://<服务器IP>:8088`

容器内同步与出报表：

```bash
# 增量拉取会话存档
docker compose exec wecom-report python -m app.main sync

# 月报 / 季报 / 年报
docker compose exec wecom-report python -m app.main report --period month --year 2026 --month 9
docker compose exec wecom-report python -m app.main report --period quarter --year 2026 --quarter 3
docker compose exec wecom-report python -m app.main report --period year --year 2026

# 库统计
docker compose exec wecom-report python -m app.main stats
```

HTML 落在宿主机 `./output/`（已挂载）。索引页也可从控制台「生成 HTML」后的链接打开。

停止与更新：

```bash
docker compose down
git pull
docker compose up -d --build
```

`data/`、`output/` 在宿主机，重建容器不会丢已同步消息和报表。

### 7. 方式 B：源码部署

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 先拉消息，再出报表，最后开 Web
python -m app.main sync
python -m app.main report --period month
python -m app.main serve --host 0.0.0.0 --port 8088
```

用 systemd 常驻 Web（路径按实际安装目录改）：

```ini
# /etc/systemd/system/wecom-report.service
[Unit]
Description=WeCom customer group report
After=network.target

[Service]
WorkingDirectory=/opt/wecom-customer-group-report
Environment=WECOM_REPORT_CONFIG=/opt/wecom-customer-group-report/config.yaml
ExecStart=/opt/wecom-customer-group-report/.venv/bin/python -m app.main serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wecom-report
```

定时同步与出月报（每天 02:10 同步，每月 1 日 03:10 出上月报）示例：

```cron
10 2 * * * cd /opt/wecom-customer-group-report && .venv/bin/python -m app.main sync >> /var/log/wecom-report-sync.log 2>&1
10 3 1 * * cd /opt/wecom-customer-group-report && .venv/bin/python -m app.main report --period month >> /var/log/wecom-report-html.log 2>&1
```

季度、年度同理，把 `--period` 换成 `quarter` / `year`。

### 8. 验收

```bash
python -m app.main stats
# 期望 messages > 0，cursor_seq 持续增长
```

浏览器打开最新 `output/customer_groups_*/index.html`，确认：

- 每个外部客户群一行
- 问题数、满意度、模块 Top3 有数
- 点进单群页能看到明细和遗留

演示环境（任意系统，不连企微）：

```bash
python -m app.main demo --period month --year 2026 --month 9
```

### 9. CLI 一览

```text
python -m app.main sync [--json path]
python -m app.main report --period month|quarter|year|days [--year N] [--month N] [--quarter N] [--days N]
python -m app.main demo --period month --year 2026 --month 9
python -m app.main stats
python -m app.main serve [--host 0.0.0.0] [--port 8088]
python -m app.main --config /path/config.yaml <子命令>
```

`mode` 含义：

| mode | 行为 |
|------|------|
| `sdk` | 调官方 Finance SDK 增量拉档并解密 |
| `demo` | 导入 `data/sample_messages.json` |
| `json` | 导入 `data/messages.json`（也可用 `sync --json`） |

### 10. 故障排查

| 现象 | 处理 |
|------|------|
| `未找到会话存档 SDK` | 确认 `lib/libWeWorkFinanceSdk_C.so` 存在，且 `sdk.library_path` 正确 |
| `Init 失败` | 核对 `corp_id`、`archive_secret`，以及 SDK 与企业是否匹配 |
| `GetChatData 失败` | 检查可信 IP、Secret、服务器出网；公司代理时填 `sdk.proxy` |
| 解密失败 / 私钥错误 | 后台公钥必须与 `keys/private.pem` 成对；换公钥后历史消息无法解密 |
| 同步成功但群数为 0 | `external_only: true` 会跳过内部群；确认 msgid 带 `_external`，或暂时关掉过滤做核对 |
| 群名是 `群:wr...` | 未配 `contact_secret`，或该 roomid 不是客户群 API 能查到的外部群 |
| Docker 启动后配置不生效 | `config.yaml` 必须在 compose 同级目录，容器读的是 `/app/config.yaml` |
| Windows 上 `mode: sdk` 失败 | 预期行为。Windows 只跑 `demo` / `json` |

### 11. 安全

- 私钥、Secret、`config.yaml` 只放服务器或密钥管理系统
- 报表含客户沟通摘要，按内部权限分发，不要挂到公网无鉴权目录
- Web 端口 `8088` 建议只对内网或反向代理开放，前面加登录或 IP 白名单

---

## 配置项说明

| 项 | 说明 |
|----|------|
| `wecom.corp_id` | 企业 ID |
| `wecom.archive_secret` | 会话存档 Secret |
| `wecom.contact_secret` | 客户联系 Secret（可选，补外部群名） |
| `wecom.private_key_path` | 存档 RSA 私钥 PEM |
| `wecom.room_allowlist` | 只同步这些 roomid；空为全部 |
| `wecom.external_only` | 只保留外部客户群消息 |
| `sdk.library_path` | `lib/libWeWorkFinanceSdk_C.so` |
| `analyze.staff_userids` | 员工 userid，用于区分客户提问和员工回复 |
| `analyze.sla_hours` | 遗留超期阈值，默认 48 小时 |

## 目录

```text
app/                 # 应用代码
lib/                 # 放置官方 .so（勿提交）
keys/                # 放置 RSA 私钥（勿提交）
data/                # SQLite + 演示 JSON
output/              # HTML 报表
config.example.yaml
Dockerfile
docker-compose.yml
```
