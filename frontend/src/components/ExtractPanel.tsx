// Form for extracting parts of a column into new columns: described in plain English,
// turned into a regex with named groups by the LLM, previewed, then applied.

import { useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Dataset, ExtractTransformation } from '../api/types'
import { useApply, useExtractPreview } from '../hooks/datasets'
import { ErrorMessage } from './ErrorMessage'
import { ExtractionResult } from './ExtractionResult'

const EXAMPLES = [
  'Extract the email domain',
  'Split Name into first and last name',
  'Extract the year from the date',
]

export function ExtractPanel({ dataset }: { dataset: Dataset }) {
  const columns = dataset.current_version.columns
  const [instruction, setInstruction] = useState('')
  // Empty: let the LLM pick the column from the description.
  const [column, setColumn] = useState('')
  const [applied, setApplied] = useState<ExtractTransformation | null>(null)

  const preview = useExtractPreview(dataset.id)
  const apply = useApply(dataset.id)

  const canSubmit = !preview.isPending && instruction.trim() !== ''

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    setApplied(null)
    apply.reset()
    preview.mutate({ instruction: instruction.trim(), column: column || undefined })
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
        if (transformation.kind === 'extract') setApplied(transformation)
        preview.reset()
      },
    })
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <label htmlFor="extract-instruction" className="text-sm font-medium text-slate-800">
            What do you want to extract?
          </label>
          <textarea
            id="extract-instruction"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={submitOnModEnter}
            rows={3}
            maxLength={1000}
            placeholder="e.g. Split Name into first and last name"
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
          <p className="mt-1 text-xs text-slate-500">
            Each piece becomes a new column next to the original, which is not changed. Only
            the first match in each cell is used.
          </p>
        </div>

        <div>
          <label htmlFor="extract-column" className="text-sm font-medium text-slate-800">
            From column
          </label>
          <select
            id="extract-column"
            value={column}
            onChange={(event) => setColumn(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-600 focus:ring-1 focus:ring-teal-600 focus:outline-none"
          >
            <option value="">Let Claude choose from the description</option>
            {columns.map(({ name }) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {preview.isPending ? 'Generating a pattern with Claude…' : 'Preview extraction'}
        </button>
      </form>

      {preview.error && <ErrorMessage error={preview.error} />}

      {preview.data && (
        <ExtractionResult
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
          Added {applied.params.new_columns.map(({ column }) => column).join(', ')}. The new
          columns are highlighted in the table.
        </div>
      )}
    </div>
  )
}
