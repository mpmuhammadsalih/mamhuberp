const TOKEN_KEY = 'mamahub_token'
const REFRESH_TOKEN_KEY = 'mamahub_refresh_token'
const GUEST_CART_KEY = 'mamahub_guest_cart'

export const storage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  setTokens: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  },
  clearToken: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
  clearSession: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
  hasSession: () =>
    Boolean(localStorage.getItem(TOKEN_KEY) || localStorage.getItem(REFRESH_TOKEN_KEY)),
  getGuestCartToken: () => localStorage.getItem(GUEST_CART_KEY),
  setGuestCartToken: (token: string) => localStorage.setItem(GUEST_CART_KEY, token),
}
