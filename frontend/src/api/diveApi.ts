import { apiFetch } from './client'
import type { Dive } from './types'

/** Real endpoint: GET /api/v1/annotate/dives?region={uuid}. Any authenticated role. */
export function fetchDivesForRegion(regionUuid: string): Promise<Dive[]> {
  return apiFetch<{ dives: Dive[] }>(`/api/v1/annotate/dives?region=${regionUuid}`).then((res) => res.dives)
}

export interface DiveMetadataInput {
  [key: string]: unknown
}

/** Scientist/admin only - real endpoint: POST /api/v1/dataset/dives/create. */
export function createDive(input: {
  title: string
  description?: string | null
  metadata?: DiveMetadataInput | null
  region: string
}): Promise<Dive> {
  return apiFetch<Dive>('/api/v1/dataset/dives/create', {
    method: 'POST',
    body: JSON.stringify({ uuid: crypto.randomUUID(), ...input }),
  })
}

/** Scientist/admin only - real endpoint: POST /api/v1/dataset/dives/update. */
export function updateDive(
  uuid: string,
  input: { title?: string; description?: string | null; metadata?: DiveMetadataInput | null },
): Promise<Dive> {
  return apiFetch<Dive>('/api/v1/dataset/dives/update', {
    method: 'POST',
    body: JSON.stringify({ uuid, ...input }),
  })
}
