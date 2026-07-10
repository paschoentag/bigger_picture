import { useEffect, useRef, useState } from 'react'
import { fetchStory, updateStory, type UserStory } from '../../api/storyApi'
import type { GameId } from '../HomeScreen'

/**
 * Drives a game's first-play tutorial. On mount it reads the user's stored
 * story and shows the tutorial only if this game hasn't been completed before.
 * `show` starts false and flips true only after the fetch resolves, so users
 * who have already seen it get no flash of the modal.
 *
 * `complete()` hides the modal and records this game as seen (merge-write, so
 * other story keys survive). The write is fire-and-forget: if it fails the
 * tutorial simply shows once more next time.
 */
export function useTutorial(game: GameId) {
  const [show, setShow] = useState(false)
  const storyRef = useRef<UserStory | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchStory()
      .then((story) => {
        if (cancelled) return
        storyRef.current = story
        if (!(story?.tutorialsSeen ?? []).includes(game)) {
          setShow(true)
        }
      })
      .catch(() => {
        // Can't tell if it's been seen; don't interrupt play.
      })
    return () => {
      cancelled = true
    }
  }, [game])

  const complete = () => {
    setShow(false)
    const seen = storyRef.current?.tutorialsSeen ?? []
    if (seen.includes(game)) return
    const next: UserStory = { ...storyRef.current, tutorialsSeen: [...seen, game] }
    storyRef.current = next
    updateStory(next).catch(() => {
      // Non-fatal: the tutorial may reappear on the next visit.
    })
  }

  return { show, complete }
}
