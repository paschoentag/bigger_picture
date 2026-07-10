import { apiFetch } from './client'

/** Mirrors `AccuracyStat` from `backend/src/models/annotate.py`. */
export interface AccuracyStat {
  correct: number
  reviewed: number
  /** correct / reviewed, or null when nothing has been reviewed yet. */
  accuracy: number | null
}

/** Format an accuracy fraction as a percentage, or "n/a" when nothing is reviewed yet. */
export function formatAccuracy(stat: AccuracyStat): string {
  if (stat.accuracy === null) return 'n/a'
  return `${Math.round(stat.accuracy * 100)}%`
}

/** Mirrors `OverlapStats` from `backend/src/models/annotate.py`. */
export interface OverlapStats {
  pairs_marked: number
  overlaps_found: number
  overall_pairs_with_overlap: number
  accuracy_all_time: AccuracyStat
  accuracy_window: AccuracyStat
}

/** Mirrors `AnnotateStats` from `backend/src/models/annotate.py`. */
export interface AnnotateStats {
  annotations: number
  annotations_verified: number
  pairs_marked: number
  pairs_verified: number
  accuracy_all_time: AccuracyStat
  accuracy_window: AccuracyStat
}

/** Mirrors `VerifyStats` from `backend/src/models/annotate.py`. */
export interface VerifyStats {
  verified: number
  accepted: number
  faulty_found: number
}

/** Mirrors `MyStatsResponse` from `backend/src/models/annotate.py`. */
export interface MyStats {
  window: number
  overlap: OverlapStats
  annotate: AnnotateStats
  verify: VerifyStats
}

/**
 * Real endpoint: GET /api/v1/annotate/stats/me. Returns the signed-in player's
 * own counters and accuracies across all three game stages. `window` bounds the
 * recent-annotation window used for the windowed accuracies (default 100).
 */
export function fetchMyStats(window?: number): Promise<MyStats> {
  const query = window !== undefined ? `?window=${window}` : ''
  return apiFetch<MyStats>(`/api/v1/annotate/stats/me${query}`)
}

/** Mirrors `CommunityOverlapStats` from `backend/src/models/annotate.py`. */
export interface CommunityOverlapStats {
  votes_cast: number
  pairs_with_overlap: number
  pairs_no_overlap: number
  pairs_still_open: number
}

/** Mirrors `CommunityAnnotateStats` from `backend/src/models/annotate.py`. */
export interface CommunityAnnotateStats {
  points_submitted: number
  points_verified: number
  points_pending_review: number
  pairs_annotated: number
}

/** Mirrors `CommunityVerifyStats` from `backend/src/models/annotate.py`. */
export interface CommunityVerifyStats {
  reviews_completed: number
  accepted: number
  rejected: number
}

/** Mirrors `CommunityStatsResponse` from `backend/src/models/annotate.py`. */
export interface CommunityStats {
  users_total: number
  regions_total: number
  dives_total: number
  images_total: number
  overlap: CommunityOverlapStats
  annotate: CommunityAnnotateStats
  verify: CommunityVerifyStats
}

/**
 * Real endpoint: GET /api/v1/annotate/stats/overall. Returns aggregate,
 * site-wide statistics across the whole database - dataset size plus totals
 * for all three game stages, summed over every player rather than scoped to
 * the caller.
 */
export function fetchCommunityStats(): Promise<CommunityStats> {
  return apiFetch<CommunityStats>('/api/v1/annotate/stats/overall')
}
