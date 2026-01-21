import { useState, useMemo } from 'react'
import { usePrincipals, useCreatePrincipal, useUpdatePrincipal, useDeletePrincipal } from '../hooks/usePrincipals'
import { useRoles } from '../hooks/useRoles'
import { Modal } from '../components/Modal'
import type { PrincipalCreate, Principal, AuthRole } from '../api/types'

interface PrincipalListProps {
    realmId: number
}

export function PrincipalList({ realmId }: PrincipalListProps) {
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [editPrincipal, setEditPrincipal] = useState<Principal | null>(null)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [searchTerm, setSearchTerm] = useState('')

    const { data: principals, isLoading, error } = usePrincipals(realmId)
    const { data: roles } = useRoles(realmId)
    const createPrincipal = useCreatePrincipal(realmId)
    const updatePrincipal = useUpdatePrincipal(realmId)
    const deletePrincipal = useDeletePrincipal(realmId)

    // Form state
    const [formUsername, setFormUsername] = useState('')
    const [formRoleIds, setFormRoleIds] = useState<number[]>([])
    const [formError, setFormError] = useState<string | null>(null)

    // Filter principals by search term
    const filteredPrincipals = useMemo(() => {
        if (!principals || !searchTerm.trim()) return principals || []
        const term = searchTerm.toLowerCase()
        return principals.filter((p: Principal) =>
            p.username.toLowerCase().includes(term) ||
            p.id.toString().includes(term) ||
            p.roles?.some((r: AuthRole) => r.name.toLowerCase().includes(term))
        )
    }, [principals, searchTerm])

    const resetForm = () => {
        setFormUsername('')
        setFormRoleIds([])
        setFormError(null)
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!formUsername.trim()) {
            setFormError('Username is required')
            return
        }
        try {
            const data: PrincipalCreate = {
                username: formUsername.trim(),
                role_ids: formRoleIds.length > 0 ? formRoleIds : undefined
            }
            await createPrincipal.mutateAsync(data)
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating principal')
        }
    }

    const handleUpdate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!editPrincipal || !formUsername.trim()) {
            setFormError('Username is required')
            return
        }
        try {
            await updatePrincipal.mutateAsync({
                id: editPrincipal.id,
                data: { username: formUsername.trim(), role_ids: formRoleIds }
            })
            setEditPrincipal(null)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error updating principal')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await deletePrincipal.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const openEditModal = (principal: Principal) => {
        setFormUsername(principal.username)
        setFormRoleIds(principal.roles?.map(r => r.id) || [])
        setFormError(null)
        setEditPrincipal(principal)
    }

    const toggleRole = (roleId: number) => {
        setFormRoleIds(prev =>
            prev.includes(roleId) ? prev.filter(id => id !== roleId) : [...prev, roleId]
        )
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading principals...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load principals: {error.message}</div>
    }

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">Principals ({filteredPrincipals.length}{searchTerm ? ` of ${principals?.length || 0}` : ''})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add Principal
                    </button>
                </div>

                {/* Search Bar */}
                <div className="search-bar">
                    <input
                        type="text"
                        className="form-input"
                        placeholder="Search by username, role, or ID..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{ maxWidth: '350px' }}
                    />
                    {searchTerm && (
                        <button className="btn btn-sm btn-ghost" onClick={() => setSearchTerm('')}>Clear</button>
                    )}
                </div>

                {filteredPrincipals.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">{searchTerm ? 'No principals match your search' : 'No principals yet'}</h3>
                        <p className="empty-state-description">
                            {searchTerm ? 'Try adjusting your search.' : 'Principals represent users or services that can be authenticated.'}
                        </p>
                    </div>
                ) : (
                    <div className="table-container">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Username</th>
                                    <th>Roles</th>
                                    <th style={{ width: '140px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredPrincipals.map((principal: Principal) => (
                                    <tr key={principal.id}>
                                        <td className="text-muted">{principal.id}</td>
                                        <td style={{ fontWeight: 500 }}>{principal.username}</td>
                                        <td>
                                            {principal.roles && principal.roles.length > 0 ? (
                                                <div className="flex gap-xs" style={{ flexWrap: 'wrap' }}>
                                                    {principal.roles.map((role: AuthRole) => (
                                                        <span key={role.id} className="badge badge-primary">{role.name}</span>
                                                    ))}
                                                </div>
                                            ) : (
                                                <span className="text-muted">No roles</span>
                                            )}
                                        </td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => openEditModal(principal)}>Edit</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(principal.id)}>Delete</button>
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
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Principal">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Username *</label>
                        <input
                            type="text"
                            className="form-input"
                            value={formUsername}
                            onChange={e => setFormUsername(e.target.value)}
                            placeholder="e.g., john.doe@example.com"
                        />
                    </div>
                    {roles && roles.length > 0 && (
                        <div className="form-group">
                            <label className="form-label">Roles</label>
                            <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
                                {roles.map((role: AuthRole) => (
                                    <label key={role.id} className="form-checkbox">
                                        <input type="checkbox" checked={formRoleIds.includes(role.id)} onChange={() => toggleRole(role.id)} />
                                        <span>{role.name}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={createPrincipal.isPending}>
                            {createPrincipal.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Modal */}
            <Modal isOpen={editPrincipal !== null} onClose={() => setEditPrincipal(null)} title="Edit Principal">
                <form onSubmit={handleUpdate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Username *</label>
                        <input type="text" className="form-input" value={formUsername} onChange={e => setFormUsername(e.target.value)} />
                    </div>
                    {roles && roles.length > 0 && (
                        <div className="form-group">
                            <label className="form-label">Roles</label>
                            <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
                                {roles.map((role: AuthRole) => (
                                    <label key={role.id} className="form-checkbox">
                                        <input type="checkbox" checked={formRoleIds.includes(role.id)} onChange={() => toggleRole(role.id)} />
                                        <span>{role.name}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setEditPrincipal(null)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={updatePrincipal.isPending}>
                            {updatePrincipal.isPending ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Delete Modal */}
            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Principal">
                <p className="mb-lg">Are you sure you want to delete this principal?</p>
                <div className="flex justify-end gap-sm">
                    <button className="btn btn-secondary" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                    <button className="btn btn-danger" onClick={handleDelete} disabled={deletePrincipal.isPending}>
                        {deletePrincipal.isPending ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </Modal>
        </>
    )
}
