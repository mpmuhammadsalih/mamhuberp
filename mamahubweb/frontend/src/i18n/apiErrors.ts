import type { TranslationTree } from './types'
import { getApiErrorMessage } from '../lib/api'

const ENGLISH_ERROR_MAP: Record<string, keyof TranslationTree['errors']> = {
  'Please sign in to continue.': 'signInRequired',
  'Backend unavailable. Please try again shortly.': 'backendUnavailableShort',
  'Backend unavailable. Start Nova on port 5055.': 'backendUnavailable',
  'Request timed out. Please try again.': 'requestTimeout',
  'Request timed out. Is the storefront API running?': 'requestTimeoutServer',
  'Store connection failed. Please try again.': 'storeConnectionFailed',
  'Store connection failed. Wait a moment and try again.': 'storeConnectionRetry',
  'Could not reach the server. Check that Nova is running on port 5055.': 'networkError5055',
  'Something went wrong. Please try again.': 'generic',
}

export function getLocalizedApiErrorMessage(error: unknown, t: TranslationTree): string {
  const message = getApiErrorMessage(error)
  const key = ENGLISH_ERROR_MAP[message]
  return key ? t.errors[key] : message
}
