import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

type Lang = 'en' | 'zh'

interface I18nContextValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: string) => string
}

const translations: Record<string, Record<Lang, string>> = {
  'nav.home': { en: 'Home', zh: '首页' },
  'nav.browse': { en: 'Browse', zh: '浏览' },
  'nav.about': { en: 'About', zh: '关于' },
  'hero.title': { en: 'Everything AI Coding', zh: 'Everything AI Coding' },
  'hero.subtitle': { en: 'Discover 4000+ curated dev resources', zh: '发现 4000+ 精选开发资源' },
  'hero.search': { en: 'Search resources...', zh: '搜索资源...' },
  'stats.mcp': { en: 'MCP Servers', zh: 'MCP 服务' },
  'stats.skill': { en: 'Skills', zh: '技能' },
  'stats.rule': { en: 'Rules', zh: '规则' },
  'stats.prompt': { en: 'Prompts', zh: '提示词' },
  'featured.title': { en: 'Featured Picks', zh: '精选推荐' },
  'trending.title': { en: 'Trending', zh: '热门趋势' },
  'browse.all': { en: 'All', zh: '全部' },
  'browse.sort.score': { en: 'Score', zh: '评分' },
  'browse.sort.stars': { en: 'Stars', zh: 'Stars' },
  'browse.category': { en: 'Category', zh: '分类' },
  'browse.category.all': { en: 'All Categories', zh: '全部分类' },
  'search.loading': { en: 'Loading search index...', zh: '加载搜索索引...' },
  'search.placeholder': { en: 'Search by name or description...', zh: '按名称或描述搜索...' },
  'search.results': { en: 'results', zh: '个结果' },
  'search.noResults': { en: 'No results found', zh: '未找到结果' },
  'detail.health': { en: 'Health', zh: '健康度' },
  'detail.evaluation': { en: 'Evaluation', zh: '评估详情' },
  'detail.install': { en: 'Installation', zh: '安装指引' },
  'detail.install.copy': { en: 'Copy', zh: '复制' },
  'detail.install.copied': { en: 'Copied!', zh: '已复制!' },
  'detail.install.manual': { en: 'Follow the README for installation instructions', zh: '请参照 README 安装' },
  'detail.install.skillExtract': { en: 'Use the direct source path below for this skill.', zh: '该技能请直接使用下面的源码直达路径。' },
  'detail.install.sourcePathLabel': { en: 'Direct source path', zh: '直达路径' },
  'detail.install.skillExtractHint': { en: 'Open the linked path and install only that skill directory into your local skills folder.', zh: '打开这个直达路径，只安装对应的 skill 目录到本地技能目录。' },
  'detail.tags': { en: 'Tags', zh: '标签' },
  'detail.techStack': { en: 'Tech Stack', zh: '技术栈' },
  'detail.source': { en: 'Source', zh: '来源' },
  'detail.github': { en: 'View on GitHub', zh: '在 GitHub 查看' },
  'detail.lastCommit': { en: 'Last commit', zh: '最近提交' },
  'about.title': { en: 'About Everything AI Coding', zh: '关于 Everything AI Coding' },
  'about.description': { en: 'Everything AI Coding aggregates 4000+ curated MCP Servers, Skills, Rules, and Prompts from 9 upstream sources, updated weekly via CI. Developed by the Costrict team.', zh: 'Everything AI Coding 聚合了来自 9 个上游源的 4000+ 精选 MCP 服务、技能、规则和提示词，每周通过 CI 自动更新。由 Costrict 团队开发。' },
  'about.sources': { en: 'Data Sources', zh: '数据源' },
  'about.github': { en: 'GitHub Repository', zh: 'GitHub 仓库' },
  'about.pipeline.title': { en: 'Data Pipeline', zh: '数据管线' },
  'about.pipeline.step1.label': { en: 'Sync', zh: '同步' },
  'about.pipeline.step1.desc': { en: '9 upstream sources crawled weekly via CI', zh: '每周 CI 自动抓取 9 个上游源' },
  'about.pipeline.step2.label': { en: 'Enrich', zh: '富化' },
  'about.pipeline.step2.desc': { en: 'source_trust · confidence · heuristic reason', zh: '来源可信度 · 置信度 · 启发式原因' },
  'about.pipeline.step3.label': { en: 'LLM Eval', zh: 'LLM 评估' },
  'about.pipeline.step3.desc': { en: 'coding_relevance · content_quality · specificity (1–5)', zh: '编程相关性 · 内容质量 · 专业度（1–5分）' },
  'about.pipeline.step4.label': { en: 'Govern', zh: '决策' },
  'about.pipeline.step4.desc': { en: 'Weighted final_score → accept / review / reject', zh: '加权 final_score → 接受 / 复审 / 拒绝' },
  'about.scoring.title': { en: 'Scoring Weights', zh: '评分权重' },
  'about.scoring.desc': { en: 'Each signal is rated 1–5 by the LLM, normalized to 0–100, then blended by type-specific weights into', zh: '各维度由 LLM 评 1–5 分，归一化到 0–100，再按类型权重加权合并为' },
  'about.thresholds.title': { en: 'Decision Thresholds', zh: '决策阈值' },
  'about.health.title': { en: 'Health Score', zh: '健康度评分' },
  'about.health.desc': { en: 'Independent from final_score — measures repository vitality, not content quality.', zh: '与 final_score 独立——衡量仓库活跃度，而非内容质量。' },
  'about.trust.title': { en: 'Source Trust', zh: '来源可信度' },
  'about.trust.desc': { en: 'Assigned per upstream source, feeds into source_trust signal (1–5).', zh: '按上游源分配，输入 source_trust 信号（1–5）。' },
  'about.signal.popularity': { en: 'Popularity', zh: '流行度' },
  'about.signal.popularity.desc': { en: 'GitHub stars (log₁₀ scale → 0–100)', zh: 'GitHub stars（log₁₀ 归一化 → 0–100）' },
  'about.signal.freshness': { en: 'Freshness', zh: '活跃度' },
  'about.signal.freshness.desc': { en: '≤90d = 100 · stale decay · abandoned = 0', zh: '90天内=100 · 线性衰减 · 废弃=0' },
  'about.signal.quality': { en: 'Quality', zh: '质量' },
  'about.signal.quality.desc': { en: 'Derived from final_score or install heuristic', zh: '来自 final_score 或安装启发式评估' },
  'about.signal.installability': { en: 'Installability', zh: '可安装性' },
  'about.signal.installability.desc': { en: 'mcp_config=100 · git_clone=60 · manual=20', zh: 'mcp_config=100 · git_clone=60 · manual=20' },
  'about.decision.accept': { en: 'Accept', zh: '接受' },
  'about.decision.review': { en: 'Review', zh: '复审' },
  'about.decision.reject': { en: 'Reject', zh: '拒绝' },
  'loading': { en: 'Loading...', zh: '加载中...' },
  'error': { en: 'Failed to load data', zh: '数据加载失败' },
  // Health radar chart labels
  'health.popularity': { en: 'Popularity', zh: '流行度' },
  'health.freshness': { en: 'Freshness', zh: '活跃度' },
  'health.quality': { en: 'Quality', zh: '质量' },
  'health.installability': { en: 'Installability', zh: '可安装性' },
  // Evaluation dimension labels
  'eval.coding_relevance': { en: 'Coding Relevance', zh: '编程相关性' },
  'eval.content_quality': { en: 'Content Quality', zh: '内容质量' },
  'eval.specificity': { en: 'Specificity', zh: '专业度' },
  'eval.source_trust': { en: 'Source Trust', zh: '来源可信度' },
  'eval.confidence': { en: 'Confidence', zh: '置信度' },
  'eval.evaluator': { en: 'Evaluator', zh: '评估模型' },
  // Category labels
  'cat.tooling': { en: 'Tooling', zh: '工具' },
  'cat.ai-ml': { en: 'AI & ML', zh: 'AI & 机器学习' },
  'cat.backend': { en: 'Backend', zh: '后端' },
  'cat.frontend': { en: 'Frontend', zh: '前端' },
  'cat.devops': { en: 'DevOps', zh: 'DevOps' },
  'cat.security': { en: 'Security', zh: '安全' },
  'cat.documentation': { en: 'Documentation', zh: '文档' },
  'cat.testing': { en: 'Testing', zh: '测试' },
  'cat.database': { en: 'Database', zh: '数据库' },
  'cat.mobile': { en: 'Mobile', zh: '移动端' },
  'cat.fullstack': { en: 'Full Stack', zh: '全栈' },
  // Featured section titles (Chinese mapping)
  'featured.Browser & Automation': { en: 'Browser & Automation', zh: '浏览器 & 自动化' },
  'featured.Git & Collaboration': { en: 'Git & Collaboration', zh: 'Git & 协作' },
  'featured.DevOps & Security': { en: 'DevOps & Security', zh: 'DevOps & 安全' },
  'featured.Documentation & Knowledge': { en: 'Documentation & Knowledge', zh: '文档 & 知识管理' },
  'featured.Frontend & Design': { en: 'Frontend & Design', zh: '前端 & 设计' },
  'featured.Backend & Databases': { en: 'Backend & Databases', zh: '后端 & 数据库' },
  'featured.AI & MCP Development': { en: 'AI & MCP Development', zh: 'AI & MCP 开发' },
}

const I18nContext = createContext<I18nContextValue | null>(null)

function detectLang(): Lang {
  const saved = localStorage.getItem('lang')
  if (saved === 'en' || saved === 'zh') return saved
  return navigator.language.startsWith('zh') ? 'zh' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang)

  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem('lang', l)
  }

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  const t = (key: string) => translations[key]?.[lang] ?? key

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used within I18nProvider')
  return ctx
}
