import type { GameId } from '../components/HomeScreen'
import { apiFetch } from './client'

/**
 * The caller's own story progression, persisted in the backend `story` field
 * (`GET`/`POST /api/v1/auth/story`). The field is free-form JSON; this is its
 * only consumer today, so we type just the keys we set. Merge, don't clobber,
 * when writing so future keys survive.
 */
export interface UserStory {
  /** Games whose first-play tutorial the user has already completed. */
  tutorialsSeen?: GameId[]
}

interface StoryResponse {
  story: UserStory | null
}

/** Returns the caller's stored story, or `null` if they have none yet. */
export async function fetchStory(): Promise<UserStory | null> {
  const { story } = await apiFetch<StoryResponse>('/api/v1/auth/story')
  return story
}

/** Overwrites the caller's whole story object. Pass the fully merged next value. */
export async function updateStory(story: UserStory): Promise<UserStory | null> {
  const res = await apiFetch<StoryResponse>('/api/v1/auth/story', {
    method: 'POST',
    body: JSON.stringify({ story }),
  })
  return res.story
}
