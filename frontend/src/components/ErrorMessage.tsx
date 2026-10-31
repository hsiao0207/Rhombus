// Shows an API or network error with a short headline per error code.

import { ApiError } from '../api/client'

// Short headlines per backend error code; the server's message supplies the details.
const TITLES: Record<string, string> = {
  NETWORK_ERROR: 'Connection problem',
  INVALID_FILE: "Can't upload this file",
  UNSUPPORTED_FILE_TYPE: 'Unsupported file type',
  FILE_TOO_LARGE: 'File too large',
  EMPTY_FILE: 'Empty file',
  FILE_PARSE_ERROR: "Couldn't read this file",
  INVALID_REGEX: 'Invalid regular expression',
  PATTERN_MATCHES_EMPTY: 'Pattern matches empty text',
  INVALID_REPLACEMENT: 'Invalid replacement',
  REGEX_TIMEOUT: 'Pattern too slow',
  UNKNOWN_COLUMNS: 'Unknown columns',
  NO_TARGET_COLUMNS: 'No text columns',
  PATTERN_GENERATION_FAILED: "Couldn't build a working pattern",
  TOO_MANY_VALUES: 'Too many distinct values',
  NOTHING_TO_CLASSIFY: 'Nothing to classify',
  TOO_MANY_CATEGORIES: 'Too many categories',
  LLM_NOT_CONFIGURED: 'AI not available',
  LLM_UNAVAILABLE: 'AI temporarily unavailable',
  LLM_REFUSED: 'Request declined',
  LLM_BAD_OUTPUT: 'Unexpected AI response',
  STALE_VERSION: 'Data changed since this preview',
  ALREADY_APPLIED: 'Already applied',
  NOT_FOUND: 'Not found',
  THROTTLED: 'Too many requests',
  VALIDATION_ERROR: 'Please check your input',
}

function describeDetails(error: ApiError): string | null {
  const { details } = error
  if (error.code === 'INVALID_REGEX' && typeof details.position === 'number') {
    return `Problem near character ${details.position + 1}.`
  }
  if (error.code === 'PATTERN_GENERATION_FAILED' && typeof details.pattern === 'string') {
    return `Last attempt: ${details.pattern} — ${String(details.reason ?? '')}`
  }
  if (error.code === 'UNKNOWN_COLUMNS' && Array.isArray(details.unknown)) {
    return `Not found: ${details.unknown.join(', ')}`
  }
  if (error.code === 'VALIDATION_ERROR' && details.fields && typeof details.fields === 'object') {
    return Object.values(details.fields as Record<string, unknown>)
      .flat()
      .map(String)
      .join(' ')
  }
  return null
}

export function ErrorMessage({ error }: { error: unknown }) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError('UNKNOWN', error instanceof Error ? error.message : 'Something went wrong.', 0)
  const extra = describeDetails(apiError)

  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm">
      <p className="font-medium text-red-800">{TITLES[apiError.code] ?? 'Something went wrong'}</p>
      <p className="mt-1 text-red-700">{apiError.message}</p>
      {extra && <p className="mt-1 break-all font-mono text-xs text-red-600">{extra}</p>}
    </div>
  )
}
