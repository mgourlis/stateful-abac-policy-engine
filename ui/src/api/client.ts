// API Client for Stateful ABAC Policy Engine

const BASE_URL = '/api/v1';

class ApiError extends Error {
    status: number;
    statusText: string;

    constructor(status: number, statusText: string, message: string) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.statusText = statusText;
    }
}

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
            const json = JSON.parse(text);
            message = json.detail || json.message || text;
        } catch {
            // Use raw text
        }
        throw new ApiError(response.status, response.statusText, message);
    }
    return response.json();
}

export const api = {
    // Generic methods
    async get<T>(endpoint: string): Promise<T> {
        const response = await fetch(`${BASE_URL}${endpoint}`);
        return handleResponse<T>(response);
    },

    async post<T>(endpoint: string, data?: unknown): Promise<T> {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: data ? JSON.stringify(data) : undefined,
        });
        return handleResponse<T>(response);
    },

    async put<T>(endpoint: string, data: unknown): Promise<T> {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        return handleResponse<T>(response);
    },

    async delete<T>(endpoint: string): Promise<T> {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
            method: 'DELETE',
        });
        return handleResponse<T>(response);
    },

    async uploadFile<T>(endpoint: string, file: File, params?: Record<string, string>): Promise<T> {
        const formData = new FormData();
        formData.append('file', file);

        let url = `${BASE_URL}${endpoint}`;
        if (params) {
            const searchParams = new URLSearchParams(params);
            url += `?${searchParams.toString()}`;
        }

        const response = await fetch(url, {
            method: 'POST',
            body: formData,
        });
        return handleResponse<T>(response);
    },

    async downloadBlob(endpoint: string): Promise<Blob> {
        const response = await fetch(`${BASE_URL}${endpoint}`);
        if (!response.ok) {
            const text = await response.text();
            throw new ApiError(response.status, response.statusText, text);
        }
        return response.blob();
    },
};

export { ApiError };
