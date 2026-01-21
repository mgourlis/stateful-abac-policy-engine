import { useState } from 'react'

// Condition structure matching backend
export interface Condition {
    op: string
    attr?: string
    val?: unknown
    source?: string
    args?: unknown
    conditions?: Condition[]
}

// Available operators
const OPERATORS = [
    { value: '=', label: 'Equals (=)' },
    { value: '!=', label: 'Not Equals (≠)' },
    { value: '>', label: 'Greater Than (>)' },
    { value: '<', label: 'Less Than (<)' },
    { value: '>=', label: 'Greater or Equal (≥)' },
    { value: '<=', label: 'Less or Equal (≤)' },
    { value: 'in', label: 'In List' },
]

const SPATIAL_OPERATORS = [
    { value: 'st_dwithin', label: 'Within Distance' },
    { value: 'st_contains', label: 'Contains' },
    { value: 'st_within', label: 'Within' },
    { value: 'st_intersects', label: 'Intersects' },
]

const SOURCES = [
    { value: 'resource', label: 'Resource Attribute' },
    { value: 'principal', label: 'Principal Attribute' },
    { value: 'context', label: 'Context Value' },
]

interface ConditionRowProps {
    condition: Condition
    onChange: (condition: Condition) => void
    onRemove: () => void
    depth?: number
}

function ConditionRow({ condition, onChange, onRemove, depth = 0 }: ConditionRowProps) {
    const isLogical = condition.op === 'and' || condition.op === 'or'
    const isSpatial = condition.op?.startsWith('st_')

    if (isLogical) {
        return (
            <div className="condition-group" style={{ marginLeft: depth * 16 }}>
                <div className="condition-group-header">
                    <select
                        className="form-select"
                        value={condition.op}
                        onChange={e => onChange({ ...condition, op: e.target.value })}
                        style={{ width: 'auto', minWidth: '80px' }}
                    >
                        <option value="and">AND</option>
                        <option value="or">OR</option>
                    </select>
                    <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => onChange({
                            ...condition,
                            conditions: [...(condition.conditions || []), { op: '=', attr: '', val: '', source: 'resource' }]
                        })}
                    >
                        + Condition
                    </button>
                    <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => onChange({
                            ...condition,
                            conditions: [...(condition.conditions || []), { op: 'and', conditions: [] }]
                        })}
                    >
                        + Group
                    </button>
                    {depth > 0 && (
                        <button type="button" className="btn btn-sm btn-ghost text-danger" onClick={onRemove}>×</button>
                    )}
                </div>
                <div className="condition-children">
                    {condition.conditions?.map((child, i) => (
                        <ConditionRow
                            key={i}
                            condition={child}
                            depth={depth + 1}
                            onChange={(updated) => {
                                const newConditions = [...(condition.conditions || [])]
                                newConditions[i] = updated
                                onChange({ ...condition, conditions: newConditions })
                            }}
                            onRemove={() => {
                                const newConditions = (condition.conditions || []).filter((_, idx) => idx !== i)
                                onChange({ ...condition, conditions: newConditions })
                            }}
                        />
                    ))}
                </div>
            </div>
        )
    }

    return (
        <div className="condition-row" style={{ marginLeft: depth * 16 }}>
            <select
                className="form-select"
                value={condition.source || 'resource'}
                onChange={e => onChange({ ...condition, source: e.target.value })}
                style={{ width: '140px' }}
            >
                {SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>

            <input
                type="text"
                className="form-input"
                placeholder="attribute"
                value={condition.attr || ''}
                onChange={e => onChange({ ...condition, attr: e.target.value })}
                style={{ width: '120px' }}
            />

            <select
                className="form-select"
                value={condition.op}
                onChange={e => onChange({ ...condition, op: e.target.value })}
                style={{ width: '150px' }}
            >
                <optgroup label="Comparison">
                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                </optgroup>
                <optgroup label="Spatial">
                    {SPATIAL_OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                </optgroup>
            </select>

            <input
                type="text"
                className="form-input"
                placeholder={condition.op === 'in' ? '["a","b"]' : 'value or $principal.attr'}
                title="Use $principal.attr, $context.attr, or $resource.attr to reference dynamic values"
                value={typeof condition.val === 'string' ? condition.val : JSON.stringify(condition.val ?? '')}
                onChange={e => {
                    let val: unknown = e.target.value
                    // Keep variable references as strings (starts with $)
                    if (e.target.value.startsWith('$')) {
                        val = e.target.value
                    }
                    // Try to parse JSON for arrays/objects
                    else if (e.target.value.startsWith('[') || e.target.value.startsWith('{')) {
                        try { val = JSON.parse(e.target.value) } catch { /* keep string */ }
                    }
                    // Try to parse numbers
                    else if (!isNaN(Number(e.target.value)) && e.target.value.trim() !== '') {
                        val = Number(e.target.value)
                    }
                    // Try to parse booleans
                    else if (e.target.value === 'true') val = true
                    else if (e.target.value === 'false') val = false
                    onChange({ ...condition, val })
                }}
                style={{ width: '160px' }}
            />

            {isSpatial && condition.op === 'st_dwithin' && (
                <input
                    type="number"
                    className="form-input"
                    placeholder="distance (m)"
                    value={typeof condition.args === 'number' ? condition.args : ''}
                    onChange={e => onChange({ ...condition, args: Number(e.target.value) })}
                    style={{ width: '100px' }}
                />
            )}

            <button type="button" className="btn btn-sm btn-ghost text-danger" onClick={onRemove}>×</button>
        </div>
    )
}

interface ConditionBuilderProps {
    value: Condition | null
    onChange: (condition: Condition | null) => void
}

export function ConditionBuilder({ value, onChange }: ConditionBuilderProps) {
    const [enabled, setEnabled] = useState(value !== null)

    const handleToggle = (checked: boolean) => {
        setEnabled(checked)
        if (checked && !value) {
            onChange({ op: 'and', conditions: [] })
        } else if (!checked) {
            onChange(null)
        }
    }

    const handleAddCondition = () => {
        if (!value) {
            onChange({ op: 'and', conditions: [{ op: '=', attr: '', val: '', source: 'resource' }] })
        } else if (value.op === 'and' || value.op === 'or') {
            onChange({
                ...value,
                conditions: [...(value.conditions || []), { op: '=', attr: '', val: '', source: 'resource' }]
            })
        }
    }

    return (
        <div className="condition-builder">
            <label className="form-checkbox mb-sm">
                <input type="checkbox" checked={enabled} onChange={e => handleToggle(e.target.checked)} />
                <span>Enable conditional access (ABAC)</span>
            </label>

            {enabled && value && (
                <div className="condition-builder-content">
                    <ConditionRow
                        condition={value}
                        onChange={onChange}
                        onRemove={() => onChange(null)}
                    />
                    {value.conditions?.length === 0 && (
                        <button type="button" className="btn btn-sm btn-secondary mt-sm" onClick={handleAddCondition}>
                            + Add First Condition
                        </button>
                    )}
                </div>
            )}

            {enabled && value && (
                <details className="mt-sm" style={{ fontSize: 'var(--font-size-xs)' }}>
                    <summary className="text-muted" style={{ cursor: 'pointer' }}>Preview JSON</summary>
                    <pre className="condition-preview">
                        {JSON.stringify(value, null, 2)}
                    </pre>
                </details>
            )}
        </div>
    )
}

// Helper to convert builder output to API format
export function conditionToAPI(condition: Condition | null): Record<string, unknown> | undefined {
    if (!condition) return undefined

    // Clean up empty groups
    if (condition.op === 'and' || condition.op === 'or') {
        if (!condition.conditions || condition.conditions.length === 0) return undefined
        if (condition.conditions.length === 1) return conditionToAPI(condition.conditions[0])
        return {
            op: condition.op,
            conditions: condition.conditions.map(c => conditionToAPI(c)).filter(Boolean)
        }
    }

    // Leaf condition
    const result: Record<string, unknown> = {
        op: condition.op,
        attr: condition.attr,
        val: condition.val,
        source: condition.source || 'resource'
    }
    if (condition.args !== undefined) result.args = condition.args
    return result
}
