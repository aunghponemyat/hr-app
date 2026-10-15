export function safeDestination(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\') ||
    Array.from(value).some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
    )
  )
    return '/'
  const path = value.split(/[?#]/)[0]
  return path === '/login' || path === '/change-password' ? '/' : value
}
