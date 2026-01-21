import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useRealms, useCreateRealm, useDeleteRealm } from '../hooks/useRealms'
import { Modal } from '../components/Modal'
import { ManifestUploadModal } from '../components/ManifestUploadModal'
import { RealmForm } from '../components/realm/RealmForm'
import type { RealmCreate, Realm } from '../api/types'

export function RealmList() {
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [showUploadModal, setShowUploadModal] = useState(false)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [searchTerm, setSearchTerm] = useState('')

    const { data: realms, isLoading, error } = useRealms()
    const createRealm = useCreateRealm()
    const deleteRealm = useDeleteRealm()

    // Filter realms by search term
    const filteredRealms = useMemo(() => {
        if (!realms || !searchTerm.trim()) return realms || []
        const term = searchTerm.toLowerCase()
        return realms.filter((r: Realm) =>
            r.name.toLowerCase().includes(term) ||
            r.description?.toLowerCase().includes(term) ||
            r.id.toString().includes(term)
        )
    }, [realms, searchTerm])

    const handleCreate = async (data: RealmCreate) => {
        await createRealm.mutateAsync(data)
        setShowCreateModal(false)
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await deleteRealm.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    if (isLoading) {
        return (
            <>
                <div className="page-header">
                    <div>
                        <h1 className="page-title">Realms</h1>
                        <p className="page-subtitle">Manage authentication realms</p>
                    </div>
                </div>
                <div className="page-content">
                    <div className="loading-container">
                        <div className="loading-spinner" />
                        <span style={{ marginLeft: '0.5rem' }}>Loading realms...</span>
                    </div>
                </div>
            </>
        )
    }

    if (error) {
        return (
            <>
                <div className="page-header">
                    <div>
                        <h1 className="page-title">Realms</h1>
                    </div>
                </div>
                <div className="page-content">
                    <div className="alert alert-danger">Failed to load realms: {error.message}</div>
                </div>
            </>
        )
    }

    return (
        <>
            <div className="page-header">
                <div>
                    <h1 className="page-title">Realms</h1>
                    <p className="page-subtitle">Manage authentication realms</p>
                </div>
                <div className="flex gap-sm">
                    <button className="btn btn-secondary" onClick={() => setShowUploadModal(true)}>
                        Upload Manifest
                    </button>
                    <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
                        + Create Realm
                    </button>
                </div>
            </div>

            <div className="page-content">
                <div className="card">
                    {/* Search Bar */}
                    <div className="search-bar">
                        <input
                            type="text"
                            className="form-input"
                            placeholder="Search by name, description, or ID..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{ maxWidth: '350px' }}
                        />
                        {searchTerm && (
                            <button className="btn btn-sm btn-ghost" onClick={() => setSearchTerm('')}>Clear</button>
                        )}
                        <span className="text-muted" style={{ marginLeft: 'auto' }}>
                            {filteredRealms.length}{searchTerm ? ` of ${realms?.length || 0}` : ''} realms
                        </span>
                    </div>

                    {filteredRealms.length === 0 ? (
                        <div className="empty-state">
                            <h3 className="empty-state-title">{searchTerm ? 'No realms match your search' : 'No realms yet'}</h3>
                            <p className="empty-state-description">
                                {searchTerm ? 'Try adjusting your search.' : 'Create your first realm to start managing authentication.'}
                            </p>
                            {!searchTerm && (
                                <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>+ Create Realm</button>
                            )}
                        </div>
                    ) : (
                        <div className="table-container">
                            <table className="table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Description</th>
                                        <th>Status</th>
                                        <th>Keycloak</th>
                                        <th style={{ width: '140px' }}>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredRealms.map((realm: Realm) => (
                                        <tr key={realm.id}>
                                            <td>
                                                <Link to={`/realms/${realm.id}`} style={{ fontWeight: 500 }}>{realm.name}</Link>
                                            </td>
                                            <td className="text-muted">{realm.description || '—'}</td>
                                            <td>
                                                <span className={`badge ${realm.is_active ? 'badge-success' : 'badge-danger'}`}>
                                                    {realm.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </td>
                                            <td>
                                                {realm.keycloak_config ? (
                                                    <span className="badge badge-primary">Configured</span>
                                                ) : (
                                                    <span className="text-muted">—</span>
                                                )}
                                            </td>
                                            <td>
                                                <div className="table-actions">
                                                    <Link to={`/realms/${realm.id}`} className="btn btn-sm btn-secondary">View</Link>
                                                    <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(realm.id)}>Delete</button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Realm">
                <RealmForm onSubmit={handleCreate} isLoading={createRealm.isPending} onCancel={() => setShowCreateModal(false)} />
            </Modal>

            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Realm">
                <p className="mb-lg">Are you sure? This will delete all associated roles, principals, resources, and ACLs.</p>
                <div className="flex justify-end gap-sm">
                    <button className="btn btn-secondary" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                    <button className="btn btn-danger" onClick={handleDelete} disabled={deleteRealm.isPending}>
                        {deleteRealm.isPending ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </Modal>

            <ManifestUploadModal
                isOpen={showUploadModal}
                onClose={() => setShowUploadModal(false)}
            />
        </>
    )
}
