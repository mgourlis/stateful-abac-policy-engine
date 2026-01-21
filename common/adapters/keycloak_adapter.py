from typing import List, Dict, Optional, Any
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakError
import logging

from common.models import RealmKeycloakConfig

logger = logging.getLogger(__name__)

class KeycloakAdapter:
    def __init__(self, config: RealmKeycloakConfig):
        self.server_url = config.server_url
        self.realm_name = config.keycloak_realm
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.verify_ssl = config.verify_ssl
        self.admin = None

    def connect(self):
        """
        Establishes connection to Keycloak Admin API.
        """
        try:
            self.admin = KeycloakAdmin(
                server_url=self.server_url,
                client_id=self.client_id,
                client_secret_key=self.client_secret,
                realm_name=self.realm_name,
                verify=self.verify_ssl
            )
            # Note: auto_refresh_token was removed in python-keycloak 5.x
            # Token refresh is now handled automatically by the library
            
        except Exception as e:
            logger.error(f"Failed to connect to Keycloak: {e}")
            raise e

    def get_roles(self) -> List[Dict[str, Any]]:
        """
        Fetches all roles from the Keycloak realm.
        """
        if not self.admin:
            self.connect()
        try:
            # keycloak_admin.get_realm_roles() returns list of dicts
            return self.admin.get_realm_roles()
        except KeycloakError as e:
            logger.error(f"Error fetching roles from Keycloak: {e}")
            raise e

    def get_principals(self) -> List[Dict[str, Any]]:
        """
        Fetches all users (principals) from the Keycloak realm.
        """
        if not self.admin:
            self.connect()
        try:
            # keycloak_admin.get_users({}) returns list of dicts
            return self.admin.get_users({})
        except KeycloakError as e:
            logger.error(f"Error fetching users from Keycloak: {e}")
            raise e

    def get_user_roles(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetches realm roles for a specific user.
        """
        if not self.admin:
            self.connect()
        try:
            return self.admin.get_realm_roles_of_user(user_id)
        except KeycloakError as e:
            logger.error(f"Error fetching roles for user {user_id}: {e}")
            raise e

    def get_groups(self) -> List[Dict[str, Any]]:
        """
        Fetches all groups from the Keycloak realm.
        """
        if not self.admin:
            self.connect()
        try:
            return self.admin.get_groups()
        except KeycloakError as e:
            logger.error(f"Error fetching groups from Keycloak: {e}")
            raise e

    def get_user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetches all groups for a specific user.
        """
        if not self.admin:
            self.connect()
        try:
            return self.admin.get_user_groups(user_id=user_id)
        except KeycloakError as e:
            logger.error(f"Error fetching groups for user {user_id}: {e}")
            raise e
