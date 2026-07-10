import { apiFetch } from './client'
import type { Role, UserSummary } from './types'

/** Mirrors `FunFactImportResponse` from `backend/src/models/admin.py`. */
export interface FunFactImportCounts {
  created: number
  updated: number
}

/** Admin only - real endpoint: POST /api/v1/admin/fun-facts/import (multipart/form-data, field "file"). */
export function uploadFunFactsZip(file: File): Promise<FunFactImportCounts> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<FunFactImportCounts>('/api/v1/admin/fun-facts/import', {
    method: 'POST',
    body: formData,
  })
}

/** Admin only - lists every registered user. */
export function listUsers(): Promise<UserSummary[]> {
  return apiFetch<{ users: UserSummary[] }>('/api/v1/admin/users').then((res) => res.users)
}

/**
 * Admin only - real endpoint: POST /api/v1/admin/users/create.
 * `password` is required for every new user, regardless of role.
 */
export function createUser(
  input: { username: string; role: Role; expert_level: number; password: string },
): Promise<UserSummary> {
  return apiFetch<UserSummary>('/api/v1/admin/users/create', {
    method: 'POST',
    body: JSON.stringify({ uuid: crypto.randomUUID(), ...input }),
  })
}

/**
 * Admin only - real endpoint: POST /api/v1/admin/users/update.
 * `password` sets/replaces the stored credential; omit to leave it untouched.
 */
export function updateUser(
  uuid: string,
  input: { username?: string; role?: Role; expert_level?: number; password?: string },
): Promise<UserSummary> {
  return apiFetch<UserSummary>('/api/v1/admin/users/update', {
    method: 'POST',
    body: JSON.stringify({ uuid, ...input }),
  })
}
