import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Principal, PrincipalCreate, PrincipalUpdate } from '../api/types'

export function usePrincipals(realmId: number) {
    return useQuery({
        queryKey: ['realms', realmId, 'principals'],
        queryFn: () => api.get<Principal[]>(`/realms/${realmId}/principals`),
    })
}

export function useCreatePrincipal(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: PrincipalCreate) => api.post<Principal>(`/realms/${realmId}/principals`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'principals'] })
        },
    })
}

export function useUpdatePrincipal(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: PrincipalUpdate }) =>
            api.put<Principal>(`/realms/${realmId}/principals/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'principals'] })
        },
    })
}

export function useDeletePrincipal(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/principals/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'principals'] })
        },
    })
}
