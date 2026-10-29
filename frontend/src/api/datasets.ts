// One typed function per backend endpoint (see backend/datasets/urls.py).

import { postJson, request } from './client'
import type { ApplyResponse, Dataset, PreviewRequest, PreviewResponse, RowsPage } from './types'

export function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  return request<Dataset>('/datasets/', { method: 'POST', body: form })
}

export function getDataset(id: string): Promise<Dataset> {
  return request<Dataset>(`/datasets/${id}/`)
}

export function getRows(id: string, page: number, pageSize: number): Promise<RowsPage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return request<RowsPage>(`/datasets/${id}/rows/?${query}`)
}

export function previewTransformation(id: string, body: PreviewRequest): Promise<PreviewResponse> {
  return postJson<PreviewResponse>(`/datasets/${id}/transformations/preview/`, body)
}

export function applyTransformation(transformationId: string): Promise<ApplyResponse> {
  return postJson<ApplyResponse>(`/transformations/${transformationId}/apply/`)
}
