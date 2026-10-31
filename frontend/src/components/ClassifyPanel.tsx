// Form for classifying a text column with the LLM, previewing the categories and
// applying them as a new column.

import { useState, type FormEvent, type KeyboardEvent } from 'react'
import type { ClassifyTransformation, Dataset } from '../api/types'
import { useApply, useClassifyPreview } from '../hooks/datasets'
import { formatCount, plural } from '../lib/format'
import { ClassificationResult } from './ClassificationResult'
import { ErrorMessage } from './ErrorMessage'

// Mirrors MAX_CLASSIFY_VALUES on the backend, which enforces it.
const MAX_DISTINCT_VALUES = 1000

const EXAMPLES = [
  'Classify as Complaint, Question, Refund request',
  'Sentiment: Positive, Neutral, Negative',
  'Group into a few topics',
]

export function ClassifyPanel({ dataset }: { dataset: Dataset }) {
  const textColumns = dataset.current_version.columns.filter((column) => column.kind === 'text')
  const [column, setColumn] = useState(textColumns[0]?.name ?? '')
  const [instruction, setInstruction] = useState('')
  const [applied, setApplied] = useState<ClassifyTransformation | null>(null)

  const preview = useClassifyPreview(dataset.id)
  const apply = useApply(dataset.id)

  const canSubmit = !preview.isPending && column !== '' && instruction.trim() !== ''

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    setApplied(null)
    apply.reset()
    preview.mutate({ column, instruction: instruction.trim() })
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
        if (transformation.kind === 'classify') setApplied(transformation)
        preview.reset()
      },
    })
  }

  if (textColumns.length === 0) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        This file has no text columns to classify.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <label htmlFor="classify-column" className="text-sm font-medium text-slate-800">
            Column to classify
          </label>
          <select
            id="classify-column"
            value={column}
            onChange={(event) => setColumn(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-600 focus:ring-1 focus:ring-teal-600 focus:outline-none"
          >
            {textColumns.map(({ name }) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            Up to {formatCount(MAX_DISTINCT_VALUES)} distinct values. Each one is labeled by
            Claude, so this suits comments, statuses or titles rather than unique IDs.
          </p>
        </div>

        <div>
          <label htmlFor="classify-instruction" className="text-sm font-medium text-slate-800">
            How should the values be classified?
          </label>
          <textarea
            id="classify-instruction"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={submitOnModEnter}
            rows={3}
            maxLength={1000}
            placeholder="e.g. Classify as Complaint, Question, Refund request"
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
            List the categories, or describe a grouping and Claude will suggest them. Values
            that fit none are labeled Other.
          </p>
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {preview.isPending ? 'Classifying with Claude…' : 'Preview classification'}
        </button>
      </form>

      {preview.error && <ErrorMessage error={preview.error} />}

      {preview.data && (
        <ClassificationResult
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
          Added the {applied.params.new_column} column:{' '}
          {plural(applied.stats.rows_classified, 'row')} classified. The new column is highlighted
          in the table.
        </div>
      )}
    </div>
  )
}
