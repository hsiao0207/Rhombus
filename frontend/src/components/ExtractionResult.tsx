// An extraction awaiting confirmation: the generated regex, the new columns with how
// many rows each one fills, example values split into those columns, and Apply.

import type { ExtractSample, ExtractTransformation, PreviewResponse } from '../api/types'
import { formatCount } from '../lib/format'
import { ErrorMessage } from './ErrorMessage'

interface ExtractionResultProps {
  preview: PreviewResponse<ExtractTransformation, ExtractSample>
  applying: boolean
  applyError: unknown
  onApply: () => void
  onDiscard: () => void
}

export function ExtractionResult({
  preview,
  applying,
  applyError,
  onApply,
  onDiscard,
}: ExtractionResultProps) {
  const { transformation, samples } = preview
  const { params, stats } = transformation
  // Ordered from params, a list: object key order is not preserved by the database.
  const newColumns = params.new_columns.map(({ column }) => column)
  const nothingMatched = stats.rows_matched === 0
  // Large datasets are previewed on their first rows only; apply always covers every row.
  const estimated = stats.rows_scanned < stats.total_rows
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

      <div>
        <h3 className="text-xs font-medium tracking-wide text-slate-500 uppercase">Pattern</h3>
        <p className="mt-0.5 rounded-md bg-slate-900 px-2.5 py-1.5 font-mono text-xs break-all text-slate-100">
          /{transformation.pattern}/{flags}
        </p>
      </div>

      <div>
        <h3 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
          New columns after {params.source_column}
        </h3>
        <ul className="mt-1 space-y-0.5 text-sm">
          {newColumns.map((column) => (
            <li key={column} className="flex justify-between gap-2">
              <span className="font-mono text-xs text-slate-800">{column}</span>
              <span className="text-slate-500 tabular-nums">
                {formatCount(stats.columns[column] ?? 0)} of {formatCount(stats.rows_scanned)} rows
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-slate-500">
          {estimated
            ? `Counted in the first ${formatCount(stats.rows_scanned)} of ${formatCount(stats.total_rows)} rows. Applying processes every row.`
            : 'Rows without a match get empty cells. The original column is not changed.'}
        </p>
      </div>

      {nothingMatched ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {estimated
            ? `Nothing matched in the first ${formatCount(stats.rows_scanned)} rows. The remaining rows are only checked when you apply.`
            : 'Nothing matched. Try describing what to extract differently.'}
        </p>
      ) : (
        <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-2 py-1.5 font-medium">Row</th>
                <th className="px-2 py-1.5 font-medium">{params.source_column}</th>
                {newColumns.map((column) => (
                  <th key={column} className="px-2 py-1.5 font-medium">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {samples.map((sample) => (
                <tr key={sample.row} className="border-t border-slate-100 align-top">
                  <td className="px-2 py-1.5 text-slate-400 tabular-nums">{sample.row + 1}</td>
                  <td className="px-2 py-1.5 break-all text-slate-600">{sample.value}</td>
                  {newColumns.map((column) => (
                    <td key={column} className="px-2 py-1.5 break-all text-emerald-800">
                      {sample.parts[column] ?? <span className="text-slate-300 italic">empty</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
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
          onClick={onApply}
          disabled={applying || (nothingMatched && !estimated)}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
        >
          {applying ? 'Applying…' : 'Apply'}
        </button>
      </div>
    </section>
  )
}
