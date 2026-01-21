import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ACL, ACLCreate, ACLUpdate } from '../api/types'

import type { PaginatedResponse } from '../api/types'

export interface ACLFilters {
    resource_type_id?: number
    action_id?: number
    principal_id?: number
    role_id?: number
    resource_id?: number
    limit?: number
    skip?: number
}

export function useACLs(realmId: number, filters: ACLFilters = {}) {
    return useQuery({
        queryKey: ['realms', realmId, 'acls', filters],
        queryFn: () => {
            const params = new URLSearchParams()
            if (filters.limit) params.append('limit', filters.limit.toString())
            if (filters.skip) params.append('skip', filters.skip.toString())
            if (filters.resource_type_id) params.append('resource_type_id', filters.resource_type_id.toString())
            if (filters.action_id) params.append('action_id', filters.action_id.toString())
            if (filters.principal_id) params.append('principal_id', filters.principal_id.toString())
            if (filters.role_id) params.append('role_id', filters.role_id.toString())
            if (filters.resource_id) params.append('resource_id', filters.resource_id.toString())

            return api.get<PaginatedResponse<ACL>>(`/realms/${realmId}/acls?${params.toString()}`)
        },
    })
}

export function useCreateACL(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: ACLCreate) => api.post<ACL>(`/realms/${realmId}/acls`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'acls'] })
        },
    })
}

export function useUpdateACL(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: ACLUpdate }) =>
            api.put<ACL>(`/realms/${realmId}/acls/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'acls'] })
        },
    })
}

export function useDeleteACL(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/acls/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'acls'] })
        },
    })
}
