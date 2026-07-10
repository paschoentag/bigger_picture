import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { fetchNextImagePair, submitAnnotation } from '../api/annotationApi'
import { fetchDivesForRegion } from '../api/diveApi'
import type { Correspondence, ImagePair, NormalizedPoint, Region, User } from '../api/types'
import AnnotateHintsModal from './AnnotateHintsModal'
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
import { ZoomLens } from './ZoomLens'
import './AnnotateGame.css'

const MIN_CORRESPONDENCES = 4

function pointFromClick(e: ReactMouseEvent<HTMLImageElement>): NormalizedPoint {
  const rect = e.currentTarget.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width
  const y = (e.clientY - rect.top) / rect.height
  return {
    x: Math.min(1, Math.max(0, x)),
    y: Math.min(1, Math.max(0, y)),
  }
}

export default function AnnotateGame({
  region,
  user,
  onUserRefresh,
  onBack,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
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
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  // undefined = still resolving a dive for this region; null = region has no dives yet.
  const [diveUuid, setDiveUuid] = useState<string | null | undefined>(undefined)
  const [pair, setPair] = useState<ImagePair | null>(null)
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [correspondences, setCorrespondences] = useState<Correspondence[]>([])
  const [pending, setPending] = useState<{ side: 'A' | 'B'; point: NormalizedPoint } | null>(null)
  const [showHints, setShowHints] = useState(true)
  const [gridSize, setGridSize] = useState<GridSize>(0)
  const [zoomPoint, setZoomPoint] = useState<{side: 'A' | 'B'; point: NormalizedPoint} | null>(null)
  const [cursorPosition, setCursorPosition] = useState<{x: number; y: number} | null>(null)
  const { stats, window: statsWindow, bump } = useGameStats('annotate')
  const { fact, recordCompletion, dismiss } = useFunFactTrigger(region.uuid)
  const imageARef = useRef<HTMLImageElement>(null)
  const imageBRef = useRef<HTMLImageElement>(null)

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
    setCorrespondences([])
    setPending(null)
    fetchNextImagePair(forDiveUuid)
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

  const handleClickImage = (side: 'A' | 'B') => (e: ReactMouseEvent<HTMLImageElement>) => {
    if (submitting) return
    const point = pointFromClick(e)

    if (pending && pending.side !== side) {
      const pointA = pending.side === 'A' ? pending.point : point
      const pointB = pending.side === 'B' ? pending.point : point
      setCorrespondences((prev) => [...prev, { pointA, pointB }])
      setPending(null)
      return
    }

    setPending({ side, point })
  }

  const handleMouseMove =  (side: 'A' | 'B') =>  (e: ReactMouseEvent<HTMLImageElement>) => {
    const point = pointFromClick(e)
    const rect = e.currentTarget.getBoundingClientRect()

    setZoomPoint({
      side,
      point })

    // setCursorPosition({
    //   x: e.clientX,
    //   y: e.clientY })
    setCursorPosition({
      x: rect.left + point.x * rect.width,
      y: rect.top + point.y * rect.height,
})

      
  }

  const handleMouseLeave = () => {
    setZoomPoint(null)
    setCursorPosition(null)
  }

  const handleUndo = () => {
    if (pending) {
      setPending(null)
      return
    }
    setCorrespondences((prev) => prev.slice(0, -1))
  }

  const handleClear = () => {
    setCorrespondences([])
    setPending(null)
  }

  const handleSkip = () => {
    if (!pair || !diveUuid || submitting) return
    loadNextPair(diveUuid)
  }

  const handleSubmit = () => {
    if (!pair || !diveUuid || correspondences.length < MIN_CORRESPONDENCES) return
    const imageA = imageARef.current
    const imageB = imageBRef.current
    if (!imageA || !imageB) return

    setSubmitting(true)
    setError(null)
    submitAnnotation(pair, correspondences, {
      widthA: imageA.naturalWidth,
      heightA: imageA.naturalHeight,
      widthB: imageB.naturalWidth,
      heightB: imageB.naturalHeight,
    })
      .then(() => {
        bump({ pairs_marked: 1, annotations: correspondences.length })
        recordCompletion()
        loadNextPair(diveUuid)
        onUserRefresh()
      })
      .catch(() => setError('Could not submit your annotation. Please try again.'))
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="game-screen" data-game="annotate">
      {fact && <FunFactModal fact={fact} onDismiss={dismiss} />}
       {zoomPoint && (
        <ZoomLens
          imageRef={
            zoomPoint.side === 'A'
              ? imageARef
              : imageBRef
          }
          point={zoomPoint.point}
          cursor={cursorPosition}
          zoom={4}
        />
      )}
      {pending && (
        <ZoomLens
          imageRef={pending.side === 'A' ? imageARef : imageBRef}
          point={pending.point}
          zoom={4}
          pinned
        />
      )}
      {showHints && <AnnotateHintsModal onDismiss={() => setShowHints(false)} />}
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
            onOpenLeaderboard={onOpenLeaderboard}
            onLogout={onLogout}
          />
        </div>
        <GameStatsBar game="annotate" stats={stats} window={statsWindow} />
        <h1>Yellow Eel League — Annotating</h1>
        <p className="game-flavor">
          For years, a yellow eel learns every rock and reed of its river home by heart.
        </p>
        <p>
          Select at least {MIN_CORRESPONDENCES} corresponding points for the image pair.
          <button
            type="button"
            className="info-button"
            onClick={() => setShowHints(true)}
            aria-label="More information about annotation"
          >
            i
          </button>
        </p>
        <p className="game-region">Region: {region.title}</p>
      </header>

      {loading && <p className="game-status">Loading image pair…</p>}
      {error && <p className="game-status game-status-error">{error}</p>}
      {!loading && !error && diveUuid === null && (
        <p className="game-status">No dive imagery is available for this region yet.</p>
      )}
      {!loading && !error && diveUuid && done && (
        <p className="game-status">No more pairs to annotate in this region right now — nice work!</p>
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
              <img
                ref={imageARef}
                src={pair.imageA}
                alt="Image A"
                onClick={handleClickImage('A')}
                onMouseMove={handleMouseMove('A')}
                onMouseLeave={handleMouseLeave}
                className={`clickable${pending?.side === 'A' ? ' awaiting-match' : ''}`}
              />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
              {correspondences.map((c, i) => (
                <Marker key={`a-${i}`} point={c.pointA} color={markerColor(i)} label={i + 1} />
              ))}
              {pending?.side === 'A' && (
                <div
                  className="marker marker-pending"
                  style={{ left: `${pending.point.x * 100}%`, top: `${pending.point.y * 100}%` }}
                >
                  {correspondences.length + 1}
                </div>
              )}
            </div>
            <div className="image-pane">
              <img
                ref={imageBRef}
                src={pair.imageB}
                alt="Image B"
                onClick={handleClickImage('B')}
                onMouseMove={handleMouseMove('B')}
                onMouseLeave={handleMouseLeave}
                className={`clickable${pending?.side === 'B' ? ' awaiting-match' : ''}`}
              />
              {gridSize !== 0 && <GridOverlay size={gridSize} />}
              {correspondences.map((c, i) => (
                <Marker key={`b-${i}`} point={c.pointB} color={markerColor(i)} label={i + 1} />
              ))}
              {pending?.side === 'B' && (
                <div
                  className="marker marker-pending"
                  style={{ left: `${pending.point.x * 100}%`, top: `${pending.point.y * 100}%` }}
                >
                  {correspondences.length + 1}
                </div>
              )}
            </div>
          </div>

          <p className="game-hint">
            {pending
              ? `Now click the matching point in the ${pending.side === 'A' ? 'right' : 'left'} image.`
              : 'Click a point in either image to start a new match.'}
          </p>

          <footer className="game-footer">
            <span className="game-count">
              {correspondences.length} point{correspondences.length === 1 ? '' : 's'} matched
            </span>
            <button type="button" className="btn" onClick={handleSkip} disabled={submitting}>
              Skip
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleUndo}
              disabled={submitting || (correspondences.length === 0 && !pending)}
            >
              Undo
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleClear}
              disabled={submitting || (correspondences.length === 0 && !pending)}
            >
              Clear
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={submitting || correspondences.length < MIN_CORRESPONDENCES}
            >
              {submitting ? 'Submitting…' : `Submit & next pair`}
            </button>
          </footer>
        </>
      )}
    </div>
  )
}
