import { useCallback, useEffect, useState } from 'react'
import { fetchDivesForRegion } from '../api/diveApi'
import { fetchNextCandidatePair, submitOverlapDecision } from '../api/overlapApi'
import type { CandidatePair, Region, User } from '../api/types'
import { GridOverlay } from './GridOverlay'
import type { GridSize } from './gridSize'
import { gridToggleLabel, nextGridSize } from './gridSize'
import { GameStatsBar } from './GameStatsBar'
import AccountBar from './AccountBar'
import { useGameStats } from './useGameStats'
import { useFunFactTrigger } from './useFunFactTrigger'
import FunFactModal from './FunFactModal'
import OverlapTutorial from './tutorials/OverlapTutorial'
import { useTutorial } from './tutorials/useTutorial'

export default function OverlapGame({
  region,
  user,
  onUserRefresh,
  onBack,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  region: Region
  user: User
  onUserRefresh: () => void
  onBack: () => void
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenQuests: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  // undefined = still resolving a dive for this region; null = region has no dives yet.
  const [diveUuid, setDiveUuid] = useState<string | null | undefined>(undefined)
  const [pair, setPair] = useState<CandidatePair | null>(null)
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewedCount, setReviewedCount] = useState(0)
  const [gridSize, setGridSize] = useState<GridSize>(0)
  const { stats, window: statsWindow, bump } = useGameStats('overlap')
  const { fact, recordCompletion, dismiss } = useFunFactTrigger(region.uuid)
  const { show: showTutorial, complete: completeTutorial } = useTutorial('overlap')

  useEffect(() => {
    setDiveUuid(undefined)
    setLoading(true)
    setError(null)
    fetchDivesForRegion(region.uuid)
      .then((dives) => setDiveUuid(dives[0]?.uuid ?? null))
      .catch(() => setError('Could not load dive imagery for this region. Please try again.'))
  }, [region.uuid])

  const loadNextPair = useCallback((forDiveUuid: string) => {
    setLoading(true)
    setError(null)
    fetchNextCandidatePair(forDiveUuid)
      .then((next) => {
        setPair(next)
        setDone(next === null)
      })
      .catch(() => setError('Could not load an image pair. Please try again.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (diveUuid) {
      loadNextPair(diveUuid)
    } else if (diveUuid === null) {
      setLoading(false)
    }
  }, [diveUuid, loadNextPair])

  const handleDecision = (overlaps: boolean) => {
    if (!pair || !diveUuid || submitting) return
    setSubmitting(true)
    setError(null)
    submitOverlapDecision(pair, overlaps)
      .then(() => {
        setReviewedCount((count) => count + 1)
        bump({ pairs_marked: 1, ...(overlaps ? { overlaps_found: 1 } : {}) })
        recordCompletion()
        loadNextPair(diveUuid)
        onUserRefresh()
      })
      .catch(() => setError('Could not submit your answer. Please try again.'))
      .finally(() => setSubmitting(false))
  }

  const handleSkip = () => {
    if (!pair || !diveUuid || submitting) return
    loadNextPair(diveUuid)
  }

  return (
    <div className="game-screen" data-game="overlap">
      {fact && <FunFactModal fact={fact} onDismiss={dismiss} />}
      {showTutorial && <OverlapTutorial onComplete={completeTutorial} />}
      <header className="game-header">
        <div className="game-header-top">
          <button type="button" className="back-link" onClick={onBack}>
            ← Back to games
          </button>
          <AccountBar
            user={user}
            onOpenAdmin={onOpenAdmin}
            onOpenStats={onOpenStats}
            onOpenQuests={onOpenQuests}
            onOpenCommunityStats={onOpenCommunityStats}
            onOpenLeaderboard={onOpenLeaderboard}
            onLogout={onLogout}
          />
        </div>
        <GameStatsBar game="overlap" stats={stats} window={statsWindow} />
        <h1>Glass Eel League — Finding Overlap</h1>
        <p className="game-flavor">
          A glass eel drifts in from the open ocean, scanning the coastline for familiar water.
        </p>
        <p>Look at both images below and decide whether they show the same physical scene.</p>
        <p className="game-region">Region: {region.title}</p>
      </header>

      {loading && <p className="game-status">Loading image pair…</p>}
      {error && <p className="game-status game-status-error">{error}</p>}
      {!loading && !error && diveUuid === null && (
        <p className="game-status">No dive imagery is available for this region yet.</p>
      )}
      {!loading && !error && diveUuid && done && (
        <p className="game-status">No more pairs to review in this region right now — nice work!</p>
      )}

      {pair && !loading && (
        <>
          <div className="image-toolbar">
            <button type="button" className="btn" onClick={() => setGridSize(nextGridSize(gridSize))}>
              {gridToggleLabel(gridSize)}
            </button>
          </div>

          <div className="image-pane-row">
            <div className="image-pane">
              <img src={pair.imageA} alt="Candidate scene A" />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
            </div>
            <div className="image-pane">
              <img src={pair.imageB} alt="Candidate scene B" />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
            </div>
          </div>

          <footer className="game-footer">
            <span className="game-count">
              {reviewedCount} pair{reviewedCount === 1 ? '' : 's'} reviewed
            </span>
            <button type="button" className="btn" onClick={handleSkip} disabled={submitting}>
              Skip
            </button>
            <button type="button" className="btn" onClick={() => handleDecision(false)} disabled={submitting}>
              Different scene
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => handleDecision(true)}
              disabled={submitting}
            >
              Same scene
            </button>
          </footer>
        </>
      )}
    </div>
  )
}
