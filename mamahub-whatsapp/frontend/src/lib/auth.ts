const TOKEN_KEY = "wa_crm_token";
const USER_KEY = "wa_crm_user";

export type AuthUser = {
  access_token: string;
  refresh_token: string;
  role: string;
  username: string;
  full_name: string;
  permissions: string[];
};

export function saveAuth(user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, user.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getRefreshToken() {
  return getUser()?.refresh_token || "";
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as AuthUser) : null;
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}
