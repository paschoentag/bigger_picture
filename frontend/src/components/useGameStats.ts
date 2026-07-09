import { useCallback, useEffect, useState } from 'react'
import { fetchMyStats } from '../api/statsApi'
import type { MyStats } from '../api/statsApi'
import type { GameId } from './HomeScreen'

/** The stat slice for a single game, e.g. `MyStats['overlap']`. */
export type GameSlice<G extends GameId = GameId> = MyStats[G]

/** Numeric counter keys of a game's slice (excludes the nested accuracy objects). */
type CounterKeys<G extends GameId> = {
  [K in keyof GameSlice<G>]: GameSlice<G>[K] extends number ? K : never
}[keyof GameSlice<G>]

/** Integer deltas to optimistically add to a game's counters after a submit. */
export type StatDeltas<G extends GameId> = Partial<Record<CounterKeys<G>, number>>

export interface UseGameStats<G extends GameId> {
  /** This game's counters, or null while loading (or if the fetch failed). */
  stats: GameSlice<G> | null
  /** Window size backing the recent-accuracy stats, or null before load. */
  window: number | null
  /** Exp pending confirmation from other players' reviews, or null before load. */
  unconfirmedExp: number | null
  /** Optimistically add integer deltas to this game's counters, then reconcile from the server. */
  bump: (deltas: StatDeltas<G>) => void
}

/**
 * Loads the signed-in player's stats and exposes the slice for a single game plus a
 * `bump` that applies optimistic counter increments. XP is deliberately not touched
 * here — it only moves once other players confirm the work (via `onUserRefresh`).
 */
export function useGameStats<G extends GameId>(game: G): UseGameStats<G> {
  const [stats, setStats] = useState<MyStats | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchMyStats()
      .then((s) => {
        if (!cancelled) setStats(s)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const bump = useCallback(
    (deltas: StatDeltas<G>) => {
      // Apply the delta immediately for snappy "+N" feedback...
      setStats((prev) => {
        if (!prev) return prev
        const nextSlice = { ...prev[game] } as Record<string, unknown>
        for (const key of Object.keys(deltas)) {
          const delta = (deltas as Record<string, number | undefined>)[key]
          if (typeof delta === 'number' && typeof nextSlice[key] === 'number') {
            nextSlice[key] = (nextSlice[key] as number) + delta
          }
        }
        return { ...prev, [game]: nextSlice as unknown as GameSlice<G> }
      })
      // ...then reconcile with the server, which also refreshes unconfirmed exp.
      fetchMyStats()
        .then(setStats)
        .catch(() => {})
    },
    [game],
  )

  return {
    stats: stats ? (stats[game] as GameSlice<G>) : null,
    window: stats ? stats.window : null,
    unconfirmedExp: stats ? stats.unconfirmed_exp : null,
    bump,
  }
}
