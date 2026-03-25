# costrict-skills-repo

Coding 相关 AI 扩展资源的一站式索引仓库。聚合 MCP Servers、Skills、Rules、Prompts，只收录编程开发相关资源。

## 资源类型

| 类型 | 说明 | 安装目标 |
|------|------|----------|
| MCP | Model Context Protocol 服务器 | `.claude/settings.json` |
| Skill | Claude Code Agent Skills | `~/.claude/skills/` |
| Rule | 编码规范 / AI 辅助规则 | `.claude/rules/` |
| Prompt | 开发者专用 Prompt | `.claude/rules/` |

## 分类

frontend, backend, fullstack, mobile, devops, database, testing, security, ai-ml, tooling, documentation

## 上游数据源

- **MCP**: [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) + [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH)
- **Skills**: [anthropics/skills](https://github.com/anthropics/skills) + [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills)
- **Rules**: [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) + [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized)
- **Prompts**: [prompts.chat](https://github.com/f/prompts.chat) + [wonderful-prompts](https://github.com/langgptai/wonderful-prompts)

## 安装 Skill

```bash
# 复制 skill 目录到 Claude Code skills
cp -r skill/ ~/.claude/skills/coding-hub/
```

## 使用

在 Claude Code 中：

```
/coding-hub search <关键词>        # 搜索资源
/coding-hub browse [分类]          # 浏览分类
/coding-hub recommend              # 基于当前项目推荐
/coding-hub install <资源名>       # 安装资源
```

## 数据同步

通过 GitHub Actions 每周自动从上游源同步，过滤 star > 10 的 coding 相关资源。

## 贡献

欢迎通过 PR 向 `catalog/<type>/curated.json` 添加精选资源。
