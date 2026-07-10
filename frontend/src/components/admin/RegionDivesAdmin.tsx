import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { createDive, fetchDivesForRegion, updateDive } from '../../api/diveApi'
import type { Dive } from '../../api/types'
import '../admin/AdminPanels.css'

export default function RegionDivesAdmin({ regionUuid }: { regionUuid: string }) {
  const [dives, setDives] = useState<Dive[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState<Dive | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [metadataJson, setMetadataJson] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchDivesForRegion(regionUuid)
      .then(setDives)
      .catch(() => setError('Could not load dives.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [regionUuid])

  const startCreate = () => {
    setEditing(null)
    setTitle('')
    setDescription('')
    setMetadataJson('')
    setFormError(null)
  }

  const startEdit = (dive: Dive) => {
    setEditing(dive)
    setTitle(dive.title)
    setDescription(dive.description ?? '')
    setMetadataJson(dive.metadata ? JSON.stringify(dive.metadata, null, 2) : '')
    setFormError(null)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (submitting) return

    let metadataValue: Record<string, unknown> | null = null
    if (metadataJson.trim() !== '') {
      try {
        metadataValue = JSON.parse(metadataJson)
      } catch {
        setFormError('Metadata must be valid JSON.')
        return
      }
    }

    const description_ = description.trim() === '' ? null : description

    setFormError(null)
    setSubmitting(true)
    const request = editing
      ? updateDive(editing.uuid, { title, description: description_, metadata: metadataValue })
      : createDive({ title, description: description_, metadata: metadataValue, region: regionUuid })
    request
      .then(() => {
        load()
        startCreate()
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiError ? err.message : 'Could not save this dive.')
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-list">
        {loading && <p className="game-status">Loading…</p>}
        {error && <p className="game-status game-status-error">{error}</p>}
        {dives && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Description</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {dives.map((dive) => (
                <tr key={dive.uuid} className={editing?.uuid === dive.uuid ? 'admin-row-active' : ''}>
                  <td>{dive.title}</td>
                  <td>{dive.description ?? ''}</td>
                  <td>
                    <button type="button" className="btn" onClick={() => startEdit(dive)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {dives.length === 0 && (
                <tr>
                  <td colSpan={3}>No dives yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <form className="admin-form" onSubmit={handleSubmit}>
        <h4>{editing ? 'Edit dive' : 'New dive'}</h4>

        <label className="admin-form-field">
          Title
          <input type="text" value={title} required onChange={(e) => setTitle(e.target.value)} />
        </label>

        <label className="admin-form-field">
          Description
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>

        <label className="admin-form-field">
          Metadata (JSON, optional)
          <textarea rows={4} value={metadataJson} onChange={(e) => setMetadataJson(e.target.value)} />
        </label>

        {formError && <p className="game-status game-status-error">{formError}</p>}
        <div className="admin-form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create'}
          </button>
          {editing && (
            <button type="button" className="btn" onClick={startCreate}>
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
