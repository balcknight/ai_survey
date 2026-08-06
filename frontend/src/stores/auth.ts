import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getMe, login as loginApi, logout as logoutApi } from '../api/auth'
import type { AuthUser } from '../types/auth'
import { clearToken, getToken, setToken } from '../utils/auth-token'

export const useAuthStore = defineStore('auth', () => {
  // 当前用户信息只存内存；token 存 localStorage（由 utils/auth-token 管理）。
  const currentUser = ref<AuthUser | null>(null)

  const isLoggedIn = () => !!getToken()

  async function login(username: string, password: string) {
    const res = await loginApi(username.trim(), password)
    setToken(res.access_token)
    currentUser.value = res.user
  }

  async function fetchMe() {
    currentUser.value = await getMe()
  }

  async function logout() {
    try {
      await logoutApi()
    } catch {
      // 登出接口幂等；即使后端不可达也继续本地清理。
    } finally {
      clearToken()
      currentUser.value = null
      // 整页跳转清空所有内存态，且 replace 使浏览器后退回不到原页面。
      window.location.replace('/login')
    }
  }

  return { currentUser, isLoggedIn, login, fetchMe, logout }
})
