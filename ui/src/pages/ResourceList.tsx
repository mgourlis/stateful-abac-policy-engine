import { useState, useMemo } from 'react'
import { useResources, useCreateResource, useDeleteResource } from '../hooks/useResources'
import { useResourceTypes } from '../hooks/useResourceTypes'
import { Modal } from '../components/Modal'
import { Pagination } from '../components/Pagination'
import { ACLCreateModal } from '../components/ACLCreateModal'
import type { Resource, ResourceType } from '../api/types'

interface ResourceListProps {
    realmId: number
}

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState(value)

    useMemo(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay)
        return () => clearTimeout(handler)
    }, [value, delay])

    return debouncedValue
}

export function ResourceList({ realmId }: ResourceListProps) {
    // Pagination state
    const [skip, setSkip] = useState(0)
    const [limit, setLimit] = useState(25)

    // Search state
    const [searchTypeId, setSearchTypeId] = useState<number | ''>('')
    const [searchExternalId, setSearchExternalId] = useState('')
    const [searchAttributes, setSearchAttributes] = useState('')
    const debouncedExternalId = useDebounce(searchExternalId, 300)
    const debouncedAttributes = useDebounce(searchAttributes, 500)

    // Modal states
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [viewResource, setViewResource] = useState<Resource | null>(null)
    const [showACLModal, setShowACLModal] = useState(false)
    const [aclResource, setACLResource] = useState<Resource | null>(null)

    // Parse attributes filter
    const attributesFilter = debouncedAttributes.trim() ? (() => {
        try {
            return JSON.parse(debouncedAttributes)
        } catch {
            return undefined
        }
    })() : undefined

    // Data queries
    const { data: resourcesData, isLoading, error } = useResources(realmId, {
        skip,
        limit,
        resource_type_id: searchTypeId || undefined,
        external_id: debouncedExternalId || undefined,
        attributes: attributesFilter,
    })
    const { data: resourceTypes } = useResourceTypes(realmId)
    const create = useCreateResource(realmId)
    const del = useDeleteResource(realmId)

    // Form state
    const [formTypeId, setFormTypeId] = useState<number | ''>('')
    const [formExternalIds, setFormExternalIds] = useState('')
    const [formError, setFormError] = useState<string | null>(null)

    const resetForm = () => {
        setFormTypeId('')
        setFormExternalIds('')
        setFormError(null)
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!formTypeId) {
            setFormError('Resource type is required')
            return
        }
        try {
            await create.mutateAsync({
                resource_type_id: Number(formTypeId),
                external_id: formExternalIds.trim() || undefined
            })
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating resource')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await del.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const openACLModal = (resource: Resource) => {
        setACLResource(resource)
        setShowACLModal(true)
    }

    const getTypeName = (typeId: number) => {
        return resourceTypes?.find((rt: ResourceType) => rt.id === typeId)?.name || `Type ${typeId}`
    }

    // Reset to first page when filters change
    const handleFilterChange = () => {
        setSkip(0)
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading resources...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load resources: {error.message}</div>
    }

    const resources = resourcesData?.items || []
    const total = resourcesData?.total || 0

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">Resources ({total})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add Resource
                    </button>
                </div>

                {/* Search Bar */}
                <div className="search-bar">
                    <select
                        className="form-select"
                        value={searchTypeId}
                        onChange={(e) => { setSearchTypeId(e.target.value ? Number(e.target.value) : ''); handleFilterChange() }}
                        style={{ maxWidth: '180px' }}
                    >
                        <option value="">All Types</option>
                        {resourceTypes?.map((rt: ResourceType) => (
                            <option key={rt.id} value={rt.id}>{rt.name}</option>
                        ))}
                    </select>

                    <input
                        type="text"
                        className="form-input"
                        placeholder="External ID..."
                        value={searchExternalId}
                        onChange={(e) => { setSearchExternalId(e.target.value); handleFilterChange() }}
                        style={{ maxWidth: '180px' }}
                    />

                    <input
                        type="text"
                        className="form-input"
                        placeholder='Attributes: {"key": "value"}'
                        value={searchAttributes}
                        onChange={(e) => { setSearchAttributes(e.target.value); handleFilterChange() }}
                        style={{ maxWidth: '250px' }}
                    />

                    {(searchTypeId || searchExternalId || searchAttributes) && (
                        <button
                            className="btn btn-sm btn-ghost"
                            onClick={() => { setSearchTypeId(''); setSearchExternalId(''); setSearchAttributes(''); handleFilterChange() }}
                        >
                            Clear
                        </button>
                    )}
                </div>

                {resources.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">
                            {searchTypeId || searchExternalId ? 'No resources match your filters' : 'No resources yet'}
                        </h3>
                        <p className="empty-state-description">
                            {searchTypeId || searchExternalId
                                ? 'Try adjusting your search criteria.'
                                : 'Resources are specific instances that can be protected by ACLs.'
                            }
                        </p>
                    </div>
                ) : (
                    <div className="table-container">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Type</th>
                                    <th>External IDs</th>
                                    <th style={{ width: '180px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {resources.map((resource: Resource) => (
                                    <tr key={resource.id}>
                                        <td className="text-muted">{resource.id}</td>
                                        <td>
                                            <span className="badge badge-primary">{getTypeName(resource.resource_type_id)}</span>
                                        </td>
                                        <td>
                                            {resource.external_id ? (
                                                <div className="flex gap-xs" style={{ flexWrap: 'wrap' }}>
                                                    {(Array.isArray(resource.external_id) ? resource.external_id : [resource.external_id]).slice(0, 3).map((eid: string) => (
                                                        <code key={eid} style={{ fontSize: 'var(--font-size-xs)' }}>
                                                            {eid}
                                                        </code>
                                                    ))}
                                                    {Array.isArray(resource.external_id) && resource.external_id.length > 3 && (
                                                        <span className="text-muted">+{resource.external_id.length - 3} more</span>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="text-muted">—</span>
                                            )}
                                        </td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => setViewResource(resource)}>View</button>
                                                <button className="btn btn-sm btn-secondary" onClick={() => openACLModal(resource)}>+ ACL</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(resource.id)}>Delete</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                <Pagination
                    total={total}
                    skip={skip}
                    limit={limit}
                    onPageChange={setSkip}
                    onPageSizeChange={(newLimit) => { setLimit(newLimit); setSkip(0) }}
                />
            </div>

            {/* Create Resource Modal */}
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Resource">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Resource Type *</label>
                        <select
                            className="form-select"
                            value={formTypeId}
                            onChange={e => setFormTypeId(e.target.value ? Number(e.target.value) : '')}
                        >
                            <option value="">Select a type...</option>
                            {resourceTypes?.map((rt: ResourceType) => (
                                <option key={rt.id} value={rt.id}>{rt.name}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">External IDs</label>
                        <input
                            type="text"
                            className="form-input"
                            value={formExternalIds}
                            onChange={e => setFormExternalIds(e.target.value)}
                            placeholder="Comma-separated: id1, id2, id3"
                        />
                        <p className="form-help">Optional identifiers for external systems</p>
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
                            {create.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* View Resource Modal */}
            <Modal isOpen={viewResource !== null} onClose={() => setViewResource(null)} title="Resource Details">
                {viewResource && (
                    <div>
                        <p><strong>ID:</strong> {viewResource.id}</p>
                        <p><strong>Type:</strong> {getTypeName(viewResource.resource_type_id)}</p>
                        <p className="mt-md"><strong>External IDs:</strong></p>
                        {viewResource.external_id ? (
                            <ul style={{ marginLeft: 'var(--spacing-lg)' }}>
                                {(Array.isArray(viewResource.external_id) ? viewResource.external_id : [viewResource.external_id]).map((eid: string) => (
                                    <li key={eid}><code>{eid}</code></li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-muted">None</p>
                        )}
                        <p className="mt-md"><strong>Attributes:</strong></p>
                        <pre style={{ background: 'var(--color-bg-primary)', padding: 'var(--spacing-md)', borderRadius: 'var(--radius-md)', overflow: 'auto', fontSize: 'var(--font-size-sm)' }}>
                            {JSON.stringify(viewResource.attributes, null, 2)}
                        </pre>
                    </div>
                )}
            </Modal>

            {/* ACL Create Modal with preset resource */}
            <ACLCreateModal
                realmId={realmId}
                isOpen={showACLModal}
                onClose={() => { setShowACLModal(false); setACLResource(null) }}
                presetResource={aclResource || undefined}
            />

            {/* Delete Modal */}
            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete Resource">
                <p className="mb-lg">Are you sure you want to delete this resource?</p>
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
