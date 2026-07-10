import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { claimQuest, fetchDailyQuests, type Quest } from '../api/questApi'
import type { User } from '../api/types'
import AccountBar from './AccountBar'
import './DailyQuestsScreen.css'

/**
 * Dedicated page for today's daily quests, reachable from the header menu.
 * Quests are the same for every player on a given day and rotate daily;
 * progress counts only confirmed (reviewed & approved) work, so a quest
 * advances once the player's work is confirmed, not merely submitted.
 */
export default function DailyQuestsScreen({
  user,
  onBack,
  onUserRefresh,
  onOpenAdmin,
  onOpenStats,
  onOpenQuests,
  onOpenCommunityStats,
  onOpenLeaderboard,
  onLogout,
}: {
  user: User
  onBack: () => void
  onUserRefresh: () => void
  onOpenAdmin: () => void
  onOpenStats: () => void
  onOpenQuests: () => void
  onOpenCommunityStats: () => void
  onOpenLeaderboard: () => void
  onLogout: () => void
}) {
  const [quests, setQuests] = useState<Quest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [claiming, setClaiming] = useState<string | null>(null)

  useEffect(() => {
    fetchDailyQuests()
      .then((data) => setQuests(data.quests))
      .catch(() => setError('Could not load today’s quests.'))
  }, [])

  async function handleClaim(key: string) {
    setClaiming(key)
    try {
      const result = await claimQuest(key)
      setQuests((prev) => prev?.map((q) => (q.key === key ? result.quest : q)) ?? prev)
      onUserRefresh()
    } catch (err) {
      // Progress/claim state moved on under us (e.g. a 409) — resync from server.
      if (err instanceof ApiError) {
        fetchDailyQuests()
          .then((data) => setQuests(data.quests))
          .catch(() => {})
      }
    } finally {
      setClaiming(null)
    }
  }

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
        <h1>Daily Quests</h1>
        <p>Today's goals, {user.username} — the same for every player, resetting each day.</p>
      </header>

      {error && <p className="game-status game-status-error">{error}</p>}
      {!error && quests === null && <p className="game-status">Loading…</p>}
      {!error && quests !== null && quests.length === 0 && <p className="game-status">No quests today.</p>}

      {quests && quests.length > 0 && (
        <ul className="daily-quests-list">
          {quests.map((quest) => {
            const pct = quest.target > 0 ? Math.min(1, quest.progress / quest.target) : 0
            return (
              <li key={quest.key} className={`quest-card${quest.completed ? ' quest-card-done' : ''}`}>
                <div className="quest-card-head">
                  <span className="quest-card-name">{quest.title}</span>
                  <span className="quest-card-reward">+{quest.reward_exp} XP</span>
                </div>
                <p className="quest-card-desc">{quest.description}</p>
                <div className="quest-progress">
                  <span className="quest-progress-bar">
                    <span className="quest-progress-fill" style={{ width: `${pct * 100}%` }} />
                  </span>
                  <span className="quest-progress-count">
                    {quest.progress}/{quest.target}
                  </span>
                </div>
                {quest.claimed ? (
                  <span className="quest-claimed">✓ Claimed</span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-primary quest-claim-btn"
                    disabled={!quest.completed || claiming === quest.key}
                    onClick={() => handleClaim(quest.key)}
                  >
                    {claiming === quest.key ? 'Claiming…' : quest.completed ? 'Claim reward' : 'In progress'}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
