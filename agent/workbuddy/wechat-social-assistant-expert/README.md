# 微信社交助手 WorkBuddy 专家包

此包将项目的 WorkBuddy 连接器配置为一个面向用户的专家入口：**微信社交助手**。它使用本地可见聊天记录提供关系回顾、联系人简报与跟进草稿，并保持项目既有的本地优先和人工审核边界。

市场职称为「微信社交助手」，专家花名为「海纳·社交专家」。原专家 ID 为 `oe_9bb6e718bd1a6318`，重新提交应更新该资产。

## 包含内容

- `agents/wechat-social-assistant.md`：专家角色、工具使用边界和首轮交互规则。
- `skills/`：关系回顾与跟进、联系人背景与沟通草稿、采集与资料整理三个技能。
- `avatars/wechat-social-assistant.png`：512×512 市场头像。
- `.codebuddy-plugin/plugin.json`：WorkBuddy 专家市场配置。

## 连接器依赖

`plugin.json` 当前声明的连接器 ID 为 `oc_a3f7d4a2da76c7cd`，对应开放平台中“微信社交助手”的当前审核版本。该 ID 必须在连接器重新创建或发布新资产后复核；专家依赖应始终指向已上架的实际连接器 ID。

连接器处于审核中时，专家包可以提交审核，但用户无法完成实际连接和调用。待连接器通过后，WorkBuddy 会在用户召唤专家前引导其连接。

## 打包与提交

从 `agent/workbuddy/wechat-social-assistant-expert/` 目录打包，必须保留隐藏目录 `.codebuddy-plugin/`。提交前运行：

```bash
python3 -m unittest tests.test_workbuddy_expert_assets
```
