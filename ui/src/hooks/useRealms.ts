import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Realm, RealmCreate, RealmUpdate } from '../api/types'

export function useRealms() {
    return useQuery({
        queryKey: ['realms'],
        queryFn: () => api.get<Realm[]>('/realms'),
    })
}

export function useRealm(realmId: number | undefined) {
    return useQuery({
        queryKey: ['realms', realmId],
        queryFn: () => api.get<Realm>(`/realms/${realmId}`),
        enabled: !!realmId,
    })
}

export function useCreateRealm() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: RealmCreate) => api.post<Realm>('/realms', data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms'] })
        },
    })
}

export function useUpdateRealm() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: RealmUpdate }) =>
            api.put<Realm>(`/realms/${id}`, data),
        onSuccess: (_, { id }) => {
            queryClient.invalidateQueries({ queryKey: ['realms'] })
            queryClient.invalidateQueries({ queryKey: ['realms', id] })
        },
    })
}

export function useDeleteRealm() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms'] })
        },
    })
}

export function useSyncRealm() {
    return useMutation({
        mutationFn: (realmId: number) => api.post(`/realms/${realmId}/sync`),
    })
}
