// Mirrors the backend serializers in backend/datasets/serializers.py.

export type ColumnKind = 'text' | 'numeric'

export interface ColumnInfo {
  name: string
  kind: ColumnKind
}

export interface DatasetVersion {
  version_no: number
  row_count: number
  columns: ColumnInfo[]
  created_at: string
}

export interface Dataset {
  id: string
  original_name: string
  file_format: 'csv' | 'xlsx'
  file_size: number
  current_version: DatasetVersion
  created_at: string
}

export interface RowsPage {
  version: number
  page: number
  page_size: number
  total_rows: number
  total_pages: number
  columns: string[]
  rows: (string | null)[][]
  /** [row, column] positions on this page that changed in the latest version. */
  changed: [number, number][]
}

export type RegexFlag = 'IGNORECASE' | 'MULTILINE' | 'DOTALL'

export interface TransformationStats {
  total_matches: number
  total_cells_changed: number
  rows_affected: number
  // A preview scans only the first rows of a large dataset; when rows_scanned is less
  // than total_rows, the counts above are estimates. An applied transformation scans all.
  rows_scanned: number
  total_rows: number
  columns: Record<string, { matches: number; cells_changed: number }>
}

export interface Transformation {
  id: string
  dataset: string
  status: 'previewed' | 'applied'
  instruction: string
  explanation: string
  pattern: string
  flags: RegexFlag[]
  replacement: string
  columns: string[]
  stats: TransformationStats
  source_version: number
  result_version: number | null
  created_at: string
  applied_at: string | null
}

export interface CellChange {
  row: number
  column: string
  before: string
  after: string
}

export interface PreviewRequest {
  /** Plain-English description, turned into a regex by the LLM. */
  instruction?: string
  /** Hand-written regex; takes precedence over `instruction`. */
  pattern?: string
  /** `null`/omitted with an instruction: inferred from it. `""`: delete matches. */
  replacement?: string | null
  /** Omitted: every text column (or the columns named in the instruction). */
  columns?: string[]
  flags?: RegexFlag[]
}

export interface PreviewResponse {
  transformation: Transformation
  samples: CellChange[]
}

export interface ApplyResponse {
  transformation: Transformation
  dataset: Dataset
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}
