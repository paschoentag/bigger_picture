import { useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import type { NormalizedPoint } from '../../api/types'
import { Marker } from '../Marker'
import { markerColor } from '../markerColor'
import { SceneBackground } from './ExampleScene'
import './tutorialShell.css'
import './AnnotateTutorial.css'

type Side = 'left' | 'right'
type Stage = 'left1' | 'right1' | 'left2' | 'right2' | 'moving'

// Placeholder targets, positioned against the stylized reef in ExampleScene's
// SceneBackground. Swap alongside real example imagery later.
const TARGET_1: NormalizedPoint = { x: 0.28, y: 0.75 } // rock edge
const TARGET_2: NormalizedPoint = { x: 0.68, y: 0.78 } // coral tip
const FISH: NormalizedPoint = { x: 0.55, y: 0.33 }
const BUBBLES: NormalizedPoint = { x: 0.8, y: 0.17 }
const HIT_RADIUS = 0.11

const NARRATION: Record<Stage, { title: string; body: string }> = {
  left1: {
    title: 'Find a fixed point',
    body: 'Good points are sharp, unmoving features — a rock edge, a coral tip, a crack, a bolt. Click the highlighted spot on the left photo.',
  },
  right1: {
    title: 'Match it on the right',
    body: 'Now click that exact same rock edge in the photo on the right.',
  },
  left2: {
    title: 'Spread your points out',
    body: 'Nice — that’s your first match. Correspondences work best spread across the whole image, not bunched in one corner. Click the highlighted coral tip on the left.',
  },
  right2: {
    title: 'Match the second point',
    body: 'Now find that same coral tip in the photo on the right and click it.',
  },
  moving: {
    title: 'Never mark things that move',
    body: 'Fish, divers, swaying plants and bubbles won’t be in the same spot in the next photo, so skip them — like the fish and bubbles highlighted below.',
  },
}

function distance(a: NormalizedPoint, b: NormalizedPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function pointFromClick(e: ReactMouseEvent<HTMLDivElement>): NormalizedPoint {
  const rect = e.currentTarget.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
  }
}

/**
 * A guided, action-driven first-play tutorial for the Annotate game. Rather
 * than paging through static slides, it puts the reader in front of the real
 * two-image layout and has them perform the actual mechanic: click a fixed
 * point on the left, match it on the right, do it again to learn spreading
 * points out, then see moving objects called out as things to avoid.
 */
export default function AnnotateTutorial({ onComplete }: { onComplete: () => void }) {
  const [stage, setStage] = useState<Stage>('left1')
  const [correspondences, setCorrespondences] = useState<{ left: NormalizedPoint; right: NormalizedPoint }[]>([])
  const [pendingPoint, setPendingPoint] = useState<NormalizedPoint | null>(null)
  const [hint, setHint] = useState<string | null>(null)

  const activeTarget: { side: Side; point: NormalizedPoint } | null =
    stage === 'left1' || stage === 'left2'
      ? { side: 'left', point: stage === 'left1' ? TARGET_1 : TARGET_2 }
      : stage === 'right1' || stage === 'right2'
        ? { side: 'right', point: stage === 'right1' ? TARGET_1 : TARGET_2 }
        : null

  const handlePaneClick = (side: Side) => (e: ReactMouseEvent<HTMLDivElement>) => {
    if (stage === 'moving') {
      const point = pointFromClick(e)
      if (distance(point, FISH) <= HIT_RADIUS) {
        setHint('Good eye — that fish will have swum off by the next photo.')
      } else if (distance(point, BUBBLES) <= HIT_RADIUS) {
        setHint('Good eye — those bubbles won’t be there a moment later.')
      }
      return
    }

    if (!activeTarget || side !== activeTarget.side) {
      setHint(side === 'left' ? 'Click the matching spot on the left photo.' : 'Now click the matching spot on the right photo.')
      return
    }

    const point = pointFromClick(e)
    if (distance(point, activeTarget.point) > HIT_RADIUS) {
      setHint('Click the highlighted spot.')
      return
    }

    setHint(null)
    if (stage === 'left1') {
      setPendingPoint(TARGET_1)
      setStage('right1')
    } else if (stage === 'right1') {
      setCorrespondences((prev) => [...prev, { left: TARGET_1, right: TARGET_1 }])
      setPendingPoint(null)
      setStage('left2')
    } else if (stage === 'left2') {
      setPendingPoint(TARGET_2)
      setStage('right2')
    } else if (stage === 'right2') {
      setCorrespondences((prev) => [...prev, { left: TARGET_2, right: TARGET_2 }])
      setPendingPoint(null)
      setStage('moving')
    }
  }

  const narration = NARRATION[stage]

  return (
    <div className="tut-backdrop" data-game="annotate">
      <div
        className="tut-modal annot-tut-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="annot-tut-title"
      >
        <button type="button" className="tut-skip" onClick={onComplete}>
          Skip tutorial
        </button>
        <h2 id="annot-tut-title">{narration.title}</h2>
        <p className="tut-body">{narration.body}</p>

        <div className="tut-scene-row">
          {(['left', 'right'] as const).map((side) => (
            <div
              key={side}
              className="tut-scene annot-tut-pane"
              onClick={handlePaneClick(side)}
            >
              <SceneBackground />
              {correspondences.map((c, i) => (
                <Marker key={i} point={c[side]} color={markerColor(i)} label={i + 1} />
              ))}
              {pendingPoint && side === 'left' && (
                <div
                  className="marker marker-pending"
                  style={{ left: `${pendingPoint.x * 100}%`, top: `${pendingPoint.y * 100}%` }}
                >
                  {correspondences.length + 1}
                </div>
              )}
              {activeTarget && activeTarget.side === side && (
                <div
                  className="tut-hint"
                  style={{ left: `${activeTarget.point.x * 100}%`, top: `${activeTarget.point.y * 100}%` }}
                />
              )}
              {stage === 'moving' && (
                <>
                  <div className="tut-avoid" style={{ left: `${FISH.x * 100}%`, top: `${FISH.y * 100}%` }}>
                    <span className="tut-avoid-label">moves — skip</span>
                  </div>
                  <div className="tut-avoid" style={{ left: `${BUBBLES.x * 100}%`, top: `${BUBBLES.y * 100}%` }}>
                    <span className="tut-avoid-label">moves — skip</span>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>

        {hint && <p className="tut-feedback tut-feedback-bad">{hint}</p>}

        {stage === 'moving' && (
          <footer className="tut-footer">
            <button type="button" className="btn btn-primary tut-start" onClick={onComplete}>
              Start playing
            </button>
          </footer>
        )}
      </div>
    </div>
  )
}
