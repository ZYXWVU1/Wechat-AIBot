# 安全说明

## 网络边界

- 路由器不得转发 TCP 8787、10086、10087 或 RDP。
- Windows 防火墙的 8787 规则只允许 NAS 的固定 IPv4，网络配置文件使用 Private。
- WCF 的 10086/10087 只由 Windows 本机进程使用。
- NAS backend 不发布任何容器端口；它只主动访问 Windows bridge 和 AI 服务。

## 密钥

- `WCF_BRIDGE_KEY` 至少 32 个随机字符，Windows 与 NAS 使用同一个值。
- Windows 保存为当前用户环境变量；NAS 保存于未提交的 `.env`。
- `.env` 不应出现在截图、日志、备份分享或 Git 中。
- 临时测试容器如果把密钥写进 Command，测试后删除容器并轮换密钥。

轮换方式：停止两端，生成新的 Windows 用户环境变量，更新 NAS `.env`，再依次启动
Windows bridge 和 NAS backend。

## 双层白名单

真实接收者必须同时存在于：

1. Windows `WCF_ALLOWED_RECEIVERS`；
2. NAS 的 `ALLOWED_DIRECT_SENDERS` 或 `ALLOWED_GROUPS`。

桥接层还要求每次发送包含唯一 `request_id`，相同 ID 重试不会重复发送；同一接收者
默认至少间隔两秒。

## 数据

- Windows bridge 默认保留 7 天事件用于 NAS 断线后的重放。
- NAS SQLite 保存对话内容和 outbox。Docker 命名卷为 `wechat-ai-data`。
- 不把数据库、聊天内容或 wxid 上传到公开问题、代码仓库或截图。
- 备份数据库前停止 NAS 项目，避免复制一个正在写入的 SQLite 文件。

## 账号与披露

- 使用非重要测试账号；Hook 和旧版客户端可能触发风控或失效。
- 测试群成员应知道账号由 AI 辅助或自动回复。
- 默认 persona 和 `DISCLOSURE_PREFIX` 会保留 AI 身份提示；不建议删除。
- 不使用机器人冒充具体真人，不编造真人经历或关系。

## 紧急停止

按风险从低到高：

1. NAS `.env` 设置 `AUTO_REPLY_ENABLED=false` 并重启项目；
2. 停止 NAS 项目；
3. Windows bridge 窗口按 `Ctrl+C`；
4. 在 VMM 中关闭 Windows VM；
5. 回滚最近的已知良好 VMM 快照。

