import { Outlet, Link, useLocation } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import { useTheme } from '../hooks/useTheme'

const navItems = [
  { path: '/', key: 'nav.home' },
  { path: '/browse', key: 'nav.browse' },
  { path: '/about', key: 'nav.about' },
] as const

export default function Layout() {
  const { lang, setLang, t } = useI18n()
  const { theme, toggle } = useTheme()
  const location = useLocation()

  return (
    <div className="relative min-h-screen">
      {/* Background orbs */}
      <div className="bg-orb bg-orb-purple" />
      <div className="bg-orb bg-orb-blue" />
      <div className="bg-orb bg-orb-pink" />

      {/* Nav bar */}
      <nav className="glass sticky top-0 z-50 px-6 py-3 flex items-center justify-between rounded-none border-x-0 border-t-0">
        <div className="flex items-center gap-8">
          <Link to="/" className="text-xl font-bold text-gray-900 dark:text-white no-underline tracking-tight">
            Coding Hub
          </Link>
          <div className="hidden sm:flex items-center gap-1">
            {navItems.map(({ path, key }) => {
              const active = path === '/'
                ? location.pathname === '/'
                : location.pathname.startsWith(path)
              return (
                <Link
                  key={path}
                  to={path}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium no-underline transition-colors ${
                    active
                      ? 'bg-apple-blue text-white'
                      : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-white/10'
                  }`}
                >
                  {t(key)}
                </Link>
              )
            })}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/zgsm-ai/costrict"
            target="_blank"
            rel="noopener noreferrer"
            className="px-2.5 py-1.5 rounded-lg hover:bg-white/50 dark:hover:bg-white/10 transition-colors inline-flex items-center"
            aria-label="Costrict"
            title="Costrict"
          >
            <img src="/costrict_logo.png" alt="Costrict" className="w-5 h-5 rounded-sm" />
          </a>
          <a
            href="https://github.com/zgsm-sangfor/costrict-coding-hub"
            target="_blank"
            rel="noopener noreferrer"
            className="px-2.5 py-1.5 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-white/50 dark:hover:bg-white/10 transition-colors inline-flex items-center"
            aria-label="GitHub"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
          </a>
          <button
            onClick={toggle}
            className="px-2.5 py-1.5 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-white/50 dark:hover:bg-white/10 transition-colors border-none cursor-pointer bg-transparent"
            aria-label="Toggle theme"
          >
            {theme === 'light' ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            )}
          </button>
          <button
            onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}
            className="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-white/50 dark:hover:bg-white/10 transition-colors border-none cursor-pointer bg-transparent"
          >
            {lang === 'en' ? '中文' : 'EN'}
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
