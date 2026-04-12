interface ConfirmationModalProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  confirmTone?: 'primary' | 'danger'
  disabled?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ConfirmationModal({
  open,
  title,
  description,
  confirmLabel,
  confirmTone = 'primary',
  disabled = false,
  onCancel,
  onConfirm,
}: ConfirmationModalProps) {
  if (!open) {
    return null
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="confirmation-title">
        <p className="eyebrow">Execution confirmation</p>
        <h2 id="confirmation-title">{title}</h2>
        <p className="modal-card__description">{description}</p>
        <div className="modal-card__actions">
          <button className="button button--ghost" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button
            className={`button ${confirmTone === 'danger' ? 'button--danger' : 'button--primary'}`}
            type="button"
            onClick={onConfirm}
            disabled={disabled}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
