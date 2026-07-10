const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/** Thrown for any non-2xx response; `detail` mirrors FastAPI's `{"detail": "..."}` body. */
export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Formats a FastAPI error `detail` into a message string. Usually a plain
 * string, but some endpoints (e.g. zip-upload) return a structured
 * `{file, row, reason}` object instead.
 */
function formatDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const { file, row, reason } = detail as { file?: string; row?: number | null; reason?: string }
    if (typeof reason === 'string') {
      const location = file ? ` (${file}${row != null ? `, row ${row}` : ''})` : ''
      return `${reason}${location}`
    }
  }
  return undefined
}

/**
 * Reads a cookie by name via `document.cookie`. Used only for the
 * non-httponly `csrf_token` cookie - the `session_uuid` auth cookie is
 * httponly and never readable from JS.
 */
function readCookie(name: string): string | undefined {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : undefined
}

const CSRF_COOKIE_NAME = 'csrf_token'
const CSRF_HEADER_NAME = 'X-CSRF-Token'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * Thin fetch wrapper for the backend API. Always sends cookies (the
 * `session_uuid` auth cookie is httponly, so it can't be attached manually)
 * and resolves to the parsed JSON body, or rejects with `ApiError`.
 *
 * A `FormData` body (multipart file uploads) is sent without a `Content-Type`
 * header so the browser can set it itself, including the boundary.
 *
 * For any state-changing request, echoes the `csrf_token` cookie (set for
 * every logged-in session) back as the `X-CSRF-Token` header - the backend
 * requires this for any authenticated session.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const method = (init?.method ?? 'GET').toUpperCase()
  const csrfToken = SAFE_METHODS.has(method) ? undefined : readCookie(CSRF_COOKIE_NAME)
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, formatDetail(body?.detail) ?? response.statusText)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

/** Builds a URL for an asset served from the backend's `/assets` static mount, given an `Image.filepath`. */
export function assetUrl(filepath: string): string {
  return `${API_BASE_URL}/assets/${filepath}`
}

/**
 * Fetches a file response (e.g. a CSV export) and triggers a browser download for it. The
 * filename is read from the response's `Content-Disposition` header when present, falling back
 * to `fallbackFilename` otherwise.
 */
export async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include' })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, formatDetail(body?.detail) ?? response.statusText)
  }

  const disposition = response.headers.get('Content-Disposition')
  const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? fallbackFilename

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}
