import { useState, useEffect } from 'react'
import { useResourceTypes } from '../hooks/useResourceTypes'
import { useActions } from '../hooks/useActions'
import { useRoles } from '../hooks/useRoles'
import { usePrincipals } from '../hooks/usePrincipals'
import { useCreateACL } from '../hooks/useACLs'
import { Modal } from './Modal'
import { ResourcePickerModal } from './ResourcePickerModal'
import { ConditionBuilder, conditionToAPI, type Condition } from './ConditionBuilder'
import type { ResourceType, Action, AuthRole, Principal, Resource } from '../api/types'

interface ACLCreateModalProps {
    realmId: number
    isOpen: boolean
    onClose: () => void
    // Pre-configured values
    presetResourceTypeId?: number
    presetResource?: Resource
    onSuccess?: () => void
}

export function ACLCreateModal({
    realmId,
    isOpen,
    onClose,
    presetResourceTypeId,
    presetResource,
    onSuccess,
}: ACLCreateModalProps) {
    const { data: resourceTypes } = useResourceTypes(realmId)
    const { data: actions } = useActions(realmId)
    const { data: roles } = useRoles(realmId)
    const { data: principals } = usePrincipals(realmId)
    const create = useCreateACL(realmId)

    const [showResourcePicker, setShowResourcePicker] = useState(false)

    // Form state
    const [formResourceTypeId, setFormResourceTypeId] = useState<number | ''>('')
    const [formActionId, setFormActionId] = useState<number | ''>('')
    const [formRoleId, setFormRoleId] = useState<number | ''>('')
    const [formPrincipalId, setFormPrincipalId] = useState<number | ''>('')
    const [formResourceId, setFormResourceId] = useState<number | ''>('')
    const [selectedResource, setSelectedResource] = useState<Resource | null>(null)
    const [formConditions, setFormConditions] = useState<Condition | null>(null)
    const [formError, setFormError] = useState<string | null>(null)

    // Initialize with presets when modal opens
    useEffect(() => {
        if (isOpen) {
            if (presetResource) {
                setFormResourceTypeId(presetResource.resource_type_id)
                setFormResourceId(presetResource.id)
                setSelectedResource(presetResource)
            } else if (presetResourceTypeId) {
                setFormResourceTypeId(presetResourceTypeId)
                setFormResourceId('')
                setSelectedResource(null)
            }
        }
    }, [isOpen, presetResourceTypeId, presetResource])

    const resetForm = () => {
        setFormResourceTypeId(presetResourceTypeId || (presetResource?.resource_type_id) || '')
        setFormActionId('')
        setFormRoleId('')
        setFormPrincipalId('')
        setFormResourceId(presetResource?.id || '')
        setSelectedResource(presetResource || null)
        setFormConditions(null)
        setFormError(null)
    }

    const handleClose = () => {
        resetForm()
        onClose()
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
                realm_id: realmId,
                resource_type_id: Number(formResourceTypeId),
                action_id: Number(formActionId),
                role_id: formRoleId ? Number(formRoleId) : undefined,
                principal_id: formPrincipalId ? Number(formPrincipalId) : undefined,
                resource_id: formResourceId ? Number(formResourceId) : undefined,
                conditions
            })
            handleClose()
            onSuccess?.()
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Error creating ACL')
        }
    }

    const handleResourceSelect = (resource: Resource) => {
        setSelectedResource(resource)
        setFormResourceId(resource.id)
        setFormResourceTypeId(resource.resource_type_id)
    }

    const getTypeName = (id: number) =>
        resourceTypes?.find((rt: ResourceType) => rt.id === id)?.name || `Type ${id}`

    // Determine what's locked/hidden
    // presetResourceTypeId = type-level ACL (hide resource selection entirely)
    // presetResource = resource-level ACL (hide both type and resource selection)
    const isTypeLevelPreset = presetResourceTypeId !== undefined && !presetResource
    const isResourcePreset = presetResource !== undefined

    return (
        <>
            <Modal isOpen={isOpen} onClose={handleClose} title="Create ACL">
                <form onSubmit={handleCreate}>
                    {formError && <div className="alert alert-danger mb-md">{formError}</div>}

                    {/* Info banner for presets */}
                    {(presetResource || presetResourceTypeId) && (
                        <div className="alert alert-info mb-md">
                            {presetResource
                                ? `Creating ACL for resource #${presetResource.id}`
                                : `Creating type-level ACL for ${getTypeName(presetResourceTypeId!)}`}
                        </div>
                    )}

                    {/* Resource Type - hidden when preset resource, shown when no preset or type-level preset */}
                    {!isResourcePreset && (
                        <div className="form-group">
                            <label className="form-label">Resource Type *</label>
                            <select
                                className="form-select"
                                value={formResourceTypeId}
                                onChange={e => setFormResourceTypeId(e.target.value ? Number(e.target.value) : '')}
                                disabled={isTypeLevelPreset}
                            >
                                <option value="">Select...</option>
                                {resourceTypes?.map((rt: ResourceType) => (
                                    <option key={rt.id} value={rt.id}>{rt.name}</option>
                                ))}
                            </select>
                        </div>
                    )}

                    <div className="form-group">
                        <label className="form-label">Action *</label>
                        <select
                            className="form-select"
                            value={formActionId}
                            onChange={e => setFormActionId(e.target.value ? Number(e.target.value) : '')}
                        >
                            <option value="">Select...</option>
                            {actions?.map((a: Action) => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Role (choose one)</label>
                        <select
                            className="form-select"
                            value={formRoleId}
                            onChange={e => { setFormRoleId(e.target.value ? Number(e.target.value) : ''); setFormPrincipalId('') }}
                        >
                            <option value="">None</option>
                            {roles?.map((r: AuthRole) => <option key={r.id} value={r.id}>{r.name}</option>)}
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Or Principal</label>
                        <select
                            className="form-select"
                            value={formPrincipalId}
                            onChange={e => { setFormPrincipalId(e.target.value ? Number(e.target.value) : ''); setFormRoleId('') }}
                        >
                            <option value="">None</option>
                            {principals?.map((p: Principal) => <option key={p.id} value={p.id}>{p.username}</option>)}
                        </select>
                    </div>

                    {/* Resource selection - hidden when preset resource OR type-level preset */}
                    {!isResourcePreset && !isTypeLevelPreset && (
                        <div className="form-group">
                            <label className="form-label">Specific Resource (optional)</label>
                            <div className="flex gap-sm">
                                <input
                                    type="text"
                                    className="form-input"
                                    readOnly
                                    value={selectedResource ? `#${selectedResource.id} (${selectedResource.external_id || 'no ext id'})` : 'All resources of this type'}
                                />
                                <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => setShowResourcePicker(true)}
                                    disabled={!formResourceTypeId}
                                >
                                    Browse...
                                </button>
                                {selectedResource && (
                                    <button
                                        type="button"
                                        className="btn btn-ghost"
                                        onClick={() => { setSelectedResource(null); setFormResourceId('') }}
                                    >
                                        Clear
                                    </button>
                                )}
                            </div>
                            <p className="form-help">Leave empty for type-level ACL</p>
                        </div>
                    )}

                    <div className="form-group">
                        <label className="form-label">Conditions</label>
                        <ConditionBuilder value={formConditions} onChange={setFormConditions} />
                    </div>

                    <div className="flex justify-end gap-sm">
                        <button type="button" className="btn btn-secondary" onClick={handleClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
                            {create.isPending ? 'Creating...' : 'Create ACL'}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Resource Picker - filtered by selected type */}
            <ResourcePickerModal
                realmId={realmId}
                isOpen={showResourcePicker}
                onClose={() => setShowResourcePicker(false)}
                onSelect={handleResourceSelect}
                title="Select Resource"
                resourceTypeId={typeof formResourceTypeId === 'number' ? formResourceTypeId : undefined}
            />
        </>
    )
}
