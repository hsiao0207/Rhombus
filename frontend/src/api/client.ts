import type { ApiErrorBody } from './types'

/** An error returned by the backend in its standard `{"error": {...}}` shape. */
export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(code: string, message: string, status: number, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as ApiErrorBody).error?.code === 'string'
  )
}

/** Fetch a JSON API endpoint, throwing `ApiError` for any failure. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Could not reach the server. Check your connection.', 0)
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (isApiErrorBody(body)) {
      const { code, message, details } = body.error
      throw new ApiError(code, message, response.status, details)
    }
    throw new ApiError('HTTP_ERROR', `Request failed (${response.status}).`, response.status)
  }
  return body as T
}

export function postJson<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  })
}
