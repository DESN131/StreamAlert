# Stream-Alert

使用 Flask 接收录播姬 Webhook v2，并通过 Telegram Bot 发送提醒消息。

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置环境变量

复制 `.env.example` 为 `.env`，修改以下必填项：

- `TELEGRAM_BOT_TOKEN`：你的 Telegram Bot Token
- `TELEGRAM_CHAT_ID`：接收消息的 chat id（个人、群组或频道）

可选项：

- `WEBHOOK_PATH`：Webhook 路径，默认 `/webhook`
- `FLASK_HOST`/`FLASK_PORT`：监听地址和端口

## 3. 启动服务

### PowerShell

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $name, $value = $_ -split '=', 2
  [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}

python app.py
```

启动后健康检查：

- `GET /health`

Webhook 接口：

- `POST {WEBHOOK_PATH}`（默认 `POST /webhook`）

## Docker 部署

1. 确保 `.env` 已按 `.env.example` 配置好。
2. 构建并启动：

```bash
docker compose up -d --build
```

3. 查看日志：

```bash
docker compose logs -f
```

4. 停止服务：

```bash
docker compose down
```

## 4. 在录播姬中配置

在录播姬 Webhook 设置中填入：

```text
http://你的服务器IP或域名:5000/webhook
```

如果你修改了 `WEBHOOK_PATH` 或端口，请同步修改 URL。

## 5. 行为说明

- 支持 `SessionStarted`、`FileOpening`、`FileClosed`、`SessionEnded`、`StreamStarted`、`StreamEnded`
- 收到未知事件类型也会通知（显示为未知事件）
- 使用 `EventId` 做去重，避免重试造成重复推送
- Telegram 发送失败会返回非 2xx，录播姬可按其机制重试
