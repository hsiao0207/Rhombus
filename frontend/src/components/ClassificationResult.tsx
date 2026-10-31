// A classification awaiting confirmation: the categories with their share of rows,
// example values with their category, and the Apply button.

import type { ClassifyTransformation, PreviewResponse } from '../api/types'
import { formatCount, plural } from '../lib/format'
import { ErrorMessage } from './ErrorMessage'

interface ClassificationResultProps {
  preview: PreviewResponse<ClassifyTransformation>
  applying: boolean
  applyError: unknown
  onApply: () => void
  onDiscard: () => void
}

// Catch-all buckets are drawn muted so the user's own categories stand out.
const BAR_COLORS: Record<string, string> = { Other: 'bg-slate-400', Unclassified: 'bg-amber-400' }

export function ClassificationResult({
  preview,
  applying,
  applyError,
  onApply,
  onDiscard,
}: ClassificationResultProps) {
  const { transformation, samples } = preview
  const { params, stats } = transformation
  const emptyRows = stats.total_rows - stats.rows_classified

  return (
    <section aria-label="Preview" className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-semibold text-slate-900">Preview</h2>
        <span className="text-xs text-slate-500">Nothing is changed until you apply</span>
      </div>

      {transformation.explanation && (
        <p className="text-sm text-slate-700">{transformation.explanation}</p>
      )}

      <p className="text-sm text-slate-800">
        Adds a <strong className="font-mono text-xs">{params.new_column}</strong> column after{' '}
        {params.source_column}. The original column is not changed.
      </p>

      <div className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
          Categories
        </h3>
        <ul className="space-y-1.5">
          {Object.entries(stats.categories).map(([category, rows]) => {
            const share = stats.rows_classified ? rows / stats.rows_classified : 0
            return (
              <li key={category} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="text-slate-800">{category}</span>
                  <span className="text-slate-500 tabular-nums">
                    {formatCount(rows)} · {Math.round(share * 100)}%
                  </span>
                </div>
                <div className="mt-0.5 h-1.5 rounded-full bg-slate-100">
                  <div
                    className={`h-1.5 rounded-full ${BAR_COLORS[category] ?? 'bg-teal-600'}`}
                    style={{ width: `${share * 100}%` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
        <p className="text-xs text-slate-500">
          {plural(stats.distinct_values, 'distinct value')} in{' '}
          {plural(stats.rows_classified, 'row')} classified
          {emptyRows > 0 && `; ${plural(emptyRows, 'empty cell')} stay empty`}.
        </p>
      </div>

      <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-2 py-1.5 font-medium">Row</th>
              <th className="px-2 py-1.5 font-medium">{params.source_column}</th>
              <th className="px-2 py-1.5 font-medium">Category</th>
            </tr>
          </thead>
          <tbody>
            {samples.map((sample) => (
              <tr key={sample.row} className="border-t border-slate-100 align-top">
                <td className="px-2 py-1.5 text-slate-400 tabular-nums">{sample.row + 1}</td>
                <td className="px-2 py-1.5 break-words text-slate-800">{sample.before}</td>
                <td className="px-2 py-1.5 whitespace-nowrap text-teal-800">{sample.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
          onClick={onApply}
          disabled={applying}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
        >
          {applying ? 'Applying…' : 'Apply'}
        </button>
      </div>
    </section>
  )
}
