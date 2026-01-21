import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AuthRole, AuthRoleCreate, AuthRoleUpdate } from '../api/types'

export function useRoles(realmId: number) {
    return useQuery({
        queryKey: ['realms', realmId, 'roles'],
        queryFn: () => api.get<AuthRole[]>(`/realms/${realmId}/roles`),
    })
}

export function useCreateRole(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: AuthRoleCreate) => api.post<AuthRole>(`/realms/${realmId}/roles`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'roles'] })
        },
    })
}

export function useUpdateRole(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: AuthRoleUpdate }) =>
            api.put<AuthRole>(`/realms/${realmId}/roles/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'roles'] })
        },
    })
}

export function useDeleteRole(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/roles/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'roles'] })
        },
    })
}
