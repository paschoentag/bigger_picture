import { useState } from 'react'
import { createLabel, fetchLabels, updateLabel } from '../api/labelApi'
import type { User } from '../api/types'
import AdminImportAdmin from './admin/AdminImportAdmin'
import DatasetAdmin from './admin/DatasetAdmin'
import FunFactsAdmin from './admin/FunFactsAdmin'
import PasswordSettings from './admin/PasswordSettings'
import RegionsAdmin from './admin/RegionsAdmin'
import SimpleEntityAdmin from './admin/SimpleEntityAdmin'
import UsersAdmin from './admin/UsersAdmin'
import ZipUploadAdmin from './admin/ZipUploadAdmin'
import AccountBar from './AccountBar'
import './AdminScreen.css'

/**
 * SimpleEntityAdmin builds its create/update payload dynamically from a field
 * config, so it only knows the input shape as `Record<string, unknown>`. The
 * real API functions want a narrower, specific input type; these adapters
 * bridge that gap in one place instead of loosening SimpleEntityAdmin's types.
 */
function createLabelAdapter(input: Record<string, unknown>) {
  return createLabel(input as { scope: string; title: string; description?: string | null })
}
function updateLabelAdapter(uuid: string, input: Record<string, unknown>) {
  return updateLabel(uuid, input as { scope?: string; title?: string; description?: string | null })
}

type Tab = 'regions' | 'labels' | 'facts' | 'users' | 'dataset' | 'import' | 'adminImport' | 'password'

const LABEL_FIELDS = [
  { key: 'scope', label: 'Scope', type: 'text', required: true } as const,
  { key: 'title', label: 'Title', type: 'text', required: true } as const,
  { key: 'description', label: 'Description', type: 'textarea' } as const,
]

export default function AdminScreen({
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
  const isAdmin = user.role === 'admin'
  const isAnnotator = user.role === 'annotator'
  const [tab, setTab] = useState<Tab>(isAnnotator ? 'password' : 'regions')

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
        {isAnnotator ? (
          <>
            <h1>Password</h1>
            <p>Set or change the password for your account.</p>
          </>
        ) : (
          <>
            <h1>Admin</h1>
            <p>Manage regions, labels, facts, the dataset, and bulk imports{isAdmin ? ', and users' : ''}.</p>
          </>
        )}
      </header>

      {!isAnnotator && (
        <div className="admin-tab-bar">
          <button type="button" className={`btn${tab === 'regions' ? ' btn-primary' : ''}`} onClick={() => setTab('regions')}>
            Regions
          </button>
          <button type="button" className={`btn${tab === 'labels' ? ' btn-primary' : ''}`} onClick={() => setTab('labels')}>
            Labels
          </button>
          <button type="button" className={`btn${tab === 'facts' ? ' btn-primary' : ''}`} onClick={() => setTab('facts')}>
            Facts
          </button>
          <button type="button" className={`btn${tab === 'dataset' ? ' btn-primary' : ''}`} onClick={() => setTab('dataset')}>
            Dataset
          </button>
          <button type="button" className={`btn${tab === 'import' ? ' btn-primary' : ''}`} onClick={() => setTab('import')}>
            Bulk Import
          </button>
          {isAdmin && (
            <button
              type="button"
              className={`btn${tab === 'adminImport' ? ' btn-primary' : ''}`}
              onClick={() => setTab('adminImport')}
            >
              Admin Import
            </button>
          )}
          {isAdmin && (
            <button type="button" className={`btn${tab === 'users' ? ' btn-primary' : ''}`} onClick={() => setTab('users')}>
              Users
            </button>
          )}
          <button type="button" className={`btn${tab === 'password' ? ' btn-primary' : ''}`} onClick={() => setTab('password')}>
            Password
          </button>
        </div>
      )}

      {tab === 'regions' && !isAnnotator && <RegionsAdmin />}
      {tab === 'labels' && !isAnnotator && (
        <SimpleEntityAdmin
          entityName="Labels"
          fields={LABEL_FIELDS}
          fetchList={fetchLabels}
          create={createLabelAdapter}
          update={updateLabelAdapter}
        />
      )}
      {tab === 'facts' && !isAnnotator && <FunFactsAdmin />}
      {tab === 'dataset' && !isAnnotator && <DatasetAdmin />}
      {tab === 'import' && !isAnnotator && <ZipUploadAdmin />}
      {tab === 'adminImport' && isAdmin && <AdminImportAdmin />}
      {tab === 'users' && isAdmin && <UsersAdmin currentUserUuid={user.uuid} />}
      {tab === 'password' && <PasswordSettings />}
    </div>
  )
}
