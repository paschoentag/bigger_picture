import { useState } from 'react'
import type { FormEvent } from 'react'
import { createCandidatePairsByStride } from '../../api/datasetApi'
import type { StrideCandidatePairResult } from '../../api/datasetApi'
import { ApiError } from '../../api/client'
import './AdminPanels.css'
import './CreateStrideCandidatePairsModal.css'

export default function CreateStrideCandidatePairsModal({
  diveUuid,
  onCancel,
  onCreated,
}: {
  diveUuid: string
  onCancel: () => void
  onCreated: (result: StrideCandidatePairResult) => void
}) {
  const [sortBy, setSortBy] = useState<'filename' | 'filepath'>('filename')
  const [stride, setStride] = useState('1')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (submitting) return

    const strideValue = Number(stride)
    if (!Number.isInteger(strideValue) || strideValue < 1) {
      setFormError('Stride must be a whole number of at least 1.')
      return
    }

    setFormError(null)
    setSubmitting(true)
    createCandidatePairsByStride(diveUuid, strideValue, sortBy)
      .then(onCreated)
      .catch((err: unknown) => {
        setFormError(err instanceof ApiError ? err.message : 'Could not create candidate pairs.')
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="stride-modal-backdrop" onClick={onCancel}>
      <div
        className="stride-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stride-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <form className="admin-form" onSubmit={handleSubmit}>
          <h3 id="stride-modal-title">Create pairs by stride</h3>
          <label className="admin-form-field">
            Sort by
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'filename' | 'filepath')}>
              <option value="filename">Filename</option>
              <option value="filepath">Filepath</option>
            </select>
          </label>
          <label className="admin-form-field">
            Stride
            <input
              type="number"
              min={1}
              step={1}
              value={stride}
              required
              onChange={(e) => setStride(e.target.value)}
            />
          </label>
          {formError && <p className="game-status game-status-error">{formError}</p>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating…' : 'Confirm'}
            </button>
            <button type="button" className="btn" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
