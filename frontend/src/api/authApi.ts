import { apiFetch } from './client'
import type { User } from './types'

/** Creates a new `annotator` user with the given password and sets the session cookie. */
export function signup(username: string, password: string): Promise<User> {
  return apiFetch<User>('/api/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

/**
 * Looks up an existing user by username and sets the session cookie.
 * Every account requires a password to log in. Omit `password` to probe
 * whether the account exists / already has a credential before asking for one.
 */
export function login(username: string, password?: string): Promise<User> {
  return apiFetch<User>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

/** Resolves the identity behind the current session cookie, if any. */
export function me(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

/** Clears the session cookie. */
export function logout(): Promise<void> {
  return apiFetch<void>('/api/v1/auth/logout', { method: 'POST' })
}

/** Sets or replaces the password for the current session's account. */
export function setPassword(password: string): Promise<void> {
  return apiFetch<void>('/api/v1/auth/password', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}
