import { useCallback, useEffect, useState } from 'react'
import { fetchDivesForRegion } from '../api/diveApi'
import { fetchNextPendingVerification, submitPointVerification } from '../api/verifyApi'
import type { PendingVerification, Region, User } from '../api/types'
import { GridOverlay } from './GridOverlay'
import type { GridSize } from './gridSize'
import { gridToggleLabel, nextGridSize } from './gridSize'
import { GameStatsBar } from './GameStatsBar'
import { LevelBadge } from './LevelBadge'
import { useGameStats } from './useGameStats'
import { Marker } from './Marker'
import { markerColor } from './markerColor'

type PointStatus = 'approved' | 'flagged'

export default function VerifyGame({
  region,
  user,
  onUserRefresh,
  onBack,
}: {
  region: Region
  user: User
  onUserRefresh: () => void
  onBack: () => void
}) {
  // undefined = still resolving a dive for this region; null = region has no dives yet.
  const [diveUuid, setDiveUuid] = useState<string | null | undefined>(undefined)
  const [item, setItem] = useState<PendingVerification | null>(null)
  const [statuses, setStatuses] = useState<Map<string, PointStatus>>(new Map())
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submittingUuid, setSubmittingUuid] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reviewedCount, setReviewedCount] = useState(0)
  const [gridSize, setGridSize] = useState<GridSize>(0)
  const { stats, window: statsWindow, unconfirmedExp, bump } = useGameStats('verify')

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

  // Once every point in the current pair has a decision, move on to the next one.
  useEffect(() => {
    if (!item || !diveUuid) return
    if (statuses.size > 0 && statuses.size === item.correspondences.length) {
      loadNext(diveUuid)
    }
  }, [statuses, item, diveUuid, loadNext])

  const handlePointDecision = (pointUuid: string, approved: boolean) => {
    if (!item || !diveUuid || submittingUuid) return
    setSubmittingUuid(pointUuid)
    setError(null)
    submitPointVerification(pointUuid, approved)
      .then(() => {
        setReviewedCount((count) => count + 1)
        setStatuses((prev) => new Map(prev).set(pointUuid, approved ? 'approved' : 'flagged'))
        bump({ verified: 1, ...(approved ? { accepted: 1 } : { faulty_found: 1 }) })
        onUserRefresh()
      })
      .catch(() => setError('Could not submit your review. Please try again.'))
      .finally(() => setSubmittingUuid(null))
  }

  return (
    <div className="game-screen">
      <header className="game-header">
        <div className="game-header-top">
          <button type="button" className="back-link" onClick={onBack}>
            ← Back to games
          </button>
          <LevelBadge exp={user.exp} />
        </div>
        <GameStatsBar game="verify" stats={stats} window={statsWindow} unconfirmedExp={unconfirmedExp} />
        <h1>Silver Eel League — Verification</h1>
        <p className="game-flavor">
          Before the long migration back to sea, a silver eel double-checks its bearings.
        </p>
        <p>
          Review the numbered points below - does each pair mark the same physical spot in both
          images? Approve or flag each point on its own.
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
                  reviewed={statuses.has(c.pointUuid)}
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
                  reviewed={statuses.has(c.pointUuid)}
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
                  {status ? (
                    <span className={`verify-point-status verify-point-status-${status}`}>
                      {status === 'approved' ? 'Approved' : 'Flagged'}
                    </span>
                  ) : (
                    <span className="verify-point-actions">
                      <button
                        type="button"
                        className="btn"
                        onClick={() => handlePointDecision(c.pointUuid, false)}
                        disabled={submittingUuid === c.pointUuid}
                      >
                        Flag
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => handlePointDecision(c.pointUuid, true)}
                        disabled={submittingUuid === c.pointUuid}
                      >
                        Approve
                      </button>
                    </span>
                  )}
                </li>
              )
            })}
          </ul>

          <footer className="game-footer">
            <span className="game-count">{reviewedCount} reviewed</span>
          </footer>
        </>
      )}
    </div>
  )
}
