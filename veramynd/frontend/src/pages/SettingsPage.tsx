import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, withProject } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { OverviewLoading } from '../components/OverviewStates'
import { UserAvatar } from '../components/UserAvatar'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

type Health = {
  ok: boolean
  error?: string | null
  project_id?: string
  default_project_id?: string
  lessons?: number
  alignments?: number
}

function validateName(name: string): string | null {
  const n = name.trim()
  if (n.length < 2) return 'Name must be at least 2 characters'
  if (!/^[A-Za-z][A-Za-z .'-]{1,118}$/.test(n)) return 'Use letters only (spaces and - \' . allowed)'
  return null
}

function validatePassword(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters'
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return 'Include letters and a number'
  return null
}

export function SettingsPage({
  reloadKey = 0,
  onReload,
}: {
  reloadKey?: number
  onReload?: () => void | Promise<void>
}) {
  const { project, projectId, hasProject, refreshProjects } = useProject()
  const { user, updateProfile, changePassword, logout, uploadAvatar, removeAvatar } = useAuth()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [reloading, setReloading] = useState(false)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [avatarErr, setAvatarErr] = useState<string | null>(null)

  const [name, setName] = useState(user?.name || '')
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileMsg, setProfileMsg] = useState<string | null>(null)
  const [profileErr, setProfileErr] = useState<string | null>(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwBusy, setPwBusy] = useState(false)
  const [pwMsg, setPwMsg] = useState<string | null>(null)
  const [pwErr, setPwErr] = useState<string | null>(null)

  useEffect(() => {
    setName(user?.name || '')
  }, [user?.name])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path =
        hasProject && projectId !== NONE_PROJECT_ID
          ? withProject('/api/health', projectId)
          : '/api/health'
      const data = await api<Health>(path)
      setHealth(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [hasProject, projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const reloadCatalog = async () => {
    setReloading(true)
    setError(null)
    setSuccess(null)
    try {
      if (onReload) {
        await onReload()
      } else {
        const q =
          hasProject && projectId !== NONE_PROJECT_ID
            ? `?project_id=${encodeURIComponent(projectId)}`
            : ''
        const res = await fetch(`/api/reload${q}`, { method: 'POST', credentials: 'include' })
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`)
      }
      await refreshProjects()
      await load()
      setSuccess('Catalog reloaded successfully.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReloading(false)
    }
  }

  const onSaveProfile = async (e: FormEvent) => {
    e.preventDefault()
    setProfileErr(null)
    setProfileMsg(null)
    const err = validateName(name)
    if (err) return setProfileErr(err)
    setProfileBusy(true)
    try {
      await updateProfile(name.trim())
      setProfileMsg('Profile updated')
    } catch (err2) {
      setProfileErr(err2 instanceof Error ? err2.message : String(err2))
    } finally {
      setProfileBusy(false)
    }
  }

  const onChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    setPwErr(null)
    setPwMsg(null)
    const err = validatePassword(newPassword)
    if (err) return setPwErr(err)
    if (newPassword !== confirmPassword) return setPwErr('Passwords do not match')
    setPwBusy(true)
    try {
      const message = await changePassword(currentPassword, newPassword)
      setPwMsg(message)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err2) {
      setPwErr(err2 instanceof Error ? err2.message : String(err2))
    } finally {
      setPwBusy(false)
    }
  }

  const onLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const onPickAvatar = () => fileRef.current?.click()

  const onAvatarSelected = async (file: File | undefined) => {
    if (!file) return
    setAvatarErr(null)
    if (!file.type.startsWith('image/')) {
      setAvatarErr('Choose an image file')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setAvatarErr('Image must be 2MB or smaller')
      return
    }
    setAvatarBusy(true)
    try {
      await uploadAvatar(file)
    } catch (err2) {
      setAvatarErr(err2 instanceof Error ? err2.message : String(err2))
    } finally {
      setAvatarBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onRemoveAvatar = async () => {
    setAvatarErr(null)
    setAvatarBusy(true)
    try {
      await removeAvatar()
    } catch (err2) {
      setAvatarErr(err2 instanceof Error ? err2.message : String(err2))
    } finally {
      setAvatarBusy(false)
    }
  }

  if (loading && !health) return <OverviewLoading />

  return (
    <div className="analytics ov-dash ops-page settings-page">
      <div className="ov-head">
        <div>
          <h2 className="ov-title">Settings</h2>
          <p className="ov-sub">Manage your account, security, and workspace.</p>
        </div>
        <div className="ov-head-actions">
          <span className={`ov-status-pill ${health?.ok ? 'ok' : 'warn'}`}>
            {health?.ok ? 'Healthy' : 'Needs check'}
          </span>
        </div>
      </div>

      {error ? (
        <div className="ops-alert bad" role="alert">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="ops-alert ok" role="status">
          {success}
        </div>
      ) : null}

      <section className="ov-card settings-panel">
        <div className="settings-identity">
          <div className="settings-avatar-block">
            <div className="settings-avatar-wrap">
              <UserAvatar name={user?.name} avatarUrl={user?.avatar_url} size="lg" />
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                hidden
                onChange={(e) => void onAvatarSelected(e.target.files?.[0])}
              />
              <button
                type="button"
                className="settings-avatar-edit"
                disabled={avatarBusy}
                onClick={onPickAvatar}
                aria-label={avatarBusy ? 'Uploading photo' : 'Change profile photo'}
                title="Change photo"
              >
                {avatarBusy ? (
                  <span className="settings-avatar-spin" aria-hidden />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path
                      d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.2l1.1-1.6A1.5 1.5 0 0 1 10 3.8h4a1.5 1.5 0 0 1 1.2.6L16.3 6h1.2A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-8Z"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinejoin="round"
                    />
                    <circle cx="12" cy="12.2" r="3.2" stroke="currentColor" strokeWidth="1.7" />
                  </svg>
                )}
              </button>
              {user?.avatar_url ? (
                <button
                  type="button"
                  className="settings-avatar-remove"
                  disabled={avatarBusy}
                  onClick={() => void onRemoveAvatar()}
                  aria-label="Remove profile photo"
                  title="Remove photo"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </button>
              ) : null}
            </div>
            {avatarErr ? <div className="auth-error">{avatarErr}</div> : null}
          </div>
          <div className="settings-identity-copy">
            <strong>{user?.name || 'Reviewer'}</strong>
            <em>{user?.email}</em>
            <div className="settings-meta-row">
              <span className={`badge ${user?.email_verified ? 'ok' : 'warn'}`}>
                {user?.email_verified ? 'Verified' : 'Unverified'}
              </span>
              {user?.oauth_provider ? (
                <span className="badge info">{user.oauth_provider}</span>
              ) : (
                <span className="badge neutral">Password account</span>
              )}
            </div>
          </div>
        </div>

        <div className="settings-divider" />

        <div className="settings-stack">
          <form className="settings-form" onSubmit={(e) => void onSaveProfile(e)}>
            <h3 className="settings-section-title">Profile</h3>
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </label>
            <label>
              Email
              <input value={user?.email || ''} disabled readOnly />
            </label>
            {profileErr ? <div className="auth-error">{profileErr}</div> : null}
            {profileMsg ? <div className="auth-info">{profileMsg}</div> : null}
            <button type="submit" className="btn primary" disabled={profileBusy}>
              {profileBusy ? 'Saving…' : 'Save profile'}
            </button>
          </form>

          <div className="settings-soft-rule" />

          <form className="settings-form" onSubmit={(e) => void onChangePassword(e)}>
            <h3 className="settings-section-title">Password</h3>
            <label>
              Current password
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </label>
            <label>
              New password
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </label>
            {pwErr ? <div className="auth-error">{pwErr}</div> : null}
            {pwMsg ? <div className="auth-info">{pwMsg}</div> : null}
            <button type="submit" className="btn primary" disabled={pwBusy}>
              {pwBusy ? 'Updating…' : 'Update password'}
            </button>
          </form>
        </div>

        <div className="settings-divider" />

        <div className="settings-footer">
          <div className="settings-footer-meta">
            <div className="settings-ws-row">
              <span>Active project</span>
              <strong title={hasProject ? projectId : undefined}>
                {hasProject ? project?.name || projectId : 'No project selected'}
              </strong>
            </div>
            <div className="settings-ws-row">
              <span>Catalog</span>
              <span className={`ov-status-pill ${health?.ok ? 'ok' : 'warn'}`}>
                {health?.ok ? 'OK' : 'Issue'}
              </span>
            </div>
            {health?.error ? (
              <p className="card-sub" style={{ margin: 0, color: 'var(--bad)' }}>
                {health.error}
              </p>
            ) : null}
          </div>
          <div className="settings-footer-actions">
            <button
              type="button"
              className="btn"
              disabled={reloading}
              onClick={() => void reloadCatalog()}
            >
              {reloading ? 'Reloading…' : 'Reload catalog'}
            </button>
            <button type="button" className="btn danger-ghost" onClick={() => void onLogout()}>
              Log out
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
