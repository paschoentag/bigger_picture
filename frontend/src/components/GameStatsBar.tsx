import { useEffect, useRef, useState } from 'react'
import { formatAccuracy } from '../api/statsApi'
import type { AnnotateStats, OverlapStats, VerifyStats } from '../api/statsApi'
import type { GameId } from './HomeScreen'
import type { GameSlice } from './useGameStats'
import './GameStatsBar.css'

interface StatDescriptor {
  key: string
  label: string
  tooltip: string
  tier: 'primary' | 'secondary'
  /** Numeric counter value that animates a "+N" on increase. */
  value: number | null
  /** Display text for non-counter stats (e.g. accuracy); shown instead of `value`. */
  text?: string
}

/** Builds the ordered stat chips for a game from its current slice. */
function buildDescriptors(game: GameId, slice: GameSlice, window: number | null): StatDescriptor[] {
  const recent = window === null ? 'recent reviews' : `last ${window} reviews`
  if (game === 'overlap') {
    const s = slice as OverlapStats
    return [
      { key: 'pairs_marked', label: 'Pairs marked', tooltip: 'Image pairs you have judged for overlap.', tier: 'primary', value: s.pairs_marked },
      { key: 'overlaps_found', label: 'Overlaps found', tooltip: 'Pairs you marked as showing the same scene.', tier: 'primary', value: s.overlaps_found },
      { key: 'overall_pairs', label: 'Overlaps overall', tooltip: 'Overlapping pairs confirmed across all players.', tier: 'secondary', value: s.overall_pairs_with_overlap },
      { key: 'acc_all', label: 'Accuracy', tooltip: `Share of your judged pairs that matched the consensus (${s.accuracy_all_time.correct}/${s.accuracy_all_time.reviewed}).`, tier: 'secondary', value: null, text: formatAccuracy(s.accuracy_all_time) },
      { key: 'acc_window', label: 'Recent accuracy', tooltip: `Accuracy over your ${recent} (${s.accuracy_window.correct}/${s.accuracy_window.reviewed}).`, tier: 'secondary', value: null, text: formatAccuracy(s.accuracy_window) },
    ]
  }
  if (game === 'annotate') {
    const s = slice as AnnotateStats
    return [
      { key: 'annotations', label: 'Points', tooltip: 'Correspondence points you have placed.', tier: 'primary', value: s.annotations },
      { key: 'pairs_marked', label: 'Pairs annotated', tooltip: 'Image pairs you have submitted annotations for.', tier: 'primary', value: s.pairs_marked },
      { key: 'annotations_verified', label: 'Points verified', tooltip: 'Your points that have since been reviewed by others.', tier: 'secondary', value: s.annotations_verified },
      { key: 'pairs_verified', label: 'Pairs verified', tooltip: 'Your annotated pairs that have been reviewed by others.', tier: 'secondary', value: s.pairs_verified },
      { key: 'acc_all', label: 'Accuracy', tooltip: `Share of your reviewed points accepted (${s.accuracy_all_time.correct}/${s.accuracy_all_time.reviewed}).`, tier: 'secondary', value: null, text: formatAccuracy(s.accuracy_all_time) },
      { key: 'acc_window', label: 'Recent accuracy', tooltip: `Accuracy over your ${recent} (${s.accuracy_window.correct}/${s.accuracy_window.reviewed}).`, tier: 'secondary', value: null, text: formatAccuracy(s.accuracy_window) },
    ]
  }
  const s = slice as VerifyStats
  return [
    { key: 'verified', label: 'Reviews done', tooltip: 'Points you have reviewed for other players.', tier: 'primary', value: s.verified },
    { key: 'accepted', label: 'Accepted', tooltip: 'Reviewed points you judged to be correct.', tier: 'secondary', value: s.accepted },
    { key: 'faulty_found', label: 'Faults found', tooltip: 'Reviewed points you flagged as wrong.', tier: 'secondary', value: s.faulty_found },
  ]
}

/** A single stat with a hover tooltip and a green "+N" animation when its counter increases. */
function StatChip({
  label,
  tooltip,
  value,
  text,
  className,
}: Omit<StatDescriptor, 'key' | 'tier'> & { className?: string }) {
  const prev = useRef<number | null>(null)
  const nextId = useRef(0)
  const [bumps, setBumps] = useState<{ id: number; amount: number }[]>([])

  useEffect(() => {
    if (value === null) return
    if (prev.current !== null && value > prev.current) {
      const amount = value - prev.current
      const id = nextId.current++
      setBumps((list) => [...list, { id, amount }])
    }
    prev.current = value
  }, [value])

  return (
    <span className={className ? `stat-chip ${className}` : 'stat-chip'} tabIndex={0}>
      <span className="stat-chip-value">
        {text ?? value}
        {bumps.map((b) => (
          <span
            key={b.id}
            className="stat-bump"
            onAnimationEnd={() => setBumps((list) => list.filter((x) => x.id !== b.id))}
          >
            +{b.amount}
          </span>
        ))}
      </span>
      <span className="stat-chip-label">{label}</span>
      <span className="stat-chip-tooltip" role="tooltip">
        {tooltip}
      </span>
    </span>
  )
}

/**
 * How and when experience changes — shown as the tooltip on the pending-XP chip so
 * players understand why the number moves (and why it isn't instant).
 */
const EXP_EXPLANATION =
  'XP is only confirmed once other players review your work. You gain XP each time you review ' +
  "someone's submission, and again when your own overlap votes and annotations are approved. " +
  "Pending XP is what you'll earn once your current submissions are confirmed."

/** Compact strip of a single game's own stats, shown under the experience bar. */
export function GameStatsBar({
  game,
  stats,
  window,
  unconfirmedExp,
}: {
  game: GameId
  stats: GameSlice | null
  window: number | null
  unconfirmedExp: number | null
}) {
  const [expanded, setExpanded] = useState(false)
  if (!stats) return null

  const descriptors = buildDescriptors(game, stats, window)
  const primary = descriptors.filter((d) => d.tier === 'primary')
  const secondary = descriptors.filter((d) => d.tier === 'secondary')

  return (
    <div className="game-stats-bar">
      <div className="game-stats-row">
        {unconfirmedExp !== null && (
          <StatChip
            className="stat-chip-pending"
            label="Pending XP"
            tooltip={EXP_EXPLANATION}
            value={unconfirmedExp}
            text={`+${unconfirmedExp}`}
          />
        )}
        {primary.map((d) => (
          <StatChip key={d.key} label={d.label} tooltip={d.tooltip} value={d.value} text={d.text} />
        ))}
        {secondary.length > 0 && (
          <button
            type="button"
            className="game-stats-toggle"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Hide more stats' : 'Show more stats'}
          >
            <span className="game-stats-toggle-arrow" aria-hidden="true">▾</span>
          </button>
        )}
      </div>
      {expanded && secondary.length > 0 && (
        <div className="game-stats-more">
          {secondary.map((d) => (
            <StatChip key={d.key} label={d.label} tooltip={d.tooltip} value={d.value} text={d.text} />
          ))}
        </div>
      )}
    </div>
  )
}
