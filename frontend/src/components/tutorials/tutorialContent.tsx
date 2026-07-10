import type { SceneContent } from './ExampleScene'

/**
 * One page of Verify's tutorial: passive explanation plus a static example
 * scene. Scene art is data-driven: without an `image` a stylized placeholder
 * reef is drawn instead, so real photos (plus their point coordinates) can be
 * dropped in later without touching the modal. See {@link ExampleScene}.
 */
export interface TutorialStep {
  title: string
  body: string
  tips?: string[]
  scene?: SceneContent
}

// Overlap and Annotate each have their own bespoke, action-driven walkthrough
// (see OverlapTutorial.tsx / AnnotateTutorial.tsx) rather than this static
// step deck, which only Verify still uses.
export type TutorialContent = Record<'verify', TutorialStep[]>

// NOTE: placeholder example art. Point coordinates are positioned against the
// stylized SVG reef in ExampleScene; when swapping in real imagery, set
// `scene.image` and re-place these points to match the photo's features.
export const TUTORIALS: TutorialContent = {
  verify: [
    {
      title: 'Check another player’s work',
      body: 'You are reviewing points that someone else placed. Each numbered marker should sit on the same physical spot in both images. Your job is to judge each one.',
      scene: {
        points: [
          { point: { x: 0.32, y: 0.6 }, kind: 'good', label: '1' },
          { point: { x: 0.68, y: 0.4 }, kind: 'good', label: '2' },
        ],
      },
    },
    {
      title: 'Approve the good, flag the wrong',
      body: 'Approve a point when both markers clearly land on the same feature. Flag it when they do not line up, or when it sits on something that moves (a fish, a diver, a bubble). When in doubt, flag it.',
      scene: {
        points: [
          { point: { x: 0.3, y: 0.62 }, kind: 'good', label: 'lines up' },
          { point: { x: 0.62, y: 0.28 }, kind: 'bad', label: 'on a fish' },
        ],
      },
    },
    {
      title: 'Nothing saves until you submit',
      body: 'Your approve/flag choices are staged — nothing is sent until you press Submit, so you can change or clear a mark first. It is fine to submit only the points you are sure about and leave the rest.',
    },
  ],
}
