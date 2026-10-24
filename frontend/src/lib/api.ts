import type { Company, Metrics } from '../types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const SESSION_TOKEN_KEY = 'prativ.access_token'

export const EVALUATOR_KEY = 'prativ.evaluator'

export type AuthenticatedUser = {
  name: string
  email?: string
  provider: string
}

export function getSessionToken() {
  return window.sessionStorage.getItem(SESSION_TOKEN_KEY)
}

export function setSessionToken(token: string) {
  window.sessionStorage.setItem(SESSION_TOKEN_KEY, token)
}

export function clearSessionToken() {
  window.sessionStorage.removeItem(SESSION_TOKEN_KEY)
}

/** OAuth is handled by the Spring Boot backend. A static host (Vercel) has no /oauth2 route, so the buttons only
 *  work when a backend URL was configured at build time (VITE_API_BASE_URL) or the app runs on localhost. */
export const oauthAvailable =
  API_BASE_URL !== '' || ['localhost', '127.0.0.1'].includes(window.location.hostname)

export function oauthAuthorizationUrl(provider: 'google' | 'github') {
  return `${API_BASE_URL}/oauth2/authorization/${provider}`
}

export class BackendUnavailableError extends Error {}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const token = getSessionToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${url}`, { ...init, headers })
  } catch {
    throw new BackendUnavailableError('Backend API is unreachable.')
  }
  // A static host (e.g. Vercel SPA rewrite) answers /api/* with index.html, not JSON.
  const isJson = response.headers.get('content-type')?.includes('json') ?? false
  if (!isJson && (response.ok || response.status === 404 || response.status >= 502)) {
    throw new BackendUnavailableError('Backend API is not available at this address.')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail ?? body.error ?? `Request failed (${response.status})`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body as T
}

export const api = {
  currentUser: () => requestJson<{ status: string; user: AuthenticatedUser }>('/api/auth/me'),
  companies: () => requestJson<Company[]>('/api/companies'),
  metrics: () => requestJson<Metrics>('/api/metrics'),
  lookup: (companyNumber: string) =>
    requestJson<Company>(`/api/companies/lookup/${companyNumber}`, { method: 'POST' }),
}

export function normalizedName(company: Company) {
  return company.official_legal_name || company.company_name || 'Unknown legal name'
}

export function hasMetricEvidence(company: Company, metricKey: string) {
  return Boolean(company.lineage_evidences?.some((evidence) =>
    evidence.target_metric_key?.toLowerCase() === metricKey.toLowerCase()
      && Boolean(evidence.source_url_link)
      && Boolean(evidence.extracted_text_snippet),
  ))
}

export function formatDate(value?: string) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' }).format(date)
}