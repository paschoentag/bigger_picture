import type { NormalizedPoint } from '../../api/types'

/**
 * How far the placeholder reef's fixed landmarks (rock, coral) move, in the
 * scene's own normalized [0,1] space, between the default framing and
 * ExampleScene's `'angled'` variant (a small pan/rotate - both landmarks stay
 * fully visible). Exported so callers (e.g. OverlapTutorial) can shift a
 * highlight ring to track the same landmark across both scenes.
 */
export const ANGLED_LANDMARK_SHIFT: NormalizedPoint = { x: 9 / 100, y: -2 / 60 }

/**
 * Same idea as {@link ANGLED_LANDMARK_SHIFT}, but for the `'partial'` variant:
 * a much larger pan that pushes the coral mostly out of frame, leaving only
 * the rock shared between the two scenes - a partial overlap still counts as
 * the same physical place.
 */
export const PARTIAL_LANDMARK_SHIFT: NormalizedPoint = { x: 38 / 100, y: -3 / 60 }
