import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { uploadFunFactsZip } from '../../api/adminApi'
import type { FunFactImportCounts } from '../../api/adminApi'
import { ApiError } from '../../api/client'
import '../admin/AdminPanels.css'

export default function AdminImportAdmin() {
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<FunFactImportCounts | null>(null)

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null)
    setError(null)
    setResult(null)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!file || submitting) return
    setSubmitting(true)
    setError(null)
    setResult(null)
    uploadFunFactsZip(file)
      .then((counts) => {
        setResult(counts)
        setFile(null)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Could not upload this zip file.')
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <form className="admin-form" onSubmit={handleSubmit}>
      <h3>Import fun facts from zip</h3>

      <p className="zip-upload-description">
        Upload a zip in the same format as the fun facts zip export (fun_facts.csv,
        helper_images.csv, helper_images/) and upsert each fun fact by uuid. Requires the admin
        role.
      </p>
      <p className="zip-upload-description">
        The whole import is all-or-nothing: any error aborts with nothing persisted and no asset
        files left behind. Fails with 422 identifying the offending file and row if any row is
        invalid, references a nonexistent region, or has a title that collides with a different
        fact's title, or if the zip is malformed or contains an unsafe path.
      </p>

      <label className="admin-form-field">
        Zip file
        <input type="file" accept=".zip,application/zip" onChange={handleFileChange} />
      </label>

      {error && <p className="game-status game-status-error">{error}</p>}
      {result && (
        <p className="game-status">
          Imported {result.created} fun fact(s), updated {result.updated}.
        </p>
      )}

      <div className="admin-form-actions">
        <button type="submit" className="btn btn-primary" disabled={!file || submitting}>
          {submitting ? 'Uploading…' : 'Upload'}
        </button>
      </div>
    </form>
  )
}
