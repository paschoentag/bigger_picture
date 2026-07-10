import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { createUser, listUsers, updateUser } from '../../api/adminApi'
import { ApiError } from '../../api/client'
import type { Role, UserSummary } from '../../api/types'
import './AdminPanels.css'

const ROLES: Role[] = ['annotator', 'scientist', 'admin']

// Mirrors MIN_PASSWORD_LENGTH / MAX_PASSWORD_LENGTH in backend/src/password_auth/hashing.py.
const MIN_PASSWORD_LENGTH = 10
const MAX_PASSWORD_LENGTH = 127

type FieldName = 'username' | 'password' | 'expertLevel'

export default function UsersAdmin({ currentUserUuid }: { currentUserUuid: string }) {
  const [users, setUsers] = useState<UserSummary[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<UserSummary | null>(null)
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<Role>('annotator')
  const [expertLevel, setExpertLevel] = useState('0')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [touched, setTouched] = useState<Record<FieldName, boolean>>({
    username: false,
    password: false,
    expertLevel: false,
  })

  const expertLevelNumber = Number(expertLevel)
  const fieldErrors: Partial<Record<FieldName, string>> = {}
  if (!username.trim()) fieldErrors.username = 'Username is required.'
  if (!Number.isInteger(expertLevelNumber)) fieldErrors.expertLevel = 'Must be a whole number.'
  if (!editing && !password) {
    fieldErrors.password = 'Password is required.'
  } else if (password && (password.length < MIN_PASSWORD_LENGTH || password.length > MAX_PASSWORD_LENGTH)) {
    fieldErrors.password = `Must be ${MIN_PASSWORD_LENGTH}-${MAX_PASSWORD_LENGTH} characters.`
  }
  const hasFieldErrors = Object.keys(fieldErrors).length > 0
  const touchField = (field: FieldName) => setTouched((t) => ({ ...t, [field]: true }))

  const load = () => {
    setLoading(true)
    setError(null)
    listUsers()
      .then(setUsers)
      .catch(() => setError('Could not load users.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const startCreate = () => {
    setEditing(null)
    setUsername('')
    setRole('annotator')
    setExpertLevel('0')
    setPassword('')
    setFormError(null)
    setTouched({ username: false, password: false, expertLevel: false })
  }

  const startEdit = (user: UserSummary) => {
    setEditing(user)
    setUsername(user.username)
    setRole(user.role)
    setExpertLevel(String(user.expert_level))
    setPassword('')
    setFormError(null)
    setTouched({ username: false, password: false, expertLevel: false })
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (submitting) return

    setTouched({ username: true, password: true, expertLevel: true })
    if (hasFieldErrors) return

    setFormError(null)
    setSubmitting(true)
    const request = editing
      ? updateUser(editing.uuid, {
          username,
          role,
          expert_level: expertLevelNumber,
          ...(password ? { password } : {}),
        })
      : createUser({ username, role, expert_level: expertLevelNumber, password })
    request
      .then(() => {
        load()
        startCreate()
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiError ? err.message : 'Could not save this user.')
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-list">
        {loading && <p className="game-status">Loading…</p>}
        {error && <p className="game-status game-status-error">{error}</p>}
        {users && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Expert level</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.uuid} className={editing?.uuid === user.uuid ? 'admin-row-active' : ''}>
                  <td>
                    {user.username}
                    {user.uuid === currentUserUuid && ' (you)'}
                  </td>
                  <td>{user.role}</td>
                  <td>{user.expert_level}</td>
                  <td>
                    <button type="button" className="btn" onClick={() => startEdit(user)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form className="admin-form" onSubmit={handleSubmit}>
        <h3>{editing ? 'Edit user' : 'New user'}</h3>
        <label className="admin-form-field">
          Username
          <input
            type="text"
            value={username}
            required
            onChange={(e) => setUsername(e.target.value)}
            onBlur={() => touchField('username')}
            aria-invalid={touched.username && !!fieldErrors.username}
          />
          {touched.username && fieldErrors.username && (
            <span className="admin-field-error">{fieldErrors.username}</span>
          )}
        </label>
        <label className="admin-form-field">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="admin-form-field">
          Expert level
          <input
            type="number"
            value={expertLevel}
            required
            onChange={(e) => setExpertLevel(e.target.value)}
            onBlur={() => touchField('expertLevel')}
            aria-invalid={touched.expertLevel && !!fieldErrors.expertLevel}
          />
          {touched.expertLevel && fieldErrors.expertLevel && (
            <span className="admin-field-error">{fieldErrors.expertLevel}</span>
          )}
        </label>
        <label className="admin-form-field">
          {editing ? 'New password (leave blank to keep existing)' : 'Password'}
          <input
            type="password"
            value={password}
            required={!editing}
            minLength={MIN_PASSWORD_LENGTH}
            maxLength={MAX_PASSWORD_LENGTH}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => touchField('password')}
            aria-invalid={touched.password && !!fieldErrors.password}
          />
          {touched.password && fieldErrors.password ? (
            <span className="admin-field-error">{fieldErrors.password}</span>
          ) : (
            <span className="admin-field-hint">
              {editing ? `Leave blank to keep the current password, or use ${MIN_PASSWORD_LENGTH}-${MAX_PASSWORD_LENGTH} characters.` : `${MIN_PASSWORD_LENGTH}-${MAX_PASSWORD_LENGTH} characters.`}
            </span>
          )}
        </label>
        {formError && <p className="game-status game-status-error">{formError}</p>}
        <div className="admin-form-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || hasFieldErrors}
            title={hasFieldErrors ? Object.values(fieldErrors).join(' ') : undefined}
          >
            {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create'}
          </button>
          {editing && (
            <button type="button" className="btn" onClick={startCreate}>
              Cancel
            </button>
          )}
        </div>
        {hasFieldErrors && (
          <p className="admin-field-hint admin-form-blocking-hint">
            Can't submit yet: {Object.values(fieldErrors).join(' ')}
          </p>
        )}
      </form>
    </div>
  )
}
