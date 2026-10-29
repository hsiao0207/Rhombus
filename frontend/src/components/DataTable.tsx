// Paginated table of the current dataset version. Cells changed by the latest apply
// are highlighted.

import type { ColumnInfo, RowsPage } from '../api/types'
import { formatCount } from '../lib/format'

const PAGE_SIZES = [25, 50, 100, 200]

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
        <div className="flex items-center gap-2">
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
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="rounded-md border border-slate-300 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
          >
            ‹ Prev
          </button>
          <span className="tabular-nums">
            {formatCount(page)} / {formatCount(totalPages)}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="rounded-md border border-slate-300 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
          >
            Next ›
          </button>
        </div>
      </div>
    </div>
  )
}
