import { useEffect, useState } from 'react'
import { ApiError, assetUrl } from '../../api/client'
import {
  downloadAnnotationsCsv,
  downloadCandidateAnnotationsFlatCsv,
  downloadDiveZip,
  downloadFullDatasetCsvOnlyZip,
  downloadFullDatasetZip,
  downloadFunFactsCsv,
  downloadFunFactsZip,
  downloadPointAnnotationsFlatCsv,
  fetchAnnotationsForDive,
  fetchCandidatePairsForDive,
  fetchImagePairsForDive,
  fetchImagesForDive,
  publishCandidatePairs,
} from '../../api/datasetApi'
import type { PublishCandidatesResult, StrideCandidatePairResult } from '../../api/datasetApi'
import { fetchDivesForRegion } from '../../api/diveApi'
import { fetchRegions } from '../../api/regionApi'
import type { AnnotationSummary, CandidatePairSummary, DatasetImage, Dive, ImagePairSummary, Region } from '../../api/types'
import CreateStrideCandidatePairsModal from './CreateStrideCandidatePairsModal'
import UploadImagesModal from './UploadImagesModal'
import '../admin/AdminPanels.css'
import './DatasetAdmin.css'

const PAGE_SIZE = 25

function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  if (pageCount <= 1) return null
  return (
    <div className="dataset-admin-pagination">
      <button type="button" className="btn" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
        Previous
      </button>
      <span>
        Page {page} of {pageCount} ({total} total)
      </span>
      <button type="button" className="btn" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount}>
        Next
      </button>
    </div>
  )
}

export default function DatasetAdmin() {
  const [regions, setRegions] = useState<Region[] | null>(null)
  const [regionUuid, setRegionUuid] = useState('')
  const [dives, setDives] = useState<Dive[] | null>(null)
  const [diveUuid, setDiveUuid] = useState('')

  const [images, setImages] = useState<DatasetImage[] | null>(null)
  const [imagesTotal, setImagesTotal] = useState(0)
  const [imagesPage, setImagesPage] = useState(1)

  const [candidates, setCandidates] = useState<CandidatePairSummary[] | null>(null)
  const [candidatesTotal, setCandidatesTotal] = useState(0)
  const [candidatesHiddenCount, setCandidatesHiddenCount] = useState(0)
  const [candidatesPage, setCandidatesPage] = useState(1)

  const [pairs, setPairs] = useState<ImagePairSummary[] | null>(null)
  const [pairsTotal, setPairsTotal] = useState(0)
  const [pairsPage, setPairsPage] = useState(1)

  const [annotations, setAnnotations] = useState<AnnotationSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [strideModalOpen, setStrideModalOpen] = useState(false)
  const [strideResult, setStrideResult] = useState<StrideCandidatePairResult | null>(null)

  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadResult, setUploadResult] = useState<number | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [publishResult, setPublishResult] = useState<PublishCandidatesResult | null>(null)
  const [publishError, setPublishError] = useState<string | null>(null)

  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const [globalDownloading, setGlobalDownloading] = useState(false)
  const [globalDownloadError, setGlobalDownloadError] = useState<string | null>(null)

  useEffect(() => {
    fetchRegions()
      .then(setRegions)
      .catch(() => setError('Could not load regions.'))
  }, [])

  useEffect(() => {
    setDives(null)
    setDiveUuid('')
    if (!regionUuid) return
    fetchDivesForRegion(regionUuid)
      .then(setDives)
      .catch(() => setError('Could not load dives for this region.'))
  }, [regionUuid])

  useEffect(() => {
    setImages(null)
    setImagesTotal(0)
    setImagesPage(1)
    setCandidates(null)
    setCandidatesTotal(0)
    setCandidatesHiddenCount(0)
    setCandidatesPage(1)
    setPairs(null)
    setPairsTotal(0)
    setPairsPage(1)
    setAnnotations(null)
  }, [diveUuid])

  const loadImages = () => {
    if (!diveUuid) return
    fetchImagesForDive(diveUuid, imagesPage, PAGE_SIZE)
      .then(({ items, total }) => {
        setImages(items)
        setImagesTotal(total)
      })
      .catch(() => setError('Could not load images for this dive.'))
  }

  useEffect(loadImages, [diveUuid, imagesPage])

  const loadCandidatePairs = () => {
    if (!diveUuid) return
    fetchCandidatePairsForDive(diveUuid, candidatesPage, PAGE_SIZE)
      .then(({ items, total, hiddenCount }) => {
        setCandidates(items)
        setCandidatesTotal(total)
        setCandidatesHiddenCount(hiddenCount)
      })
      .catch(() => setError('Could not load candidate pairs for this dive.'))
  }

  useEffect(loadCandidatePairs, [diveUuid, candidatesPage])

  const handlePublish = () => {
    if (!diveUuid || publishing) return
    setPublishing(true)
    setPublishError(null)
    publishCandidatePairs(diveUuid)
      .then((result) => {
        setPublishResult(result)
        loadCandidatePairs()
      })
      .catch((err: unknown) => {
        setPublishError(err instanceof ApiError ? err.message : 'Could not publish candidate pairs.')
      })
      .finally(() => setPublishing(false))
  }

  const handlePublishAll = async () => {
    if (!diveUuid || publishing) return
    setPublishing(true)
    setPublishError(null)
    try {
      let totalPublished = 0
      let remainingHidden: number
      do {
        const result = await publishCandidatePairs(diveUuid)
        totalPublished += result.published
        remainingHidden = result.remaining_hidden
        if (result.published === 0) break
      } while (remainingHidden > 0)
      setPublishResult({ published: totalPublished, remaining_hidden: remainingHidden })
      loadCandidatePairs()
    } catch (err) {
      setPublishError(err instanceof ApiError ? err.message : 'Could not publish candidate pairs.')
    } finally {
      setPublishing(false)
    }
  }

  useEffect(() => {
    if (!diveUuid) return
    fetchImagePairsForDive(diveUuid, pairsPage, PAGE_SIZE)
      .then(({ items, total }) => {
        setPairs(items)
        setPairsTotal(total)
      })
      .catch(() => setError('Could not load image pairs for this dive.'))
  }, [diveUuid, pairsPage])

  useEffect(() => {
    if (!diveUuid) return
    fetchAnnotationsForDive(diveUuid)
      .then(setAnnotations)
      .catch(() => setError('Could not load annotations for this dive.'))
  }, [diveUuid])

  const annotationsFor = (pair: ImagePairSummary) =>
    (annotations ?? []).filter((a) => a.image_a === pair.image_a && a.image_b === pair.image_b)

  const runDiveDownload = (action: () => Promise<void>, errorMessage: string) => {
    if (!diveUuid || downloading) return
    setDownloading(true)
    setDownloadError(null)
    action()
      .catch((err: unknown) => {
        setDownloadError(err instanceof ApiError ? err.message : errorMessage)
      })
      .finally(() => setDownloading(false))
  }

  const runGlobalDownload = (action: () => Promise<void>, errorMessage: string) => {
    if (globalDownloading) return
    setGlobalDownloading(true)
    setGlobalDownloadError(null)
    action()
      .catch((err: unknown) => {
        setGlobalDownloadError(err instanceof ApiError ? err.message : errorMessage)
      })
      .finally(() => setGlobalDownloading(false))
  }

  const handleDownload = () => runDiveDownload(() => downloadAnnotationsCsv(diveUuid), 'Could not download the CSV.')
  const handleDownloadPointsFlat = () =>
    runDiveDownload(() => downloadPointAnnotationsFlatCsv(diveUuid), 'Could not download the CSV.')
  const handleDownloadCandidatesFlat = () =>
    runDiveDownload(() => downloadCandidateAnnotationsFlatCsv(diveUuid), 'Could not download the CSV.')
  const handleDownloadDiveZip = () => runDiveDownload(() => downloadDiveZip(diveUuid), 'Could not download the zip.')

  const handleDownloadFullDataset = () =>
    runGlobalDownload(() => downloadFullDatasetZip(), 'Could not download the dataset zip.')
  const handleDownloadFullDatasetCsvOnly = () =>
    runGlobalDownload(() => downloadFullDatasetCsvOnlyZip(), 'Could not download the dataset zip.')
  const handleDownloadFunFactsCsv = () =>
    runGlobalDownload(() => downloadFunFactsCsv(), 'Could not download the CSV.')
  const handleDownloadFunFactsZip = () =>
    runGlobalDownload(() => downloadFunFactsZip(), 'Could not download the zip.')

  return (
    <div className="dataset-admin">
      {error && <p className="game-status game-status-error">{error}</p>}

      <div className="dataset-admin-toolbar dataset-admin-toolbar-global">
        <button type="button" className="btn" onClick={handleDownloadFullDataset} disabled={globalDownloading}>
          {globalDownloading ? 'Downloading…' : 'Download full dataset (zip)'}
        </button>
        <button type="button" className="btn" onClick={handleDownloadFullDatasetCsvOnly} disabled={globalDownloading}>
          {globalDownloading ? 'Downloading…' : 'Download full dataset - CSVs only (zip)'}
        </button>
        <button type="button" className="btn" onClick={handleDownloadFunFactsCsv} disabled={globalDownloading}>
          {globalDownloading ? 'Downloading…' : 'Download fun facts (CSV)'}
        </button>
        <button type="button" className="btn" onClick={handleDownloadFunFactsZip} disabled={globalDownloading}>
          {globalDownloading ? 'Downloading…' : 'Download fun facts + images (zip)'}
        </button>
        {globalDownloadError && <p className="game-status game-status-error">{globalDownloadError}</p>}
      </div>

      <div className="dataset-admin-pickers">
        <label className="admin-form-field">
          Region
          <select value={regionUuid} onChange={(e) => setRegionUuid(e.target.value)}>
            <option value="">Select a region…</option>
            {(regions ?? []).map((region) => (
              <option key={region.uuid} value={region.uuid}>
                {region.title}
              </option>
            ))}
          </select>
        </label>

        <label className="admin-form-field">
          Dive
          <select
            value={diveUuid}
            onChange={(e) => setDiveUuid(e.target.value)}
            disabled={!regionUuid || dives === null || dives.length === 0}
          >
            <option value="">
              {!regionUuid
                ? 'Select a region first'
                : dives === null
                  ? 'Loading…'
                  : dives.length === 0
                    ? 'No dives in this region'
                    : 'Select a dive…'}
            </option>
            {(dives ?? []).map((dive) => (
              <option key={dive.uuid} value={dive.uuid}>
                {dive.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      {diveUuid && (
        <>
          <div className="dataset-admin-toolbar">
            <button type="button" className="btn" onClick={handleDownload} disabled={downloading}>
              {downloading ? 'Downloading…' : 'Download point annotations (CSV)'}
            </button>
            <button type="button" className="btn" onClick={handleDownloadPointsFlat} disabled={downloading}>
              {downloading ? 'Downloading…' : 'Download points (flat CSV)'}
            </button>
            <button type="button" className="btn" onClick={handleDownloadCandidatesFlat} disabled={downloading}>
              {downloading ? 'Downloading…' : 'Download candidates (flat CSV)'}
            </button>
            <button type="button" className="btn" onClick={handleDownloadDiveZip} disabled={downloading}>
              {downloading ? 'Downloading…' : 'Download dive export (zip)'}
            </button>
            {downloadError && <p className="game-status game-status-error">{downloadError}</p>}
          </div>

          <section className="dataset-admin-section">
            <div className="dataset-admin-section-header">
              <h3>Images ({imagesTotal})</h3>
              <button type="button" className="btn" onClick={() => setUploadModalOpen(true)}>
                Upload images…
              </button>
            </div>
            {uploadResult !== null && (
              <p className="game-status">Uploaded {uploadResult} image(s).</p>
            )}
            {images === null ? (
              <p className="game-status">Loading…</p>
            ) : (
              <>
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Preview</th>
                      <th>Filename</th>
                      <th>Status</th>
                      <th>Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {images.map((image) => (
                      <tr key={image.uuid}>
                        <td>
                          <img src={assetUrl(image.filepath)} alt={image.filename} className="dataset-admin-thumb" />
                        </td>
                        <td>{image.filename}</td>
                        <td>{image.status ?? '—'}</td>
                        <td>
                          {image.size_x} × {image.size_y}
                        </td>
                      </tr>
                    ))}
                    {images.length === 0 && (
                      <tr>
                        <td colSpan={4}>No images in this dive yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
                <Pagination page={imagesPage} pageSize={PAGE_SIZE} total={imagesTotal} onPageChange={setImagesPage} />
              </>
            )}
          </section>

          <section className="dataset-admin-section">
            <div className="dataset-admin-section-header">
              <h3>Candidate pairs ({candidatesTotal})</h3>
              <div className="dataset-admin-section-actions">
                <button type="button" className="btn" onClick={() => setStrideModalOpen(true)}>
                  Create pairs by stride…
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={handlePublish}
                  disabled={candidatesHiddenCount === 0 || publishing}
                >
                  {publishing ? 'Publishing…' : `Publish up to 100 (${candidatesHiddenCount} hidden)`}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={handlePublishAll}
                  disabled={candidatesHiddenCount === 0 || publishing}
                >
                  {publishing ? 'Publishing…' : 'Publish all'}
                </button>
              </div>
            </div>
            {strideResult && (
              <p className="game-status">
                Created {strideResult.pairs_created} new candidate pairs ({strideResult.pairs_skipped} already
                existed).
              </p>
            )}
            {publishResult && (
              <p className="game-status">
                Published {publishResult.published} candidate pairs ({publishResult.remaining_hidden} still hidden).
              </p>
            )}
            {publishError && <p className="game-status game-status-error">{publishError}</p>}
            {candidates === null ? (
              <p className="game-status">Loading…</p>
            ) : (
              <>
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Image A</th>
                      <th>Image B</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((pair) => (
                      <tr key={`${pair.image_a}:${pair.image_b}`}>
                        <td>{pair.image_a_filename}</td>
                        <td>{pair.image_b_filename}</td>
                        <td>{pair.status ?? '—'}</td>
                      </tr>
                    ))}
                    {candidates.length === 0 && (
                      <tr>
                        <td colSpan={3}>No candidate pairs in this dive yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
                <Pagination
                  page={candidatesPage}
                  pageSize={PAGE_SIZE}
                  total={candidatesTotal}
                  onPageChange={setCandidatesPage}
                />
              </>
            )}
          </section>

          <section className="dataset-admin-section">
            <h3>Image pairs ({pairsTotal})</h3>
            {pairs === null ? (
              <p className="game-status">Loading…</p>
            ) : (
              <>
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Image A</th>
                      <th>Image B</th>
                      <th>Difficulty</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Annotations</th>
                      <th>Expert levels</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairs.map((pair) => {
                      const pairAnnotations = annotationsFor(pair)
                      return (
                        <tr key={`${pair.image_a}:${pair.image_b}`}>
                          <td>{pair.image_a_filename}</td>
                          <td>{pair.image_b_filename}</td>
                          <td>{pair.difficulty ?? '—'}</td>
                          <td>{pair.priority ?? '—'}</td>
                          <td>{pair.status ?? '—'}</td>
                          <td>{pairAnnotations.length === 0 ? 'None' : pairAnnotations.length}</td>
                          <td>
                            {pairAnnotations.length === 0
                              ? '—'
                              : pairAnnotations.map((a) => a.expert_level).join(', ')}
                          </td>
                        </tr>
                      )
                    })}
                    {pairs.length === 0 && (
                      <tr>
                        <td colSpan={7}>No image pairs in this dive yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
                <Pagination page={pairsPage} pageSize={PAGE_SIZE} total={pairsTotal} onPageChange={setPairsPage} />
              </>
            )}
          </section>
        </>
      )}

      {uploadModalOpen && (
        <UploadImagesModal
          diveUuid={diveUuid}
          onCancel={() => setUploadModalOpen(false)}
          onUploaded={(uploadedCount) => {
            setUploadResult(uploadedCount)
            setUploadModalOpen(false)
            if (imagesPage === 1) {
              loadImages()
            } else {
              setImagesPage(1)
            }
          }}
        />
      )}

      {strideModalOpen && (
        <CreateStrideCandidatePairsModal
          diveUuid={diveUuid}
          onCancel={() => setStrideModalOpen(false)}
          onCreated={(result) => {
            setStrideResult(result)
            setStrideModalOpen(false)
            // If already on page 1, changing the page is a no-op, so refetch directly;
            // otherwise resetting the page triggers the existing effect to refetch.
            if (candidatesPage === 1) {
              loadCandidatePairs()
            } else {
              setCandidatesPage(1)
            }
          }}
        />
      )}
    </div>
  )
}
