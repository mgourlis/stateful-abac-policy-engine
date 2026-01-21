import { useState, useMemo } from 'react'
import { useActions, useCreateAction, useUpdateAction, useDeleteAction } from '../hooks/useActions'
import { Modal } from '../components/Modal'
import type { Action } from '../api/types'

interface ActionListProps {
    realmId: number
}

export function ActionList({ realmId }: ActionListProps) {
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [editAction, setEditAction] = useState<Action | null>(null)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [searchTerm, setSearchTerm] = useState('')

    const { data: actions, isLoading, error } = useActions(realmId)
    const createAction = useCreateAction(realmId)
    const updateAction = useUpdateAction(realmId)
    const deleteAction = useDeleteAction(realmId)

    const [formName, setFormName] = useState('')
    const [formError, setFormError] = useState<string | null>(null)

    // Filter actions by search term
    const filteredActions = useMemo(() => {
        if (!actions || !searchTerm.trim()) return actions || []
        const term = searchTerm.toLowerCase()
        return actions.filter((a: Action) =>
            a.name.toLowerCase().includes(term) ||
            a.id.toString().includes(term)
        )
    }, [actions, searchTerm])

    const resetForm = () => {
        setFormName('')
        setFormError(null)
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!formName.trim()) {
            setFormError('Name is required')
            return
        }
        try {
            await createAction.mutateAsync({ name: formName.trim() })
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating action')
        }
    }

    const handleUpdate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!editAction || !formName.trim()) {
            setFormError('Name is required')
            return
        }
        try {
            await updateAction.mutateAsync({ id: editAction.id, data: { name: formName.trim() } })
            setEditAction(null)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error updating action')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await deleteAction.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const openEditModal = (action: Action) => {
        setFormName(action.name)
        setFormError(null)
        setEditAction(action)
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading actions...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load actions: {error.message}</div>
    }

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">Actions ({filteredActions.length}{searchTerm ? ` of ${actions?.length || 0}` : ''})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add Action
                    </button>
                </div>

                {/* Search Bar */}
                <div className="search-bar">
                    <input
                        type="text"
                        className="form-input"
                        placeholder="Search by name or ID..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{ maxWidth: '300px' }}
                    />
                    {searchTerm && (
                        <button className="btn btn-sm btn-ghost" onClick={() => setSearchTerm('')}>Clear</button>
                    )}
                </div>

                {filteredActions.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">{searchTerm ? 'No actions match your search' : 'No actions yet'}</h3>
                        <p className="empty-state-description">
                            {searchTerm ? 'Try adjusting your search.' : 'Actions represent operations like read, write, delete.'}
                        </p>
                    </div>
                ) : (
                    <div className="table-container">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th style={{ width: '140px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredActions.map((action: Action) => (
                                    <tr key={action.id}>
                                        <td className="text-muted">{action.id}</td>
                                        <td style={{ fontWeight: 500 }}>{action.name}</td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => openEditModal(action)}>Edit</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(action.id)}>Delete</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Create Modal */}
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Action">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Action Name *</label>
                        <input
                            type="text"
                            className="form-input"
                            value={formName}
                            onChange={e => setFormName(e.target.value)}
                            placeholder="e.g., read, write, delete"
                        />
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={createAction.isPending}>
                            {createAction.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Modal */}
            <Modal isOpen={editAction !== null} onClose={() => setEditAction(null)} title="Edit Action">
                <form onSubmit={handleUpdate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Action Name *</label>
                        <input type="text" className="form-input" value={formName} onChange={e => setFormName(e.target.value)} />
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setEditAction(null)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={updateAction.isPending}>
                            {updateAction.isPending ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Delete Modal */}
            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Action">
                <p className="mb-lg">Are you sure? It will be removed from all ACLs.</p>
                <div className="flex justify-end gap-sm">
                    <button className="btn btn-secondary" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                    <button className="btn btn-danger" onClick={handleDelete} disabled={deleteAction.isPending}>
                        {deleteAction.isPending ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </Modal>
        </>
    )
}
