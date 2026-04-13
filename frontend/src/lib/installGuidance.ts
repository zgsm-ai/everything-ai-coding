import type { CatalogItem } from '../types'

type Lang = 'en' | 'zh'

type GitCloneGuidance = {
  kind: 'git_clone'
  copyText: string
}

type SkillExtractGuidance = {
  kind: 'skill_extract'
  repo: string
  branch?: string
  paths: string[]
  sourceUrl: string | null
  copyText: null
}

type DownloadFileGuidance = {
  kind: 'download_file'
  fileUrl: string
  targetDir: string
  targetFile: string
  copyText: string
}

type McpConfigGuidance = {
  kind: 'mcp_config'
  copyText: string | null
}

type ManualGuidance = {
  kind: 'manual'
  copyText: null
}

type UnsupportedGuidance = {
  kind: 'unsupported'
  copyText: null
}

export type InstallGuidance =
  | GitCloneGuidance
  | SkillExtractGuidance
  | DownloadFileGuidance
  | McpConfigGuidance
  | ManualGuidance
  | UnsupportedGuidance

export function buildInstallGuidance(item: CatalogItem, lang: Lang): InstallGuidance {
  void lang
  const install = item.install
  if (!install) {
    return { kind: 'unsupported', copyText: null }
  }

  if (install.method === 'mcp_config' || install.method === 'mcp_config_template') {
    return {
      kind: 'mcp_config',
      copyText: install.config ? JSON.stringify(install.config, null, 2) : null,
    }
  }

  if (install.method === 'manual') {
    return { kind: 'manual', copyText: null }
  }

  if (install.method === 'download_file') {
    const targetDir = item.type === 'rule' || item.type === 'prompt' ? '.claude/rules' : '.'
    const targetFile = `${targetDir}/${item.id}.md`
    const fileUrl = install.files?.[0] ?? ''
    return {
      kind: 'download_file',
      fileUrl,
      targetDir,
      targetFile,
      copyText: `curl -sL "${fileUrl}" -o ${targetFile}`,
    }
  }

  if (install.method === 'git_clone') {
    const repo = install.repo
    if (!repo) {
      return { kind: 'unsupported', copyText: null }
    }

    if (item.type === 'skill') {
      const files = install.files?.filter(Boolean) ?? []
      if (files.length > 0) {
        return {
          kind: 'skill_extract',
          repo,
          paths: files,
          sourceUrl: item.source_url || buildTreeUrl(repo, 'main', files[0]),
          copyText: null,
        }
      }

      if (install.branch && install.path) {
        return {
          kind: 'skill_extract',
          repo,
          branch: install.branch,
          paths: [install.path],
          sourceUrl: item.source_url || buildTreeUrl(repo, install.branch, install.path),
          copyText: null,
        }
      }
    }

    return {
      kind: 'git_clone',
      copyText: `git clone ${repo}`,
    }
  }

  return { kind: 'unsupported', copyText: null }
}

function buildTreeUrl(repo: string, branch: string, path: string): string | null {
  const normalizedPath = path.replace(/^\/+|\/+$/g, '')
  if (!normalizedPath) {
    return null
  }

  if (repo.startsWith('https://github.com/')) {
    const base = repo.replace(/\.git$/, '').replace(/\/+$/, '')
    return `${base}/tree/${branch}/${normalizedPath}`
  }

  const repoSlugMatch = /^[^/]+\/[^/]+$/.test(repo)
  if (repoSlugMatch) {
    return `https://github.com/${repo}/tree/${branch}/${normalizedPath}`
  }

  return null
}
