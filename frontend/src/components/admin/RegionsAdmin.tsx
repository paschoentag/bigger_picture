import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import Globe from 'react-globe.gl'
import { ApiError } from '../../api/client'
import { createRegion, fetchRegions, updateRegion } from '../../api/regionApi'
import type { Region, RegionMesh } from '../../api/types'
import { normalizeMeshWinding } from '../../geo'
import { useContainerSize } from '../../useContainerSize'
import '../admin/AdminPanels.css'
import RegionDivesAdmin from './RegionDivesAdmin'
import './RegionsAdmin.css'

const OTHER_CAP_COLOR = 'rgba(42, 120, 214, 0.35)'
const OTHER_STROKE_COLOR = 'rgba(255, 255, 255, 0.6)'
const DRAWN_POINT_COLOR = '#e9a82f'
const DRAWN_PATH_COLOR = '#e9a82f'

interface LatLng {
  lat: number
  lng: number
}

/** Reads the exterior ring of a `Polygon` mesh as drawable vertices; anything else (no mesh, `MultiPolygon`) starts empty. */
function meshToPoints(mesh: RegionMesh | undefined): LatLng[] {
  if (!mesh || mesh.type !== 'Polygon') return []
  const ring = (mesh.coordinates as number[][][])[0]
  if (!ring || ring.length < 3) return []
  const points = ring.map(([lng, lat]) => ({ lat, lng }))
  const first = points[0]
  const last = points[points.length - 1]
  if (points.length > 1 && first.lat === last.lat && first.lng === last.lng) {
    points.pop()
  }
  return points
}

function pointsToMesh(points: LatLng[]): RegionMesh | undefined {
  if (points.length < 3) return undefined
  const ring = points.map((p) => [p.lng, p.lat])
  ring.push(ring[0])
  return { type: 'Polygon', coordinates: [ring] }
}

export default function RegionsAdmin() {
  const [regions, setRegions] = useState<Region[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Region | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [points, setPoints] = useState<LatLng[]>([])
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { ref: globeContainerRef, size: globeSize } = useContainerSize()
  const globeSectionRef = useRef<HTMLDivElement>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchRegions()
      .then(setRegions)
      .catch(() => setError('Could not load regions.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const startCreate = () => {
    setEditing(null)
    setTitle('')
    setDescription('')
    setPoints([])
    setFormError(null)
  }

  const startEdit = (region: Region) => {
    setEditing(region)
    setTitle(region.title)
    setDescription(region.description ?? '')
    setPoints(meshToPoints(region.metadata?.mesh))
    setFormError(null)
    globeSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (submitting) return

    if (points.length > 0 && points.length < 3) {
      setFormError('Draw at least 3 points to define an area, or clear them to save without one.')
      return
    }

    const mesh = pointsToMesh(points)
    const input = { title, description: description.trim() === '' ? null : description, metadata: mesh ? { mesh } : null }

    setFormError(null)
    setSubmitting(true)
    const request = editing ? updateRegion(editing.uuid, input) : createRegion(input)
    request
      .then(() => {
        load()
        startCreate()
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiError ? err.message : 'Could not save this region.')
      })
      .finally(() => setSubmitting(false))
  }

  const otherRegionsMeshed = useMemo(
    () =>
      (regions ?? [])
        .filter((r) => r.uuid !== editing?.uuid)
        .filter((r): r is Region & { metadata: { mesh: RegionMesh } } => !!r.metadata?.mesh)
        .map((r) => ({ ...r, metadata: { ...r.metadata, mesh: normalizeMeshWinding(r.metadata.mesh) } })),
    [regions, editing],
  )

  const drawnPath = points.length >= 2 ? [...points, points[0]] : points

  return (
    <div className="regions-admin">
      <div className="admin-panel-list">
        {loading && <p className="game-status">Loading…</p>}
        {error && <p className="game-status game-status-error">{error}</p>}
        {regions && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Description</th>
                <th>Area</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {regions.map((region) => (
                <tr key={region.uuid} className={editing?.uuid === region.uuid ? 'admin-row-active' : ''}>
                  <td>{region.title}</td>
                  <td>{region.description ?? ''}</td>
                  <td>{region.metadata?.mesh ? 'Defined' : '—'}</td>
                  <td>
                    <button type="button" className="btn" onClick={() => startEdit(region)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {regions.length === 0 && (
                <tr>
                  <td colSpan={4}>No regions yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <form className="regions-admin-form" onSubmit={handleSubmit}>
        <h3>{editing ? 'Edit region' : 'New region'}</h3>

        <div className="regions-admin-text-fields">
          <label className="admin-form-field">
            Title
            <input type="text" value={title} required onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="admin-form-field">
            Description
            <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </div>

        <div className="regions-admin-globe-field" ref={globeSectionRef}>
          <p className="regions-admin-globe-hint">
            Click the globe to place the region's boundary points
            {points.length > 0 && points.length < 3 ? ` (${points.length} placed, need at least 3)` : ''}.
          </p>
          <div className="regions-admin-globe-container" ref={globeContainerRef}>
            {globeSize.width > 0 && (
              <Globe
                width={globeSize.width}
                height={globeSize.height}
                globeImageUrl="/globe/earth-blue-marble.jpg"
                backgroundImageUrl="/globe/night-sky.png"
                onGlobeClick={({ lat, lng }) => setPoints((prev) => [...prev, { lat, lng }])}
                polygonsData={otherRegionsMeshed}
                // react-globe.gl's bundled GeoJsonGeometry type declares `coordinates: number[]`,
                // which is too narrow for real Polygon/MultiPolygon geometry (nested arrays).
                polygonGeoJsonGeometry={(r) =>
                  (r as (typeof otherRegionsMeshed)[number]).metadata.mesh as unknown as { type: string; coordinates: number[] }
                }
                polygonCapColor={() => OTHER_CAP_COLOR}
                polygonSideColor={() => 'rgba(42, 120, 214, 0.15)'}
                polygonStrokeColor={() => OTHER_STROKE_COLOR}
                polygonAltitude={0.006}
                polygonLabel={(r) => (r as Region).title}
                pointsData={points}
                pointLat="lat"
                pointLng="lng"
                pointColor={() => DRAWN_POINT_COLOR}
                pointAltitude={0.012}
                pointRadius={0.35}
                pathsData={drawnPath.length >= 2 ? [drawnPath] : []}
                pathPoints={(p) => p as LatLng[]}
                pathPointLat="lat"
                pathPointLng="lng"
                pathColor={() => DRAWN_PATH_COLOR}
                pathStroke={2}
              />
            )}
          </div>
          <div className="admin-form-actions">
            <button
              type="button"
              className="btn"
              onClick={() => setPoints((prev) => prev.slice(0, -1))}
              disabled={points.length === 0}
            >
              Undo point
            </button>
            <button type="button" className="btn" onClick={() => setPoints([])} disabled={points.length === 0}>
              Clear points
            </button>
          </div>
        </div>

        {formError && <p className="game-status game-status-error">{formError}</p>}
        <div className="admin-form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create'}
          </button>
          {editing && (
            <button type="button" className="btn" onClick={startCreate}>
              Cancel
            </button>
          )}
        </div>
      </form>

      {editing && (
        <div className="regions-admin-dives">
          <h3>Dives in {editing.title}</h3>
          <RegionDivesAdmin key={editing.uuid} regionUuid={editing.uuid} />
        </div>
      )}
    </div>
  )
}
