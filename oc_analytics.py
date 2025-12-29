import time
import json
import os
import tomli
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.decorators import hook, endpoint
from cat.log import log
from cat.db import crud
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry

from cat.convo.messages import CatMessage

# Global variables for Transformers pipeline
_sentiment_pipeline = None

def _get_sentiment_pipeline():
    """Get or load the Transformers sentiment pipeline."""
    global _sentiment_pipeline
    if _sentiment_pipeline:
        return _sentiment_pipeline
        
    try:
        from transformers import pipeline
        # Use a distilled multilingual model for better CPU performance
        # lxyuan/distilbert-base-multilingual-cased-sentiments-student
        # ~540MB, supports many languages, faster than BERT
        model_name = "lxyuan/distilbert-base-multilingual-cased-sentiments-student"
        
        log.info(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_load_start",
            "data": {
                "model_name": model_name
            }
        }))
        
        _sentiment_pipeline = pipeline("sentiment-analysis", model=model_name, top_k=None)
        
        log.info(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_load_success",
            "data": {
                "model_name": model_name
            }
        }))
        return _sentiment_pipeline

    except ImportError:
        log.warning(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "import_error",
            "data": {
                "message": "Transformers or Torch not installed. Install with: pip install transformers torch"
            }
        }))
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
    """Analyze sentiment using Transformers (Multilingual)."""
    pipe = _get_sentiment_pipeline()
    
    if pipe:
        try:
            # Truncate text to avoid token limit errors (DistilBERT limit is 512 tokens)
            # Using char limit as rough proxy to avoid tokenization overhead just for check
            if len(text) > 2000:
                text = text[:2000]
                
            results = pipe(text)
            # results is [[{'label': 'positive', 'score': 0.9}, ...]]
            
            scores = {r['label']: r['score'] for r in results[0]}
            
            # Calculate weighted score (-1 to 1)
            pos = scores.get('positive', 0.0)
            neg = scores.get('negative', 0.0)
            
            # Result is positive score minus negative score
            return pos - neg
            
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

# Metrics
MESSAGE_COUNTER = Counter('chat_messages_total', 'Total number of messages', ['sender'], registry=_registry)
# Custom buckets for sentiment (-1 to 1)
SENTIMENT_SCORE = Histogram('chat_sentiment_score', 'Sentiment score of messages', ['sender'], 
                            buckets=[-1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0], registry=_registry)
SENTIMENT_COUNTS = Counter('chat_sentiment_counts', 'Sentiment counts (sad, neutral, happy)', ['sender', 'type'], registry=_registry)

NEW_SESSIONS = Counter('chat_sessions_total', 'Total number of new chat sessions', registry=_registry)
RAG_DOCUMENTS_RETRIEVED = Counter('rag_documents_retrieved_total', 'Total number of documents retrieved from RAG', ['source'], registry=_registry)
AVG_MESSAGES_PER_CHAT = Gauge('chat_messages_per_chat_avg', 'Average number of messages per chat', registry=_registry)
MAX_MESSAGES_PER_CHAT = Gauge('chat_messages_per_chat_max', 'Maximum number of messages in a single chat', registry=_registry)

LLM_INPUT_TOKENS_TOTAL = Counter('llm_input_tokens_total', 'Total input tokens', ['model'], registry=_registry)
LLM_OUTPUT_TOKENS_TOTAL = Counter('llm_output_tokens_total', 'Total output tokens', ['model'], registry=_registry)
LLM_INPUT_TOKENS_AVG = Gauge('llm_input_tokens_avg', 'Average input tokens', ['model'], registry=_registry)
LLM_OUTPUT_TOKENS_AVG = Gauge('llm_output_tokens_avg', 'Average output tokens', ['model'], registry=_registry)

NO_RELEVANT_MEMORY_COUNTER = Counter('chat_no_relevant_memory_total', 'Total number of times no relevant memory was found', registry=_registry)

RESPONSE_TIME_SUM = Counter('chat_response_time_seconds_sum', 'Sum of response times in seconds', registry=_registry)
RESPONSE_TIME_COUNT = Counter('chat_response_time_seconds_count', 'Count of responses for average time calculation', registry=_registry)
RESPONSE_TIME_MAX = Gauge('chat_response_time_seconds_max', 'Maximum response time in seconds', registry=_registry)

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
    sentiment = analyze_sentiment(text)
    SENTIMENT_SCORE.labels(sender=sender).observe(sentiment)
    
    sentiment_type = "neutral"
    if sentiment < -0.2:
        sentiment_type = "sad"
    elif sentiment > 0.2:
        sentiment_type = "happy"
        
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
