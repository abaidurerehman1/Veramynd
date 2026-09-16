import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  authApi,
  fetchMe,
  removeAvatar as removeAvatarApi,
  uploadAvatar as uploadAvatarApi,
  type AuthUser,
} from '../api/auth'

type AuthContextValue = {
  user: AuthUser | null
  loading: boolean
  googleEnabled: boolean
  refresh: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  signup: (name: string, email: string, password: string) => Promise<string>
  logout: () => Promise<void>
  updateProfile: (name: string) => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<string>
  uploadAvatar: (file: File) => Promise<void>
  removeAvatar: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [googleEnabled, setGoogleEnabled] = useState(false)

  const refresh = useCallback(async () => {
    const me = await fetchMe()
    setUser(me)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const [me, providers] = await Promise.all([
          fetchMe(),
          authApi<{ google: boolean }>('/api/auth/providers').catch(() => ({ google: false })),
        ])
        if (!cancelled) {
          setUser(me)
          setGoogleEnabled(Boolean(providers.google))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi<{ user: AuthUser }>('/api/auth/login', {
      method: 'POST',
      json: { email, password },
    })
    setUser(res.user)
  }, [])

  const signup = useCallback(async (name: string, email: string, password: string) => {
    const res = await authApi<{ message: string }>('/api/auth/signup', {
      method: 'POST',
      json: { name, email, password },
    })
    return res.message
  }, [])

  const logout = useCallback(async () => {
    await authApi('/api/auth/logout', { method: 'POST' })
    setUser(null)
  }, [])

  const updateProfile = useCallback(async (name: string) => {
    const res = await authApi<{ user: AuthUser }>('/api/auth/profile', {
      method: 'PATCH',
      json: { name },
    })
    setUser(res.user)
  }, [])

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    const res = await authApi<{ message: string }>('/api/auth/change-password', {
      method: 'POST',
      json: { current_password: currentPassword, new_password: newPassword },
    })
    return res.message
  }, [])

  const uploadAvatar = useCallback(async (file: File) => {
    const next = await uploadAvatarApi(file)
    setUser(next)
  }, [])

  const removeAvatar = useCallback(async () => {
    const next = await removeAvatarApi()
    setUser(next)
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      googleEnabled,
      refresh,
      login,
      signup,
      logout,
      updateProfile,
      changePassword,
      uploadAvatar,
      removeAvatar,
    }),
    [
      user,
      loading,
      googleEnabled,
      refresh,
      login,
      signup,
      logout,
      updateProfile,
      changePassword,
      uploadAvatar,
      removeAvatar,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
