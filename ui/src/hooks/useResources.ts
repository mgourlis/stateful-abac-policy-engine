import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Resource, ResourceCreate, ResourceUpdate, PaginatedResponse } from '../api/types'

interface ResourceSearchParams {
    skip?: number;
    limit?: number;
    resource_type_id?: number;
    external_id?: string;
    attributes?: Record<string, unknown>;
}

export function useResources(realmId: number, params: ResourceSearchParams = {}) {
    const { skip = 0, limit = 50, resource_type_id, external_id, attributes } = params;

    // Build query params
    const queryParams = new URLSearchParams();
    queryParams.set('skip', String(skip));
    queryParams.set('limit', String(limit));
    if (resource_type_id) queryParams.set('resource_type_id', String(resource_type_id));
    if (external_id) queryParams.set('external_id', external_id);
    if (attributes && Object.keys(attributes).length > 0) {
        queryParams.set('attributes', JSON.stringify(attributes));
    }

    return useQuery({
        queryKey: ['realms', realmId, 'resources', params],
        queryFn: () => api.get<PaginatedResponse<Resource>>(
            `/realms/${realmId}/resources?${queryParams.toString()}`
        ),
    })
}

export function useCreateResource(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: ResourceCreate) => api.post<Resource>(`/realms/${realmId}/resources`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resources'] })
        },
    })
}

export function useUpdateResource(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: ResourceUpdate }) =>
            api.put<Resource>(`/realms/${realmId}/resources/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resources'] })
        },
    })
}

export function useDeleteResource(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/resources/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'resources'] })
        },
    })
}
