// A preview awaiting confirmation: the generated regex and its explanation, match
// statistics and before/after samples, plus the Apply button.

import type { PreviewResponse } from '../api/types'
import { plural } from '../lib/format'
import { ErrorMessage } from './ErrorMessage'

interface PreviewResultProps {
  preview: PreviewResponse
  applying: boolean
  applyError: unknown
  onApply: () => void
  onEditRegex: () => void
  onDiscard: () => void
}

export function PreviewResult({
  preview,
  applying,
  applyError,
  onApply,
  onEditRegex,
  onDiscard,
}: PreviewResultProps) {
  const { transformation, samples } = preview
  const { stats } = transformation
  const nothingChanges = stats.total_cells_changed === 0
  const flags = transformation.flags.includes('IGNORECASE') ? 'i' : ''

  return (
    <section aria-label="Preview" className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-semibold text-slate-900">Preview</h2>
        <span className="text-xs text-slate-500">Nothing is changed until you apply</span>
      </div>

      {transformation.explanation && (
        <p className="text-sm text-slate-700">{transformation.explanation}</p>
      )}

      <dl className="space-y-2 text-sm">
        <div>
          <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">Pattern</dt>
          <dd className="mt-0.5 rounded-md bg-slate-900 px-2.5 py-1.5 font-mono text-xs break-all text-slate-100">
            /{transformation.pattern}/{flags}
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <div>
            <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">
              Replace with
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {transformation.replacement === '' ? (
                <span className="font-sans text-slate-500 italic">nothing (delete matches)</span>
              ) : (
                transformation.replacement
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">Columns</dt>
            <dd className="mt-0.5 text-slate-800">{transformation.columns.join(', ')}</dd>
          </div>
        </div>
      </dl>

      <p className="text-sm text-slate-800">
        <strong>{plural(stats.total_cells_changed, 'cell')}</strong> in{' '}
        {plural(stats.rows_affected, 'row')} will change ({plural(stats.total_matches, 'match', 'matches')}).
      </p>

      {nothingChanges ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Nothing would change. Try describing the pattern differently, or edit the regex.
        </p>
      ) : (
        <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-2 py-1.5 font-medium">Row</th>
                <th className="px-2 py-1.5 font-medium">Column</th>
                <th className="px-2 py-1.5 font-medium">Before → After</th>
              </tr>
            </thead>
            <tbody>
              {samples.map((change) => (
                <tr key={`${change.row}:${change.column}`} className="border-t border-slate-100 align-top">
                  <td className="px-2 py-1.5 text-slate-400 tabular-nums">{change.row + 1}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap text-slate-600">{change.column}</td>
                  <td className="px-2 py-1.5 break-all">
                    <span className="text-red-700 line-through decoration-red-300">{change.before}</span>
                    <span className="mx-1 text-slate-400">→</span>
                    <span className="text-emerald-800">{change.after}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {stats.total_cells_changed > samples.length && (
            <p className="border-t border-slate-100 px-2 py-1.5 text-xs text-slate-500">
              Showing the first {samples.length} of {plural(stats.total_cells_changed, 'change')}.
            </p>
          )}
        </div>
      )}

      {applyError != null && <ErrorMessage error={applyError} />}

      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
        >
          Discard
        </button>
        <button
          type="button"
          onClick={onEditRegex}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
        >
          Edit regex
        </button>
        <button
          type="button"
          onClick={onApply}
          disabled={applying || nothingChanges}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
        >
          {applying ? 'Applying…' : 'Apply'}
        </button>
      </div>
    </section>
  )
}
