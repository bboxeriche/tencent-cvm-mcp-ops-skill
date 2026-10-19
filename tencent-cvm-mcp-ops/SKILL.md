---
name: tencent-cvm-mcp-ops
description: 通过 tencent-cvm MCP 或腾讯云官方 Python SDK 管理 CVM、查询账单与代金券、询价和准备云服务器购买。用于腾讯云 CVM 运维、凭据接入、MCP 排障及代金券使用核对。
---

# Tencent CVM MCP Ops

使用 `tencent-cvm` MCP 处理已获授权的 CVM 查询与运维；其工具无法表达完整请求时使用腾讯云官方 SDK。创建实例模板见 [references/run_instances_template.py](references/run_instances_template.py)。

## 接入

- MCP 服务：`uvx --with "mcp<2.0.0" mcp-server-cvm==0.1.12`。这是兼容基线，不表示更新版本必然不兼容。
- Codex：在 `~/.codex/config.toml` 的 `[mcp_servers.tencent-cvm]` 设置 `command`、`args`，用 `env_vars` 传递凭据环境变量。
- WorkBuddy：在 `~/.workbuddy/mcp.json` 的 `mcpServers` 中配置同名服务，按客户端提示启用或信任。
- 使用 `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` 和目标 `TENCENTCLOUD_REGION`；SDK 模板还支持临时凭据 `TENCENTCLOUD_TOKEN`。优先使用所需权限范围内的子账号。
- 通过本地凭据配置或环境变量读取密钥，不把真实密钥写进模板、对话回复、Git 或日志。
- 服务启动、协议握手、只读 API 成功、实际资源操作成功是不同证据。先用一次已获授权的只读查询核对身份、地域和权限，不把无 Traceback 当作已连通云端。

## 操作流程

查询时确认目标账号与地域，根据工具实际 schema 调用。开关机、重启和变更配置使用用户已授权的实例与范围；保留 API RequestId 供核对。

涉及购买时：

1. 查询可用地域、可用区、镜像、机型与 VPC/子网，核对实际存在的资源。空列表可能是账号尚未创建资源。
2. 用 `InquiryPriceRunInstances` 或官方询价 API 核对相同规格、数量、磁盘与周期的当前价格。
3. 涉及代金券时核对券种、余额、适用产品、计费方式、购买时长、有效期与叠加规则。不要仅凭余额推断可用性。
4. 在创建网络、安全组或更改入站规则前，明确用户要求的范围；不要把公网开放 SSH 作为默认步骤。
5. 创建实例先预检 `DryRun=True`。用户明确确认配置、数量、周期、总价、拟用代金券和预期自付金额后，才可正式提交。CLI 的确认开关不能代替用户授权。
6. 用 `DescribeInstances` 检查创建后的状态；用订单/账单和券余额变化核对实际扣款、扣券。RequestId 或实例 ID 返回不等同于资源已就绪。

请求结果不明时，不自动重复创建。保留同一订单的 `ClientToken` 并核对实例、订单和账单后处理。

## 0.1.12 的限制与 SDK 绕过

已检查 [`mcp-server-cvm==0.1.12`](https://pypi.org/project/mcp-server-cvm/0.1.12/) 的发布包：

- `RunInstances` 的 schema 和实现没有 `InstanceChargePrepaid`。因此包年包月 `PREPAID` 请求无法通过这个工具完整提交；这不代表所有按量计费创建必然失败。
- 同一工具未暴露 `DryRun`，不要用它进行试探性的创建。创建使用本技能的 SDK 模板。
- `InquiryPriceRunInstances` 暴露了 `InstanceChargePrepaid`，可用于包年包月询价。
- 工具清单有 VPC/子网查询和安全组创建，没有 VPC/子网创建工具。需要新网络时，在已授权的范围内通过控制台或官方 VPC SDK 完成。

若服务报 `Connection closed`，先检查 stderr 中的真实错误和依赖版本；原始包记录过 `mcp` API 兼容问题。使用兼容基线重试协议握手，不能将所有连接错误都归因于 SDK 版本。

SDK 模板读取 [references/run_instances_request.example.json](references/run_instances_request.example.json) 同结构的本地 JSON 文件。先填写通过查询、询价确认的值，不保留占位符。依赖见 [requirements.txt](requirements.txt)。

```bash
python references/run_instances_template.py dryrun --request-json request.local.json
# 获得明确购买授权后，才使用：
python references/run_instances_template.py real --request-json request.local.json --confirm-purchase
```

模板使用 `from_json_string` 构造 SDK 嵌套模型。不要直接把字典赋给 `req.Placement`、`req.SystemDisk` 或 `req.InstanceChargePrepaid`，否则 SDK 序列化可能失败。`real` 会重新预检相同参数；预检异常或响应缺少 RequestId 都会阻止正式提交。

## Billing 与代金券

Billing 需要另装 `tencentcloud-sdk-python-billing`。中国站与国际站的 endpoint、可用 Region 和币种可能不同，按账号所属站点与当前接口文档选择，不机械沿用 CVM 地域。

- `DescribeVoucherInfo.Offset` 是从 **1** 开始的页号，不能照搬 CVM 列表中从 0 开始的偏移量。
- 先读取响应的 `Unit` 与币种。仅当单位是 `micro` 时，使用 `Decimal(value) / Decimal("100000000")` 换算到元或相应基础货币单位。例如 `30000000000` micro 对应 300，不能对所有 Billing 字段套用同一单位。
- 不承诺单笔订单永远只能用一张券。通用规则、特定大客户规则、现金券与活动券可能不同，以该账号和该笔订单的结算规则为准。
- 不承诺在有效期内下单就能覆盖任意购买周期；检查券的购买时长限制、适用产品、支付场景和结算时的有效性。
- 本模板未指定 `VoucherIds`，不保证选择某一张券或零自付。只有在用户理解且确认实际扣款安排后才能提交。

## 证据与参考

本技能包含源码核对与离线测试，不据此宣称账号可访问、代金券必然可用或购买已完成。操作时记录所用版本和实际 API 结果。

- [腾讯云 RunInstances](https://cloud.tencent.com/document/api/213/15730)
- [RunInstances 的 DryRun 与 ClientToken 参数](https://intl.cloud.tencent.com/document/product/213/33237)
- [DescribeVoucherInfo：分页与金额单位](https://intl.cloud.tencent.com/zh/document/api/555/45893)
- [代金券使用限制](https://intl.cloud.tencent.com/zh/document/product/555/10870)
- [大客户预付费订单多张代金券规则](https://cloud.tencent.com/document/product/555/12640)
- [腾讯云官方 Python SDK](https://github.com/TencentCloud/tencentcloud-sdk-python)
