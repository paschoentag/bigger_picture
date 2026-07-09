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
  /** Exp the player will gain once their pending (unreviewed) submissions are approved. */
  unconfirmed_exp: number
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
