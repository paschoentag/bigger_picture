import type { User } from '../api/types'
import teamPhoto from '../assets/team.jpg'
import AccountBar from './AccountBar'
import './TeamScreen.css'

interface TeamMember {
  name: string
  githubHandle: string
}

/**
 * Pulled from the project's git history (`git log --format="%an <%ae>"`),
 * since there's no dedicated contributors list elsewhere in the repo.
 */
const TEAM: TeamMember[] = [
  { name: 'Sascha Mahmood', githubHandle: 'savenger' },
  { name: 'Patricia Schöntag', githubHandle: 'paschoentag' },
  { name: 'Julius ', githubHandle: 'cateagle' },
  { name: 'Paul C. Busch', githubHandle: 'chaosbit' },
  { name: 'Wiebke Engler', githubHandle: 'Wiebke-Engler' },
  { name: 'Barbara Glemser', githubHandle: 'bglemser' },
  { name: 'Meike Nienaber', githubHandle: 'Meike1711' },
  { name: 'Raphaela Lopes', githubHandle: 'raoahela' },
]

export default function TeamScreen({
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
  return (
    <div className="team-screen">
      <div className="game-header-top">
        <button type="button" className="back-link" onClick={onBack}>
          ← Back
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

      <header className="team-header">
        <p className="team-eyebrow">Journey of the Eel</p>
        <h1>Team</h1>
        <p>The people who built Sea the Bigger Picture.</p>
      </header>

      <img src={teamPhoto} alt="The Sea the Bigger Picture team" className="team-photo" />

      <ul className="team-list">
        {TEAM.map((member) => (
          <li key={member.githubHandle} className="team-list-item">
            <span className="team-name">{member.name}</span>
            <a
              className="team-contact"
              href={`https://github.com/${member.githubHandle}`}
              target="_blank"
              rel="noreferrer"
            >
              @{member.githubHandle}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
