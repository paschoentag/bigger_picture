export type Role = 'annotator' | 'scientist' | 'admin'

/** Mirrors `UserResponse` from `backend/src/models/auth.py`. */
export interface User {
  id: number
  uuid: string
  username: string
  role: Role
  expert_level: number
  exp: number
  created_at: number
}

/** Mirrors `UserSummary` from `backend/src/models/admin.py`. */
export interface UserSummary {
  uuid: string
  username: string
  role: Role
  expert_level: number
}

/** Mirrors `LabelResponse` from `backend/src/models/annotate.py`. */
export interface Label {
  uuid: string
  scope: string
  title: string
  description: string | null
}

/** Mirrors `HelperImageResponse` from `backend/src/models/dataset.py`. */
export interface HelperImage {
  uuid: string
  filename: string
  filepath: string
}

/** A single cited source backing a fun fact. */
export interface FunFactSource {
  url: string
}

/**
 * The free-form JSON body stored per fun fact (the `fact` field of
 * `FunFactResponse`): the fact text plus optional cited sources.
 */
export interface FunFactBody {
  fact: string
  sources?: FunFactSource[]
}

/** Mirrors `FunFactResponse` from `backend/src/models/dataset.py`. */
export interface FunFact {
  uuid: string
  title: string
  fact: FunFactBody
  min_level: number
  region: string | null
  image: HelperImage | null
}

/** Mirrors `DatasetSummaryResponse` from `backend/src/models/dataset.py`. */
export interface DatasetSummary {
  dive_count: number
  image_count: number
  image_pair_count: number
}

/** GeoJSON polygon geometry, stored under `Region.metadata.mesh`. */
export interface RegionMesh {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: number[][][] | number[][][][]
}

/** Mirrors `RegionResponse` from `backend/src/models/dataset.py`. */
export interface Region {
  uuid: string
  title: string
  description: string | null
  metadata: ({ mesh?: RegionMesh } & Record<string, unknown>) | null
}

/** Mirrors `DiveResponse` from `backend/src/models/dataset.py`, as returned by `GET /api/v1/annotate/dives` and `GET /api/v1/dataset/dives`. */
export interface Dive {
  uuid: string
  created_at: number
  created_by: string
  title: string
  metadata: Record<string, unknown> | null
  description: string | null
  region: string
  camera: string
}

/** Mirrors `ImageResponse` from `backend/src/models/dataset.py`, as returned by `GET /api/v1/dataset/images`. */
export interface DatasetImage {
  uuid: string
  filename: string
  filepath: string
  status: string | null
  size_x: number
  size_y: number
}

/** Mirrors `CandidatePairResponse` from `backend/src/models/dataset.py`, as returned by `GET /api/v1/dataset/candidates`. */
export interface CandidatePairSummary {
  image_a: string
  image_b: string
  image_a_filename: string
  image_b_filename: string
  status: string | null
}

/** Mirrors `ImagePairResponse` from `backend/src/models/dataset.py`, as returned by `GET /api/v1/dataset/pairs`. */
export interface ImagePairSummary {
  image_a: string
  image_b: string
  image_a_filename: string
  image_b_filename: string
  difficulty: number | null
  priority: number | null
  status: string | null
}

/** Mirrors `PointAnnotationResponse` from `backend/src/models/annotate.py`, as returned by `GET /api/v1/dataset/annotations`. */
export interface AnnotationSummary {
  uuid: string
  image_a: string
  image_b: string
  expert_level: number
  status: string
}

export interface ImagePair {
  pairId: string
  imageA: string
  imageB: string
  /** Real backend image uuids for `image_a`/`image_b` in `PointAnnotationCreateRequest`. */
  imageAUuid: string
  imageBUuid: string
}

export interface CandidatePair {
  candidateId: string
  imageA: string
  imageB: string
  /** Real backend image uuids for `image_a`/`image_b` in `CandidateAnnotationCreateRequest`. */
  imageAUuid: string
  imageBUuid: string
}

/** A click location, normalized to the image's own [0, 1] x [0, 1] space. */
export interface NormalizedPoint {
  x: number
  y: number
}

export interface Correspondence {
  pointA: NormalizedPoint
  pointB: NormalizedPoint
}

/** A single already-submitted correspondence awaiting Stage 3 review. */
export interface VerificationPoint extends Correspondence {
  /** Real backend `PointAnnotation.uuid`, the id `points/review/{uuid}/...` acts on. */
  pointUuid: string
}

/** A Stage 2 annotation awaiting Stage 3 review. */
export interface PendingVerification {
  annotationId: string
  imageA: string
  imageB: string
  correspondences: VerificationPoint[]
}
