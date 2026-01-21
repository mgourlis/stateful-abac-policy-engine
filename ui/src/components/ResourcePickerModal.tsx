import { useState, useMemo, useEffect } from 'react'
import { useResources } from '../hooks/useResources'
import { useResourceTypes } from '../hooks/useResourceTypes'
import { Modal } from './Modal'
import { Pagination } from './Pagination'
import type { Resource, ResourceType } from '../api/types'

interface ResourcePickerModalProps {
    realmId: number;
    isOpen: boolean;
    onClose: () => void;
    onSelect: (resource: Resource) => void;
    title?: string;
    resourceTypeId?: number; // Pre-filter by type
}

export function ResourcePickerModal({
    realmId,
    isOpen,
    onClose,
    onSelect,
    title = 'Select Resource',
    resourceTypeId: initialTypeId,
}: ResourcePickerModalProps) {
    // Pagination
    const [skip, setSkip] = useState(0)
    const [limit, setLimit] = useState(10)

    // Filters
    const [typeId, setTypeId] = useState<number | ''>(initialTypeId || '')

    // Sync state with prop
    useEffect(() => {
        setTypeId(initialTypeId || '')
    }, [initialTypeId])
    const [externalId, setExternalId] = useState('')
    const [attributeSearch, setAttributeSearch] = useState('')
    const [debouncedExternalId, setDebouncedExternalId] = useState('')
    const [debouncedAttributes, setDebouncedAttributes] = useState('')

    // Debounce searches
    useMemo(() => {
        const timer = setTimeout(() => setDebouncedExternalId(externalId), 300)
        return () => clearTimeout(timer)
    }, [externalId])

    useMemo(() => {
        const timer = setTimeout(() => setDebouncedAttributes(attributeSearch), 500)
        return () => clearTimeout(timer)
    }, [attributeSearch])

    // Parse attributes filter
    const attributesFilter = debouncedAttributes.trim() ? (() => {
        try { return JSON.parse(debouncedAttributes) } catch { return undefined }
    })() : undefined

    const { data: resourcesData, isLoading } = useResources(realmId, {
        skip,
        limit,
        resource_type_id: typeId || undefined,
        external_id: debouncedExternalId || undefined,
        attributes: attributesFilter,
    })
    const { data: resourceTypes } = useResourceTypes(realmId)

    const resources = resourcesData?.items || []
    const total = resourcesData?.total || 0

    const getTypeName = (id: number) =>
        resourceTypes?.find((rt: ResourceType) => rt.id === id)?.name || `Type ${id}`

    const handleSelect = (resource: Resource) => {
        onSelect(resource)
        onClose()
    }

    const resetFilters = () => {
        setTypeId(initialTypeId || '')
        setExternalId('')
        setAttributeSearch('')
        setSkip(0)
    }

    // Lock type filter if preset
    const typeFilterLocked = initialTypeId !== undefined

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={title}>
            <div style={{ minHeight: '400px' }}>
                {/* Filters */}
                <div className="flex gap-sm mb-md" style={{ flexWrap: 'wrap' }}>
                    <select
                        className="form-select"
                        value={typeId}
                        onChange={(e) => { setTypeId(e.target.value ? Number(e.target.value) : ''); setSkip(0) }}
                        style={{ flex: 1, minWidth: '140px' }}
                        disabled={typeFilterLocked}
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
                        value={externalId}
                        onChange={(e) => { setExternalId(e.target.value); setSkip(0) }}
                        style={{ flex: 1, minWidth: '140px' }}
                    />

                    <input
                        type="text"
                        className="form-input"
                        placeholder='Attributes: {"key":"val"}'
                        value={attributeSearch}
                        onChange={(e) => { setAttributeSearch(e.target.value); setSkip(0) }}
                        style={{ flex: 1, minWidth: '180px' }}
                    />

                    {(typeId || externalId || attributeSearch) && !typeFilterLocked && (
                        <button className="btn btn-sm btn-ghost" onClick={resetFilters}>
                            Clear
                        </button>
                    )}
                </div>

                {/* Results */}
                {isLoading ? (
                    <div className="loading-container">
                        <div className="loading-spinner" />
                    </div>
                ) : resources.length === 0 ? (
                    <div className="empty-state">
                        <p className="text-muted">No resources found</p>
                    </div>
                ) : (
                    <div className="table-container" style={{ maxHeight: '300px', overflow: 'auto' }}>
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Type</th>
                                    <th>External ID</th>
                                    <th></th>
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
                                            {(Array.isArray(resource.external_id) ? resource.external_id[0] : resource.external_id) || <span className="text-muted">—</span>}
                                        </td>
                                        <td>
                                            <button
                                                className="btn btn-sm btn-primary"
                                                onClick={() => handleSelect(resource)}
                                            >
                                                Select
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                <div style={{ marginTop: 'var(--spacing-md)' }}>
                    <Pagination
                        total={total}
                        skip={skip}
                        limit={limit}
                        onPageChange={setSkip}
                        onPageSizeChange={(newLimit) => { setLimit(newLimit); setSkip(0) }}
                        pageSizeOptions={[10, 25, 50]}
                    />
                </div>
            </div>
        </Modal>
    )
}
