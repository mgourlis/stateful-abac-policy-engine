import { useState, useEffect, useCallback } from 'react'

interface Toast {
    id: string;
    type: 'success' | 'error' | 'info';
    message: string;
}

let toastId = 0;
let addToastFn: ((type: Toast['type'], message: string) => void) | null = null;

// Global function to show toasts from anywhere
export function showToast(type: Toast['type'], message: string) {
    if (addToastFn) {
        addToastFn(type, message);
    }
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const addToast = useCallback((type: Toast['type'], message: string) => {
        const id = String(++toastId);
        setToasts(prev => [...prev, { id, type, message }]);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 4000);
    }, []);

    const removeToast = (id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    };

    // Register the global function
    useEffect(() => {
        addToastFn = addToast;
        return () => { addToastFn = null; };
    }, [addToast]);

    return (
        <>
            {children}
            <div className="toast-container">
                {toasts.map(toast => (
                    <div
                        key={toast.id}
                        className={`toast toast-${toast.type}`}
                        onClick={() => removeToast(toast.id)}
                    >
                        <span className="toast-icon">
                            {toast.type === 'success' && '✓'}
                            {toast.type === 'error' && '✕'}
                            {toast.type === 'info' && 'ℹ'}
                        </span>
                        <span className="toast-message">{toast.message}</span>
                    </div>
                ))}
            </div>
        </>
    );
}
