import { useState } from 'react'
import { Routes, Route, Link, useParams, useNavigate } from 'react-router-dom'
import { useRealm, useUpdateRealm, useSyncRealm } from '../hooks/useRealms'
import { useExportManifest } from '../hooks/useManifest'
import { Modal } from '../components/Modal'
import { RealmEditForm } from '../components/realm/RealmEditForm'
import { RoleList } from './RoleList'
import { PrincipalList } from './PrincipalList'
import { ActionList } from './ActionList'
import { ResourceTypeList } from './ResourceTypeList'
import { ResourceList } from './ResourceList'
import { ACLList } from './ACLList'
import type { RealmUpdate } from '../api/types'

export function RealmDetail() {
    const { realmId } = useParams<{ realmId: string }>()
    const navigate = useNavigate()
    const [showEditModal, setShowEditModal] = useState(false)

    const numericRealmId = realmId ? parseInt(realmId, 10) : undefined
    const { data: realm, isLoading, error } = useRealm(numericRealmId)
    const updateRealm = useUpdateRealm()
    const syncRealm = useSyncRealm()
    const exportManifest = useExportManifest()

    const handleUpdate = async (data: RealmUpdate) => {
        if (numericRealmId) {
            await updateRealm.mutateAsync({ id: numericRealmId, data })
            setShowEditModal(false)
        }
    }

    const handleSync = async () => {
        if (numericRealmId) {
            await syncRealm.mutateAsync(numericRealmId)
            alert('Sync started in background')
        }
    }

    const handleExport = async () => {
        if (realm?.name) {
            try {
                await exportManifest.mutateAsync(realm.name)
            } catch (err) {
                alert(err instanceof Error ? err.message : 'Failed to export manifest')
            }
        }
    }

    if (isLoading) {
        return (
            <>
                <div className="page-header">
                    <div className="loading-container">
                        <div className="loading-spinner" />
                    </div>
                </div>
            </>
        )
    }

    if (error || !realm) {
        return (
            <>
                <div className="page-header">
                    <div>
                        <h1 className="page-title">Realm Not Found</h1>
                    </div>
                </div>
                <div className="page-content">
                    <div className="alert alert-danger">
                        {error?.message || 'Realm not found'}
                    </div>
                    <button className="btn btn-secondary" onClick={() => navigate('/realms')}>
                        Back to Realms
                    </button>
                </div>
            </>
        )
    }

    return (
        <>
            <div className="page-header">
                <div>
                    <div className="flex items-center gap-md" style={{ marginBottom: 'var(--spacing-xs)' }}>
                        <Link to="/realms" className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
                            Realms
                        </Link>
                        <span className="text-muted">/</span>
                    </div>
                    <h1 className="page-title">{realm.name}</h1>
                    <p className="page-subtitle">
                        {realm.description || 'No description'} •
                        <span className={realm.is_active ? 'text-success' : 'text-danger'} style={{ marginLeft: '0.5rem' }}>
                            {realm.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </p>
                </div>
                <div className="flex gap-sm">
                    <button
                        className="btn btn-secondary"
                        onClick={handleExport}
                        disabled={exportManifest.isPending}
                    >
                        {exportManifest.isPending ? 'Exporting...' : 'Export Manifest'}
                    </button>
                    {realm.keycloak_config && (
                        <button
                            className="btn btn-secondary"
                            onClick={handleSync}
                            disabled={syncRealm.isPending}
                        >
                            {syncRealm.isPending ? 'Syncing...' : 'Sync Keycloak'}
                        </button>
                    )}
                    <button className="btn btn-primary" onClick={() => setShowEditModal(true)}>
                        Edit Realm
                    </button>
                </div>
            </div>

            <div className="page-content">
                {/* Keycloak Info Card */}
                {realm.keycloak_config && (
                    <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
                        <div className="card-header">
                            <span className="card-title">Keycloak Integration</span>
                            <span className="badge badge-success">Connected</span>
                        </div>
                        <div className="card-content">
                            <div className="flex gap-md" style={{ flexWrap: 'wrap' }}>
                                <div>
                                    <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Server URL</span>
                                    <p>{realm.keycloak_config.server_url}</p>
                                </div>
                                <div>
                                    <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Realm</span>
                                    <p>{realm.keycloak_config.keycloak_realm}</p>
                                </div>
                                <div>
                                    <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Client ID</span>
                                    <p>{realm.keycloak_config.client_id}</p>
                                </div>
                                {realm.keycloak_config.sync_cron && (
                                    <div>
                                        <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Sync Schedule</span>
                                        <p>{realm.keycloak_config.sync_cron}</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* Entity Routes */}
                <Routes>
                    <Route index element={<RealmOverview realm={realm} />} />
                    <Route path="roles" element={<RoleList realmId={numericRealmId!} />} />
                    <Route path="principals" element={<PrincipalList realmId={numericRealmId!} />} />
                    <Route path="actions" element={<ActionList realmId={numericRealmId!} />} />
                    <Route path="resource-types" element={<ResourceTypeList realmId={numericRealmId!} />} />
                    <Route path="resources" element={<ResourceList realmId={numericRealmId!} />} />
                    <Route path="acls" element={<ACLList realmId={numericRealmId!} />} />
                </Routes>
            </div>

            <Modal
                isOpen={showEditModal}
                onClose={() => setShowEditModal(false)}
                title="Edit Realm"
            >
                <RealmEditForm
                    realm={realm}
                    onSubmit={handleUpdate}
                    isLoading={updateRealm.isPending}
                    onCancel={() => setShowEditModal(false)}
                />
            </Modal>
        </>
    )
}

import type { Realm } from '../api/types'

function RealmOverview({ realm }: { realm: Realm }) {
    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">Quick Navigation</span>
            </div>
            <div className="card-content">
                <p className="text-muted mb-lg">
                    Select an entity type from the sidebar to manage roles, principals, actions, resources, and ACLs for this realm.
                </p>
                <div className="flex gap-md" style={{ flexWrap: 'wrap' }}>
                    <Link to={`/realms/${realm.id}/roles`} className="btn btn-secondary">
                        Manage Roles
                    </Link>
                    <Link to={`/realms/${realm.id}/principals`} className="btn btn-secondary">
                        Manage Principals
                    </Link>
                    <Link to={`/realms/${realm.id}/actions`} className="btn btn-secondary">
                        Manage Actions
                    </Link>
                    <Link to={`/realms/${realm.id}/resource-types`} className="btn btn-secondary">
                        Manage Resource Types
                    </Link>
                    <Link to={`/realms/${realm.id}/acls`} className="btn btn-secondary">
                        Manage ACLs
                    </Link>
                </div>
            </div>
        </div>
    )
}
