import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuth } from '../auth/AuthContext'

function validateName(name: string): string | null {
  const n = name.trim()
  if (n.length < 2) return 'Name must be at least 2 characters'
  if (!/^[A-Za-z][A-Za-z .'-]{1,118}$/.test(n)) return 'Use letters only (spaces and - \' . allowed)'
  return null
}

function validateEmail(email: string): string | null {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return 'Enter a valid email address'
  return null
}

function validatePassword(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters'
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return 'Include letters and a number'
  return null
}

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <div className="auth-page">
      <div className="auth-ambiance" aria-hidden>
        <span className="auth-orb auth-orb-a" />
        <span className="auth-orb auth-orb-b" />
        <span className="auth-orb auth-orb-c" />
        <span className="auth-grid" />
      </div>
      <div className="auth-card glass">
        <div className="auth-brand">
          <img src="/logo.png" alt="Veramynd" className="auth-logo" />
        </div>
        <h1>{title}</h1>
        <p className="auth-sub">{subtitle}</p>
        {children}
      </div>
    </div>
  )
}

export function LoginPage() {
  const { user, loading, login, googleEnabled } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!loading && user) return <Navigate to="/" replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const emailErr = validateEmail(email)
    if (emailErr) return setError(emailErr)
    if (!password) return setError('Password is required')
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your Veramynd workspace">
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error ? <div className="auth-error">{error}</div> : null}
        <button type="submit" className="btn primary auth-submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/signup">Create account</Link>
      </div>
      {googleEnabled ? (
        <a className="btn auth-oauth" href="/api/auth/oauth/google/start">
          Continue with Google
        </a>
      ) : null}
    </AuthShell>
  )
}

export function SignupPage() {
  const { user, loading, signup, googleEnabled } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const fieldErrors = useMemo(() => {
    return {
      name: name ? validateName(name) : null,
      email: email ? validateEmail(email) : null,
      password: password ? validatePassword(password) : null,
      confirm: confirm && confirm !== password ? 'Passwords do not match' : null,
    }
  }, [name, email, password, confirm])

  if (!loading && user) return <Navigate to="/" replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setInfo(null)
    const n = validateName(name)
    const em = validateEmail(email)
    const pw = validatePassword(password)
    if (n || em || pw) return setError(n || em || pw)
    if (password !== confirm) return setError('Passwords do not match')
    setBusy(true)
    try {
      const message = await signup(name.trim(), email.trim(), password)
      setInfo(message)
      setTimeout(() => navigate('/login'), 1800)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create account" subtitle="We’ll email you a verification link">
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <label>
          Name
          <input type="text" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
          {fieldErrors.name ? <span className="field-error">{fieldErrors.name}</span> : null}
        </label>
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {fieldErrors.email ? <span className="field-error">{fieldErrors.email}</span> : null}
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {fieldErrors.password ? <span className="field-error">{fieldErrors.password}</span> : null}
        </label>
        <label>
          Confirm password
          <input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
          {fieldErrors.confirm ? <span className="field-error">{fieldErrors.confirm}</span> : null}
        </label>
        {error ? <div className="auth-error">{error}</div> : null}
        {info ? <div className="auth-info">{info}</div> : null}
        <button type="submit" className="btn primary auth-submit" disabled={busy}>
          {busy ? 'Creating…' : 'Sign up'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/login">Already have an account?</Link>
      </div>
      {googleEnabled ? (
        <a className="btn auth-oauth" href="/api/auth/oauth/google/start">
          Continue with Google
        </a>
      ) : null}
    </AuthShell>
  )
}

export function VerifyEmailPage() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [message, setMessage] = useState('Verifying your email…')

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) {
      setStatus('error')
      setMessage('Missing verification token')
      return
    }
    void (async () => {
      try {
        const res = await fetch(`/api/auth/verify-email?token=${encodeURIComponent(token)}`)
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Verification failed')
        setStatus('ok')
        setMessage(data.message || 'Email verified')
      } catch (err) {
        setStatus('error')
        setMessage(err instanceof Error ? err.message : String(err))
      }
    })()
  }, [])

  return (
    <AuthShell title="Email verification" subtitle={message}>
      {status === 'ok' ? (
        <Link className="btn primary auth-submit" to="/login">
          Sign in
        </Link>
      ) : status === 'error' ? (
        <Link className="btn auth-submit" to="/signup">
          Back to signup
        </Link>
      ) : (
        <div className="auth-info">Please wait…</div>
      )}
    </AuthShell>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setInfo(null)
    const em = validateEmail(email)
    if (em) return setError(em)
    setBusy(true)
    try {
      const res = await authApi<{ message: string }>('/api/auth/forgot-password', {
        method: 'POST',
        json: { email: email.trim() },
      })
      setInfo(res.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Forgot password" subtitle="We’ll email you a reset link">
      <form className="auth-form" onSubmit={onSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        {error ? <div className="auth-error">{error}</div> : null}
        {info ? <div className="auth-info">{info}</div> : null}
        <button type="submit" className="btn primary auth-submit" disabled={busy}>
          {busy ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/login">Back to sign in</Link>
      </div>
    </AuthShell>
  )
}

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') || '', [])
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!token) return setError('Missing reset token')
    const pw = validatePassword(password)
    if (pw) return setError(pw)
    if (password !== confirm) return setError('Passwords do not match')
    setBusy(true)
    try {
      const res = await authApi<{ message: string }>('/api/auth/reset-password', {
        method: 'POST',
        json: { token, password },
      })
      setInfo(res.message)
      setTimeout(() => navigate('/login'), 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Reset password" subtitle="Choose a new password for your account">
      <form className="auth-form" onSubmit={onSubmit}>
        <label>
          New password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <label>
          Confirm password
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </label>
        {error ? <div className="auth-error">{error}</div> : null}
        {info ? <div className="auth-info">{info}</div> : null}
        <button type="submit" className="btn primary auth-submit" disabled={busy}>
          {busy ? 'Saving…' : 'Update password'}
        </button>
      </form>
    </AuthShell>
  )
}

export function OAuthCallbackPage() {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  useEffect(() => {
    void (async () => {
      await refresh()
      navigate('/', { replace: true })
    })()
  }, [navigate, refresh])
  return (
    <AuthShell title="Signing you in" subtitle="Finishing Google sign-in…">
      <div className="auth-info">Please wait…</div>
    </AuthShell>
  )
}
