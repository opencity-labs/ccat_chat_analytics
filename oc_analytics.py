import time
import json
import os
import tomli
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.decorators import endpoint
from cat.log import log
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from cat.looking_glass.cheshire_cat import CheshireCat
from fastapi import Header, HTTPException
from cat.env import get_env
import jwt

# Import metrics and registry
from .metrics import (
    registry,
    CHATBOT_INSTANCE_INFO,
    CHATBOT_PLUGIN_INFO,
    VECTOR_MEMORY_POINTS_TOTAL,
    VECTOR_MEMORY_SOURCES_TOTAL,
    FEEDBACK_THUMB_UP_TOTAL,
    FEEDBACK_THUMB_DOWN_TOTAL
)


# Memory metrics caching
_last_memory_update = 0
_memory_update_interval = 3600 # seconds

def _update_memory_metrics():
    global _last_memory_update
    
    # Avoid frequent updates
    if time.time() - _last_memory_update < _memory_update_interval:
        return

    try:
        # Get Cat instance
        cat = CheshireCat()
        
        # Check if memory is loaded
        if not hasattr(cat, 'memory') or not cat.memory:
            return
            
        vector_memory = cat.memory.vectors
        if not vector_memory:
            return
        
        # Only process declarative memory
        if 'declarative' in vector_memory.collections:
            name = 'declarative'
            collection = vector_memory.collections['declarative']
            try:
                # 1. Count points (fast)
                col_info = collection.client.get_collection(collection.collection_name)
                points_count = col_info.points_count
                VECTOR_MEMORY_POINTS_TOTAL.labels(collection=name).set(points_count)
                
                # 2. Count sources (expensive)
                sources = set()
                offset = None
                limit = 100000
                
                while True:
                    points, offset = collection.client.scroll(
                        collection_name=collection.collection_name,
                        with_vectors=False,
                        with_payload=['metadata.source'], 
                        limit=limit,
                        offset=offset
                    )
                    
                    for point in points:
                        if point.payload and 'metadata' in point.payload:
                            meta = point.payload.get('metadata', {})
                            if isinstance(meta, dict):
                                source = meta.get('source')
                                if source:
                                    sources.add(source)
                    
                    if offset is None:
                        break
                        
                VECTOR_MEMORY_SOURCES_TOTAL.labels(collection=name).set(len(sources))
                     
            except Exception as e:
                log.error(json.dumps({
                    "component": "ccat_oc_analytics",
                    "event": "memory_metrics_collection_error", 
                    "data": {
                        "collection": name,
                        "error": str(e)
                    }
                }))

        _last_memory_update = time.time()
        
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "memory_metrics_error",
            "data": {
                "error": str(e)
            }
        }))

def _update_version_metrics():
    # Core Version
    core_version = "unknown"
    try:
        # Try to find pyproject.toml in current directory or parent directories
        pyproject_path = "pyproject.toml"
        if not os.path.exists(pyproject_path):
             # Try one level up
             pyproject_path = "../pyproject.toml"
        
        if os.path.exists(pyproject_path):
            with open(pyproject_path, "rb") as f:
                data = tomli.load(f)
                core_version = data.get("project", {}).get("version", "unknown")
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "core_version_error",
            "data": {
                "error": str(e)
            }
        }))

    # Frontend Version - currently we have no reliable way to get this from backend
    frontend_version = "unknown"

    CHATBOT_INSTANCE_INFO.labels(core_version=core_version, frontend_version=frontend_version).set(1)

    # Plugin Versions
    try:
        mad_hatter = MadHatter()
        for plugin_id, plugin in mad_hatter.plugins.items():
            version = plugin.manifest.get("version", "unknown")
            CHATBOT_PLUGIN_INFO.labels(plugin_id=plugin_id, version=version).set(1)
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "plugin_version_error",
            "data": {
                "error": str(e)
            }
        }))

@endpoint.get("/metrics")
def metrics():
    _update_version_metrics()
    _update_memory_metrics()
    data = generate_latest(registry).decode('utf-8')
    # Filter out _created lines to remove "garbage"
    lines = []
    for line in data.split('\n'):
        # Check if line is a metric definition or comment
        if line.startswith('#'):
            lines.append(line)
            continue
            
        # Check if metric name ends with _created
        # Metric line format: name{labels} value [timestamp]
        parts = line.split(' ')
        if parts:
            metric_part = parts[0]
            # Remove labels to check name
            metric_name = metric_part.split('{')[0]
            
            if metric_name.endswith('_created'):
                continue
                
            if metric_name == 'chat_sentiment_score_bucket':
                continue
                
        lines.append(line)
        
    filtered_data = "\n".join(lines)
    return Response(filtered_data, media_type=CONTENT_TYPE_LATEST)


@endpoint.post("/thumbup")
def thumbup(payload: dict, authorization: str = Header(None)):
    
    # 1. Validate Authentication
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
        
    token = authorization.split(" ")[1]
    
    try:
        # Get JWT config from env
        jwt_secret = get_env("CCAT_JWT_SECRET")
        # Default to HS256 if not set, as typical fallback, but plugin uses get_env strict
        jwt_algo = get_env("CCAT_JWT_ALGORITHM") 
        
        if not jwt_secret:
             log.error("JWT Secret not configured in environment")
             raise HTTPException(status_code=500, detail="Server misconfiguration")
             
        if not jwt_algo:
             jwt_algo = "HS256" # Fallback just in case

        # Decode token
        decoded = jwt.decode(token, jwt_secret, algorithms=[jwt_algo])
        
        # Verify it is a temporary session
        user_id = decoded.get("sub")
        
        # Get plugin settings to check prefix
        mad_hatter = MadHatter()
        auth_plugin = mad_hatter.plugins.get("ccat_temporary_chat_authentication")
        
        if not auth_plugin:
            log.warning("Received thumbup but ccat_temporary_chat_authentication plugin is not loaded")
            raise HTTPException(status_code=403, detail="Authentication plugin missing")
            
        settings = auth_plugin.load_settings()
        prefix = settings.get("session_prefix", "sess_")
        
        if not user_id or not user_id.startswith(prefix):
             raise HTTPException(status_code=403, detail="Not a temporary session")
             
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error validating thumbup token: {e}")
        raise HTTPException(status_code=500, detail="Validation error")

    # 2. Record Metric
    if payload.get("value"):
        FEEDBACK_THUMB_UP_TOTAL.inc()
    else:
        FEEDBACK_THUMB_DOWN_TOTAL.inc()

    return {"status": "success"}
