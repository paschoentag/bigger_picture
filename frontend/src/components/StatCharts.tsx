import type { AccuracyStat } from '../api/statsApi'

/**
 * Radial gauge for a bounded rate (0–1). Uses the section's `--game-accent`
 * for the arc against a neutral track, and always prints the value in the
 * centre so identity never rests on colour alone.
 */
export function AccuracyGauge({ caption, stat }: { caption: string; stat: AccuracyStat }) {
  const r = 42
  const circumference = 2 * Math.PI * r
  const fraction = stat.accuracy ?? 0
  const pct = stat.accuracy === null ? null : Math.round(stat.accuracy * 100)

  return (
    <figure className="stat-gauge">
      <svg
        viewBox="0 0 100 100"
        className="stat-gauge-svg"
        role="img"
        aria-label={`${caption}: ${pct === null ? 'not available' : `${pct}%`}`}
      >
        <circle cx="50" cy="50" r={r} className="stat-gauge-track" />
        {pct !== null && (
          <circle
            cx="50"
            cy="50"
            r={r}
            className="stat-gauge-arc"
            strokeDasharray={`${circumference * fraction} ${circumference}`}
            transform="rotate(-90 50 50)"
          />
        )}
        <text x="50" y="50" className="stat-gauge-value">
          {pct === null ? 'n/a' : `${pct}%`}
        </text>
      </svg>
      <figcaption className="stat-gauge-caption">{caption}</figcaption>
      <span className="stat-sub">
        {stat.correct}/{stat.reviewed} reviewed
      </span>
    </figure>
  )
}

/**
 * Horizontal bar splitting a whole into two or three real categories, with a
 * 2px surface gap between the fills and a labelled legend below. Segment 0
 * takes the full accent, segment 1 a pale tint of the same hue (so a 2-way
 * split reads as one family, primary vs secondary), and an optional segment 2
 * a neutral gray - for the common "resolved positive / resolved negative /
 * still pending" shape, where pending isn't part of the accent's hue family.
 */
export function SplitBar({
  segments,
}: {
  segments: { label: string; value: number }[]
}) {
  const total = segments[0].value + segments[1].value

  return (
    <div className="stat-split">
      <div
        className="stat-split-track"
        role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(', ')}
      >
        {total === 0 ? (
          <div className="stat-split-empty" />
        ) : (
          segments.map((seg, i) => (
            <div
              key={seg.label}
              className={`stat-split-seg stat-split-seg-${i}`}
              style={{ flexGrow: seg.value }}
            />
          ))
        )}
      </div>
      <ul className="stat-split-legend">
        {segments.map((seg, i) => (
          <li key={seg.label}>
            <span className={`stat-split-swatch stat-split-seg-${i}`} />
            <span className="stat-split-legend-label">{seg.label}</span>
            <span className="stat-split-legend-value">{seg.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Progress meter for a part-of-whole coverage figure (e.g. how much of your
 * work has been verified). Accent fill on a neutral track, with the raw
 * count and percentage printed alongside.
 */
export function ProgressMeter({
  label,
  value,
  total,
}: {
  label: string
  value: number
  total: number
}) {
  const pct = total === 0 ? 0 : Math.round((value / total) * 100)

  return (
    <div className="stat-meter">
      <div className="stat-meter-head">
        <span className="stat-meter-label">{label}</span>
        <span className="stat-meter-value">
          {value}/{total} · {pct}%
        </span>
      </div>
      <div
        className="stat-meter-track"
        role="img"
        aria-label={`${label}: ${value} of ${total}, ${pct} percent`}
      >
        <div className="stat-meter-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/** One row of a `StageBarChart`: a game stage's raw activity count. */
export interface StageActivityDatum {
  /** Selects the bar's fill color - one of the three fixed per-game accents. */
  game: 'overlap' | 'annotate' | 'verify'
  label: string
  value: number
}

/**
 * Horizontal bar chart comparing raw activity across the three game stages on
 * one shared scale (magnitude, not part-of-whole - bars don't sum to a
 * total). Each row is directly labelled with its own name and value, so
 * identity never depends on picking the right hue out of the three accents.
 */
export function StageActivityChart({ data }: { data: StageActivityDatum[] }) {
  const max = Math.max(1, ...data.map((d) => d.value))

  return (
    <div className="stage-bars">
      {data.map((d) => (
        <div className="stage-bar-row" key={d.game}>
          <span className="stage-bar-label">{d.label}</span>
          <div
            className="stage-bar-track"
            role="img"
            aria-label={`${d.label}: ${d.value}`}
          >
            <div
              className={`stage-bar-fill stage-bar-fill-${d.game}`}
              style={{ width: `${(d.value / max) * 100}%` }}
            />
          </div>
          <span className="stage-bar-value">{d.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}
