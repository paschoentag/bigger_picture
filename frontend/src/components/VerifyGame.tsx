import { useCallback, useEffect, useState } from 'react'
import { fetchDivesForRegion } from '../api/diveApi'
import { fetchNextPendingVerification, submitPointVerification } from '../api/verifyApi'
import type { PendingVerification, Region, User } from '../api/types'
import { GridOverlay } from './GridOverlay'
import type { GridSize } from './gridSize'
import { gridToggleLabel, nextGridSize } from './gridSize'
import { GameStatsBar } from './GameStatsBar'
import AccountBar from './AccountBar'
import { useGameStats } from './useGameStats'
import { useFunFactTrigger } from './useFunFactTrigger'
import FunFactModal from './FunFactModal'
import { Marker } from './Marker'
import { markerColor } from './markerColor'
import TutorialModal from './tutorials/TutorialModal'
import { useTutorial } from './tutorials/useTutorial'

type PointStatus = 'approved' | 'flagged'

export default function VerifyGame({
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
  const [item, setItem] = useState<PendingVerification | null>(null)
  // Staged, not-yet-submitted decisions for the current pair. Nothing reaches
  // the backend until the player commits with Submit, and any mark here can be
  // switched or cleared until then.
  const [statuses, setStatuses] = useState<Map<string, PointStatus>>(new Map())
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [gridSize, setGridSize] = useState<GridSize>(0)
  const { stats, window: statsWindow, bump } = useGameStats('verify')
  const { fact, recordCompletion, dismiss } = useFunFactTrigger(region.uuid)
  const { show: showTutorial, complete: completeTutorial } = useTutorial('verify')

  useEffect(() => {
    setDiveUuid(undefined)
    setLoading(true)
    setError(null)
    fetchDivesForRegion(region.uuid)
      .then((dives) => setDiveUuid(dives[0]?.uuid ?? null))
      .catch(() => setError('Could not load dive imagery for this region. Please try again.'))
  }, [region.uuid])

  const loadNext = useCallback((forDiveUuid: string) => {
    setLoading(true)
    setError(null)
    fetchNextPendingVerification(forDiveUuid)
      .then((next) => {
        setItem(next)
        setStatuses(new Map())
        setDone(next === null)
      })
      .catch(() => setError('Could not load an annotation to review. Please try again.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (diveUuid) {
      loadNext(diveUuid)
    } else if (diveUuid === null) {
      setLoading(false)
    }
  }, [diveUuid, loadNext])

  // Stage or update a single point's decision locally. Clicking the mark it
  // already carries clears it (undo), so an accidental click is fully
  // reversible before submitting; clicking the other mark switches it.
  const togglePoint = (pointUuid: string, status: PointStatus) => {
    if (submitting) return
    setStatuses((prev) => {
      const next = new Map(prev)
      if (next.get(pointUuid) === status) {
        next.delete(pointUuid)
      } else {
        next.set(pointUuid, status)
      }
      return next
    })
  }

  const clearMarks = () => {
    if (submitting) return
    setStatuses(new Map())
  }

  // Commit the staged decisions. Only marked points are sent — undecided ones
  // stay pending and simply come back in the next pair — so a partial review
  // is fine. Points are submitted individually (there is no batch endpoint);
  // any that fail stay staged so they can be retried.
  const handleSubmit = () => {
    if (!item || !diveUuid || submitting) return
    const decided = item.correspondences
      .map((c) => ({ uuid: c.pointUuid, status: statuses.get(c.pointUuid) }))
      .filter((d): d is { uuid: string; status: PointStatus } => d.status !== undefined)
    if (decided.length === 0) return

    setSubmitting(true)
    setError(null)
    Promise.allSettled(
      decided.map((d) => submitPointVerification(d.uuid, d.status === 'approved')),
    )
      .then((results) => {
        let accepted = 0
        let faulty = 0
        const failed = new Set<string>()
        results.forEach((res, i) => {
          if (res.status === 'fulfilled') {
            if (decided[i].status === 'approved') accepted += 1
            else faulty += 1
          } else {
            failed.add(decided[i].uuid)
          }
        })

        const submitted = accepted + faulty
        if (submitted > 0) {
          bump({ verified: submitted, accepted, faulty_found: faulty })
          recordCompletion()
          onUserRefresh()
        }

        if (failed.size > 0) {
          // Keep only the failed marks staged so the player can retry them.
          setStatuses((prev) => new Map([...prev].filter(([uuid]) => failed.has(uuid))))
          setError('Some reviews could not be submitted. Please try again.')
        } else {
          loadNext(diveUuid)
        }
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="game-screen" data-game="verify">
      {fact && <FunFactModal fact={fact} onDismiss={dismiss} />}
      {showTutorial && <TutorialModal game="verify" onComplete={completeTutorial} />}
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
        <GameStatsBar game="verify" stats={stats} window={statsWindow} />
        <h1>Silver Eel League — Verification</h1>
        <p className="game-flavor">
          Before the long migration back to sea, a silver eel double-checks its bearings.
        </p>
        <p>
          Review the numbered points below - does each pair mark the same physical spot in both
          images? Flag or approve each point, then submit. Nothing is saved until you do, so you can
          change or clear a mark first, and you can submit just the points you're sure about.
        </p>
        <p className="game-region">Region: {region.title}</p>
      </header>

      {loading && <p className="game-status">Loading annotation…</p>}
      {error && <p className="game-status game-status-error">{error}</p>}
      {!loading && !error && diveUuid === null && (
        <p className="game-status">No dive imagery is available for this region yet.</p>
      )}
      {!loading && !error && diveUuid && done && (
        <p className="game-status">Nothing left to review in this region right now — nice work!</p>
      )}

      {item && !loading && (
        <>
          <div className="image-toolbar">
            <button type="button" className="btn" onClick={() => setGridSize(nextGridSize(gridSize))}>
              {gridToggleLabel(gridSize)}
            </button>
          </div>

          <div className="image-pane-row">
            <div className="image-pane">
              <img src={item.imageA} alt="Annotated image A" />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
              {item.correspondences.map((c, i) => (
                <Marker
                  key={`a-${i}`}
                  point={c.pointA}
                  color={markerColor(i)}
                  label={i + 1}
                  status={statuses.get(c.pointUuid)}
                />
              ))}
            </div>
            <div className="image-pane">
              <img src={item.imageB} alt="Annotated image B" />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
              {item.correspondences.map((c, i) => (
                <Marker
                  key={`b-${i}`}
                  point={c.pointB}
                  color={markerColor(i)}
                  label={i + 1}
                  status={statuses.get(c.pointUuid)}
                />
              ))}
            </div>
          </div>

          <ul className="verify-points">
            {item.correspondences.map((c, i) => {
              const status = statuses.get(c.pointUuid)
              return (
                <li key={c.pointUuid} className="verify-point-row">
                  <span className="verify-point-swatch" style={{ backgroundColor: markerColor(i) }}>
                    {i + 1}
                  </span>
                  <span className="verify-point-actions">
                    <button
                      type="button"
                      className={`btn verify-toggle${status === 'flagged' ? ' verify-toggle-flagged' : ''}`}
                      aria-pressed={status === 'flagged'}
                      onClick={() => togglePoint(c.pointUuid, 'flagged')}
                      disabled={submitting}
                    >
                      Flag
                    </button>
                    <button
                      type="button"
                      className={`btn verify-toggle${status === 'approved' ? ' verify-toggle-approved' : ''}`}
                      aria-pressed={status === 'approved'}
                      onClick={() => togglePoint(c.pointUuid, 'approved')}
                      disabled={submitting}
                    >
                      Approve
                    </button>
                  </span>
                </li>
              )
            })}
          </ul>

          <footer className="game-footer">
            <span className="game-count">
              {statuses.size} of {item.correspondences.length} marked
            </span>
            <button
              type="button"
              className="btn"
              onClick={clearMarks}
              disabled={submitting || statuses.size === 0}
            >
              Clear
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={submitting || statuses.size === 0}
            >
              {submitting
                ? 'Submitting…'
                : `Submit ${statuses.size} review${statuses.size === 1 ? '' : 's'}`}
            </button>
          </footer>
        </>
      )}
    </div>
  )
}
