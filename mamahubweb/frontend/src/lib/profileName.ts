import type { UserProfile } from '../types/api'

export function profileDisplayName(
  profile?: Pick<UserProfile, 'first_name' | 'last_name' | 'email'> | null,
): string {
  const first = profile?.first_name?.trim()
  if (first) return first
  const last = profile?.last_name?.trim()
  if (last) return last
  const email = profile?.email?.trim()
  if (email) return email.split('@')[0] || email
  return ''
}
