import { useState } from 'react'
import { useACLs, useCreateACL, useDeleteACL } from '../hooks/useACLs'
import { useResourceTypes } from '../hooks/useResourceTypes'
import { useActions } from '../hooks/useActions'
import { useRoles } from '../hooks/useRoles'
import { usePrincipals } from '../hooks/usePrincipals'
import { Modal } from '../components/Modal'
import { ResourcePickerModal } from '../components/ResourcePickerModal'
import { Pagination } from '../components/Pagination'
import { ConditionBuilder, conditionToAPI, type Condition } from '../components/ConditionBuilder'
import type { ACL, ResourceType, Action, AuthRole, Principal, Resource } from '../api/types'

interface ACLListProps {
    realmId: number
}

export function ACLList({ realmId }: ACLListProps) {
    // Pagination state
    const [skip, setSkip] = useState(0)
    const [limit, setLimit] = useState(50)

    // Filter state
    const [filterResourceType, setFilterResourceType] = useState<number | ''>('')
    const [filterAction, setFilterAction] = useState<number | ''>('')
    const [filterRole, setFilterRole] = useState<number | ''>('')
    const [filterPrincipal, setFilterPrincipal] = useState<number | ''>('')
    const [filterResourceId, setFilterResourceId] = useState('')

    const { data: aclsData, isLoading, error } = useACLs(realmId, {
        skip,
        limit,
        resource_type_id: filterResourceType || undefined,
        action_id: filterAction || undefined,
        role_id: filterRole || undefined,
        principal_id: filterPrincipal || undefined,
        resource_id: filterResourceId ? Number(filterResourceId) : undefined
    })

    const { data: resourceTypes } = useResourceTypes(realmId)
    const { data: actions } = useActions(realmId)
    const { data: roles } = useRoles(realmId)
    const { data: principals } = usePrincipals(realmId)

    // Mutation hooks
    const create = useCreateACL(realmId)
    const del = useDeleteACL(realmId)

    // Modal & Form state
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
    const [viewACL, setViewACL] = useState<ACL | null>(null)
    const [showResourcePicker, setShowResourcePicker] = useState(false)

    // Create Form State
    const [formResourceTypeId, setFormResourceTypeId] = useState<number | ''>('')
    const [formActionId, setFormActionId] = useState<number | ''>('')
    const [formRoleId, setFormRoleId] = useState<number | ''>('')
    const [formPrincipalId, setFormPrincipalId] = useState<number | ''>('')
    const [formResourceId, setFormResourceId] = useState<number | ''>('')
    const [selectedResource, setSelectedResource] = useState<Resource | null>(null)
    const [formConditions, setFormConditions] = useState<Condition | null>(null)
    const [formError, setFormError] = useState<string | null>(null)

    // Helper functions
    const getName = (id: number | undefined, list: { id: number; name: string }[] | undefined) => {
        if (!id || !list) return '—'
        return list.find(i => i.id === id)?.name || `ID: ${id}`
    }

    const getUsername = (id: number | undefined) => {
        if (!id || !principals) return '—'
        return principals.find((p: Principal) => p.id === id)?.username || `ID: ${id}`
    }

    const resetForm = () => {
        setFormResourceTypeId('')
        setFormActionId('')
        setFormRoleId('')
        setFormPrincipalId('')
        setFormResourceId('')
        setSelectedResource(null)
        setFormConditions(null)
        setFormError(null)
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!formResourceTypeId || !formActionId) {
            setFormError('Resource type and action are required')
            return
        }
        if (!formRoleId && !formPrincipalId) {
            setFormError('Either a role or principal must be specified')
            return
        }

        const conditions = conditionToAPI(formConditions)

        try {
            await create.mutateAsync({
                realm_id: realmId, // Fixed: Added realm_id
                resource_type_id: Number(formResourceTypeId),
                action_id: Number(formActionId),
                role_id: formRoleId ? Number(formRoleId) : undefined,
                principal_id: formPrincipalId ? Number(formPrincipalId) : undefined,
                resource_id: formResourceId ? Number(formResourceId) : undefined,
                conditions
            })
            setShowCreateModal(false)
            resetForm()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating ACL')
        }
    }

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await del.mutateAsync(deleteConfirmId)
            setDeleteConfirmId(null)
        }
    }

    const handleResourceSelect = (resource: Resource) => {
        setSelectedResource(resource)
        setFormResourceId(resource.id)
        setFormResourceTypeId(resource.resource_type_id)
    }

    const handleFilterChange = () => {
        setSkip(0) // Reset to first page on filter change
    }

    const clearFilters = () => {
        setFilterResourceType('')
        setFilterAction('')
        setFilterRole('')
        setFilterPrincipal('')
        setFilterResourceId('')
        setSkip(0)
    }

    if (isLoading) {
        return (
            <div className="card">
                <div className="loading-container">
                    <div className="loading-spinner" />
                    <span style={{ marginLeft: '0.5rem' }}>Loading ACLs...</span>
                </div>
            </div>
        )
    }

    if (error) {
        return <div className="alert alert-danger">Failed to load ACLs: {error.message}</div>
    }

    const acls = aclsData?.items || []
    const total = aclsData?.total || 0

    return (
        <>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">ACLs ({total})</span>
                    <button className="btn btn-primary btn-sm" onClick={() => { resetForm(); setShowCreateModal(true) }}>
                        + Add ACL
                    </button>
                </div>

                {/* Filters */}
                <div className="search-bar" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
                    <select
                        className="form-select"
                        value={filterResourceType}
                        onChange={(e) => { setFilterResourceType(e.target.value ? Number(e.target.value) : ''); handleFilterChange() }}
                        style={{ maxWidth: '150px' }}
                    >
                        <option value="">type: All</option>
                        {resourceTypes?.map((rt: ResourceType) => <option key={rt.id} value={rt.id}>{rt.name}</option>)}
                    </select>

                    <select
                        className="form-select"
                        value={filterAction}
                        onChange={(e) => { setFilterAction(e.target.value ? Number(e.target.value) : ''); handleFilterChange() }}
                        style={{ maxWidth: '150px' }}
                    >
                        <option value="">action: All</option>
                        {actions?.map((a: Action) => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>

                    <select
                        className="form-select"
                        value={filterRole}
                        onChange={(e) => { setFilterRole(e.target.value ? Number(e.target.value) : ''); setFilterPrincipal(''); handleFilterChange() }}
                        style={{ maxWidth: '150px' }}
                    >
                        <option value="">role: All</option>
                        {roles?.map((r: AuthRole) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>

                    <select
                        className="form-select"
                        value={filterPrincipal}
                        onChange={(e) => { setFilterPrincipal(e.target.value ? Number(e.target.value) : ''); setFilterRole(''); handleFilterChange() }}
                        style={{ maxWidth: '150px' }}
                    >
                        <option value="">user: All</option>
                        {principals?.map((p: Principal) => <option key={p.id} value={p.id}>{p.username}</option>)}
                    </select>

                    <input
                        type="number"
                        className="form-input"
                        placeholder="Resource ID..."
                        value={filterResourceId}
                        onChange={(e) => { setFilterResourceId(e.target.value); handleFilterChange() }}
                        style={{ maxWidth: '120px' }}
                    />

                    {(filterResourceType || filterAction || filterRole || filterPrincipal || filterResourceId) && (
                        <button className="btn btn-sm btn-ghost" onClick={clearFilters}>Clear</button>
                    )}
                </div>

                {acls.length === 0 ? (
                    <div className="empty-state">
                        <h3 className="empty-state-title">No ACLs found</h3>
                        <p className="empty-state-description">Try adjusting your filters or create a new ACL.</p>
                    </div>
                ) : (
                    <div className="table-container">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Resource Type</th>
                                    <th>Action</th>
                                    <th>Role / Principal</th>
                                    <th>Resource</th>
                                    <th style={{ width: '100px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {acls.map((acl: ACL) => (
                                    <tr key={acl.id}>
                                        <td className="text-muted">{acl.id}</td>
                                        <td><span className="badge badge-primary">{getName(acl.resource_type_id, resourceTypes)}</span></td>
                                        <td>{getName(acl.action_id, actions)}</td>
                                        <td>
                                            {acl.role_id ? (
                                                <span className="badge badge-success">Role: {getName(acl.role_id, roles)}</span>
                                            ) : acl.principal_id ? (
                                                <span className="badge badge-warning">User: {getUsername(acl.principal_id)}</span>
                                            ) : (
                                                <span className="text-muted">—</span>
                                            )}
                                        </td>
                                        <td>
                                            {acl.resource_id ? <code>#{acl.resource_id}</code> : <span className="text-muted">All (type-level)</span>}
                                        </td>
                                        <td>
                                            <div className="table-actions">
                                                <button className="btn btn-sm btn-secondary" onClick={() => setViewACL(acl)}>View</button>
                                                <button className="btn btn-sm btn-ghost text-danger" onClick={() => setDeleteConfirmId(acl.id)}>Delete</button>
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

            {/* Create Modal */}
            <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create ACL">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger">{formError}</div>}
                    <div className="form-group">
                        <label className="form-label">Resource Type *</label>
                        <select className="form-select" value={formResourceTypeId} onChange={e => setFormResourceTypeId(e.target.value ? Number(e.target.value) : '')}>
                            <option value="">Select...</option>
                            {resourceTypes?.map((rt: ResourceType) => <option key={rt.id} value={rt.id}>{rt.name}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Action *</label>
                        <select className="form-select" value={formActionId} onChange={e => setFormActionId(e.target.value ? Number(e.target.value) : '')}>
                            <option value="">Select...</option>
                            {actions?.map((a: Action) => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Role (choose one)</label>
                        <select className="form-select" value={formRoleId} onChange={e => { setFormRoleId(e.target.value ? Number(e.target.value) : ''); setFormPrincipalId('') }}>
                            <option value="">None</option>
                            {roles?.map((r: AuthRole) => <option key={r.id} value={r.id}>{r.name}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Or Principal</label>
                        <select className="form-select" value={formPrincipalId} onChange={e => { setFormPrincipalId(e.target.value ? Number(e.target.value) : ''); setFormRoleId('') }}>
                            <option value="">None</option>
                            {principals?.map((p: Principal) => <option key={p.id} value={p.id}>{p.username}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Specific Resource (optional)</label>
                        <div className="flex gap-sm">
                            <input type="text" className="form-input" readOnly value={selectedResource ? `#${selectedResource.id} (${selectedResource.external_id || 'no ext id'})` : 'All resources of this type'} />
                            <button type="button" className="btn btn-secondary" onClick={() => setShowResourcePicker(true)} disabled={!formResourceTypeId}>Browse...</button>
                            {selectedResource && <button type="button" className="btn btn-ghost" onClick={() => { setSelectedResource(null); setFormResourceId('') }}>Clear</button>}
                        </div>
                        <p className="form-help">Leave empty for type-level ACL</p>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Conditions</label>
                        <ConditionBuilder
                            value={formConditions}
                            onChange={setFormConditions}
                        />
                    </div>
                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
                            {create.isPending ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </Modal>

            <ResourcePickerModal
                realmId={realmId}
                isOpen={showResourcePicker}
                onClose={() => setShowResourcePicker(false)}
                onSelect={handleResourceSelect}
                title="Select Resource for ACL"
                resourceTypeId={typeof formResourceTypeId === 'number' ? formResourceTypeId : undefined}
            />

            <Modal isOpen={viewACL !== null} onClose={() => setViewACL(null)} title="ACL Details">
                {viewACL && (
                    <div>
                        <p><strong>ID:</strong> {viewACL.id}</p>
                        <p><strong>Resource Type:</strong> {getName(viewACL.resource_type_id, resourceTypes)}</p>
                        <p><strong>Action:</strong> {getName(viewACL.action_id, actions)}</p>
                        <p><strong>Role:</strong> {viewACL.role_id ? getName(viewACL.role_id, roles) : '—'}</p>
                        <p><strong>Principal:</strong> {viewACL.principal_id ? getUsername(viewACL.principal_id) : '—'}</p>
                        <p><strong>Resource:</strong> {viewACL.resource_id ? `#${viewACL.resource_id}` : 'All (type-level)'}</p>
                        {viewACL.conditions && (
                            <>
                                <p className="mt-md"><strong>Conditions:</strong></p>
                                <pre style={{ background: 'var(--color-bg-primary)', padding: 'var(--spacing-md)', borderRadius: 'var(--radius-md)', overflow: 'auto', fontSize: 'var(--font-size-sm)' }}>
                                    {JSON.stringify(viewACL.conditions, null, 2)}
                                </pre>
                            </>
                        )}
                    </div>
                )}
            </Modal>

            <Modal isOpen={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Delete ACL">
                <p className="mb-lg">Are you sure you want to delete this ACL?</p>
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
