// Form for describing a change in plain English (or as a regex), choosing columns,
// previewing it and applying it.

import { useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Dataset, PreviewRequest, Transformation } from '../api/types'
import { useApply, usePreview } from '../hooks/datasets'
import { plural } from '../lib/format'
import { ErrorMessage } from './ErrorMessage'
import { PreviewResult } from './PreviewResult'

type Mode = 'describe' | 'regex'

const EXAMPLES = [
  "Find email addresses and replace them with 'REDACTED'",
  'Mask phone numbers with ***',
  'Remove URLs',
]

interface TransformPanelProps {
  dataset: Dataset
}

export function TransformPanel({ dataset }: TransformPanelProps) {
  const columns = dataset.current_version.columns
  const [mode, setMode] = useState<Mode>('describe')
  const [instruction, setInstruction] = useState('')
  const [pattern, setPattern] = useState('')
  const [replacement, setReplacement] = useState('')
  const [ignoreCase, setIgnoreCase] = useState(false)
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [applied, setApplied] = useState<Transformation | null>(null)

  const preview = usePreview(dataset.id)
  const apply = useApply(dataset.id)

  const canSubmit =
    !preview.isPending && (mode === 'describe' ? instruction.trim() !== '' : pattern !== '')

  function buildRequest(): PreviewRequest {
    const columnsParam = selectedColumns.length > 0 ? selectedColumns : undefined
    if (mode === 'describe') {
      return {
        instruction: instruction.trim(),
        // Empty means "use the replacement from the description".
        replacement: replacement === '' ? null : replacement,
        columns: columnsParam,
      }
    }
    return {
      pattern,
      replacement,
      flags: ignoreCase ? ['IGNORECASE'] : [],
      columns: columnsParam,
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
        setApplied(transformation)
        preview.reset()
      },
    })
  }

  function handleEditRegex() {
    if (!preview.data) return
    const { transformation } = preview.data
    setMode('regex')
    setPattern(transformation.pattern)
    setReplacement(transformation.replacement)
    setIgnoreCase(transformation.flags.includes('IGNORECASE'))
    setSelectedColumns(transformation.columns)
    preview.reset()
    apply.reset()
  }

  function toggleColumn(name: string) {
    setSelectedColumns((current) =>
      current.includes(name) ? current.filter((c) => c !== name) : [...current, name],
    )
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <div role="tablist" className="grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm">
          {(['describe', 'regex'] as const).map((value) => (
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
              {value === 'describe' ? 'Describe in English' : 'Write a regex'}
            </button>
          ))}
        </div>

        {mode === 'describe' ? (
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
        ) : (
          <div>
            <label htmlFor="pattern" className="text-sm font-medium text-slate-800">
              Regular expression
            </label>
            <input
              id="pattern"
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              spellCheck={false}
              maxLength={1000}
              placeholder="e.g. \b[\w.+-]+@[\w-]+\.[\w.]+\b"
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus:border-teal-600 focus:ring-1 focus:ring-teal-600 focus:outline-none"
            />
            <label className="mt-2 flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={ignoreCase}
                onChange={(event) => setIgnoreCase(event.target.checked)}
                className="accent-teal-700"
              />
              Ignore case
            </label>
          </div>
        )}

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
            {mode === 'describe'
              ? 'Optional. Leave empty to use the value from your description.'
              : 'Leave empty to delete matches. Use \\1 to insert a captured group.'}
          </p>
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-slate-800">Columns</legend>
          <p className="mt-0.5 text-xs text-slate-500">
            {selectedColumns.length === 0
              ? mode === 'describe'
                ? 'None selected: the columns named in your description, otherwise all text columns.'
                : 'None selected: all text columns.'
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
          {preview.isPending
            ? mode === 'describe'
              ? 'Generating a pattern with Claude…'
              : 'Running…'
            : 'Preview changes'}
        </button>
      </form>

      {preview.error && <ErrorMessage error={preview.error} />}

      {preview.data && (
        <PreviewResult
          preview={preview.data}
          applying={apply.isPending}
          applyError={apply.error}
          onApply={handleApply}
          onEditRegex={handleEditRegex}
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
