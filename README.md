# Tencent CVM MCP Ops Skill

An agent skill for Tencent Cloud CVM operations, billing and voucher workflows, with an official Python SDK fallback for prepaid instance creation.

面向 **Codex、WorkBuddy 及支持 Agent Skills 的客户端**，整理腾讯云 CVM 查询、运维、询价与代金券使用流程。本仓库提供技能说明和 SDK 模板；MCP 服务来自独立的上游项目 [`mcp-server-cvm`](https://pypi.org/project/mcp-server-cvm/0.1.12/)，不是腾讯云官方技能。

## 安装技能

```bash
git clone https://github.com/bboxeriche/tencent-cvm-mcp-ops-skill.git
cd tencent-cvm-mcp-ops-skill
```

选择你的客户端，将整个 `tencent-cvm-mcp-ops/` 目录复制到技能目录：

| 客户端 | 用户级目录 |
| --- | --- |
| Codex | `~/.agents/skills/`（也兼容本机已有的 `~/.codex/skills/` 安装方式） |
| WorkBuddy | `~/.workbuddy/skills/` |

例如，在全新 Codex 环境中安装：

```bash
mkdir -p ~/.agents/skills
cp -R tencent-cvm-mcp-ops ~/.agents/skills/
```

已有同名技能时先检查差异，避免覆盖自定义内容。Codex 会自动发现技能；如果没有出现，重启客户端。详见 [OpenAI 官方技能说明](https://learn.chatgpt.com/docs/build-skills)。

安装后可说：`使用 tencent-cvm-mcp-ops 查一下我的腾讯云服务器。`

**技能安装与腾讯云连接分别配置。** 查询云资源仍需要可用的 MCP 服务和腾讯云 API 凭据。

## 配置 MCP

先安装 [uv](https://docs.astral.sh/uv/)，确保客户端能找到 `uvx`。本仓库以 `mcp-server-cvm==0.1.12` 和 `mcp<2.0.0` 为兼容基线；升级上游时重新检查协议和工具 schema。

### Codex

在 `~/.codex/config.toml` 中合并以下配置：

```toml
[mcp_servers.tencent-cvm]
command = "uvx"
args = ["--with", "mcp<2.0.0", "mcp-server-cvm==0.1.12"]
env_vars = ["TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY"]

[mcp_servers.tencent-cvm.env]
TENCENTCLOUD_REGION = "ap-guangzhou"
```

在启动 Codex 的环境中提供 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`。桌面客户端如果没有继承终端环境，应通过客户端支持的本地凭据配置提供；配置文件不要提交到仓库。重启后用 `codex mcp list` 检查注册状态，再进行一次只读查询验证权限。MCP 的配置格式见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

### WorkBuddy

在 `~/.workbuddy/mcp.json` 的 `mcpServers` 中合并以下条目，按本地配置方式填写占位符：

```json
{
  "mcpServers": {
    "tencent-cvm": {
      "command": "uvx",
      "args": ["--with", "mcp<2.0.0", "mcp-server-cvm==0.1.12"],
      "env": {
        "TENCENTCLOUD_SECRET_ID": "<YOUR_SECRET_ID>",
        "TENCENTCLOUD_SECRET_KEY": "<YOUR_SECRET_KEY>",
        "TENCENTCLOUD_REGION": "ap-guangzhou"
      },
      "disabled": false
    }
  }
}
```

按照当前客户端的信任/启用提示激活连接器。凭据从腾讯云 CAM 获取，优先使用权限与实际操作相匹配的子账号。

## SDK 创建实例模板

`mcp-server-cvm==0.1.12` 的 `RunInstances` 工具未暴露或传递 `InstanceChargePrepaid`，无法完整表达包年包月请求。本仓库提供官方 SDK 模板绕过该限制，详见 [技能说明](tencent-cvm-mcp-ops/SKILL.md)。

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r tencent-cvm-mcp-ops/requirements.txt
cp tencent-cvm-mcp-ops/references/run_instances_request.example.json request.local.json
```

编辑 `request.local.json`，填写通过只读查询和询价确认的地域、镜像、机型、网络和购买周期。用环境变量提供 `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`、`TENCENTCLOUD_REGION`；临时凭据还可提供 `TENCENTCLOUD_TOKEN`。

预检只发出 `DryRun=True`：

```bash
.venv/bin/python tencent-cvm-mcp-ops/references/run_instances_template.py dryrun --request-json request.local.json
```

正式执行会产生实际费用。只有在用户确认了配置、数量、周期、价格与实际自付金额后，才运行：

```bash
.venv/bin/python tencent-cvm-mcp-ops/references/run_instances_template.py real --request-json request.local.json --confirm-purchase
```

`real` 会先对同一份参数重新预检，成功后才提交一次创建请求。它要求独立的 `ClientToken`；同一笔请求的结果不明时保留原 token，先核对实例和订单，避免重复购买。未知运行模式、缺少确认参数、预检失败或没有 RequestId 都会停止执行。

模板不代替实时询价，也不指定代金券或保证零自付。代金券需要核对适用产品、账户、订单类型、购买时长、有效期、叠加规则及实际结算结果。

## 验证与贡献

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试使用真实 SDK 模型和模拟客户端，检查请求序列化、预检与正式执行的边界；不连接腾讯云、不创建资源。GitHub Actions 运行相同检查。

发布前核对了上游 0.1.12 的源码和腾讯云官方接口说明，并以 `mcp-server-cvm==0.1.12`、`mcp==1.30.0` 完成本地协议握手和 34 项工具的 schema 查询；该检查不传入真实凭据、不调用云端工具。未提供真实账号的云端查询、购买、扣券或跨客户端端到端验证。欢迎用 issue/PR 提交脱敏的版本信息、错误码和可复现步骤，不要上传密钥、完整账单或账号配置。

## 来源与许可

本仓库由初始 `tencent-cvm-mcp-ops-skill.zip` 技能包整理而来，公开版补充了 Codex 接入说明，并修正模板的参数处理、SDK 嵌套模型序列化及密钥读取方式。

项目采用 [MIT License](LICENSE)。上游 MCP 服务和腾讯云 SDK 保持各自许可证；本仓库不包含它们的实现。
