// API Response Types matching backend schemas

// Pagination
export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    skip: number;
    limit: number;
    has_more: boolean;
}

export interface Realm {
    id: number;
    name: string;
    description?: string;
    is_active: boolean;
    keycloak_config?: KeycloakConfig;
}

export interface KeycloakConfig {
    id: number;
    realm_id: number;
    server_url: string;
    keycloak_realm: string;
    client_id: string;
    client_secret?: string;
    verify_ssl: boolean;
    public_key?: string;
    algorithm: string;
    settings?: Record<string, unknown>;
    sync_groups: boolean;
    sync_cron?: string;
}

export interface AuthRole {
    id: number;
    name: string;
    realm_id: number;
    attributes?: Record<string, unknown>;
}

export interface Principal {
    id: number;
    username: string;
    realm_id: number;
    attributes: Record<string, unknown>;
    roles?: AuthRole[];
}

export interface Action {
    id: number;
    name: string;
    realm_id: number;
}

export interface ResourceType {
    id: number;
    name: string;
    realm_id: number;
    is_public: boolean;
}

export interface Resource {
    id: number;
    realm_id: number;
    resource_type_id: number;
    resource_type?: ResourceType;
    attributes: Record<string, unknown>;
    external_id?: string | string[] | null; // API returns singular external_id
    geometry?: Record<string, unknown> | string | null;
}

export interface ACL {
    id: number;
    realm_id: number;
    resource_type_id: number;
    action_id: number;
    principal_id?: number;
    role_id?: number;
    resource_id?: number;
    conditions?: Record<string, unknown>;
    // Related entities for display
    resource_type?: ResourceType;
    action?: Action;
    principal?: Principal;
    role?: AuthRole;
    resource?: Resource;
}

// Request Types
export interface RealmCreate {
    name: string;
    description?: string;
    keycloak_config?: KeycloakConfigCreate;
}

export interface RealmUpdate {
    name?: string;
    description?: string;
    is_active?: boolean;
    keycloak_config?: KeycloakConfigCreate;
}

export interface KeycloakConfigCreate {
    server_url: string;
    keycloak_realm: string;
    client_id: string;
    client_secret?: string;
    verify_ssl?: boolean;
    algorithm?: string;
    settings?: Record<string, unknown>;
    sync_groups?: boolean;
    sync_cron?: string;
}

export interface AuthRoleCreate {
    name: string;
    attributes?: Record<string, unknown>;
}

export interface AuthRoleUpdate {
    name?: string;
    attributes?: Record<string, unknown>;
}

export interface PrincipalCreate {
    username: string;
    attributes?: Record<string, unknown>;
    role_ids?: number[];
}

export interface PrincipalUpdate {
    username?: string;
    attributes?: Record<string, unknown>;
    role_ids?: number[];
}

export interface ActionCreate {
    name: string;
}

export interface ActionUpdate {
    name?: string;
}

export interface ResourceTypeCreate {
    name: string;
    is_public?: boolean;
}

export interface ResourceTypeUpdate {
    name?: string;
    is_public?: boolean;
}

export interface ResourceCreate {
    resource_type_id: number;
    attributes?: Record<string, unknown>;
    external_id?: string;
    geometry?: Record<string, unknown> | string;
    srid?: number;
}

export interface ResourceUpdate {
    attributes?: Record<string, unknown>;
    external_ids?: string[];
}

export interface ACLCreate {
    realm_id: number;
    resource_type_id: number;
    action_id: number;
    principal_id?: number;
    role_id?: number;
    resource_id?: number;
    conditions?: Record<string, unknown>;
}

export interface ACLUpdate {
    resource_type_id?: number;
    action_id?: number;
    principal_id?: number;
    role_id?: number;
    resource_id?: number;
    conditions?: Record<string, unknown>;
}
