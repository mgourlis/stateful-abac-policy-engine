from typing import Optional, List, Any, Union
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint, Boolean, FetchedValue, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry

class Base(DeclarativeBase):
    pass

class Realm(Base):
    __tablename__ = 'realm'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    
    resource_types: Mapped[List["ResourceType"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    actions: Mapped[List["Action"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    principals: Mapped[List["Principal"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    roles: Mapped[List["AuthRole"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    resources: Mapped[List["Resource"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    acls: Mapped[List["ACL"]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    keycloak_config: Mapped[Optional["RealmKeycloakConfig"]] = relationship(back_populates="realm", uselist=False, cascade="all, delete-orphan")

class ResourceType(Base):
    __tablename__ = 'resource_type'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False)
    
    realm: Mapped["Realm"] = relationship(back_populates="resource_types")
    
    __table_args__ = (
        UniqueConstraint('realm_id', 'name', name='uq_resource_type_realm_name'),
    )

class Action(Base):
    __tablename__ = 'action'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False)
    
    realm: Mapped["Realm"] = relationship(back_populates="actions")
    
    __table_args__ = (
        UniqueConstraint('realm_id', 'name', name='uq_action_realm_name'),
    )

class Principal(Base):
    __tablename__ = 'principal'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONB, server_default='{}')
    
    realm: Mapped["Realm"] = relationship(back_populates="principals")
    roles: Mapped[List["AuthRole"]] = relationship(secondary="principal_roles", back_populates="principals")

class AuthRole(Base):
    __tablename__ = 'auth_role'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False)
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    realm: Mapped["Realm"] = relationship(back_populates="roles")
    principals: Mapped[List["Principal"]] = relationship(secondary="principal_roles", back_populates="roles")

class PrincipalRoles(Base):
    __tablename__ = 'principal_roles'
    
    principal_id: Mapped[int] = mapped_column(Integer, ForeignKey('principal.id'), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey('auth_role.id'), primary_key=True)

class RealmKeycloakConfig(Base):
    __tablename__ = 'realm_keycloak_config'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False, unique=True)
    server_url: Mapped[str] = mapped_column(String, nullable=False)
    keycloak_realm: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    client_secret: Mapped[Optional[str]] = mapped_column(String)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, server_default='true')
    public_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    algorithm: Mapped[str] = mapped_column(String, default='RS256', server_default='RS256')
    settings: Mapped[Optional[dict]] = mapped_column(JSONB)
    sync_groups: Mapped[bool] = mapped_column(Boolean, server_default='false', default=False)
    sync_cron: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    realm: Mapped["Realm"] = relationship(back_populates="keycloak_config")

    __table_args__ = (
        UniqueConstraint('realm_id', name='uq_realm_keycloak_realm_id'),
    )

class Resource(Base):
    __tablename__ = 'resource'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), nullable=False)
    resource_type_id: Mapped[int] = mapped_column(Integer, ForeignKey('resource_type.id'), nullable=False)
    geometry: Mapped[Optional[Any]] = mapped_column(Geometry(geometry_type='GEOMETRY', srid=3857))
    attributes: Mapped[dict] = mapped_column(JSONB, server_default='{}', nullable=False)
    
    realm: Mapped["Realm"] = relationship(back_populates="resources")
    resource_type: Mapped["ResourceType"] = relationship()
    external_ids: Mapped[List["ExternalID"]] = relationship(back_populates="resource", cascade="all, delete-orphan")

    @property
    def name(self) -> str:
        return f"Resource-{self.id}"

class ACL(Base):
    __tablename__ = 'acl'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    realm_id: Mapped[int] = mapped_column(Integer, ForeignKey('realm.id'), primary_key=True)
    resource_type_id: Mapped[int] = mapped_column(Integer, ForeignKey('resource_type.id'), primary_key=True)
    
    action_id: Mapped[int] = mapped_column(Integer, ForeignKey('action.id'))
    principal_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('principal.id'), nullable=True)
    role_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('auth_role.id'), nullable=True)
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('resource.id'))
    conditions: Mapped[Optional[dict]] = mapped_column(JSONB)
    compiled_sql: Mapped[Optional[str]] = mapped_column(String, server_default=FetchedValue())
    
    realm: Mapped["Realm"] = relationship(back_populates="acls")

class ExternalID(Base):
    __tablename__ = 'external_ids'
    
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey('resource.id'), nullable=False)
    realm_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    
    resource: Mapped["Resource"] = relationship(back_populates="external_ids")

class AuthorizationLog(Base):
    __tablename__ = 'authorization_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    realm_id: Mapped[int] = mapped_column(Integer)
    principal_id: Mapped[int] = mapped_column(Integer)
    action_name: Mapped[Optional[str]] = mapped_column(String)
    resource_type_name: Mapped[Optional[str]] = mapped_column(String)
    decision: Mapped[bool] = mapped_column(Boolean)
    resource_ids: Mapped[Optional[List[Union[int, str]]]] = mapped_column(JSONB)
    external_resource_ids: Mapped[Optional[List[str]]] = mapped_column(JSONB)
