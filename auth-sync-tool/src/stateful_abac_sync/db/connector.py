"""
Database connector for executing queries against source databases.
Uses synchronous psycopg3 for simplicity in CLI context.
"""

from typing import Dict, Any, List, Optional
import psycopg
from psycopg.rows import dict_row

from ..config.schema import DatabaseConfig


class DatabaseConnector:
    """Synchronous database connector for PostgreSQL."""
    
    def __init__(self):
        self._conn: Optional[psycopg.Connection] = None
        
    def connect(self, config: DatabaseConfig) -> None:
        """
        Establish connection to the database.
        
        Args:
            config: Database configuration.
        """
        conninfo = f"host={config.host} port={config.port} dbname={config.database} user={config.user} password={config.password}"
        self._conn = psycopg.connect(conninfo, row_factory=dict_row)
        
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as list of dictionaries.
        
        Args:
            query: SQL query string.
            
        Returns:
            List of records as dictionaries.
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        with self._conn.cursor() as cur:
            cur.execute(query)
            return list(cur.fetchall())
    
    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
