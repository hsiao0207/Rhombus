// Paginated table of the current dataset version. Cells changed by the latest apply
// are highlighted.

import { useState } from 'react'
import type { ColumnInfo, RowsPage } from '../api/types'
import { formatCount } from '../lib/format'

const PAGE_SIZES = [25, 50, 100, 200]
const NAV_BUTTON =
  'rounded-md border border-slate-300 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40'

interface DataTableProps {
  data: RowsPage | undefined
  columns: ColumnInfo[]
  isFetching: boolean
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function DataTable({
  data,
  columns,
  isFetching,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: DataTableProps) {
  if (!data) {
    return <div className="p-8 text-center text-sm text-slate-500">Loading rows…</div>
  }

  const kinds = new Map(columns.map((column) => [column.name, column.kind]))
  const changed = new Set(data.changed.map(([row, col]) => `${row}:${col}`))
  const firstRow = (data.page - 1) * data.page_size
  const totalPages = Math.max(data.total_pages, 1)

  return (
    <div className="flex min-h-0 flex-col">
      <div
        className={`overflow-auto rounded-t-xl border border-slate-200 bg-white transition-opacity ${
          isFetching ? 'opacity-60' : ''
        }`}
        style={{ maxHeight: '70vh' }}
      >
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50">
            <tr>
              <th className="border-b border-slate-200 px-3 py-2 text-right text-xs font-medium text-slate-400">
                #
              </th>
              {data.columns.map((name) => (
                <th
                  key={name}
                  className="border-b border-slate-200 px-3 py-2 text-left font-medium whitespace-nowrap text-slate-700"
                >
                  {name}
                  <span className="ml-1.5 text-xs font-normal text-slate-400">
                    {kinds.get(name) === 'numeric' ? '123' : 'abc'}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr key={firstRow + rowIndex} className="hover:bg-slate-50/60">
                <td className="border-b border-slate-100 px-3 py-1.5 text-right text-xs text-slate-400 tabular-nums">
                  {formatCount(firstRow + rowIndex + 1)}
                </td>
                {row.map((value, colIndex) => {
                  const isChanged = changed.has(`${rowIndex}:${colIndex}`)
                  return (
                    <td
                      key={colIndex}
                      title={value ?? undefined}
                      className={`max-w-xs truncate border-b border-slate-100 px-3 py-1.5 ${
                        isChanged ? 'bg-amber-100 text-amber-950' : 'text-slate-800'
                      }`}
                    >
                      {value ?? <span className="text-slate-300 italic">empty</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td
                  colSpan={data.columns.length + 1}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  This file has no rows.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-xl border border-t-0 border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
        <span className="tabular-nums">
          {data.total_rows === 0
            ? '0 rows'
            : `Rows ${formatCount(firstRow + 1)}–${formatCount(firstRow + data.rows.length)} of ${formatCount(data.total_rows)}`}
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5">
            <span className="text-slate-500">Per page</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="rounded-md border border-slate-300 bg-white px-1.5 py-1"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => onPageChange(1)}
            disabled={page <= 1}
            aria-label="First page"
            className={NAV_BUTTON}
          >
            «
          </button>
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className={NAV_BUTTON}
          >
            ‹ Prev
          </button>
          {/* Keyed by page so the box shows the new page after any navigation. */}
          <PageInput key={page} page={page} totalPages={totalPages} onPageChange={onPageChange} />
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className={NAV_BUTTON}
          >
            Next ›
          </button>
          <button
            type="button"
            onClick={() => onPageChange(totalPages)}
            disabled={page >= totalPages}
            aria-label="Last page"
            className={NAV_BUTTON}
          >
            »
          </button>
        </div>
      </div>
    </div>
  )
}

interface PageInputProps {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

/** Type a page number and press Enter to jump; out-of-range numbers are clamped. */
function PageInput({ page, totalPages, onPageChange }: PageInputProps) {
  const [draft, setDraft] = useState(String(page))

  function commit() {
    // Accept "17,217" as shown in the label, not just "17217".
    const requested = Number.parseInt(draft.replace(/[,\s]/g, ''), 10)
    if (Number.isNaN(requested)) {
      setDraft(String(page))
      return
    }
    const target = Math.min(Math.max(requested, 1), totalPages)
    if (target === page) setDraft(String(page))
    else onPageChange(target)
  }

  return (
    <label className="flex items-center gap-1.5 tabular-nums">
      <span className="text-slate-500">Page</span>
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') commit()
        }}
        onBlur={commit}
        inputMode="numeric"
        aria-label="Page number"
        className="w-20 rounded-md border border-slate-300 px-1.5 py-1 text-right"
      />
      <span className="text-slate-500">of {formatCount(totalPages)}</span>
    </label>
  )
}
