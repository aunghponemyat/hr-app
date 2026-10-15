import { useState } from 'react'
import { Dialog } from './Dialog'
import { StatusBanner } from './Feedback'

export interface Handover {
  employee_id: string
  password: string
}
export function PasswordHandover({
  value,
  onClose,
}: {
  value: Handover
  onClose: () => void
}) {
  const [message, setMessage] = useState<string | null>(null)
  return (
    <Dialog title="Account password" onClose={onClose}>
      <p>
        Employee ID: <strong>{value.employee_id}</strong>
      </p>
      <p>
        Give this password to the employee securely. It is shown once and must
        be changed at the next sign-in.
      </p>
      <output className="password-output" aria-label="Default password">
        {value.password}
      </output>
      <StatusBanner message={message} />
      <div className="actions">
        <button
          onClick={() => {
            void navigator.clipboard
              ?.writeText(value.password)
              .then(() =>
                setMessage(
                  'Copied. Clear your clipboard after handing it over.',
                ),
              )
              .catch(() =>
                setMessage(
                  'Copy is unavailable. Select the password to copy it.',
                ),
              )
            if (!navigator.clipboard)
              setMessage('Copy is unavailable. Select the password to copy it.')
          }}
        >
          Copy password
        </button>
        <button className="secondary" onClick={onClose}>
          Done
        </button>
      </div>
    </Dialog>
  )
}
