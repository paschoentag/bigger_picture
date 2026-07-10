import { useState } from 'react'
import type { NormalizedPoint } from '../../api/types'
import { SceneBackground } from './ExampleScene'
import type { SceneVariant } from './ExampleScene'
import { ANGLED_LANDMARK_SHIFT, PARTIAL_LANDMARK_SHIFT } from './sceneGeometry'
import './tutorialShell.css'

type SceneStage = 'same' | 'partial' | 'different'
type Stage = SceneStage | 'wrap'

// Placeholder target, positioned against the stylized reef in ExampleScene's
// SceneBackground. Swap alongside real example imagery later.
const ROCK: NormalizedPoint = { x: 0.28, y: 0.75 }
// The 'angled'/'partial' panes redraw the rock shifted (see sceneGeometry.ts),
// so the highlight ring needs to track that same shift to stay on target.
const ROCK_ANGLED: NormalizedPoint = { x: ROCK.x + ANGLED_LANDMARK_SHIFT.x, y: ROCK.y + ANGLED_LANDMARK_SHIFT.y }
const ROCK_PARTIAL: NormalizedPoint = { x: ROCK.x + PARTIAL_LANDMARK_SHIFT.x, y: ROCK.y + PARTIAL_LANDMARK_SHIFT.y }

// Progression: an easy full-overlap case, then a harder partial-overlap case
// (still the same scene), then a genuinely different pair.
const STAGE_ORDER: SceneStage[] = ['same', 'partial', 'different']

const NARRATION: Record<Stage, { title: string; body: string }> = {
  same: {
    title: 'Look for a shared landmark',
    body: 'These two photos share the same rock — just seen from a different angle. Ignore fish, bubbles and lighting changes; focus on fixed structure. Is this the same physical scene?',
  },
  partial: {
    title: 'A partial match still counts',
    body: 'The camera panned further this time — the coral has panned out of frame, so only the rock is still visible in both photos. That’s still enough: one clear fixed landmark is all it takes. Is this the same physical scene?',
  },
  different: {
    title: 'Now a different pair',
    body: 'This time nothing lines up: different rock, different coral, different seabed. Is this the same physical scene?',
  },
  wrap: {
    title: 'You’re ready',
    body: 'Toggle the grid overlay to help line up landmarks, and use Skip whenever you genuinely can’t tell — a confident guess from someone else beats a coin flip. Remember: the two photos don’t need to line up perfectly, or even mostly — one shared landmark is enough.',
  },
}

const SCENE_B_VARIANT: Record<SceneStage, SceneVariant> = {
  same: 'angled',
  partial: 'partial',
  different: 'different',
}

const ROCK_B: Record<'same' | 'partial', NormalizedPoint> = {
  same: ROCK_ANGLED,
  partial: ROCK_PARTIAL,
}

const INCORRECT_FEEDBACK: Record<SceneStage, string> = {
  same: 'Look again — the same rock and coral heads appear in both, which makes this the same scene.',
  partial: 'Look again — the rock is still visible in both photos, even though the coral has panned out of frame. That’s still enough to call it the same scene.',
  different: 'Look again — nothing here matches: different rock, different coral, different water color.',
}

/**
 * A guided, action-driven first-play tutorial for the Overlap game. Puts the
 * reader in front of the real two-image layout and has them make the actual
 * call three times — a full-overlap pair from a different angle, a
 * partial-overlap pair (only one landmark still shared), then a genuinely
 * different pair — before playing for real.
 */
export default function OverlapTutorial({ onComplete }: { onComplete: () => void }) {
  const [stage, setStage] = useState<Stage>('same')
  const [hint, setHint] = useState<string | null>(null)

  const choose = (chosenSame: boolean) => {
    if (stage === 'wrap') return
    const correct = chosenSame === (stage !== 'different')
    if (!correct) {
      setHint(INCORRECT_FEEDBACK[stage])
      return
    }
    setHint(null)
    const next = STAGE_ORDER[STAGE_ORDER.indexOf(stage) + 1]
    setStage(next ?? 'wrap')
  }

  const narration = NARRATION[stage]

  return (
    <div className="tut-backdrop" data-game="overlap">
      <div className="tut-modal" role="dialog" aria-modal="true" aria-labelledby="overlap-tut-title">
        <button type="button" className="tut-skip" onClick={onComplete}>
          Skip tutorial
        </button>
        <h2 id="overlap-tut-title">{narration.title}</h2>
        <p className="tut-body">{narration.body}</p>

        {stage !== 'wrap' && (
          <>
            <div className="tut-scene-row">
              <div className="tut-scene">
                <SceneBackground />
                {stage !== 'different' && (
                  <div className="tut-hint" style={{ left: `${ROCK.x * 100}%`, top: `${ROCK.y * 100}%` }} />
                )}
              </div>
              <div className="tut-scene">
                <SceneBackground variant={SCENE_B_VARIANT[stage]} />
                {stage !== 'different' && (
                  <div
                    className="tut-hint"
                    style={{ left: `${ROCK_B[stage].x * 100}%`, top: `${ROCK_B[stage].y * 100}%` }}
                  />
                )}
              </div>
            </div>

            <div className="tut-choice-buttons">
              <button type="button" className="btn" onClick={() => choose(false)}>
                Different scene
              </button>
              <button type="button" className="btn btn-primary" onClick={() => choose(true)}>
                Same scene
              </button>
            </div>
          </>
        )}

        {hint && <p className="tut-feedback tut-feedback-bad">{hint}</p>}

        {stage === 'wrap' && (
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
