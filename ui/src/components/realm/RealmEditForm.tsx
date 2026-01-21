import { useState } from 'react'
import type { Realm, RealmUpdate, KeycloakConfigCreate } from '../../api/types'

interface RealmEditFormProps {
    realm: Realm
    onSubmit: (data: RealmUpdate) => Promise<void>
    isLoading: boolean
    onCancel: () => void
}

export function RealmEditForm({ realm, onSubmit, isLoading, onCancel }: RealmEditFormProps) {
    const [name, setName] = useState(realm.name)
    const [description, setDescription] = useState(realm.description || '')
    const [isActive, setIsActive] = useState(realm.is_active)
    const [includeKeycloak, setIncludeKeycloak] = useState(!!realm.keycloak_config)
    const [keycloakConfig, setKeycloakConfig] = useState<KeycloakConfigCreate>({
        server_url: realm.keycloak_config?.server_url || '',
        keycloak_realm: realm.keycloak_config?.keycloak_realm || '',
        client_id: realm.keycloak_config?.client_id || '',
        client_secret: realm.keycloak_config?.client_secret || '',
        verify_ssl: realm.keycloak_config?.verify_ssl ?? true,
        sync_groups: realm.keycloak_config?.sync_groups ?? false,
        sync_cron: realm.keycloak_config?.sync_cron || '',
    })
    const [error, setError] = useState<string | null>(null)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError(null)

        if (!name.trim()) {
            setError('Name is required')
            return
        }

        try {
            await onSubmit({
                name: name.trim(),
                description: description.trim() || undefined,
                is_active: isActive,
                keycloak_config: includeKeycloak ? keycloakConfig : undefined,
            })
        } catch (err) {
            setError(err instanceof Error ? err.message : 'An error occurred')
        }
    }

    return (
        <form onSubmit={handleSubmit}>
            {error && <div className="alert alert-danger">{error}</div>}

            <div className="form-group">
                <label className="form-label" htmlFor="edit-name">Name *</label>
                <input
                    type="text"
                    id="edit-name"
                    className="form-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    disabled={isLoading}
                />
            </div>

            <div className="form-group">
                <label className="form-label" htmlFor="edit-description">Description</label>
                <textarea
                    id="edit-description"
                    className="form-textarea"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    rows={2}
                    disabled={isLoading}
                />
            </div>

            <div className="form-group">
                <label className="form-checkbox">
                    <input
                        type="checkbox"
                        checked={isActive}
                        onChange={e => setIsActive(e.target.checked)}
                        disabled={isLoading}
                    />
                    <span>Active</span>
                </label>
            </div>

            <div className="form-group">
                <label className="form-checkbox">
                    <input
                        type="checkbox"
                        checked={includeKeycloak}
                        onChange={e => setIncludeKeycloak(e.target.checked)}
                        disabled={isLoading}
                    />
                    <span>Keycloak Integration</span>
                </label>
            </div>

            {includeKeycloak && (
                <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
                    <div className="card-header">
                        <span className="card-title">Keycloak Configuration</span>
                    </div>
                    <div className="card-content">
                        <div className="form-group">
                            <label className="form-label">Server URL *</label>
                            <input
                                type="text"
                                className="form-input"
                                value={keycloakConfig.server_url}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, server_url: e.target.value }))}
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label">Keycloak Realm *</label>
                            <input
                                type="text"
                                className="form-input"
                                value={keycloakConfig.keycloak_realm}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, keycloak_realm: e.target.value }))}
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label">Client ID *</label>
                            <input
                                type="text"
                                className="form-input"
                                value={keycloakConfig.client_id}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, client_id: e.target.value }))}
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label">Client Secret</label>
                            <input
                                type="password"
                                className="form-input"
                                value={keycloakConfig.client_secret || ''}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, client_secret: e.target.value }))}
                                disabled={isLoading}
                            />
                        </div>

                        <div className="flex gap-md">
                            <label className="form-checkbox">
                                <input
                                    type="checkbox"
                                    checked={keycloakConfig.verify_ssl}
                                    onChange={e => setKeycloakConfig(prev => ({ ...prev, verify_ssl: e.target.checked }))}
                                    disabled={isLoading}
                                />
                                <span>Verify SSL</span>
                            </label>
                            <label className="form-checkbox">
                                <input
                                    type="checkbox"
                                    checked={keycloakConfig.sync_groups}
                                    onChange={e => setKeycloakConfig(prev => ({ ...prev, sync_groups: e.target.checked }))}
                                    disabled={isLoading}
                                />
                                <span>Sync Groups</span>
                            </label>
                        </div>

                        <div className="form-group mt-md">
                            <label className="form-label">Sync Cron Schedule</label>
                            <input
                                type="text"
                                className="form-input"
                                value={keycloakConfig.sync_cron || ''}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, sync_cron: e.target.value }))}
                                placeholder="e.g., */15 * * * *"
                                disabled={isLoading}
                            />
                        </div>
                    </div>
                </div>
            )}

            <div className="flex justify-end gap-sm">
                <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={isLoading}>
                    Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isLoading}>
                    {isLoading ? 'Saving...' : 'Save Changes'}
                </button>
            </div>
        </form>
    )
}
