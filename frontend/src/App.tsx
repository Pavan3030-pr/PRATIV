import { useEffect, useState } from 'react'
import { AuthScreen } from './components/auth/AuthScreen'
import { LandingPage } from './components/landing/LandingPage'
import { WorkspacePage } from './components/workspace/WorkspacePage'
import { Explorer } from './components/explorer/Explorer'
import { useAuth } from './context/auth'

type PublicRoute = 'landing' | 'auth' | 'workspace'

function hasPendingAuthCallback() {
  return (
    new URLSearchParams(window.location.hash.slice(1)).has('access_token') ||
    new URLSearchParams(window.location.search).has('auth_error')
  )
}

function SessionSplash() {
  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center gap-4 bg-paper"
      aria-busy="true"
      role="status"
    >
      <span className="size-6 animate-spin rounded-full border-2 border-line-strong border-t-ink" />
      <p className="text-[14px] text-muted">Validating secure session...</p>
    </main>
  )
}

const isExplorerHash = () => window.location.hash.startsWith('#/explore')

export default function App() {
  const { user, loading } = useAuth()
  const [explore, setExplore] = useState(isExplorerHash)
  useEffect(() => {
    const onHash = () => setExplore(isExplorerHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const [routeState, setRouteState] = useState<PublicRoute>(() =>
    hasPendingAuthCallback() ? 'auth' : 'landing',
  )

  if (explore) return <Explorer />
  if (loading) return <SessionSplash />
  if (user || routeState === 'workspace') return <WorkspacePage />
  if (routeState === 'auth') return <AuthScreen onBack={() => setRouteState('landing')} />

  return <LandingPage onStart={() => setRouteState('auth')} />
}
