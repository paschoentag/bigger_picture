import { useState } from 'react'
import { ExampleScene } from './ExampleScene'
import { TUTORIALS } from './tutorialContent'
import './tutorialShell.css'
import './TutorialModal.css'

/**
 * A paged, first-play tutorial slide deck. Walks through the mechanic and its
 * do's and don'ts with example imagery, then calls `onComplete` when the
 * player reaches the end and starts playing.
 */
export default function TutorialModal({
  game,
  onComplete,
}: {
  game: 'verify'
  onComplete: () => void
}) {
  const steps = TUTORIALS[game]
  const [step, setStep] = useState(0)
  const current = steps[step]
  const isLast = step === steps.length - 1

  return (
    <div className="tut-backdrop" data-game={game}>
      <div
        className="tut-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tut-title"
      >
        {current.scene && <ExampleScene scene={current.scene} />}
        <h2 id="tut-title">{current.title}</h2>
        <p className="tut-body">{current.body}</p>
        {current.tips && (
          <ul className="tut-tips">
            {current.tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        )}

        <div className="tut-dots" aria-hidden="true">
          {steps.map((_, i) => (
            <span key={i} className={`tut-dot${i === step ? ' tut-dot-active' : ''}`} />
          ))}
        </div>

        <footer className="tut-footer">
          <button
            type="button"
            className="btn"
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
          >
            Back
          </button>
          <span className="tut-progress">
            {step + 1} / {steps.length}
          </span>
          {isLast ? (
            <button type="button" className="btn btn-primary" onClick={onComplete}>
              Start playing
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => setStep((s) => s + 1)}>
              Next
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}
