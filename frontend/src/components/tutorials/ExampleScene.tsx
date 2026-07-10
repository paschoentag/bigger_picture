import type { NormalizedPoint } from '../../api/types'
import { ANGLED_LANDMARK_SHIFT, PARTIAL_LANDMARK_SHIFT } from './sceneGeometry'

/**
 * A demonstration point drawn over an example scene. `good` points are the
 * kind of feature to mark (rock edge, coral tip, bolt); `bad` points are the
 * kind to avoid (fish, divers, bubbles). `label` is an optional caption.
 */
export interface ExamplePoint {
  point: NormalizedPoint
  kind: 'good' | 'bad'
  label?: string
}

/** Which placeholder reef rendering to use; swapped for real photos later. */
export type SceneVariant = 'angled' | 'partial' | 'different'

/** A scene's backdrop (real photo or placeholder) plus its demonstration points. */
export interface SceneContent {
  image?: string
  points?: ExamplePoint[]
}

/**
 * Draws a tutorial step's example imagery with its demonstration points on top.
 * When `scene.image` is set it shows that photo; otherwise it renders a
 * stylized placeholder reef so the tutorial is self-contained until real
 * example imagery is supplied. Points are positioned in the image's normalized
 * [0,1] space, mirroring {@link Marker}.
 */
export function ExampleScene({ scene }: { scene: SceneContent }) {
  return (
    <div className="tut-scene">
      <SceneBackground image={scene.image} />
      {scene.points?.map((p, i) => (
        <div
          key={i}
          className={`tut-point tut-point-${p.kind}`}
          style={{ left: `${p.point.x * 100}%`, top: `${p.point.y * 100}%` }}
        >
          <span className="tut-point-dot" aria-hidden="true">
            {p.kind === 'bad' ? '✕' : '✓'}
          </span>
          {p.label && <span className="tut-point-label">{p.label}</span>}
        </div>
      ))}
    </div>
  )
}

/**
 * Renders a scene's backdrop only (no point overlay) — either the real photo
 * or the placeholder reef. `variant` lets a placeholder stand in for a second,
 * visually distinct example (e.g. "the same place from another angle") until
 * real photo pairs are available.
 */
export function SceneBackground({ image, variant }: { image?: string; variant?: SceneVariant }) {
  return image ? <img className="tut-scene-img" src={image} alt="" /> : <PlaceholderReef variant={variant} />
}

/**
 * A simple, themeable underwater scene used as placeholder example art.
 * `'different'` renders a structurally distinct layout (different terrain,
 * objects and positions) rather than just recoloring the same shapes, so it
 * reads as a genuinely different physical place, not a filtered clone.
 * `'angled'`/`'partial'` redraw the same reef with its landmarks panned/
 * rotated (see {@link ANGLED_LANDMARK_SHIFT}/{@link PARTIAL_LANDMARK_SHIFT}),
 * standing in for the same place shot from another angle rather than the
 * identical image - `'partial'` pans far enough that the coral is mostly out
 * of frame, leaving only the rock shared between the two scenes.
 */
function PlaceholderReef({ variant }: { variant?: SceneVariant }) {
  if (variant === 'different') {
    return <SandyScene />
  }
  if (variant === 'partial') {
    return <ReefScene shift={PARTIAL_LANDMARK_SHIFT} />
  }
  return <ReefScene shift={variant === 'angled' ? ANGLED_LANDMARK_SHIFT : undefined} />
}

function ReefScene({ shift }: { shift?: NormalizedPoint }) {
  // Fixed landmarks (rock, coral) pan and rotate together, as they would if
  // the camera moved - far enough in the 'partial' case that the coral is
  // clipped by the frame edge (SVG's default overflow: hidden), leaving only
  // the rock shared between the two scenes. Moving subjects (fish, bubbles)
  // land somewhere else entirely, same as between any two real shots.
  const landmarksTransform = shift
    ? `translate(${shift.x * 100} ${shift.y * 60}) rotate(6 45 45)`
    : undefined
  const seabed = shift
    ? 'M0 50 Q25 45 50 49 T100 48 V60 H0 Z'
    : 'M0 52 Q25 46 50 51 T100 50 V60 H0 Z'
  const fish = shift ? { cx: 38, cy: 14 } : { cx: 55, cy: 20 }
  const bubbles = shift ? [[30, 10], [33, 5], [28, 3]] : [[80, 14], [83, 9], [78, 7]]

  return (
    <svg
      className="tut-scene-svg"
      viewBox="0 0 100 60"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Illustrated underwater scene: rocky reef"
    >
      <defs>
        <linearGradient id="tut-water" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2a6f86" />
          <stop offset="100%" stopColor="#123a4a" />
        </linearGradient>
      </defs>
      <rect width="100" height="60" fill="url(#tut-water)" />
      {/* seabed */}
      <path d={seabed} fill="#4a3b2a" opacity="0.9" />
      {/* fixed landmarks: rock + coral heads */}
      <g transform={landmarksTransform}>
        <path d="M16 52 Q20 38 30 40 Q40 42 38 52 Z" fill="#5b5750" />
        <path d="M60 52 Q60 40 64 40 Q68 40 68 52 Z" fill="#b7563f" />
        <path d="M67 52 Q67 44 71 44 Q75 44 74 52 Z" fill="#c9704f" />
      </g>
      {/* fish */}
      <g fill="#e0c05a">
        <ellipse cx={fish.cx} cy={fish.cy} rx="5" ry="2.4" />
        <path d={`M${fish.cx + 5} ${fish.cy} l4 -2.5 v5 Z`} />
      </g>
      {/* bubbles */}
      <g fill="#ffffff" opacity="0.5">
        {bubbles.map(([cx, cy], i) => (
          <circle key={i} cx={cx} cy={cy} r={1.6 - i * 0.4} />
        ))}
      </g>
    </svg>
  )
}

function SandyScene() {
  return (
    <svg
      className="tut-scene-svg"
      viewBox="0 0 100 60"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Illustrated underwater scene: sandy seabed"
    >
      <defs>
        <linearGradient id="tut-water-sandy" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3f7a63" />
          <stop offset="100%" stopColor="#163c30" />
        </linearGradient>
      </defs>
      <rect width="100" height="60" fill="url(#tut-water-sandy)" />
      {/* flat sandy seabed, higher and paler than the reef's rocky bottom */}
      <path d="M0 46 Q30 42 55 45 T100 44 V60 H0 Z" fill="#c9a865" opacity="0.9" />
      {/* driftwood, opposite corner from the reef's rock */}
      <path d="M62 46 L84 40 L85 43 L64 49 Z" fill="#5a4632" />
      {/* kelp fronds, opposite the reef's coral */}
      <path d="M22 46 Q20 30 24 18 Q26 30 24 46 Z" fill="#3f7a4a" />
      <path d="M28 46 Q27 34 31 24 Q32 34 30 46 Z" fill="#4d8f57" />
      {/* fish, different position and facing direction */}
      <g fill="#d8dde0">
        <ellipse cx="70" cy="16" rx="4.5" ry="2.2" />
        <path d="M65.5 16 l-4 -2.3 v4.6 Z" />
      </g>
      {/* drifting particles, different position than the reef's bubbles */}
      <g fill="#ffffff" opacity="0.35">
        <circle cx="15" cy="12" r="1.2" />
        <circle cx="18" cy="18" r="0.9" />
        <circle cx="12" cy="20" r="0.7" />
      </g>
    </svg>
  )
}
