import { apiFetch, downloadFile } from './client'
import type { AnnotationSummary, CandidatePairSummary, DatasetImage, DatasetSummary, ImagePairSummary } from './types'

export interface PaginatedResult<T> {
  items: T[]
  total: number
}

/** Mirrors `DatasetImportCounts` from `backend/src/models/dataset.py`. */
export interface DatasetImportCounts {
  labels: number
  cameras: number
  regions: number
  dives: number
  images: number
  candidate_pairs: number
  image_pairs: number
  helper_images: number
  fun_facts: number
}

/** Scientist/admin only - counts of dives, images, and image pairs in the dataset. */
export function fetchDatasetSummary(): Promise<DatasetSummary> {
  return apiFetch<DatasetSummary>('/api/v1/dataset/summary')
}

/** Scientist only - real endpoint: POST /api/v1/dataset/zip-upload (multipart/form-data, field "file"). */
export function uploadDatasetZip(file: File): Promise<DatasetImportCounts> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<{ created: DatasetImportCounts }>('/api/v1/dataset/zip-upload', {
    method: 'POST',
    body: formData,
  }).then((res) => res.created)
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.slice(result.indexOf(',') + 1))
    }
    reader.onerror = () => reject(reader.error ?? new Error('Could not read file'))
    reader.readAsDataURL(file)
  })
}

/** Scientist only - real endpoint: POST /api/v1/dataset/images/create. Uploads one image (base64-encoded), always created with status "hidden". */
export async function createImage(diveUuid: string, file: File): Promise<DatasetImage> {
  const image = await fileToBase64(file)
  const res = await apiFetch<{
    uuid: string
    filename: string
    filepath: string
    status: string | null
    size_x: number
    size_y: number
  }>('/api/v1/dataset/images/create', {
    method: 'POST',
    body: JSON.stringify({
      uuid: crypto.randomUUID(),
      filename: file.name,
      filepath: `${diveUuid}/${crypto.randomUUID()}-${file.name}`,
      dive_uuid: diveUuid,
      image,
    }),
  })
  return res
}

export interface ImageZipImportResult {
  created: number
  skipped: number
}

export interface BrokerCsvImportResult {
  created: number
  skipped: number
  errors: string[]
}

/**
 * Scientist only - real endpoint: POST /api/v1/dataset/images/zip-upload (multipart/form-data,
 * fields "dive_uuid" and "file"). Every file in the zip is identified by its magic bytes; anything
 * that isn't a recognized image format is skipped rather than erroring. An optional
 * semicolon-delimited `images.csv` at the zip's root, with columns `filename` and `uuid`, assigns
 * specific uuids to specific filenames - everything else gets a random uuid. All images are
 * created with status "hidden".
 */
export function uploadImagesZip(diveUuid: string, zipFile: File): Promise<ImageZipImportResult> {
  const formData = new FormData()
  formData.append('dive_uuid', diveUuid)
  formData.append('file', zipFile)
  return apiFetch<ImageZipImportResult>('/api/v1/dataset/images/zip-upload', {
    method: 'POST',
    body: formData,
  })
}

/**
 * Scientist only - real endpoint: POST /api/v1/dataset/images/broker-csv-upload
 * (multipart/form-data, fields "dive_uuid" and "file").
 * The CSV must be semicolon-delimited with columns: filename, broker_url, broker_uuid, size_x, size_y.
 */
export function uploadBrokerHandlesCsv(diveUuid: string, csvFile: File): Promise<BrokerCsvImportResult> {
  const formData = new FormData()
  formData.append('dive_uuid', diveUuid)
  formData.append('file', csvFile)
  return apiFetch<BrokerCsvImportResult>('/api/v1/dataset/images/broker-csv-upload', {
    method: 'POST',
    body: formData,
  })
}

export interface ImagesPage extends PaginatedResult<DatasetImage> {
  hiddenCount: number
}

/** Scientist/admin only - real endpoint: GET /api/v1/dataset/images?dive={uuid}&page={page}&page_size={pageSize}. */
export function fetchImagesForDive(diveUuid: string, page: number, pageSize: number): Promise<ImagesPage> {
  return apiFetch<{ images: DatasetImage[]; total: number; hidden_count: number }>(
    `/api/v1/dataset/images?dive=${diveUuid}&page=${page}&page_size=${pageSize}`,
  ).then((res) => ({ items: res.images, total: res.total, hiddenCount: res.hidden_count }))
}

export interface CandidatePairsPage extends PaginatedResult<CandidatePairSummary> {
  hiddenCount: number
}

/** Scientist/admin only - real endpoint: GET /api/v1/dataset/candidates?dive={uuid}&page={page}&page_size={pageSize}. */
export function fetchCandidatePairsForDive(
  diveUuid: string,
  page: number,
  pageSize: number,
): Promise<CandidatePairsPage> {
  return apiFetch<{ candidates: CandidatePairSummary[]; total: number; hidden_count: number }>(
    `/api/v1/dataset/candidates?dive=${diveUuid}&page=${page}&page_size=${pageSize}`,
  ).then((res) => ({ items: res.candidates, total: res.total, hiddenCount: res.hidden_count }))
}

/** Scientist/admin only - real endpoint: GET /api/v1/dataset/pairs?dive={uuid}&page={page}&page_size={pageSize}. */
export function fetchImagePairsForDive(
  diveUuid: string,
  page: number,
  pageSize: number,
): Promise<PaginatedResult<ImagePairSummary>> {
  return apiFetch<{ pairs: ImagePairSummary[]; total: number }>(
    `/api/v1/dataset/pairs?dive=${diveUuid}&page=${page}&page_size=${pageSize}`,
  ).then((res) => ({ items: res.pairs, total: res.total }))
}

/** Scientist/admin only - real endpoint: GET /api/v1/dataset/annotations?dive={uuid}. */
export function fetchAnnotationsForDive(diveUuid: string): Promise<AnnotationSummary[]> {
  return apiFetch<{ annotations: AnnotationSummary[] }>(`/api/v1/dataset/annotations?dive=${diveUuid}`).then(
    (res) => res.annotations,
  )
}

export interface StrideCandidatePairResult {
  total_images: number
  pairs_considered: number
  pairs_created: number
  pairs_skipped: number
}

/** Scientist only - real endpoint: POST /api/v1/dataset/candidates/create-stride. */
export function createCandidatePairsByStride(
  diveUuid: string,
  stride: number,
  sortBy: 'filename' | 'filepath',
): Promise<StrideCandidatePairResult> {
  return apiFetch<StrideCandidatePairResult>('/api/v1/dataset/candidates/create-stride', {
    method: 'POST',
    body: JSON.stringify({ dive_uuid: diveUuid, stride, sort_by: sortBy }),
  })
}

export interface PublishCandidatesResult {
  published: number
  remaining_hidden: number
}

/** Scientist only - real endpoint: POST /api/v1/dataset/candidates/publish. Moves up to 100 hidden candidate pairs in the dive to "open", oldest first. Safe to call repeatedly. */
export function publishCandidatePairs(diveUuid: string): Promise<PublishCandidatesResult> {
  return apiFetch<PublishCandidatesResult>('/api/v1/dataset/candidates/publish', {
    method: 'POST',
    body: JSON.stringify({ dive_uuid: diveUuid }),
  })
}

export interface PublishImagesResult {
  published: number
  remaining_hidden: number
}

/** Scientist only - real endpoint: POST /api/v1/dataset/images/publish. Moves up to 100 hidden images in the dive to "open", oldest first. Safe to call repeatedly. */
export function publishImages(diveUuid: string): Promise<PublishImagesResult> {
  return apiFetch<PublishImagesResult>('/api/v1/dataset/images/publish', {
    method: 'POST',
    body: JSON.stringify({ dive_uuid: diveUuid }),
  })
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/annotations/export?dive={uuid}.
 * Exports raw point-annotation rows (one row per annotation, all statuses, with provenance) as
 * CSV and triggers a browser download.
 */
export function downloadAnnotationsCsv(diveUuid: string): Promise<void> {
  return downloadFile(
    `/api/v1/dataset/annotations/export?dive=${diveUuid}`,
    `point_annotations_${diveUuid}.csv`,
  )
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/full. Exports every content
 * table as CSV (internal ids dropped, foreign keys resolved to uuids) plus images/ and
 * helper_images/ folders, packaged as a zip.
 */
export function downloadFullDatasetZip(): Promise<void> {
  return downloadFile('/api/v1/dataset/export/full', 'dataset_export_full.zip')
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/full-csv-only. Same as
 * downloadFullDatasetZip, but without the images/ and helper_images/ asset folders - just the
 * CSVs. Use for large datasets where the asset files would make the full export impractically
 * large.
 */
export function downloadFullDatasetCsvOnlyZip(): Promise<void> {
  return downloadFile('/api/v1/dataset/export/full-csv-only', 'dataset_export_full_csv_only.zip')
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/points-flat?dive={uuid}.
 * Exports the point-annotation flat view (one row per annotation, joined to pair/image/dive/label
 * context) as CSV, optionally filtered to one dive.
 */
export function downloadPointAnnotationsFlatCsv(diveUuid?: string): Promise<void> {
  const qs = diveUuid ? `?dive=${diveUuid}` : ''
  return downloadFile(
    `/api/v1/dataset/export/points-flat${qs}`,
    `point_annotations_flat${diveUuid ? `_${diveUuid}` : ''}.csv`,
  )
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/candidates-flat?dive={uuid}.
 * Exports the candidate-annotation flat view as CSV, optionally filtered to one dive.
 */
export function downloadCandidateAnnotationsFlatCsv(diveUuid?: string): Promise<void> {
  const qs = diveUuid ? `?dive=${diveUuid}` : ''
  return downloadFile(
    `/api/v1/dataset/export/candidates-flat${qs}`,
    `candidate_annotations_flat${diveUuid ? `_${diveUuid}` : ''}.csv`,
  )
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/fun-facts. Exports fun_facts as
 * CSV only (no images).
 */
export function downloadFunFactsCsv(): Promise<void> {
  return downloadFile('/api/v1/dataset/export/fun-facts', 'fun_facts.csv')
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/fun-facts-zip. Exports
 * fun_facts as CSV plus a helper_images/ folder with only the images referenced by an exported
 * fun fact.
 */
export function downloadFunFactsZip(): Promise<void> {
  return downloadFile('/api/v1/dataset/export/fun-facts-zip', 'fun_facts.zip')
}

/**
 * Scientist/admin only - real endpoint: GET /api/v1/dataset/export/dive?dive={uuid}. Exports
 * points.csv + candidates.csv + all of the dive's images as a zip.
 */
export function downloadDiveZip(diveUuid: string): Promise<void> {
  return downloadFile(`/api/v1/dataset/export/dive?dive=${diveUuid}`, `dive_export_${diveUuid}.zip`)
}
