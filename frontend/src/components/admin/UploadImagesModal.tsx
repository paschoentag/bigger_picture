import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { createImage, uploadImagesZip, uploadBrokerHandlesCsv } from '../../api/datasetApi'
import type { BrokerCsvImportResult } from '../../api/datasetApi'
import { ApiError } from '../../api/client'
import './AdminPanels.css'
import './CreateStrideCandidatePairsModal.css'
import './UploadImagesModal.css'

type Mode = 'files' | 'zip' | 'broker-csv'

export default function UploadImagesModal({
  diveUuid,
  onCancel,
  onUploaded,
}: {
  diveUuid: string
  onCancel: () => void
  onUploaded: (uploadedCount: number) => void
}) {
  const [mode, setMode] = useState<Mode>('files')

  const [files, setFiles] = useState<File[]>([])
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvResult, setCsvResult] = useState<BrokerCsvImportResult | null>(null)

  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [formError, setFormError] = useState<string | null>(null)

  const handleFilesChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFiles(Array.from(e.target.files ?? []))
  }

  const handleZipChange = (e: ChangeEvent<HTMLInputElement>) => {
    setZipFile(e.target.files?.[0] ?? null)
  }

  const handleCsvChange = (e: ChangeEvent<HTMLInputElement>) => {
    setCsvFile(e.target.files?.[0] ?? null)
    setCsvResult(null)
  }

  const handleUploadBrokerCsv = async () => {
    if (uploading || !csvFile) return
    setFormError(null)
    setCsvResult(null)
    setUploading(true)
    try {
      const result = await uploadBrokerHandlesCsv(diveUuid, csvFile)
      setCsvResult(result)
      onUploaded(result.created)
    } catch (err: unknown) {
      setFormError(err instanceof ApiError ? err.message : 'Could not upload the CSV.')
    } finally {
      setUploading(false)
    }
  }

  const handleUploadFiles = async () => {
    if (uploading || files.length === 0) return
    setFormError(null)
    setUploading(true)
    setProgress(0)

    let uploadedCount = 0
    for (const file of files) {
      try {
        await createImage(diveUuid, file)
        uploadedCount += 1
        setProgress(uploadedCount)
      } catch (err: unknown) {
        setFormError(
          `Uploaded ${uploadedCount} of ${files.length} images before failing on "${file.name}": ${
            err instanceof ApiError ? err.message : 'Could not upload image.'
          }`,
        )
        setUploading(false)
        onUploaded(uploadedCount)
        return
      }
    }

    setUploading(false)
    onUploaded(uploadedCount)
  }

  const handleUploadZip = async () => {
    if (uploading || !zipFile) return
    setFormError(null)
    setUploading(true)
    try {
      const result = await uploadImagesZip(diveUuid, zipFile)
      onUploaded(result.created)
    } catch (err: unknown) {
      setFormError(err instanceof ApiError ? err.message : 'Could not upload the zip.')
    } finally {
      setUploading(false)
    }
  }

  const handleUpload = () => {
    if (mode === 'files') return handleUploadFiles()
    if (mode === 'zip') return handleUploadZip()
    return handleUploadBrokerCsv()
  }

  const canSubmit = mode === 'files' ? files.length > 0 : mode === 'zip' ? zipFile !== null : csvFile !== null

  return (
    <div className="stride-modal-backdrop" onClick={uploading ? undefined : onCancel}>
      <div
        className="stride-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-images-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="admin-form">
          <h3 id="upload-images-modal-title">Upload images</h3>
          <div className="upload-images-warning" role="alert">
            <span aria-hidden="true">⚠️</span>
            <span>
              <strong>Note:</strong> unless a uuid is supplied via an images.csv (zip mode only), each
              uploaded image is assigned a random uuid; the original filename is kept for display only.
            </span>
          </div>

          <div className="admin-form-field" role="radiogroup" aria-label="Upload mode">
            <label>
              <input
                type="radio"
                name="upload-mode"
                checked={mode === 'files'}
                disabled={uploading}
                onChange={() => setMode('files')}
              />{' '}
              Select images
            </label>
            <label>
              <input
                type="radio"
                name="upload-mode"
                checked={mode === 'zip'}
                disabled={uploading}
                onChange={() => setMode('zip')}
              />{' '}
              Zip archive
            </label>
            <label>
              <input
                type="radio"
                name="upload-mode"
                checked={mode === 'broker-csv'}
                disabled={uploading}
                onChange={() => setMode('broker-csv')}
              />{' '}
              Broker CSV
            </label>
          </div>

          {mode === 'files' ? (
            // ...existing files UI...
            <>
              <label className="admin-form-field">
                Select images
                <input type="file" accept="image/*" multiple disabled={uploading} onChange={handleFilesChange} />
              </label>
              {files.length > 0 && (
                <p className="game-status">
                  {uploading ? `Uploading ${progress} of ${files.length}…` : `${files.length} image(s) selected.`}
                </p>
              )}
            </>
          ) : mode === 'zip' ? (
            <>
              <label className="admin-form-field">
                Zip file
                <input type="file" accept=".zip,application/zip" disabled={uploading} onChange={handleZipChange} />
              </label>
              <p className="game-status">
                Non-image files in the zip are ignored. To assign specific uuids, include a
                semicolon-delimited <code>images.csv</code> at the root of the zip with columns{' '}
                <code>filename;uuid</code> - any image not listed there gets a random uuid.
              </p>
              {zipFile && <p className="game-status">{uploading ? 'Uploading…' : `Selected: ${zipFile.name}`}</p>}
            </>
          ) : (
            <>
              <label className="admin-form-field">
                Broker CSV file
                <input type="file" accept=".csv,text/csv" disabled={uploading} onChange={handleCsvChange} />
              </label>
              <p className="game-status">
                Semicolon-delimited CSV with columns:{' '}
                <code>filename;broker_url;broker_uuid;size_x;size_y</code>. Images are linked by
                URL — no bytes are stored locally. The{' '}
                <code>broker_uuid</code> is saved in the image metadata.
              </p>
              {csvFile && <p className="game-status">{uploading ? 'Importing…' : `Selected: ${csvFile.name}`}</p>}
              {csvResult && (
                <p className="game-status">
                  ✅ {csvResult.created} created, {csvResult.skipped} skipped.
                  {csvResult.errors.length > 0 && (
                    <> <strong>Errors:</strong> {csvResult.errors.join('; ')}</>
                  )}
                </p>
              )}
            </>
          )}

          {formError && <p className="game-status game-status-error">{formError}</p>}
          <div className="admin-form-actions">
            <button type="button" className="btn btn-primary" onClick={handleUpload} disabled={uploading || !canSubmit}>
              {uploading ? 'Uploading…' : 'Upload'}
            </button>
            <button type="button" className="btn" onClick={onCancel} disabled={uploading}>
              {uploading ? 'Close' : 'Cancel'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
