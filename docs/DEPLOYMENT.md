# 部署说明

下面假设 Windows VM 和 NAS 已经能够通过局域网互通，并且 Windows 防火墙的
TCP 8787 入站规则只允许 NAS IPv4。

## 1. Windows VM

### 1.1 准备目录

将整个 `windows_bridge` 目录复制到 Windows VM，例如：

```text
C:\WCF-Bridge
```

不要与之前的临时 `C:\WCF-Test` 混用。先退出所有临时 WCF Python 进程，并完全
退出微信。

### 1.2 安装

在 Windows PowerShell 中：

```powershell
cd C:\WCF-Bridge
.\setup_bridge.ps1
```

脚本使用 Python 3.10 x64 创建 `.venv`，固定安装 WCF `39.5.2.0`，并在缺少密钥
时生成新的 Windows 用户环境变量 `WCF_BRIDGE_KEY`。脚本不会打印密钥。

### 1.3 设置桥接参数

将 IP 换成 Windows VM 的固定局域网 IPv4：

```powershell
[Environment]::SetEnvironmentVariable("WCF_BRIDGE_HOST", "192.168.1.120", "User")
[Environment]::SetEnvironmentVariable("WCF_BRIDGE_PORT", "8787", "User")
[Environment]::SetEnvironmentVariable("WCF_ALLOWED_RECEIVERS", "filehelper", "User")
```

关闭并重新打开 PowerShell，然后启动：

```powershell
cd C:\WCF-Bridge
.\run_bridge.ps1
```

不要增加 `--reload`，也不要运行多个 worker。微信会由 WCF 启动，必要时扫码。

### 1.4 健康检查

另开 PowerShell：

```powershell
$taskBridgeKey = [Environment]::GetEnvironmentVariable("WCF_BRIDGE_KEY", "User")
$taskVmIp = [Environment]::GetEnvironmentVariable("WCF_BRIDGE_HOST", "User")

Invoke-RestMethod `
  -Uri "http://${taskVmIp}:8787/health" `
  -Headers @{"X-Bridge-Key" = $taskBridgeKey}
```

必须看到 `wechat_login=True` 和 `receiving=True`。

## 2. NAS backend

### 2.1 上传目录

通过 File Station 将 `nas_backend` 上传到例如：

```text
/volume1/docker/wechat-ai
```

在该目录把 `.env.example` 复制为 `.env`。不要把 `.env` 上传到公开仓库。

### 2.2 配置 `.env`

必须修改：

```text
BRIDGE_URL=http://WINDOWS_VM_IP:8787
BRIDGE_KEY=与Windows用户环境变量完全相同的密钥
```

Windows 上查看密钥的命令是：

```powershell
[Environment]::GetEnvironmentVariable("WCF_BRIDGE_KEY", "User")
```

只在本地复制，不要发到聊天、截图或日志。初次部署保留：

```text
AUTO_REPLY_ENABLED=false
DRY_RUN=true
AI_PROVIDER=disabled
```

可以编辑 `config/persona.txt`，但必须保留 AI 身份披露和隐私约束。

### 2.3 用 Container Manager 建立项目

在 DSM：

```text
Container Manager → Project → Create
```

- Project name：`wechat-ai`
- Path：选择 `/volume1/docker/wechat-ai`
- Compose source：选择或粘贴该目录的 `compose.yaml`
- 不建立 Web Portal，不添加端口映射。

构建并启动后查看容器日志。成功应出现：

```text
Backend started; auto_reply=False dry_run=True AI=disabled
```

此时后端只会读取并保存消息，不会调用 AI，也不会发送。

## 3. 配置 AI，但保持演练模式

所选服务必须明确提供 Chat Completions 兼容接口。修改 `.env`：

```text
AI_PROVIDER=http_chat_completions
AI_CHAT_COMPLETIONS_URL=https://provider.example/v1/chat/completions
AI_API_KEY=你的API密钥
AI_MODEL=服务商提供的模型ID
AUTO_REPLY_ENABLED=true
DRY_RUN=true
```

不要将 API Key 放进 `compose.yaml`。重新构建/启动项目，使环境变量生效。

## 4. 只启用一个测试对象

### 私聊

NAS `.env`：

```text
DIRECT_REPLY_ENABLED=true
ALLOWED_DIRECT_SENDERS=wxid_测试联系人
```

Windows 用户环境变量必须包含同一接收者：

```powershell
[Environment]::SetEnvironmentVariable(
  "WCF_ALLOWED_RECEIVERS",
  "filehelper,wxid_测试联系人",
  "User"
)
```

### 群聊

NAS `.env`：

```text
GROUP_REPLY_ENABLED=true
ALLOWED_GROUPS=测试群roomid@chatroom
```

Windows：

```powershell
[Environment]::SetEnvironmentVariable(
  "WCF_ALLOWED_RECEIVERS",
  "filehelper,测试群roomid@chatroom",
  "User"
)
```

重启 Windows bridge 和 NAS 项目。群聊只有同时满足“群在白名单”和“明确 @ 机器人”
才会进入 AI 回复流程。

## 5. 开启真实发送

先以 `DRY_RUN=true` 观察一轮完整日志，确认没有非测试对象进入规则。然后仅修改：

```text
DRY_RUN=false
```

重新启动 NAS 项目。第一轮只在已知情的测试群中进行。

## 6. 快照

建议在以下节点创建 VMM 快照：

```text
08-new-bridge-filehelper-only
09-nas-backend-dry-run
10-single-test-target-enabled
```

