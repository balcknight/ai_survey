export interface AuthUser {
  id: number
  username: string
  display_name: string
  is_active: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: AuthUser
}
