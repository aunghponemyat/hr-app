import { useAuthState } from '../auth/useAuthState'

export function usePermissions() {
  const { profile } = useAuthState()
  return (...codes: string[]) =>
    codes.some((code) => profile?.permissions.includes(code))
}
