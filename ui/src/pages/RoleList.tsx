import { useState, useMemo } from 'react'
import { useRoles, useCreateRole, useUpdateRole, useDeleteRole } from '../hooks/useRoles'
import { Modal } from '../components/Modal'
import type { AuthRole } from '../api/types'

interface RoleListProps {
    realmId: number
}

export function RoleList({ realmId }: RoleListProps) {
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [editRole, setEditRole] = useState<AuthRole | null>(null)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [searchTerm, setSearchTerm] = useState('')

    const { data: roles, isLoading, error } = useRoles(realmId)
    const createRole = useCreateRole(realmId)
    const updateRole = useUpdateRole(realmId)
    const deleteRole = useDeleteRole(realmId)

    // Form state
    const [formName, setFormName] = useState('')
    const [formError, setFormError] = useState<string | null>(null)

    // Filter roles by search term
    const filteredRoles = useMemo(() => {
        if (!roles || !searchTerm.trim()) return roles || []
        const term = searchTerm.toLowerCase()
        return roles.filter((r: AuthRole) =>
            r.name.toLowerCase().includes(term) ||
            r.id.toString().includes(term)
        )
    }, [roles, searchTerm])

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
            await createRole.mutateAsync({ name: formName.trim() })
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating role')
        }
    }

    const handleUpdate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!editRole || !formName.trim()) {
            setFormError('Name is required')
            return
        }
        try {
            await updateRole.mutateAsync({ id: editRole.id, data: { name: formName.trim() } })
            setEditRole(null)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error updating role')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await deleteRole.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const openEditModal = (role: AuthRole) => {
        setFormName(role.name)
        setFormError(null)
        setEditRole(role)
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading roles...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load roles: {error.message}</div>
    }

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">Roles ({filteredRoles.length}{searchTerm ? ` of ${roles?.length || 0}` : ''})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add Role
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
                        <button className="btn btn-sm btn-ghost" onClick={() => setSearchTerm('')}>
                            Clear
                        </button>
                    )}
                </div>

                {filteredRoles.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">{searchTerm ? 'No roles match your search' : 'No roles yet'}</h3>
                        <p className="empty-state-description">
                            {searchTerm ? 'Try adjusting your search.' : 'Create roles to assign permissions to principals.'}
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
                                {filteredRoles.map((role: AuthRole) => (
                                    <tr key={role.id}>
                                        <td className="text-muted">{role.id}</td>
                                        <td style={{ fontWeight: 500 }}>{role.name}</td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => openEditModal(role)}>Edit</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(role.id)}>Delete</button>
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
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Role">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Role Name *</label>
                        <input
                            type="text"
                            className="form-input"
                            value={formName}
                            onChange={e => setFormName(e.target.value)}
                            placeholder="e.g., admin, viewer"
                        />
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={createRole.isPending}>
                            {createRole.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Modal */}
            <Modal isOpen={editRole !== null} onClose={() => setEditRole(null)} title="Edit Role">
                <form onSubmit={handleUpdate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Role Name *</label>
                        <input type="text" className="form-input" value={formName} onChange={e => setFormName(e.target.value)} />
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setEditRole(null)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={updateRole.isPending}>
                            {updateRole.isPending ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Delete Modal */}
            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Role">
                <p className="mb-lg">Are you sure? This will remove the role from all principals and ACLs.</p>
                <div className="flex justify-end gap-sm">
                    <button className="btn btn-secondary" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                    <button className="btn btn-danger" onClick={handleDelete} disabled={deleteRole.isPending}>
                        {deleteRole.isPending ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </Modal>
        </>
    )
}
