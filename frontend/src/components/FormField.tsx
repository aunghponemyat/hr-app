import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}
export const FormField = forwardRef<HTMLInputElement, Props>(function FormField(
  { label, error, id, ...input },
  ref,
) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        {...input}
        id={id}
        ref={ref}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {error && (
        <p className="field-error" id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  )
})
