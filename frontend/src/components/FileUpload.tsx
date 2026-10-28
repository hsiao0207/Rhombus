import { useRef, useState, type DragEvent } from 'react'
import { ApiError } from '../api/client'
import type { Dataset } from '../api/types'
import { useUploadDataset } from '../hooks/datasets'
import { ErrorMessage } from './ErrorMessage'

// Mirrors the backend limits; the server re-validates everything.
const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx']
const MAX_UPLOAD_MB = 50

const SAMPLE_CSV = `ID,Name,Email,Phone,Notes
1,John Doe,john.doe@example.com,0912-345-678,Call me at 0912-345-678 or email john.doe@example.com
2,Jane Smith,jane_smith@domain.com,(02) 2345-6789,Order #A1023 shipped to 12 Main St.
3,Alice Brown,alice.brown@website.org,+886 912 345 678,Visit https://example.com/promo for details
`

function validate(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'Please choose a .csv or .xlsx file.'
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `Files must be ${MAX_UPLOAD_MB} MB or smaller.`
  }
  if (file.size === 0) {
    return 'This file is empty.'
  }
  return null
}

export function FileUpload({ onUploaded }: { onUploaded: (dataset: Dataset) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [clientError, setClientError] = useState<string | null>(null)
  const upload = useUploadDataset()

  function handleFile(file: File | undefined) {
    if (!file || upload.isPending) return
    const problem = validate(file)
    setClientError(problem)
    if (problem) return
    upload.mutate(file, { onSuccess: onUploaded })
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    handleFile(event.dataTransfer.files[0])
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a CSV or Excel file"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 ${
          dragging ? 'border-teal-500 bg-teal-50' : 'border-slate-300 bg-white hover:border-slate-400'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={(event) => {
            handleFile(event.target.files?.[0])
            event.target.value = ''
          }}
        />
        <p className="text-base font-medium text-slate-900">
          {upload.isPending ? 'Uploading…' : 'Drop a CSV or Excel file here, or click to browse'}
        </p>
        <p className="mt-1 text-sm text-slate-500">.csv or .xlsx, up to {MAX_UPLOAD_MB} MB</p>
      </div>

      <div className="text-center text-sm text-slate-500">
        No file handy?{' '}
        <button
          type="button"
          disabled={upload.isPending}
          onClick={() => handleFile(new File([SAMPLE_CSV], 'sample-contacts.csv', { type: 'text/csv' }))}
          className="font-medium text-teal-700 underline-offset-2 hover:underline disabled:opacity-50"
        >
          Try the sample data
        </button>
      </div>

      {clientError && <ErrorMessage error={new ApiError('INVALID_FILE', clientError, 0)} />}
      {upload.error && <ErrorMessage error={upload.error} />}
    </div>
  )
}
