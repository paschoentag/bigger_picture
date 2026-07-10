import { useEffect, useState } from 'react'
import { fetchNextImagePair } from '../api/annotationApi'
import { fetchDivesForRegion } from '../api/diveApi'
import { fetchNextCandidatePair } from '../api/overlapApi'
import type { Region, User } from '../api/types'
import { fetchNextPendingVerification } from '../api/verifyApi'
import AccountBar from './AccountBar'
import './HomeScreen.css'
import glass_eel_2 from '../../images/glass_eel_2.png'
import yellow_eel from '../../images/yellow_eel.png'
import silver_eel_2 from '../../images/silver_eel_2.png'

export type GameId = 'overlap' | 'annotate' | 'verify'

interface GameCard {
  id: GameId
  league: string
  title: string
  flavor: string
  longflavor: string
  description: string
  image: string
  active: boolean
}

const GAMES: GameCard[] = [
  {
    id: 'overlap',
    league: 'Glass Eel League',
    title: 'Finding Overlap',
    flavor: 'A glass eel drifts in from the open ocean, scanning the coastline for familiar water.',
    longflavor: 'After drifting around for 2 years, the larvae of the european eel reach the continental shelf. Upon approaching they metamorphose into the transparent juveniles called glass eels and set off on a journey inland.',
    image: glass_eel_2,
    description: 'Look at two marine images and decide whether they show the same physical scene.',
    active: true,
  },
  {
    id: 'annotate',
    league: 'Yellow Eel League',
    title: 'Annotating',
    flavor: 'For years, a yellow eel learns every rock and reed of its river home by heart.',
    longflavor: 'In Coastal Waters, the Eel reaches the next stage of life and grows into a yellow eel. This stage typically lasts 5-20 years.',
    image: yellow_eel,
    description: 'Click matching points between two overlapping images to build ground-truth correspondences.',
    active: true,
  },
  {
    id: 'verify',
    league: 'Silver Eel League',
    title: 'Verification',
    image: silver_eel_2,
    flavor: 'Before the long migration back to sea, a silver eel double-checks its bearings.',
    longflavor: 'As a silver eel, they set out to return to their birth place, the Sargasso Sea, to mate. In large groups they undertake a 6.000 km long journey.',
    description: "Review another player's annotation and flag it if it doesn't look right.",
    active: true,
  },
]

export default function HomeScreen({
  onPlay,
  user,
  region,
  onChangeRegion,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  onPlay: (id: GameId) => void
  user: User
  region: Region
  onChangeRegion: () => void
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenQuests: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  // Per-game availability for this region: `undefined` while we're still probing;
  // otherwise `true` if the game has something to serve, `false` if it's empty.
  // A region can have dives but no candidate/image pairs for a given stage (or the
  // player may have already worked through them), so we probe each game the same
  // way the game screen does — resolve a dive, then ask that stage's "next" endpoint.
  const [availability, setAvailability] = useState<Record<GameId, boolean> | undefined>(undefined)

  const [expandedCards, setExpandedCards] = useState<Record<GameId, boolean>>({
    overlap: false,
    annotate: false,
    verify: false,
  })
  
  const toggleCard = (id: GameId) => {
    setExpandedCards((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }
  

  useEffect(() => {
    let cancelled = false
    setAvailability(undefined)

    async function probe(diveUuid: string): Promise<Record<GameId, boolean>> {
      const [overlap, annotate, verify] = await Promise.all([
        fetchNextCandidatePair(diveUuid),
        fetchNextImagePair(diveUuid),
        fetchNextPendingVerification(diveUuid),
      ])
      return { overlap: overlap !== null, annotate: annotate !== null, verify: verify !== null }
    }

    fetchDivesForRegion(region.uuid)
      .then((dives) => {
        const dive = dives[0]
        if (!dive) return { overlap: false, annotate: false, verify: false }
        return probe(dive.uuid)
      })
      // On a fetch error we can't be sure the region is empty, so leave every game
      // playable and let the game screen surface the failure itself.
      .catch(() => ({ overlap: true, annotate: true, verify: true }))
      .then((result) => {
        if (!cancelled) setAvailability(result)
      })

    return () => {
      cancelled = true
    }
  }, [region.uuid])

  const tooltip = `There's nothing to play in this stage for ${region.title} right now — it has no imagery for this stage yet, or you've already worked through it. Try another region.`

  return (
    <div className="home-screen">
      <AccountBar
        user={user}
        region={region}
        onChangeRegion={onChangeRegion}
        onOpenAdmin={onOpenAdmin}
        onOpenStats={onOpenStats}
        onOpenQuests={onOpenQuests}
        onOpenCommunityStats={onOpenCommunityStats}
        onOpenLeaderboard={onOpenLeaderboard}
        onLogout={onLogout}
      />

      <header className="home-header">
        <p className="home-eyebrow">Journey of the Eel</p>
        <h1>Sea the Bigger Picture</h1>
        <p>
          Every year, European eels leave the rivers where they grew up and swim thousands of kilometres back to
          the Sargasso Sea to spawn — a route no one has ever fully mapped. Play through three leagues of the
          eel's life to help scientists retrace it, one matched image at a time.
        </p>
      </header>

      <div className="game-card-row">
        {GAMES.map((game) => {
          // `undefined` availability = still probing; treat as playable so the
          // buttons don't flash disabled on every home visit.
          const noData = game.active && availability?.[game.id] === false
          const disabled = !game.active || noData
          return (
            <article
              className={`game-card${disabled ? ' game-card-locked' : ''}${noData ? ' game-card-nodata' : ''}`}
              data-game={game.id}
              key={game.id}
            >
              <span className="game-card-league">{game.league}</span>
              <h2>{game.title}</h2>
              <p className="game-card-flavor">{game.flavor}</p>
              {expandedCards[game.id] && (
              <p className="game-card-longtext">
                  {game.longflavor}
                </p>
              )}

              <button
                type="button"
                className="read-more-button"
                onClick={() => toggleCard(game.id)}
              >
                {expandedCards[game.id] ? 'Read less' : 'Read more'}
              </button>
              <img
                src={game.image}
                alt={game.title}
                className="game-card-image"
              />
              <p>{game.description}</p>
              <button
                type="button"
                className="btn btn-primary"
                disabled={disabled}
                onClick={() => onPlay(game.id)}
              >
                {!game.active ? 'Coming soon' : noData ? 'No data yet' : 'Play'}
              </button>
              {noData && (
                <span className="game-card-tooltip" role="tooltip">
                  {tooltip}
                </span>
              )}
            </article>
          )
        })}
      </div>
    </div>
  )
}
