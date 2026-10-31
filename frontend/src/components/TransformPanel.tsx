// The two ways to transform a dataset, as tabs: find and replace (described in plain
// English, turned into a regex) and classify (an LLM label per value, as a new column).

import { useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Dataset, PreviewRequest, ReplaceTransformation } from '../api/types'
import { useApply, usePreview } from '../hooks/datasets'
import { plural } from '../lib/format'
import { ClassifyPanel } from './ClassifyPanel'
import { ErrorMessage } from './ErrorMessage'
import { PreviewResult } from './PreviewResult'

type Mode = 'replace' | 'classify'

const MODES: { value: Mode; label: string }[] = [
  { value: 'replace', label: 'Find & replace' },
  { value: 'classify', label: 'Classify' },
]

const EXAMPLES = [
  "Find email addresses and replace them with 'REDACTED'",
  'Mask phone numbers with ***',
  'Remove URLs',
]

interface TransformPanelProps {
  dataset: Dataset
}

export function TransformPanel({ dataset }: TransformPanelProps) {
  const [mode, setMode] = useState<Mode>('replace')

  return (
    <div className="space-y-4">
      <div role="tablist" className="grid grid-cols-2 rounded-lg bg-slate-200/60 p-1 text-sm">
        {MODES.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            onClick={() => setMode(value)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              mode === value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {mode === 'replace' ? <ReplacePanel dataset={dataset} /> : <ClassifyPanel dataset={dataset} />}
    </div>
  )
}

function ReplacePanel({ dataset }: TransformPanelProps) {
  const columns = dataset.current_version.columns
  const [instruction, setInstruction] = useState('')
  const [replacement, setReplacement] = useState('')
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [applied, setApplied] = useState<ReplaceTransformation | null>(null)

  const preview = usePreview(dataset.id)
  const apply = useApply(dataset.id)

  const canSubmit = !preview.isPending && instruction.trim() !== ''

  function buildRequest(): PreviewRequest {
    return {
      instruction: instruction.trim(),
      // Empty means "use the replacement from the description".
      replacement: replacement === '' ? null : replacement,
      columns: selectedColumns.length > 0 ? selectedColumns : undefined,
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    setApplied(null)
    apply.reset()
    preview.mutate(buildRequest())
  }

  function submitOnModEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.currentTarget.form?.requestSubmit()
    }
  }

  function handleApply() {
    if (!preview.data) return
    apply.mutate(preview.data.transformation.id, {
      onSuccess: ({ transformation }) => {
        if (transformation.kind === 'replace') setApplied(transformation)
        preview.reset()
      },
    })
  }

  function toggleColumn(name: string) {
    setSelectedColumns((current) =>
      current.includes(name) ? current.filter((c) => c !== name) : [...current, name],
    )
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <label htmlFor="instruction" className="text-sm font-medium text-slate-800">
            What do you want to find?
          </label>
          <textarea
            id="instruction"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={submitOnModEnter}
            rows={3}
            maxLength={1000}
            placeholder="e.g. Find email addresses in the Email column and replace them with 'REDACTED'"
            className="mt-1.5 w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:ring-1 focus:ring-teal-600 focus:outline-none"
          />
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => setInstruction(example)}
                className="rounded-full border border-slate-200 px-2.5 py-0.5 text-xs text-slate-600 hover:border-slate-300 hover:bg-slate-50"
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label htmlFor="replacement" className="text-sm font-medium text-slate-800">
            Replace with
          </label>
          <input
            id="replacement"
            value={replacement}
            onChange={(event) => setReplacement(event.target.value)}
            maxLength={1000}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus:border-teal-600 focus:ring-1 focus:ring-teal-600 focus:outline-none"
          />
          <p className="mt-1 text-xs text-slate-500">
            Optional. Leave empty to use the value from your description.
          </p>
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-slate-800">Columns</legend>
          <p className="mt-0.5 text-xs text-slate-500">
            {selectedColumns.length === 0
              ? 'None selected: the columns named in your description, otherwise all text columns.'
              : `Only the ${plural(selectedColumns.length, 'selected column')}.`}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {columns.map((column) => {
              const selected = selectedColumns.includes(column.name)
              return (
                <button
                  key={column.name}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => toggleColumn(column.name)}
                  className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                    selected
                      ? 'border-teal-700 bg-teal-700 text-white'
                      : 'border-slate-300 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {column.name}
                </button>
              )
            })}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {preview.isPending ? 'Generating a pattern with Claude…' : 'Preview changes'}
        </button>
      </form>

      {preview.error && <ErrorMessage error={preview.error} />}

      {preview.data && (
        <PreviewResult
          preview={preview.data}
          applying={apply.isPending}
          applyError={apply.error}
          onApply={handleApply}
          onDiscard={() => {
            preview.reset()
            apply.reset()
          }}
        />
      )}

      {applied && (
        <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Applied: {plural(applied.stats.total_cells_changed, 'cell')} changed in{' '}
          {plural(applied.stats.rows_affected, 'row')}. Changed cells are highlighted in the table.
        </div>
      )}
    </div>
  )
}
