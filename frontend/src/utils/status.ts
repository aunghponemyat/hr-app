export const statusLabel = (value: string | null) =>
  value
    ? { 'half-day': 'Half-day' }[value] ||
      value[0].toUpperCase() + value.slice(1)
    : 'Not recorded'
