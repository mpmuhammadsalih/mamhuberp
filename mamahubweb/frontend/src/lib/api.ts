import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { refreshCustomerSession } from './session'
import { storage } from './storage'
import type { ApiResponse } from '../types/api'

const LOCALE_STORAGE_KEY = 'mamahub_locale'

function currentLocale(): string {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored === 'ar' || stored === 'en') return stored
  } catch {
    /* ignore */
  }
  return 'en'
}

type RetriedRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean }

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
})

api.interceptors.request.use((config) => {
  const token = storage.getToken()
  const guest = storage.getGuestCartToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (guest) config.headers['X-Guest-Cart-Token'] = guest
  config.headers['Accept-Language'] = currentLocale()
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    config.headers.set('Content-Type', false)
  }
  return config
})

function isCustomerAuthAttempt(url: string): boolean {
  return (
    url.includes('/customer/auth/login') ||
    url.includes('/customer/auth/register') ||
    url.includes('/customer/auth/refresh') ||
    url.includes('/customer/auth/forgot-password') ||
    url.includes('/customer/auth/reset-password')
  )
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(error)
    }

    const url = error.config?.url ?? ''
    const isAdminRoute = url.includes('/admin/')
    const isAuthAttempt = isCustomerAuthAttempt(url)

    if (isAdminRoute || isAuthAttempt) {
      if (!url.includes('/customer/auth/login') && !url.includes('/customer/auth/register')) {
        storage.clearSession()
      }
      return Promise.reject(error)
    }

    const original = error.config as RetriedRequestConfig | undefined
    if (!original || original._retry) {
      storage.clearSession()
      return Promise.reject(error)
    }

    if (!storage.getRefreshToken()) {
      storage.clearSession()
      return Promise.reject(error)
    }

    original._retry = true
    const refreshed = await refreshCustomerSession()
    if (!refreshed) {
      return Promise.reject(error)
    }

    const accessToken = storage.getToken()
    if (!accessToken) {
      return Promise.reject(error)
    }

    original.headers.Authorization = `Bearer ${accessToken}`
    return api(original)
  },
)

type RequestConfig = { signal?: AbortSignal }

export async function getData<T>(
  url: string,
  params?: Record<string, unknown>,
  config?: RequestConfig,
) {
  const { data } = await api.get<ApiResponse<T>>(url, { params, signal: config?.signal })
  return data.data
}

export async function getDataWithMeta<T>(
  url: string,
  params?: Record<string, unknown>,
  config?: RequestConfig,
) {
  const { data } = await api.get<ApiResponse<T>>(url, { params, signal: config?.signal })
  return { data: data.data, meta: data.meta }
}

export async function postData<T>(url: string, body?: unknown, timeoutMs = 15_000) {
  const { data } = await api.post<ApiResponse<T>>(url, body, { timeout: timeoutMs })
  return data.data
}

export async function patchData<T>(url: string, body?: unknown) {
  const { data } = await api.patch<ApiResponse<T>>(url, body)
  return data.data
}

export async function deleteData<T>(url: string) {
  const { data } = await api.delete<ApiResponse<T>>(url)
  return data.data
}

export async function uploadFile(url: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<ApiResponse<{ filename: string; image_url: string }>>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data.data
}

export async function postForm<T>(url: string, form: FormData, timeoutMs = 45_000) {
  const { data } = await api.post<ApiResponse<T>>(url, form, {
    timeout: timeoutMs,
    headers: { 'Content-Type': undefined },
  })
  return data.data
}

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as
      | { message?: string; detail?: string }
      | string
      | undefined
    if (typeof body === 'string') {
      if (/cloudflare/i.test(body)) {
        return 'Store connection failed. Wait a moment and try again.'
      }
      const trimmed = body.trim()
      if (trimmed.startsWith('{')) {
        try {
          const parsed = JSON.parse(trimmed) as { message?: string; detail?: string }
          if (parsed.message) return parsed.message
          if (typeof parsed.detail === 'string') return parsed.detail
        } catch {
          /* ignore */
        }
      }
    } else {
      if (body?.message) return body.message
      if (typeof body?.detail === 'string') return body.detail
    }
    if (error.response?.status === 401) {
      return 'Please sign in to continue.'
    }
    if (error.response?.status === 502 || error.response?.status === 520) {
      return 'Backend unavailable. Please try again shortly.'
    }
    if (error.response?.status === 522 || error.response?.status === 524) {
      return 'Request timed out. Please try again.'
    }
    if (error.code === 'ECONNABORTED') return 'Request timed out. Is the storefront API running?'
    if (error.message === 'Network Error') {
      return 'Could not reach the server. Check that Nova is running on port 5055.'
    }
    if (/cloudflare/i.test(error.message)) {
      return 'Store connection failed. Wait a moment and try again.'
    }
    return error.message
  }
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

function isRetryableCartError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  const status = error.response?.status
  if (status === 502 || status === 520 || status === 522 || status === 524) return true
  if (error.code === 'ECONNABORTED' || error.message === 'Network Error') return true
  const body = error.response?.data
  if (typeof body === 'string' && /cloudflare/i.test(body)) return true
  return /cloudflare/i.test(error.message)
}

export async function postDataWithRetry<T>(
  url: string,
  body?: unknown,
  timeoutMs = 15_000,
  retries = 1,
): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await postData<T>(url, body, timeoutMs)
    } catch (error) {
      lastError = error
      if (attempt < retries && isRetryableCartError(error)) {
        await new Promise((resolve) => window.setTimeout(resolve, 600))
        continue
      }
      throw error
    }
  }
  throw lastError
}
