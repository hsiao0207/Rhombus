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

interface TransformationBase {
  id: string
  dataset: string
  status: 'previewed' | 'applied'
  instruction: string
  explanation: string
  /** Columns the operation reads. */
  columns: string[]
  source_version: number
  result_version: number | null
  created_at: string
  applied_at: string | null
}

export interface ReplaceTransformation extends TransformationBase {
  kind: 'replace'
  pattern: string
  flags: RegexFlag[]
  replacement: string
  stats: TransformationStats
}

export interface ClassificationParams {
  source_column: string
  new_column: string
  /** In order, ending with the automatic "Other". */
  categories: string[]
}

export interface ClassificationStats {
  /** Rows per category; may include "Unclassified" for values the LLM left unlabeled. */
  categories: Record<string, number>
  distinct_values: number
  /** Non-empty rows; empty cells are not classified. */
  rows_classified: number
  total_rows: number
}

export interface ClassifyTransformation extends TransformationBase {
  kind: 'classify'
  params: ClassificationParams
  stats: ClassificationStats
}

export type Transformation = ReplaceTransformation | ClassifyTransformation

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

export interface ClassifyRequest {
  column: string
  /** Categories to use, or a description of how to group the values. */
  instruction: string
}

export interface PreviewResponse<T extends Transformation = ReplaceTransformation> {
  transformation: T
  /** For a classification: before = the value, after = its category. */
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
