import { useState } from 'react'
import { FileUpload } from './components/FileUpload'
import { Workspace } from './components/Workspace'

/** The open dataset lives in the URL (?dataset=<id>) so a refresh or shared link keeps it. */
function useDatasetIdInUrl() {
  const [datasetId, setDatasetId] = useState(
    () => new URLSearchParams(window.location.search).get('dataset'),
  )

  function update(id: string | null) {
    const url = new URL(window.location.href)
    if (id) url.searchParams.set('dataset', id)
    else url.searchParams.delete('dataset')
    window.history.replaceState(null, '', url)
    setDatasetId(id)
  }

  return [datasetId, update] as const
}

export default function App() {
  const [datasetId, setDatasetId] = useDatasetIdInUrl()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-3">
          <span aria-hidden className="size-3 rotate-45 rounded-[2px] bg-teal-600" />
          <span className="font-semibold">Regex Replace</span>
          <span className="hidden text-sm text-slate-500 sm:inline">
            · find and replace in spreadsheets using plain English
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {datasetId ? (
          // Keyed so all per-dataset state resets when another file is opened.
          <Workspace key={datasetId} datasetId={datasetId} onNewFile={() => setDatasetId(null)} />
        ) : (
          <div className="mx-auto max-w-xl space-y-6 py-10">
            <div className="text-center">
              <h1 className="text-2xl font-semibold tracking-tight">
                Find and replace patterns in your data
              </h1>
              <p className="mt-2 text-slate-600">
                Upload a CSV or Excel file, describe what to find in plain English, preview the
                changes, then apply them.
              </p>
            </div>
            <FileUpload onUploaded={(dataset) => setDatasetId(dataset.id)} />
          </div>
        )}
      </main>
    </div>
  )
}
