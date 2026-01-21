import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ResourceType, ResourceTypeCreate, ResourceTypeUpdate } from '../api/types'

export function useResourceTypes(realmId: number) {
    return useQuery({
        queryKey: ['realms', realmId, 'resource-types'],
        queryFn: () => api.get<ResourceType[]>(`/realms/${realmId}/resource-types?limit=1000`),
    })
}

export function useCreateResourceType(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: ResourceTypeCreate) => api.post<ResourceType>(`/realms/${realmId}/resource-types`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resource-types'] })
        },
    })
}

export function useUpdateResourceType(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: ResourceTypeUpdate }) =>
            api.put<ResourceType>(`/realms/${realmId}/resource-types/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resource-types'] })
        },
    })
}

export function useDeleteResourceType(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/resource-types/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resource-types'] })
        },
    })
}
