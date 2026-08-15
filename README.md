# WeChat AI Bot

这是一个面向单个微信账号的分层机器人项目：Windows VM 只运行微信和
WeChatFerry，Synology NAS 负责消息持久化、回复规则、AI 调用和发送队列。

## 当前包含

- `windows_bridge/`：带密钥认证、来源 IP 防火墙配合、事件持久化、发送白名单、
  限速和幂等保护的 WCF 桥接服务。
- `nas_backend/`：Docker 后端，使用 SQLite WAL 保存消息、游标和 outbox；支持私聊
  与群内 `@` 的显式白名单规则。
- 通用 Chat Completions HTTP AI 适配器，可连接明确支持该请求格式的服务。
- 持久化阅读/输入延迟、回复切片、重试和新消息到达时取消旧的待发送碎片。
- 离线单元测试，不需要微信、WCF 或外部 API。

## 默认安全状态

初始配置不会自动发送任何微信消息：

```text
AUTO_REPLY_ENABLED=false
DRY_RUN=true
DIRECT_REPLY_ENABLED=false
GROUP_REPLY_ENABLED=false
AI_PROVIDER=disabled
```

Windows 端默认也只允许接收者 `filehelper`。启用真实联系人或群聊必须同时修改
Windows 白名单和 NAS 白名单，因此单点误配置不会直接向外发送。

## 拓扑

```text
好友/测试群
    ↓
Windows VM: 微信 3.9.12.51 x64 + WCF 39.5.2.0
    ↓  HTTP 8787 / X-Bridge-Key / Windows 防火墙仅允许 NAS IP
NAS Docker: policy → AI → SQLite outbox → bridge /send
```

## 从这里开始

1. 按 [部署说明](docs/DEPLOYMENT.md) 部署 Windows bridge。
2. 保持只读/文件传输助手模式完成验证。
3. 部署 NAS backend，先以 `AI_PROVIDER=disabled` 运行并确认消息持续落库。
4. 配置 AI 后仍保持 `DRY_RUN=true` 做一次完整演练。
5. 只为一个测试联系人或测试群放行，最后才改为 `DRY_RUN=false`。

安全边界和恢复方式见 [安全说明](docs/SECURITY.md)，接口格式见
[桥接接口](docs/BRIDGE_API.md)。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python -m compileall -q windows_bridge nas_backend tests
```

## 重要限制

WeChatFerry 使用进程 Hook，原项目已经归档，并且依赖精确微信版本。它不是微信
官方 API，存在客户端升级、登录限制、账号风控和项目停止工作的风险。不要使用主号，
不要将 `8787`、`10086`、`10087` 或 RDP 暴露到公网。

