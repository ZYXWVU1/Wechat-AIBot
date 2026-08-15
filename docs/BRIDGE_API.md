# Bridge API

所有请求必须携带：

```text
X-Bridge-Key: <shared secret>
```

接口只应位于可信局域网，并由 Windows 防火墙限制为 NAS IP。

## `GET /health`

返回微信登录、消息接收和白名单数量，不返回密钥或 wxid。

## `GET /events?after=<event_id>&limit=100`

按递增 `event_id` 返回已持久化的入站消息。NAS 在 SQLite 保存游标；断线重连后从
最后成功处理的位置继续。桥接事件表默认保留 7 天。

主要字段：

- `wechat_message_id`：微信消息 ID，作为二次去重键。
- `is_group`、`at_me`、`is_text`：策略判断字段。
- `sender`、`roomid`、`receiver`：路由字段。
- `content`：UTF-8 文本。

## `POST /send`

请求：

```json
{
  "request_id": "outbox-unique-id",
  "receiver": "filehelper",
  "content": "Bridge test",
  "at_users": ""
}
```

约束：

- `receiver` 必须在 Windows `WCF_ALLOWED_RECEIVERS`。
- `content` 去除首尾空白后为 1–500 个字符。
- 同一 `request_id` 和相同内容会返回已有结果，不会再次发送。
- 同一 `request_id` 搭配不同内容返回 HTTP 409。
- 超过发送频率返回 HTTP 429。
- WCF 非零结果返回 HTTP 502。

