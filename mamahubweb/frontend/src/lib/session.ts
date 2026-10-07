import axios from 'axios'
import type { ApiResponse } from '../types/api'
import { storage } from './storage'

type AuthTokens = {
  access_token: string
  refresh_token: string
  token_type?: string
  expires_in?: number
}

let inflightRefresh: Promise<boolean> | null = null

export function hasCustomerSession(): boolean {
  return storage.hasSession()
}

export async function refreshCustomerSession(): Promise<boolean> {
  const refreshToken = storage.getRefreshToken()
  if (!refreshToken) {
    storage.clearSession()
    return false
  }

  if (inflightRefresh) {
    return inflightRefresh
  }

  inflightRefresh = (async () => {
    try {
      const { data } = await axios.post<ApiResponse<{ tokens: AuthTokens }>>(
        '/api/v1/customer/auth/refresh',
        { refresh_token: refreshToken },
        { headers: { 'Content-Type': 'application/json' }, timeout: 15_000 },
      )
      const tokens = data.data?.tokens
      if (tokens?.access_token && tokens?.refresh_token) {
        storage.setTokens(tokens.access_token, tokens.refresh_token)
        return true
      }
    } catch {
      /* fall through */
    }
    storage.clearSession()
    return false
  })().finally(() => {
    inflightRefresh = null
  })

  return inflightRefresh
}

/** Restore access token on app load when a refresh token is still valid. */
export async function bootstrapCustomerSession(): Promise<boolean> {
  if (!storage.getRefreshToken()) return false
  if (storage.getToken()) return true
  return refreshCustomerSession()
}
