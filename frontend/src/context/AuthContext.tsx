import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, clearSessionToken, EVALUATOR_KEY, getSessionToken, setSessionToken, type AuthenticatedUser } from '../lib/api'

const evaluatorUser: AuthenticatedUser = { name: 'Evaluator', provider: 'evaluator' }
import { AuthContext } from './auth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(() =>
    window.sessionStorage.getItem(EVALUATOR_KEY) ? evaluatorUser : null,
  )
  const [loading, setLoading] = useState(() => Boolean(
    getSessionToken() || new URLSearchParams(window.location.hash.slice(1)).get('access_token'),
  ))
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const fragment = new URLSearchParams(window.location.hash.slice(1))
    const callbackToken = fragment.get('access_token')
    if (callbackToken) {
      setSessionToken(callbackToken)
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
    }

    if (!getSessionToken()) return () => { active = false }

    void api.currentUser()
      .then((session) => {
        if (active) setUser(session.user)
      })
      .catch(() => {
        clearSessionToken()
        if (active) setError('Your sign-in session could not be validated. Please sign in again.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => { active = false }
  }, [])

  const value = useMemo(() => ({
    user,
    loading,
    error,
    enterEvaluator: () => {
      window.sessionStorage.setItem(EVALUATOR_KEY, '1')
      setError('')
      setUser(evaluatorUser)
    },
    signOut: () => {
      window.sessionStorage.removeItem(EVALUATOR_KEY)
      clearSessionToken()
      setUser(null)
      setError('')
    },
  }), [user, loading, error])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
