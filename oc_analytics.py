import time
import json
import os
import sys
import subprocess
import tomli
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.decorators import hook, endpoint
from cat.log import log
from cat.db import crud
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry

from cat.convo.messages import CatMessage

# Global variables for spaCy model
_spacy_model = None
_spacy_available = None

def _check_spacy_availability() -> bool:
    """Check if spaCy is available."""
    global _spacy_available
    if _spacy_available is not None:
        return _spacy_available
    
    try:
        import spacy
        _spacy_available = True
    except ImportError:
        log.warning(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "import_error",
            "data": {
                "message": "spaCy not installed. Install with: pip install spacy"
            }
        }))
        _spacy_available = False
    
    return _spacy_available

def _download_model(model_name: str) -> bool:
    """Download a spaCy model if not present."""
    try:
        log.info(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_start",
            "data": {
                "model_name": model_name
            }
        }))
        
        result = subprocess.run([
            sys.executable, "-m", "spacy", "download", model_name
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_download_success",
                "data": {
                    "model_name": model_name
                }
            }))
            return True
        else:
            log.error(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_download_error",
                "data": {
                    "model_name": model_name,
                    "error": result.stderr
                }
            }))
            return False
    except subprocess.TimeoutExpired:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_timeout",
            "data": {
                "model_name": model_name
            }
        }))
        return False
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_error",
            "data": {
                "model_name": model_name,
                "error": str(e)
            }
        }))
        return False

def _get_spacy_model(model_name: str):
    """Get or load a spaCy model, downloading if necessary."""
    global _spacy_model
    
    if _spacy_model:
        return _spacy_model
    
    if not _check_spacy_availability():
        return None
    
    try:
        import spacy
        
        # First try to load the model
        try:
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_load_start",
                "data": {
                    "model_name": model_name
                }
            }))
            
            nlp = spacy.load(model_name)
            
            # Add sentiment analysis component using spacytextblob
            try:
                from spacytextblob.spacytextblob import SpacyTextBlob
                if 'spacytextblob' not in nlp.pipe_names:
                    nlp.add_pipe('spacytextblob')
                    log.info(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "sentiment_component_added",
                        "data": {
                            "model_name": model_name
                        }
                    }))
            except ImportError:
                log.warning(json.dumps({
                    "component": "ccat_oc_analytics",
                    "event": "spacytextblob_not_found",
                    "data": {
                        "message": "spacytextblob not installed. Install with: pip install spacytextblob"
                    }
                }))
            
            _spacy_model = nlp
            
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_load_success",
                "data": {
                    "model_name": model_name
                }
            }))
            return nlp
        except OSError:
            # Model not found, try to download it
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_not_found",
                "data": {
                    "model_name": model_name,
                    "message": "Attempting to download..."
                }
            }))
            
            if _download_model(model_name):
                # Try loading again after download
                try:
                    nlp = spacy.load(model_name)
                    
                    # Add sentiment analysis component using spacytextblob
                    try:
                        from spacytextblob.spacytextblob import SpacyTextBlob
                        if 'spacytextblob' not in nlp.pipe_names:
                            nlp.add_pipe('spacytextblob')
                    except ImportError:
                        log.warning(json.dumps({
                            "component": "ccat_oc_analytics",
                            "event": "spacytextblob_not_found",
                            "data": {
                                "message": "spacytextblob not installed. Install with: pip install spacytextblob"
                            }
                        }))
                    
                    _spacy_model = nlp
                    log.info(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "model_load_success",
                        "data": {
                            "model_name": model_name,
                            "after_download": True
                        }
                    }))
                    return nlp
                except OSError:
                    log.error(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "model_load_error",
                        "data": {
                            "model_name": model_name,
                            "error": "Failed to load even after download"
                        }
                    }))
                    return None
            else:
                return None
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_load_error",
            "data": {
                "error": str(e)
            }
        }))
        return None

def analyze_sentiment(text: str):
    """Analyze sentiment using spaCy with spacytextblob.
    
    Returns polarity score from -1 (negative) to 1 (positive).
    Uses TextBlob sentiment analysis via spacytextblob extension.
    """
    model_name = "xx_sent_ud_sm"
    nlp = _get_spacy_model(model_name)
    
    if nlp:
        try:
            # Truncate text to avoid processing very long texts
            if len(text) > 2000:
                text = text[:2000]
            
            doc = nlp(text)
            
            # spacytextblob provides polarity in doc._.polarity (ranges from -1 to 1)
            # and subjectivity in doc._.subjectivity (ranges from 0 to 1)
            if hasattr(doc._, 'polarity'):
                polarity = doc._.polarity
                # Ensure the value is within expected range
                return max(-1.0, min(1.0, polarity))
            else:
                # Fallback: calculate average polarity from sentences
                if doc.sents:
                    polarities = [
                        sent._.polarity if hasattr(sent._, 'polarity') else 0.0 
                        for sent in doc.sents
                    ]
                    if polarities:
                        avg_polarity = sum(polarities) / len(polarities)
                        return max(-1.0, min(1.0, avg_polarity))
                return 0.0
            
        except Exception as e:
            log.error(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "sentiment_analysis_error",
                "data": {
                    "error": str(e)
                }
            }))
            return 0.0
    return 0.0

# Custom registry to avoid global pollution and control output
_registry = CollectorRegistry()

# ============================================================================
# Metrics Definition
# ============================================================================
# NOTE: Counters are cumulative. To see activity in a specific time range in Grafana,
# use these query patterns:
#   - increase(metric_name[5m])              -> total increase in 5 minutes
#   - rate(metric_name[1m]) * 60             -> per-minute rate
#   - increase(metric_name[$__interval])     -> adapts to selected time range
#
# Example Grafana queries:
#   - increase(chatbot_chat_sessions_total[1h])                    -> new sessions in the last hour
#   - increase(chatbot_chat_messages_total{sender="user"}[5m])     -> user messages in 5 min
#   - rate(chatbot_chat_messages_total[1m]) * 60                   -> messages per minute
# ============================================================================

MESSAGE_COUNTER = Counter('chatbot_chat_messages_total', 'Total number of messages', ['sender'], registry=_registry)
# Custom buckets for sentiment polarity (-1 to 1) from spacytextblob
# Buckets: very negative, negative, slightly negative, neutral, slightly positive, positive, very positive
SENTIMENT_SCORE = Histogram('chatbot_chat_sentiment_score', 'Sentiment polarity score of messages from spacytextblob', ['sender'], 
                            buckets=[-1.0, -0.6, -0.2, -0.05, 0.05, 0.2, 0.6, 1.0], registry=_registry)
SENTIMENT_COUNTS = Counter('chatbot_chat_sentiment_counts', 'Sentiment counts (negative, neutral, positive)', ['sender', 'type'], registry=_registry)

NEW_SESSIONS = Counter('chatbot_chat_sessions_total', 'Total number of new chat sessions', registry=_registry)
RAG_DOCUMENTS_RETRIEVED = Counter('chatbot_rag_documents_retrieved_total', 'Total number of documents retrieved from RAG', ['source'], registry=_registry)
AVG_MESSAGES_PER_CHAT = Gauge('chatbot_chat_messages_per_chat_avg', 'Average number of messages per chat', registry=_registry)
MAX_MESSAGES_PER_CHAT = Gauge('chatbot_chat_messages_per_chat_max', 'Maximum number of messages in a single chat', registry=_registry)

LLM_INPUT_TOKENS_TOTAL = Counter('chatbot_llm_input_tokens_total', 'Total input tokens', ['model'], registry=_registry)
LLM_OUTPUT_TOKENS_TOTAL = Counter('chatbot_llm_output_tokens_total', 'Total output tokens', ['model'], registry=_registry)
LLM_INPUT_TOKENS_AVG = Gauge('chatbot_llm_input_tokens_avg', 'Average input tokens', ['model'], registry=_registry)
LLM_OUTPUT_TOKENS_AVG = Gauge('chatbot_llm_output_tokens_avg', 'Average output tokens', ['model'], registry=_registry)

NO_RELEVANT_MEMORY_COUNTER = Counter('chatbot_chat_no_relevant_memory_total', 'Total number of times no relevant memory was found', registry=_registry)

RESPONSE_TIME_SUM = Counter('chatbot_chat_response_time_seconds_sum', 'Sum of response times in seconds', registry=_registry)
RESPONSE_TIME_COUNT = Counter('chatbot_chat_response_time_seconds_count', 'Count of responses for average time calculation', registry=_registry)
RESPONSE_TIME_MAX = Gauge('chatbot_chat_response_time_seconds_max', 'Maximum response time in seconds', registry=_registry)

CHATBOT_INSTANCE_INFO = Gauge('chatbot_instance_info', 'Global version information (Core and Frontend)', ['core_version', 'frontend_version'], registry=_registry)
CHATBOT_PLUGIN_INFO = Gauge('chatbot_plugin_info', 'Plugin version information', ['plugin_id', 'version'], registry=_registry)

# Global state for simple tracking (Note: this resets on restart and grows with unique users)
USER_MESSAGE_COUNTS = {}
_llm_stats = {}
_max_response_time = 0.0

def _update_llm_stats(model_name, input_tokens, output_tokens):
    if model_name not in _llm_stats:
        _llm_stats[model_name] = {
            'count': 0,
            'total_input': 0,
            'total_output': 0
        }
    
    stats = _llm_stats[model_name]
    stats['count'] += 1
    stats['total_input'] += input_tokens
    stats['total_output'] += output_tokens
    
    # Update Gauges
    if stats['count'] > 0:
        avg_input = stats['total_input'] / stats['count']
        avg_output = stats['total_output'] / stats['count']
        
        LLM_INPUT_TOKENS_AVG.labels(model=model_name).set(avg_input)
        LLM_OUTPUT_TOKENS_AVG.labels(model=model_name).set(avg_output)

def _get_llm_name(cat):
    try:
        # Try to get from settings first as it is more reliable for the configured name
        selected_llm = crud.get_setting_by_name("llm_selected")
        if selected_llm:
             config_name = selected_llm.get("value", {}).get("name")
             if config_name:
                 llm_settings = crud.get_setting_by_name(config_name)
                 if llm_settings:
                     vals = llm_settings.get("value", {})
                     # Check common fields for model name
                     return vals.get("model_name") or vals.get("model") or vals.get("repo_id") or config_name
        
        # Fallback to inspecting the object
        llm = cat._llm
        if hasattr(llm, "model_name"):
            return llm.model_name
        if hasattr(llm, "model"):
            return llm.model
        if hasattr(llm, "repo_id"):
            return llm.repo_id
        return llm.__class__.__name__
    except:
        return "unknown"

def _track_sentiment(sender, text):
    """Track sentiment polarity and classify into negative/neutral/positive.
    
    Uses spacytextblob polarity score (-1 to 1):
    - Negative: polarity < -0.05
    - Neutral: -0.05 <= polarity <= 0.05
    - Positive: polarity > 0.05
    """
    sentiment = analyze_sentiment(text)
    SENTIMENT_SCORE.labels(sender=sender).observe(sentiment)
    
    # Classify sentiment based on polarity thresholds
    # TextBlob polarity around 0 is neutral, so we use a small threshold
    sentiment_type = "neutral"
    if sentiment < -0.05:
        sentiment_type = "negative"
    elif sentiment > 0.05:
        sentiment_type = "positive"
        
    SENTIMENT_COUNTS.labels(sender=sender, type=sentiment_type).inc()

def _cluster_source(source: str) -> str:
    if not source:
        return "unknown"
    
    # Remove trailing slash if present
    source = source.rstrip('/')
    
    # Handle URLs with protocol
    if '://' in source:
        try:
            protocol, rest = source.split('://', 1)
            if rest.count('/') > 1:
                rest = rest.rsplit('/', 1)[0]
            return f"{protocol}://{rest}"
        except ValueError:
            pass

    # If there is more than one slash, remove the last segment
    # e.g. example.com/services/s1 -> example.com/services
    # e.g. example.com/services -> example.com/services
    if source.count('/') > 1:
        return source.rsplit('/', 1)[0]
        
    return source

@hook
def before_cat_reads_message(user_message_json, cat):
    # Store start time for response time calculation
    cat.working_memory.oc_analytics_start_time = time.time()

    settings = cat.mad_hatter.get_plugin().load_settings()

    if settings.get("enable_message_metrics", True):
        # Track user message
        MESSAGE_COUNTER.labels(sender='user').inc()
        
        # Update user stats
        user_id = cat.user_id
        if user_id not in USER_MESSAGE_COUNTS:
            NEW_SESSIONS.inc()
            
        USER_MESSAGE_COUNTS[user_id] = USER_MESSAGE_COUNTS.get(user_id, 0) + 1
        
        # Update Gauges
        counts = list(USER_MESSAGE_COUNTS.values())
        if counts:
            AVG_MESSAGES_PER_CHAT.set(sum(counts) / len(counts))
            MAX_MESSAGES_PER_CHAT.set(max(counts))
    
    # Sentiment
    if settings.get("enable_sentiment_metrics", True):
        text = user_message_json.get("text", "")
        if text:
            _track_sentiment('user', text)
            
    return user_message_json

@hook
def after_cat_recalls_memories(cat):
    settings = cat.mad_hatter.get_plugin().load_settings()
    if not settings.get("enable_rag_metrics", True):
        return

    # Declarative memories (RAG)
    # cat.working_memory.declarative_memories is a list of tuples/lists where the first element is the Document
    for memory in cat.working_memory.declarative_memories:
        try:
            # memory[0] is the Document object
            doc = memory[0]
            if hasattr(doc, 'metadata'):
                source = doc.metadata.get('source', 'unknown')
                clustered_source = _cluster_source(source)
                RAG_DOCUMENTS_RETRIEVED.labels(source=clustered_source).inc()
        except Exception as e:
            log.error(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "rag_metrics_error",
                "data": {
                    "error": str(e)
                }
            }))

@hook(priority=0)
def fast_reply(message, cat):
    # Check if this is the default message from context_guardian_enricher
    # We check this here because fast_reply bypasses before_cat_sends_message
    try:
        if not message:
            return message
            
        # Get the text from the message (CatMessage or dict)
        text = None
        if isinstance(message, CatMessage):
            text = message.text
        elif isinstance(message, dict):
            text = message.get("output") or message.get("text")
            
        if text:
            # Try to get the default message from context_guardian_enricher settings
            # We access the plugin directly if available
            plugin = cat.mad_hatter.plugins.get("ccat_context_guardian_enricher")
            if plugin:
                settings = plugin.load_settings()
                default_message = settings.get('default_message', 'Sorry, I can\'t help you.')
                
                if text == default_message:
                    NO_RELEVANT_MEMORY_COUNTER.inc()
                    
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "fast_reply_check_error",
            "data": {
                "error": str(e)
            }
        }))
        
    return message

@hook
def before_cat_sends_message(message, cat):
    # Response Time Tracking
    # We do this here to capture the full processing time for normal responses
    # Fast replies (like the default message) bypass this hook, so they are automatically excluded
    try:
        if hasattr(cat.working_memory, 'oc_analytics_start_time'):
            start_time = cat.working_memory.oc_analytics_start_time
            duration = time.time() - start_time
            
            RESPONSE_TIME_SUM.inc(duration)
            RESPONSE_TIME_COUNT.inc()
            
            global _max_response_time
            if duration > _max_response_time:
                _max_response_time = duration
                RESPONSE_TIME_MAX.set(_max_response_time)
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "response_time_error",
            "data": {
                "error": str(e)
            }
        }))

    # Sentiment tracking for bot removed as requested
    
    # Token Usage & LLM Name
    try:
        # Get last interaction
        if cat.working_memory.model_interactions:
            last_interaction = cat.working_memory.model_interactions[-1]
            if last_interaction.model_type == "llm":
                input_tokens = last_interaction.input_tokens
                output_tokens = last_interaction.output_tokens
                
                model_name = _get_llm_name(cat)
                
                # Update Metrics
                LLM_INPUT_TOKENS_TOTAL.labels(model=model_name).inc(input_tokens)
                LLM_OUTPUT_TOKENS_TOTAL.labels(model=model_name).inc(output_tokens)
                
                _update_llm_stats(model_name, input_tokens, output_tokens)
                
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "token_tracking_error",
            "data": {
                "error": str(e)
            }
        }))
        
    return message

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
    data = generate_latest(_registry).decode('utf-8')
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
