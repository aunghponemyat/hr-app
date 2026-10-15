export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  pwd_change_required: boolean
}

export interface Profile {
  id: number
  employee_id: string
  first_name: string
  last_name: string
  display_name: string | null
  position: string | null
  department: string | null
  role: { id: number; name: string }
  team: { id: number; name: string } | null
  permissions: string[]
  must_change_password: boolean
  app: { timezone: string; today: string; max_report_range_days: number }
}

export interface LoginInput {
  username: string
  password: string
}

export interface ChangePasswordInput {
  current_password: string
  new_password: string
}

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown> | null
}
