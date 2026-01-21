import { useState, useMemo } from 'react'
import { useResourceTypes, useCreateResourceType, useUpdateResourceType, useDeleteResourceType } from '../hooks/useResourceTypes'
import { Modal } from '../components/Modal'
import { ACLCreateModal } from '../components/ACLCreateModal'
import type { ResourceType } from '../api/types'

interface ResourceTypeListProps {
    realmId: number
}

export function ResourceTypeList({ realmId }: ResourceTypeListProps) {
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [editResourceType, setEditResourceType] = useState<ResourceType | null>(null)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [showACLModal, setShowACLModal] = useState(false)
    const [aclResourceType, setACLResourceType] = useState<ResourceType | null>(null)
    const [searchTerm, setSearchTerm] = useState('')

    const { data: resourceTypes, isLoading, error } = useResourceTypes(realmId)
    const create = useCreateResourceType(realmId)
    const update = useUpdateResourceType(realmId)
    const del = useDeleteResourceType(realmId)

    const [formName, setFormName] = useState('')
    const [formIsPublic, setFormIsPublic] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    // Filter by search term
    const filteredTypes = useMemo(() => {
        if (!resourceTypes || !searchTerm.trim()) return resourceTypes || []
        const term = searchTerm.toLowerCase()
        return resourceTypes.filter((rt: ResourceType) =>
            rt.name.toLowerCase().includes(term) ||
            rt.id.toString().includes(term) ||
            (rt.is_public && 'public'.includes(term)) ||
            (!rt.is_public && 'private'.includes(term))
        )
    }, [resourceTypes, searchTerm])

    const resetForm = () => {
        setFormName('')
        setFormIsPublic(false)
        setFormError(null)
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!formName.trim()) {
            setFormError('Name is required')
            return
        }
        try {
            await create.mutateAsync({ name: formName.trim(), is_public: formIsPublic })
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating resource type')
        }
    }

    const handleUpdate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!editResourceType || !formName.trim()) {
            setFormError('Name is required')
            return
        }
        try {
            await update.mutateAsync({ id: editResourceType.id, data: { name: formName.trim(), is_public: formIsPublic } })
            setEditResourceType(null)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error updating resource type')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await del.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const openEditModal = (rt: ResourceType) => {
        setFormName(rt.name)
        setFormIsPublic(rt.is_public)
        setFormError(null)
        setEditResourceType(rt)
    }

    const openACLModal = (rt: ResourceType) => {
        setACLResourceType(rt)
        setShowACLModal(true)
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading resource types...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load resource types: {error.message}</div>
    }

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">Resource Types ({filteredTypes.length}{searchTerm ? ` of ${resourceTypes?.length || 0}` : ''})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add Resource Type
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

                {filteredTypes.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">{searchTerm ? 'No types match your search' : 'No resource types yet'}</h3>
                        <p className="empty-state-description">
                            {searchTerm ? 'Try adjusting your search.' : 'Resource types categorize your protected resources.'}
                        </p>
                    </div>
                ) : (
                    <div className="table-container">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th>Public</th>
                                    <th style={{ width: '180px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredTypes.map((rt: ResourceType) => (
                                    <tr key={rt.id}>
                                        <td className="text-muted">{rt.id}</td>
                                        <td style={{ fontWeight: 500 }}>{rt.name}</td>
                                        <td>
                                            <span className={`badge ${rt.is_public ? 'badge-success' : 'badge-warning'}`}>
                                                {rt.is_public ? 'Public' : 'Private'}
                                            </span>
                                        </td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => openEditModal(rt)}>Edit</button>
                                                <button className="btn btn-sm btn-secondary" onClick={() => openACLModal(rt)}>+ ACL</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(rt.id)}>Delete</button>
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
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Resource Type">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Name *</label>
                        <input type="text" className="form-input" value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g., Document, Project, File" />
                    </div>
                    <div className="form-group">
                        <label className="form-checkbox">
                            <input type="checkbox" checked={formIsPublic} onChange={e => setFormIsPublic(e.target.checked)} />
                            <span>Public (accessible without authentication)</span>
                        </label>
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
                            {create.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Modal */}
            <Modal isOpen={editResourceType !== null} onClose={() => setEditResourceType(null)} title="Edit Resource Type">
                <form onSubmit={handleUpdate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Name *</label>
                        <input type="text" className="form-input" value={formName} onChange={e => setFormName(e.target.value)} />
                    </div>
                    <div className="form-group">
                        <label className="form-checkbox">
                            <input type="checkbox" checked={formIsPublic} onChange={e => setFormIsPublic(e.target.checked)} />
                            <span>Public</span>
                        </label>
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setEditResourceType(null)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={update.isPending}>
                            {update.isPending ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* ACL Create Modal with preset resource type */}
            <ACLCreateModal
                realmId={realmId}
                isOpen={showACLModal}
                onClose={() => { setShowACLModal(false); setACLResourceType(null) }}
                presetResourceTypeId={aclResourceType?.id}
            />

            {/* Delete Modal */}
            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Resource Type">
                <p className="mb-lg">Are you sure? This will delete all resources of this type.</p>
                <div className="flex justify-end gap-sm">
                    <button className="btn btn-secondary" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                    <button className="btn btn-danger" onClick={handleDelete} disabled={del.isPending}>
                        {del.isPending ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </Modal>
        </>
    )
}
