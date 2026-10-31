// Main screen for an open dataset: file summary, transform panel and data table.

import { useState } from 'react'
import { useDataset, useRows } from '../hooks/datasets'
import { formatBytes, plural } from '../lib/format'
import { DataTable } from './DataTable'
import { ErrorMessage } from './ErrorMessage'
import { TransformPanel } from './TransformPanel'

interface WorkspaceProps {
  datasetId: string
  onNewFile: () => void
}

export function Workspace({ datasetId, onNewFile }: WorkspaceProps) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const dataset = useDataset(datasetId)
  const rows = useRows(datasetId, page, pageSize)

  if (dataset.isPending) {
    return <p className="py-16 text-center text-sm text-slate-500">Loading dataset…</p>
  }
  if (dataset.isError) {
    return (
      <div className="mx-auto max-w-md space-y-4 py-16">
        <ErrorMessage error={dataset.error} />
        <button
          type="button"
          onClick={onNewFile}
          className="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Upload a file
        </button>
      </div>
    )
  }

  const { original_name, file_size, current_version: version } = dataset.data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold text-slate-900">{original_name}</h1>
          <p className="text-sm text-slate-500">
            {plural(version.row_count, 'row')} · {plural(version.columns.length, 'column')} ·{' '}
            {formatBytes(file_size)} · version {version.version_no}
          </p>
        </div>
        <button
          type="button"
          onClick={onNewFile}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
        >
          Upload another file
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(320px,400px)_1fr] lg:items-start">
        <TransformPanel dataset={dataset.data} />
        <div className="min-w-0 space-y-2">
          {rows.error && <ErrorMessage error={rows.error} />}
          {version.version_no > 1 && (
            <p className="flex items-center gap-2 text-xs text-slate-500">
              <span className="inline-block size-3 rounded-sm bg-amber-100 ring-1 ring-amber-300" />
              Cells changed or added by the last apply
            </p>
          )}
          <DataTable
            data={rows.data}
            columns={version.columns}
            isFetching={rows.isFetching}
            page={page}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
        </div>
      </div>
    </div>
  )
}
