/**
 * 登录 token 的本地存取。
 *
 * 独立无依赖模块：http.ts 与各 store 都可安全引用，
 * 避免 http.ts <-> pinia store 之间的循环依赖。
 */
const TOKEN_KEY = 'survey_auth_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * 给浏览器原生加载的资源 URL 追加 ?token= 查询参数。
 * 用于 <img>/<iframe>/<a> 等无法携带 Authorization 头的场景。
 */
export function appendAuthToken(url: string): string {
  const token = getToken()
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}
