import { createContext, useContext } from 'react'
import type { AuthenticatedUser } from '../lib/api'

type AuthContextValue = {
  user: AuthenticatedUser | null
  loading: boolean
  error: string
  signOut: () => void
  enterEvaluator: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within an AuthProvider')
  return value
}
