import { useState, useRef } from 'react'
import { Modal } from './Modal'
import { useApplyManifest, type ManifestMode } from '../hooks/useManifest'

interface ManifestUploadModalProps {
    isOpen: boolean
    onClose: () => void
}

export function ManifestUploadModal({ isOpen, onClose }: ManifestUploadModalProps) {
    const [selectedFile, setSelectedFile] = useState<File | null>(null)
    const [mode, setMode] = useState<ManifestMode>('update')
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState<string | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    const applyManifest = useApplyManifest()

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) {
            setSelectedFile(file)
            setError(null)
            setSuccess(null)
        }
    }

    const handleUpload = async () => {
        if (!selectedFile) {
            setError('Please select a file')
            return
        }

        setError(null)
        setSuccess(null)

        try {
            const result = await applyManifest.mutateAsync({ file: selectedFile, mode })
            setSuccess(result.message || 'Manifest applied successfully!')
            setSelectedFile(null)
            if (fileInputRef.current) {
                fileInputRef.current.value = ''
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to apply manifest')
        }
    }

    const handleClose = () => {
        setSelectedFile(null)
        setError(null)
        setSuccess(null)
        setMode('update')
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
        onClose()
    }

    return (
        <Modal isOpen={isOpen} onClose={handleClose} title="Upload Manifest">
            <div className="form-group">
                <label className="form-label">Manifest File</label>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,application/json"
                    onChange={handleFileChange}
                    className="form-input"
                />
                {selectedFile && (
                    <p className="text-muted" style={{ fontSize: 'var(--font-size-sm)', marginTop: 'var(--spacing-xs)' }}>
                        Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                    </p>
                )}
            </div>

            <div className="form-group">
                <label className="form-label">Mode</label>
                <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as ManifestMode)}
                    className="form-input"
                >
                    <option value="update">Update (add/modify, keep existing)</option>
                    <option value="create">Create (add only, skip existing)</option>
                    <option value="replace">Replace (delete all, recreate)</option>
                </select>
            </div>

            {error && (
                <div className="alert alert-danger" style={{ marginBottom: 'var(--spacing-md)' }}>
                    {error}
                </div>
            )}

            {success && (
                <div className="alert alert-success" style={{ marginBottom: 'var(--spacing-md)' }}>
                    {success}
                </div>
            )}

            <div className="flex gap-sm" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={handleClose}>
                    Cancel
                </button>
                <button
                    className="btn btn-primary"
                    onClick={handleUpload}
                    disabled={!selectedFile || applyManifest.isPending}
                >
                    {applyManifest.isPending ? 'Uploading...' : 'Upload'}
                </button>
            </div>
        </Modal>
    )
}
