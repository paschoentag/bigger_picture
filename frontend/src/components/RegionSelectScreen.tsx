import { useEffect, useMemo, useState } from 'react'
import Globe from 'react-globe.gl'
import { fetchRegions } from '../api/regionApi'
import type { Region, RegionMesh, User } from '../api/types'
import { meshCentroid, normalizeMeshWinding } from '../geo'
import { useContainerSize } from '../useContainerSize'
import AccountBar from './AccountBar'
import './RegionSelectScreen.css'

const CAP_COLOR = 'rgba(42, 120, 214, 0.55)'
const CAP_COLOR_HOVER = 'rgba(233, 168, 47, 0.75)'
const STROKE_COLOR = 'rgba(255, 255, 255, 0.85)'

// Warm gold beacons (rings + an anchor dot) mark every region's location so
// tiny areas stay findable — and clickable — against the blue ocean, even when
// their polygon is only a few pixels across.
const BEACON_RGB = '233, 168, 47'
const BEACON_RGB_HOVER = '255, 214, 120'

/** A region's location on the globe, used for its beacon ring and anchor dot. */
type Beacon = { region: Region; lat: number; lng: number; span: number }

export default function RegionSelectScreen({
  user,
  onSelect,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  user: User
  onSelect: (region: Region) => void
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenQuests: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  const [regions, setRegions] = useState<Region[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hovered, setHovered] = useState<Region | null>(null)
  const { ref: globeContainerRef, size: globeSize } = useContainerSize()

  useEffect(() => {
    fetchRegions()
      .then(setRegions)
      .catch(() => setError('Could not load regions. Please try again.'))
  }, [])

  const meshedRegions = useMemo(
    () =>
      (regions ?? [])
        .filter((r): r is Region & { metadata: { mesh: RegionMesh } } => !!r.metadata?.mesh)
        .map((r) => ({ ...r, metadata: { ...r.metadata, mesh: normalizeMeshWinding(r.metadata.mesh) } })),
    [regions],
  )

  const beacons = useMemo<Beacon[]>(
    () => meshedRegions.map((r) => ({ region: r, ...meshCentroid(r.metadata.mesh) })),
    [meshedRegions],
  )

  return (
    <div className="region-select-screen">
      <AccountBar
        user={user}
        onOpenAdmin={onOpenAdmin}
        onOpenStats={onOpenStats}
        onOpenQuests={onOpenQuests}
        onOpenCommunityStats={onOpenCommunityStats}
        onOpenLeaderboard={onOpenLeaderboard}
        onLogout={onLogout}
      />

      <header className="region-select-header">
        <p className="region-select-eyebrow">Journey of the Eel</p>
        <h1>Choose a region</h1>
        <p>Every region holds its own set of dive imagery. Spin the globe and pick a highlighted area, or choose from the list below.</p>
      </header>

      {error && <p className="game-status game-status-error">{error}</p>}
      {!error && regions === null && <p className="game-status">Loading regions…</p>}

      {regions !== null && (
        <>
          <div className="region-globe-container" ref={globeContainerRef}>
            {globeSize.width > 0 && (
              <Globe
                width={globeSize.width}
                height={globeSize.height}
                globeImageUrl="/globe/earth-blue-marble.jpg"
                backgroundImageUrl="/globe/night-sky.png"
                polygonsData={meshedRegions}
                // react-globe.gl's bundled GeoJsonGeometry type declares `coordinates: number[]`,
                // which is too narrow for real Polygon/MultiPolygon geometry (nested arrays).
                polygonGeoJsonGeometry={(r) =>
                  (r as (typeof meshedRegions)[number]).metadata.mesh as unknown as { type: string; coordinates: number[] }
                }
                polygonCapColor={(r) => ((r as Region) === hovered ? CAP_COLOR_HOVER : CAP_COLOR)}
                polygonSideColor={() => 'rgba(42, 120, 214, 0.25)'}
                polygonStrokeColor={() => STROKE_COLOR}
                polygonAltitude={(r) => ((r as Region) === hovered ? 0.02 : 0.008)}
                polygonLabel={(r) => (r as Region).title}
                onPolygonHover={(r) => setHovered(r as Region | null)}
                onPolygonClick={(r) => onSelect(r as Region)}
                // A thin gold spike standing orthogonally off the surface: a
                // point rendered as a tall, thin radial cylinder. Visible from
                // any angle even when the region's footprint is a few pixels,
                // and its whole height is a generous click target.
                pointsData={beacons}
                pointColor={(b) =>
                  `rgba(${(b as Beacon).region === hovered ? BEACON_RGB_HOVER : BEACON_RGB}, 0.92)`
                }
                pointAltitude={(b) => ((b as Beacon).region === hovered ? 0.2 : 0.16)}
                pointRadius={(b) => ((b as Beacon).region === hovered ? 0.28 : 0.18)}
                pointLabel={(b) => (b as Beacon).region.title}
                onPointHover={(b) => setHovered(b ? (b as Beacon).region : null)}
                onPointClick={(b) => onSelect((b as Beacon).region)}
                // Pulsing ring: draws the eye to each region's location.
                ringsData={beacons}
                ringAltitude={0.011}
                ringMaxRadius={(b) => Math.min(6, Math.max(2.5, (b as Beacon).span))}
                ringPropagationSpeed={2}
                ringRepeatPeriod={1400}
                ringColor={(b: object) => {
                  const rgb = (b as Beacon).region === hovered ? BEACON_RGB_HOVER : BEACON_RGB
                  return (t: number) => `rgba(${rgb}, ${0.55 * (1 - t)})`
                }}
              />
            )}
          </div>

          <div className="region-list">
            {regions.length === 0 && <p className="game-status">No regions have been added yet.</p>}
            {regions.map((region) => (
              <button
                type="button"
                key={region.uuid}
                className="btn region-list-item"
                onClick={() => onSelect(region)}
              >
                {region.title}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
