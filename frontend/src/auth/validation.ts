import { z } from 'zod'

// Python str.isdigit includes Decimal_Number plus these compatibility digits.
const digit =
  /[\p{Nd}\u{b2}-\u{b3}\u{b9}\u{1369}-\u{1371}\u{19da}\u{2070}\u{2074}-\u{2079}\u{2080}-\u{2089}\u{2460}-\u{2468}\u{2474}-\u{247c}\u{2488}-\u{2490}\u{24ea}\u{24f5}-\u{24fd}\u{24ff}\u{2776}-\u{277e}\u{2780}-\u{2788}\u{278a}-\u{2792}\u{10a40}-\u{10a43}\u{10e60}-\u{10e68}\u{11052}-\u{1105a}\u{1f100}-\u{1f10a}]/u
const boundedString = (min: number, max: number, message: string) =>
  z
    .string()
    .refine(
      (value) =>
        Array.from(value).length >= min && Array.from(value).length <= max,
      message,
    )
export const loginSchema = z.object({
  username: boundedString(
    1,
    20,
    'Enter your employee ID (up to 20 characters).',
  ),
  password: boundedString(
    1,
    1024,
    'Enter your password (up to 1024 characters).',
  ),
})
export const passwordSchema = z
  .object({
    current_password: boundedString(1, 1024, 'Enter your current password.'),
    new_password: boundedString(8, 1024, 'Use 8–1024 characters.').refine(
      (value) => /\p{L}/u.test(value) && digit.test(value),
      'Include at least one letter and one digit.',
    ),
    confirmation: z.string(),
  })
  .refine((value) => value.new_password !== value.current_password, {
    path: ['new_password'],
    message: 'Choose a different password from your current one.',
  })
  .refine((value) => value.confirmation === value.new_password, {
    path: ['confirmation'],
    message: 'The passwords do not match.',
  })
export type PasswordForm = z.infer<typeof passwordSchema>
