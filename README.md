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

---

# English Translation

This is a layered bot project for a single WeChat account: the Windows VM runs only WeChat
and WeChatFerry, while the Synology NAS handles message persistence, reply rules, AI calls,
and the sending queue.

## Included

- `windows_bridge/`: a WCF bridge service with key-based authentication, source-IP firewall
  integration, event persistence, a sending allowlist, rate limiting, and idempotency protection.
- `nas_backend/`: a Docker backend that uses SQLite WAL to store messages, cursors, and the
  outbox; it supports explicit allowlist rules for direct messages and `@` mentions in groups.
- A generic Chat Completions HTTP AI adapter that can connect to services supporting this request format.
- Persistent reading/input delays, reply chunking, retries, and cancellation of old pending reply
  chunks when new messages arrive.
- Offline unit tests that do not require WeChat, WCF, or an external API.

## Default Safety State

The initial configuration does not automatically send any WeChat messages:

```text
AUTO_REPLY_ENABLED=false
DRY_RUN=true
DIRECT_REPLY_ENABLED=false
GROUP_REPLY_ENABLED=false
AI_PROVIDER=disabled
```

The Windows side also only allows `filehelper` as a recipient by default. Enabling real contacts
or group chats requires changing both the Windows allowlist and the NAS allowlist, so a single
misconfiguration cannot directly send messages externally.

## Architecture

```text
Friend/test group
    ↓
Windows VM: WeChat 3.9.12.51 x64 + WCF 39.5.2.0
    ↓  HTTP 8787 / X-Bridge-Key / Windows firewall allows NAS IP only
NAS Docker: policy → AI → SQLite outbox → bridge /send
```

## Getting Started

1. Deploy the Windows bridge according to the [deployment guide](docs/DEPLOYMENT.md).
2. Complete verification while keeping the read-only/File Transfer Assistant mode enabled.
3. Deploy the NAS backend with `AI_PROVIDER=disabled` first, and confirm that messages continue
   to be persisted.
4. After configuring AI, keep `DRY_RUN=true` for a complete rehearsal.
5. Allow only one test contact or test group, and change to `DRY_RUN=false` only at the end.

See the [security guide](docs/SECURITY.md) for security boundaries and recovery procedures, and
the [bridge API documentation](docs/BRIDGE_API.md) for the interface format.

## Local Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall -q windows_bridge nas_backend tests
```

## Important Limitations

WeChatFerry uses process hooking. The original project has been archived and depends on an exact
WeChat version. It is not an official WeChat API, and there are risks related to client upgrades,
login restrictions, account risk controls, and the project becoming unusable. Do not use your main
account, and do not expose `8787`, `10086`, `10087`, or RDP to the public internet.

