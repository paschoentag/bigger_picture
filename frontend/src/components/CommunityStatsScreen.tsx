import { useEffect, useState } from 'react'
import { fetchCommunityStats } from '../api/statsApi'
import type { CommunityStats } from '../api/statsApi'
import type { User } from '../api/types'
import AccountBar from './AccountBar'
import { SplitBar, StageActivityChart } from './StatCharts'
import './MyStatsScreen.css'

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat-cell">
      <span className="stat-value">{value.toLocaleString()}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

export default function CommunityStatsScreen({
  user,
  onBack,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  user: User
  onBack: () => void
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenQuests: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  const [stats, setStats] = useState<CommunityStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCommunityStats()
      .then(setStats)
      .catch(() => setError('Could not load community statistics.'))
  }, [])

  return (
    <div className="game-screen">
      <header className="game-header">
        <div className="game-header-top">
          <button type="button" className="back-link" onClick={onBack}>
            ← Back to games
          </button>
          <AccountBar
            user={user}
            onOpenAdmin={onOpenAdmin}
            onOpenStats={onOpenStats}
            onOpenQuests={onOpenQuests}
            onOpenCommunityStats={onOpenCommunityStats}
            onOpenLeaderboard={onOpenLeaderboard}
            onLogout={onLogout}
          />
        </div>
        <h1>Community Stats</h1>
        <p>What every player has built together, across the whole dataset.</p>
      </header>

      {error && <p className="game-status game-status-error">{error}</p>}
      {!error && !stats && <p className="game-status">Loading…</p>}

      {stats && (
        <>
          <section className="stat-section" data-game="dataset">
            <h2>The Dataset</h2>
            <div className="stat-grid">
              <Stat label="Players" value={stats.users_total} />
              <Stat label="Regions" value={stats.regions_total} />
              <Stat label="Dives" value={stats.dives_total} />
              <Stat label="Images" value={stats.images_total} />
            </div>
          </section>

          <section className="stat-section" data-game="activity">
            <h2>Activity by Stage</h2>
            <StageActivityChart
              data={[
                { game: 'overlap', label: 'Overlap votes', value: stats.overlap.votes_cast },
                { game: 'annotate', label: 'Points submitted', value: stats.annotate.points_submitted },
                { game: 'verify', label: 'Reviews completed', value: stats.verify.reviews_completed },
              ]}
            />
          </section>

          <section className="stat-section" data-game="overlap">
            <h2>Finding Overlap</h2>
            <div className="stat-grid">
              <Stat label="Votes cast" value={stats.overlap.votes_cast} />
            </div>
            <div className="stat-charts">
              <div className="stat-charts-wide">
                <span className="stat-charts-title">How candidate pairs resolved</span>
                <SplitBar
                  segments={[
                    { label: 'Overlap found', value: stats.overlap.pairs_with_overlap },
                    { label: 'No overlap', value: stats.overlap.pairs_no_overlap },
                    { label: 'Still open', value: stats.overlap.pairs_still_open },
                  ]}
                />
              </div>
            </div>
          </section>

          <section className="stat-section" data-game="annotate">
            <h2>Annotating</h2>
            <div className="stat-grid">
              <Stat label="Points submitted" value={stats.annotate.points_submitted} />
              <Stat label="Pairs annotated" value={stats.annotate.pairs_annotated} />
            </div>
            <div className="stat-charts">
              <div className="stat-charts-wide">
                <span className="stat-charts-title">How submitted points resolved</span>
                <SplitBar
                  segments={[
                    { label: 'Verified', value: stats.annotate.points_verified },
                    {
                      label: 'Not approved',
                      value:
                        stats.annotate.points_submitted -
                        stats.annotate.points_verified -
                        stats.annotate.points_pending_review,
                    },
                    { label: 'Pending review', value: stats.annotate.points_pending_review },
                  ]}
                />
              </div>
            </div>
          </section>

          <section className="stat-section" data-game="verify">
            <h2>Verification</h2>
            <div className="stat-grid">
              <Stat label="Reviews completed" value={stats.verify.reviews_completed} />
            </div>
            <div className="stat-charts">
              <div className="stat-charts-wide">
                <span className="stat-charts-title">How reviewers judged</span>
                <SplitBar
                  segments={[
                    { label: 'Accepted', value: stats.verify.accepted },
                    { label: 'Rejected', value: stats.verify.rejected },
                  ]}
                />
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
