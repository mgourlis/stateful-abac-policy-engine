import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Action, ActionCreate, ActionUpdate } from '../api/types'

export function useActions(realmId: number) {
    return useQuery({
        queryKey: ['realms', realmId, 'actions'],
        queryFn: () => api.get<Action[]>(`/realms/${realmId}/actions`),
    })
}

export function useCreateAction(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: ActionCreate) => api.post<Action>(`/realms/${realmId}/actions`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'actions'] })
        },
    })
}

export function useUpdateAction(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: ActionUpdate }) =>
            api.put<Action>(`/realms/${realmId}/actions/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'actions'] })
        },
    })
}

export function useDeleteAction(realmId: number) {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (id: number) => api.delete(`/realms/${realmId}/actions/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['realms', realmId, 'actions'] })
        },
    })
}
