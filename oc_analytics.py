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

# Import metrics and registry
from .metrics import (
    registry,
    CHATBOT_INSTANCE_INFO,
    CHATBOT_PLUGIN_INFO,
    VECTOR_MEMORY_POINTS_TOTAL,
    VECTOR_MEMORY_SOURCES_TOTAL
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
