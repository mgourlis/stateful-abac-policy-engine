"""
Geometry Service - Handles geometry format detection, parsing, and transformation
"""
import json
import logging
from typing import Any, Optional, Union
from shapely.geometry import shape, Point
from shapely import wkt
from shapely.errors import ShapelyError
from geoalchemy2.shape import from_shape
from geoalchemy2.elements import WKBElement

logger = logging.getLogger(__name__)



# Target SRID for all geometries in the system
TARGET_SRID = 3857


class GeometryService:
    """
    Service for handling geometry input in various formats.
    
    Supported input formats:
    - GeoJSON Geometry object
    - GeoJSON Feature object
    - WKT string
    - EWKT string (with SRID prefix)
    - Coordinate list/tuple [lng, lat]
    
    All geometries are normalized to SRID 3857.
    """
    
    @classmethod
    def parse(cls, value: Any, srid: int = None) -> Optional[WKBElement]:
        """
        Parse geometry from various input formats and return geoalchemy2 geometry.
        
        Args:
            value: Geometry input (dict, string, list, or None)
            srid: Optional SRID to use if not specified in the input
            
        Returns:
            geoalchemy2 geometry element or None
            
        Raises:
            ValueError: If geometry format cannot be detected or parsed
        """
        if value is None:
            return None
        
        shapely_geom = cls._auto_detect_geometry(value, default_srid=srid)
        if shapely_geom is None:
            return None
        
        # Convert to geoalchemy2 with target SRID
        # Note: _auto_detect_geometry handles transformation to TARGET_SRID (3857)
        return from_shape(shapely_geom, srid=TARGET_SRID)
    
    @classmethod
    def parse_to_ewkt(cls, value: Any, srid: Optional[int] = None) -> Optional[str]:
        """
        Parse geometry from various input formats and return EWKT string.
        
        Args:
            value: Geometry input (dict, string, list, or None)
            srid: Optional SRID to use if not specified in the input
            
        Returns:
            EWKT string or None
        """
        if value is None:
            return None
        
        shapely_geom = cls._auto_detect_geometry(value, default_srid=srid)
        if shapely_geom is None:
            return None
        
        return f"SRID={TARGET_SRID};{shapely_geom.wkt}"
    
    # =====================================================================
    # AUTO-DETECT FORMAT
    # =====================================================================
    
    @classmethod
    def _auto_detect_geometry(cls, value: Any, default_srid: Optional[int] = None):
        """
        Detect input format and return a Shapely geometry.
        
        Supported:
            - GeoJSON Geometry
            - GeoJSON Feature
            - WKT or EWKT
            - Coordinate list [lng, lat]
        """
        
        # ---------------------------
        # Case 1: dict (GeoJSON)
        # ---------------------------
        if isinstance(value, dict):
            geom_obj = cls._extract_geometry_from_geojson(value)
            if geom_obj is not None:
                # Check for CRS in GeoJSON - default to default_srid or 4326 (WGS84)
                input_srid = cls._extract_srid_from_geojson(value)
                if input_srid is None:
                    input_srid = default_srid if default_srid is not None else 4326
                
                geom = shape(geom_obj)
                
                # Transform if input SRID differs from target
                print(f"DEBUG: Input SRID: {input_srid}, Target SRID: {TARGET_SRID}")
                if input_srid != TARGET_SRID:
                    print("DEBUG: Calling transform...")
                    geom = cls._transform_geometry(geom, input_srid, TARGET_SRID)
                    print(f"DEBUG: Result of transform: {geom}")
                
                return geom
            
            raise ValueError(f"Unrecognized dict format: {value}")
        
        # ---------------------------
        # Case 2: list/tuple → [lng, lat]
        # ---------------------------
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            lng = cls._to_float(value[0], "lng")
            lat = cls._to_float(value[1], "lat")
            point = Point(lng, lat)
            
            # Use provided SRID or default to 4326
            source_srid = default_srid if default_srid is not None else 4326
            
            return cls._transform_geometry(point, source_srid, TARGET_SRID)
        
        # ---------------------------
        # Case 3: string input (WKT/EWKT/GeoJSON)
        # ---------------------------
        if isinstance(value, str):
            value = value.strip()
            
            # Check for EWKT format: "SRID=xxxx;WKT"
            if value.upper().startswith("SRID="):
                srid, wkt_part = cls._parse_ewkt(value)
                try:
                    geom = wkt.loads(wkt_part)
                    if srid != TARGET_SRID:
                        geom = cls._transform_geometry(geom, srid, TARGET_SRID)
                    return geom
                except ShapelyError as e:
                    raise ValueError(f"Invalid WKT in EWKT string: {e}")
            
            # Try WKT first
            try:
                geom = wkt.loads(value)
                # If WKT doesn't specify SRID, use default or 4326
                source_srid = default_srid if default_srid is not None else 4326
                return cls._transform_geometry(geom, source_srid, TARGET_SRID)
            except ShapelyError:
                pass
            
            # Try GeoJSON (Feature / Geometry) as string
            geom_obj = cls._extract_geometry_from_geojson(value)
            if geom_obj is not None:
                # Same logic as dict GeoJSON
                if isinstance(geom_obj, dict):
                    try:
                        parsed = json.loads(value)
                        input_srid = cls._extract_srid_from_geojson(parsed)
                        if input_srid is None:
                            input_srid = default_srid if default_srid is not None else 4326
                            
                        geom = shape(geom_obj)
                        if input_srid != TARGET_SRID:
                            geom = cls._transform_geometry(geom, input_srid, TARGET_SRID)
                        return geom
                    except:
                        pass
                
                return shape(geom_obj)

            
            raise ValueError(f"String is not valid WKT, EWKT, or GeoJSON: {value}")
        
        raise ValueError(f"Cannot detect geometry format from: {type(value).__name__}")
    
    # =====================================================================
    # HELPERS: EWKT Parsing
    # =====================================================================
    
    @classmethod
    def _parse_ewkt(cls, ewkt_str: str) -> tuple:
        """
        Parse EWKT string into SRID and WKT components.
        
        Args:
            ewkt_str: EWKT string like "SRID=3857;POINT(0 0)"
            
        Returns:
            Tuple of (srid: int, wkt: str)
        """
        # Format: SRID=xxxx;WKT_DATA
        parts = ewkt_str.split(";", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid EWKT format: {ewkt_str}")
        
        srid_part = parts[0].upper()
        if not srid_part.startswith("SRID="):
            raise ValueError(f"Invalid SRID prefix: {srid_part}")
        
        try:
            srid = int(srid_part[5:])
        except ValueError:
            raise ValueError(f"Invalid SRID value: {srid_part[5:]}")
        
        return srid, parts[1]
    
    # =====================================================================
    # HELPERS: GeoJSON
    # =====================================================================
    
    @classmethod
    def _extract_geometry_from_geojson(cls, value) -> Optional[dict]:
        """
        Extract geometry from GeoJSON value, handling both Feature and Geometry objects.
        
        Args:
            value: The value to extract geometry from (dict, str, or other)
            
        Returns:
            dict or None: The geometry object, or None if not valid GeoJSON
        """
        if isinstance(value, dict):
            # Feature
            if (
                value.get("type") == "Feature"
                and "geometry" in value
                and cls._is_geojson_geometry(value["geometry"])
            ):
                return value["geometry"]
            
            # Geometry
            if cls._is_geojson_geometry(value):
                return value
        
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                return cls._extract_geometry_from_geojson(parsed)
            except (json.JSONDecodeError, TypeError):
                return None
        
        return None
    
    @classmethod
    def _extract_srid_from_geojson(cls, value: dict) -> Optional[int]:
        """
        Extract SRID from GeoJSON CRS property if present.
        """
        if not isinstance(value, dict):
            return None
        
        crs = value.get("crs")
        if not crs or not isinstance(crs, dict):
            return None
        
        # Named CRS format: {"type": "name", "properties": {"name": "EPSG:3857"}}
        if crs.get("type") == "name":
            props = crs.get("properties", {})
            name = props.get("name", "")
            if name.upper().startswith("EPSG:"):
                try:
                    return int(name[5:])
                except ValueError:
                    pass
            elif name.upper().startswith("URN:OGC:DEF:CRS:EPSG::"):
                try:
                    return int(name[22:])
                except ValueError:
                    pass
        
        return None
    
    @classmethod
    def _is_geojson_geometry(cls, value) -> bool:
        """
        Check if a value is a GeoJSON geometry object.
        """
        if isinstance(value, dict):
            return (
                "type" in value
                and value.get("type") in [
                    "Point",
                    "LineString",
                    "Polygon",
                    "MultiPoint",
                    "MultiLineString",
                    "MultiPolygon",
                    "GeometryCollection",
                ]
                and (
                    "coordinates" in value
                    or value.get("type") == "GeometryCollection"
                )
            )
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                return cls._is_geojson_geometry(parsed)
            except (json.JSONDecodeError, TypeError):
                return False
        
        return False
    
    # =====================================================================
    # HELPERS: Coordinate transformation
    # =====================================================================
    
    @classmethod
    def _transform_geometry(cls, geom, from_srid: int, to_srid: int):
        """
        Transform geometry from one SRID to another using pyproj.
        """
        if from_srid == to_srid:
            return geom
        
        try:
            from pyproj import Transformer
            from shapely.ops import transform
            
            transformer = Transformer.from_crs(
                f"EPSG:{from_srid}",
                f"EPSG:{to_srid}",
                always_xy=True
            )
            
            return transform(transformer.transform, geom)
        except ImportError:
            logger.error(f"pyproj not available, cannot transform from SRID {from_srid} to {to_srid}")
            raise
        except Exception as e:
            logger.error(f"Failed to transform geometry: {e}")
            raise
    
    # =====================================================================
    # HELPERS: Type conversion
    # =====================================================================
    
    @classmethod
    def _to_float(cls, value: Any, name: str) -> float:
        """Convert value to float with descriptive error."""
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {name} value: {value}")
