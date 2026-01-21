import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

interface ManifestResult {
    message: string
    details?: Record<string, unknown>
}

export type ManifestMode = 'replace' | 'create' | 'update'

export function useApplyManifest() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: async ({ file, mode }: { file: File; mode: ManifestMode }) => {
            return api.uploadFile<ManifestResult>('/manifest/apply', file, { mode })
        },
        onSuccess: () => {
            // Invalidate all realm-related queries
            queryClient.invalidateQueries({ queryKey: ['realms'] })
        },
    })
}

export function useExportManifest() {
    return useMutation({
        mutationFn: async (realmName: string) => {
            const blob = await api.downloadBlob(`/realms/${encodeURIComponent(realmName)}/manifest`)

            // Create download link
            const url = window.URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${realmName}_manifest.json`
            document.body.appendChild(a)
            a.click()

            // Cleanup
            window.URL.revokeObjectURL(url)
            document.body.removeChild(a)

            return { message: 'Manifest downloaded successfully' }
        },
    })
}
