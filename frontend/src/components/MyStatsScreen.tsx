import { useEffect, useState } from 'react'
import { fetchMyStats } from '../api/statsApi'
import type { MyStats } from '../api/statsApi'
import type { User } from '../api/types'
import AccountBar from './AccountBar'
import { AccuracyGauge, ProgressMeter, SplitBar } from './StatCharts'
import './MyStatsScreen.css'

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat-cell">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

export default function MyStatsScreen({
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
  const [stats, setStats] = useState<MyStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyStats()
      .then(setStats)
      .catch(() => setError('Could not load your statistics.'))
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
        <h1>My Stats</h1>
        <p>Your contributions and accuracy across the three leagues, {user.username}.</p>
      </header>

      {error && <p className="game-status game-status-error">{error}</p>}
      {!error && !stats && <p className="game-status">Loading…</p>}

      {stats && (
        <>
          <section className="stat-section" data-game="overlap">
            <h2>Finding Overlap</h2>
            <div className="stat-grid">
              <Stat label="Pairs marked" value={stats.overlap.pairs_marked} />
              <Stat label="Overlapping pairs overall" value={stats.overlap.overall_pairs_with_overlap} />
            </div>
            <div className="stat-charts">
              <AccuracyGauge caption="Accuracy (all time)" stat={stats.overlap.accuracy_all_time} />
              <AccuracyGauge caption={`Accuracy (last ${stats.window})`} stat={stats.overlap.accuracy_window} />
              <div className="stat-charts-wide">
                <span className="stat-charts-title">Your calls</span>
                <SplitBar
                  segments={[
                    { label: 'Overlaps found', value: stats.overlap.overlaps_found },
                    {
                      label: 'Different scene',
                      value: stats.overlap.pairs_marked - stats.overlap.overlaps_found,
                    },
                  ]}
                />
              </div>
            </div>
          </section>

          <section className="stat-section" data-game="annotate">
            <h2>Annotating</h2>
            <div className="stat-grid">
              <Stat label="Annotations" value={stats.annotate.annotations} />
              <Stat label="Pairs marked" value={stats.annotate.pairs_marked} />
            </div>
            <div className="stat-charts">
              <AccuracyGauge caption="Accuracy (all time)" stat={stats.annotate.accuracy_all_time} />
              <AccuracyGauge caption={`Accuracy (last ${stats.window})`} stat={stats.annotate.accuracy_window} />
              <div className="stat-charts-wide">
                <span className="stat-charts-title">Reviewed so far</span>
                <ProgressMeter
                  label="Annotations verified"
                  value={stats.annotate.annotations_verified}
                  total={stats.annotate.annotations}
                />
                <ProgressMeter
                  label="Pairs verified"
                  value={stats.annotate.pairs_verified}
                  total={stats.annotate.pairs_marked}
                />
              </div>
            </div>
          </section>

          <section className="stat-section" data-game="verify">
            <h2>Verification</h2>
            <div className="stat-grid">
              <Stat label="Reviews done" value={stats.verify.verified} />
            </div>
            <div className="stat-charts">
              <div className="stat-charts-wide">
                <span className="stat-charts-title">How you judged them</span>
                <SplitBar
                  segments={[
                    { label: 'Faults found', value: stats.verify.faulty_found },
                    { label: 'Accepted', value: stats.verify.accepted },
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
