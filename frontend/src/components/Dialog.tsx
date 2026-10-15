import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

export function Dialog({
  title,
  children,
  onClose,
  busy = false,
  drawer = false,
}: {
  title: string
  children: ReactNode
  onClose: () => void
  busy?: boolean
  drawer?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const heading = useId()
  useEffect(() => {
    const previous = document.activeElement
    const dialog = ref.current!
    dialog.showModal()
    return () => {
      dialog.close()
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className={drawer ? 'modal drawer' : 'modal'}
      aria-labelledby={heading}
      aria-busy={busy}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div className="modal-content">
        <div className="section-heading">
          <h2 id={heading}>{title}</h2>
          <button
            className="secondary"
            type="button"
            aria-label="Close dialog"
            disabled={busy}
            onClick={onClose}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

export function ConfirmDialog({
  title,
  children,
  onClose,
  onConfirm,
  busy = false,
  confirmLabel = 'Confirm',
}: {
  title: string
  children?: ReactNode
  onClose: () => void
  onConfirm: () => void
  busy?: boolean
  confirmLabel?: string
}) {
  return (
    <Dialog title={title} onClose={onClose} busy={busy}>
      <div>{children}</div>
      <div className="actions">
        <button
          type="button"
          className="secondary"
          onClick={onClose}
          disabled={busy}
        >
          Cancel
        </button>
        <button type="button" onClick={onConfirm} disabled={busy}>
          {busy ? 'Please wait…' : confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}
