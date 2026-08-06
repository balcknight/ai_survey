import http from './http'
import type { AuthUser, LoginResponse } from '../types/auth'

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await http.post('/api/auth/login', { username, password })
  return data
}

export async function logout(): Promise<void> {
  await http.post('/api/auth/logout')
}

export async function getMe(): Promise<AuthUser> {
  const { data } = await http.get('/api/auth/me')
  return data
}
