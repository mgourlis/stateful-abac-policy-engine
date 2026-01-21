import { useState } from 'react'
import type { RealmCreate, KeycloakConfigCreate } from '../../api/types'

interface RealmFormProps {
    onSubmit: (data: RealmCreate) => Promise<void>
    isLoading: boolean
    onCancel: () => void
    initialData?: Partial<RealmCreate>
}

export function RealmForm({ onSubmit, isLoading, onCancel, initialData }: RealmFormProps) {
    const [name, setName] = useState(initialData?.name || '')
    const [description, setDescription] = useState(initialData?.description || '')
    const [includeKeycloak, setIncludeKeycloak] = useState(!!initialData?.keycloak_config)
    const [keycloakConfig, setKeycloakConfig] = useState<KeycloakConfigCreate>({
        server_url: initialData?.keycloak_config?.server_url || '',
        keycloak_realm: initialData?.keycloak_config?.keycloak_realm || '',
        client_id: initialData?.keycloak_config?.client_id || '',
        client_secret: initialData?.keycloak_config?.client_secret || '',
        verify_ssl: initialData?.keycloak_config?.verify_ssl ?? true,
        sync_groups: initialData?.keycloak_config?.sync_groups ?? false,
        sync_cron: initialData?.keycloak_config?.sync_cron || '',
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
                <label className="form-label" htmlFor="name">Name *</label>
                <input
                    type="text"
                    id="name"
                    className="form-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g., my-app-realm"
                    disabled={isLoading}
                />
            </div>

            <div className="form-group">
                <label className="form-label" htmlFor="description">Description</label>
                <textarea
                    id="description"
                    className="form-textarea"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    placeholder="Optional description"
                    rows={2}
                    disabled={isLoading}
                />
            </div>

            <div className="form-group">
                <label className="form-checkbox">
                    <input
                        type="checkbox"
                        checked={includeKeycloak}
                        onChange={e => setIncludeKeycloak(e.target.checked)}
                        disabled={isLoading}
                    />
                    <span>Configure Keycloak Integration</span>
                </label>
            </div>

            {includeKeycloak && (
                <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
                    <div className="card-header">
                        <span className="card-title">Keycloak Configuration</span>
                    </div>
                    <div className="card-content">
                        <div className="form-group">
                            <label className="form-label" htmlFor="server_url">Server URL *</label>
                            <input
                                type="text"
                                id="server_url"
                                className="form-input"
                                value={keycloakConfig.server_url}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, server_url: e.target.value }))}
                                placeholder="https://keycloak.example.com"
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="keycloak_realm">Keycloak Realm *</label>
                            <input
                                type="text"
                                id="keycloak_realm"
                                className="form-input"
                                value={keycloakConfig.keycloak_realm}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, keycloak_realm: e.target.value }))}
                                placeholder="master"
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="client_id">Client ID *</label>
                            <input
                                type="text"
                                id="client_id"
                                className="form-input"
                                value={keycloakConfig.client_id}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, client_id: e.target.value }))}
                                placeholder="my-client"
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="client_secret">Client Secret</label>
                            <input
                                type="password"
                                id="client_secret"
                                className="form-input"
                                value={keycloakConfig.client_secret || ''}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, client_secret: e.target.value }))}
                                placeholder="Optional"
                                disabled={isLoading}
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-checkbox">
                                <input
                                    type="checkbox"
                                    checked={keycloakConfig.verify_ssl}
                                    onChange={e => setKeycloakConfig(prev => ({ ...prev, verify_ssl: e.target.checked }))}
                                    disabled={isLoading}
                                />
                                <span>Verify SSL</span>
                            </label>
                        </div>

                        <div className="form-group">
                            <label className="form-checkbox">
                                <input
                                    type="checkbox"
                                    checked={keycloakConfig.sync_groups}
                                    onChange={e => setKeycloakConfig(prev => ({ ...prev, sync_groups: e.target.checked }))}
                                    disabled={isLoading}
                                />
                                <span>Sync Groups as Roles</span>
                            </label>
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="sync_cron">Sync Cron Schedule</label>
                            <input
                                type="text"
                                id="sync_cron"
                                className="form-input"
                                value={keycloakConfig.sync_cron || ''}
                                onChange={e => setKeycloakConfig(prev => ({ ...prev, sync_cron: e.target.value }))}
                                placeholder="e.g., */15 * * * * (every 15 mins)"
                                disabled={isLoading}
                            />
                            <p className="form-help">Leave empty to disable automatic sync</p>
                        </div>
                    </div>
                </div>
            )}

            <div className="flex justify-end gap-sm">
                <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={isLoading}>
                    Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isLoading}>
                    {isLoading ? 'Creating...' : 'Create Realm'}
                </button>
            </div>
        </form>
    )
}
