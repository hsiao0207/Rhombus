import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  applyTransformation,
  getDataset,
  getRows,
  previewTransformation,
  uploadDataset,
} from '../api/datasets'
import type { PreviewRequest } from '../api/types'

const keys = {
  dataset: (id: string) => ['dataset', id] as const,
  allRows: (id: string) => ['dataset', id, 'rows'] as const,
  rows: (id: string, page: number, pageSize: number) =>
    ['dataset', id, 'rows', page, pageSize] as const,
}

export function useDataset(id: string) {
  return useQuery({ queryKey: keys.dataset(id), queryFn: () => getDataset(id) })
}

export function useRows(id: string, page: number, pageSize: number) {
  return useQuery({
    queryKey: keys.rows(id, page, pageSize),
    queryFn: () => getRows(id, page, pageSize),
    // Keep showing the current page while the next one loads, instead of flashing empty.
    placeholderData: keepPreviousData,
  })
}

export function useUploadDataset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: uploadDataset,
    onSuccess: (dataset) => queryClient.setQueryData(keys.dataset(dataset.id), dataset),
  })
}

export function usePreview(datasetId: string) {
  return useMutation({
    mutationFn: (body: PreviewRequest) => previewTransformation(datasetId, body),
  })
}

export function useApply(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: applyTransformation,
    onSuccess: ({ dataset }) => {
      // The response already contains the new current version; the cached pages are
      // now outdated and will be refetched by any table that is showing them.
      queryClient.setQueryData(keys.dataset(datasetId), dataset)
      return queryClient.invalidateQueries({ queryKey: keys.allRows(datasetId) })
    },
  })
}
