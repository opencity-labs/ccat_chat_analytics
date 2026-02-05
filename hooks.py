import time
import json
import tiktoken
from cat.mad_hatter.decorators import hook
from cat.log import log
from cat.db import crud
from cat.convo.messages import CatMessage
from .metrics import (
    MESSAGE_COUNTER, BROWSER_LANGUAGE_MESSAGES, SENTIMENT_SCORE, SENTIMENT_COUNTS, NEW_SESSIONS, RAG_DOCUMENTS_RETRIEVED,
    AVG_MESSAGES_PER_CHAT, MAX_MESSAGES_PER_CHAT, LLM_INPUT_TOKENS_TOTAL, LLM_OUTPUT_TOKENS_TOTAL,
    LLM_INPUT_TOKENS_AVG, LLM_OUTPUT_TOKENS_AVG, EMBEDDING_TOKENS_TOTAL, NO_RELEVANT_MEMORY_COUNTER,
    RESPONSE_TIME_SUM, RESPONSE_TIME_COUNT, RESPONSE_TIME_MAX
)
from .sentiment import analyze_sentiment

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

def _get_embedder_name(cat):
    try:
        # Try to get from settings first as it is more reliable for the configured name
        selected_embedder = crud.get_setting_by_name("embedder_selected")
        if selected_embedder:
             config_name = selected_embedder.get("value", {}).get("name")
             if config_name:
                 embedder_settings = crud.get_setting_by_name(config_name)
                 if embedder_settings:
                     vals = embedder_settings.get("value", {})
                     # Check common fields for model name
                     return vals.get("model_name") or vals.get("model") or config_name
        
        # Fallback to inspecting the object
        embedder = cat.embedder
        if hasattr(embedder, "model_name"):
            return embedder.model_name
        if hasattr(embedder, "model"):
            return embedder.model
        return embedder.__class__.__name__
    except:
        return "unknown"

@hook(priority=9)
def before_rabbithole_stores_documents(docs, cat):
    try:
        model_name = _get_embedder_name(cat)
        
        # Count tokens - using tiktoken's cl100k_base as a standard approximation
        # Ideally we'd use the specific tokenizer for the model, but this is a reasonable default
        encoding = None
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
             pass

        for doc in docs:
            text = doc.page_content
            tokens = 0
            try:
                if encoding:
                    tokens = len(encoding.encode(text))
                else:
                    tokens = len(text.split())
            except Exception:
                 # Fallback if tiktoken fails
                 tokens = len(text.split()) 

            EMBEDDING_TOKENS_TOTAL.labels(model=model_name).inc(tokens)
        
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "embedding_token_tracking_error",
            "data": {
                "error": str(e)
            }
        }))
    
    return docs

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

    # Track user message
    MESSAGE_COUNTER.labels(sender='user').inc()

    # Browser language tracking
    info = user_message_json.get('info', {})
    lang = None
    if isinstance(info, dict):
        bl = info.get('browser_lang')
        if bl and isinstance(bl, str):
            lang = bl.split('-')[0].lower()
    elif isinstance(info, str):
        lang = info.split('-')[0].lower()
    if lang:
        BROWSER_LANGUAGE_MESSAGES.labels(lang=lang).inc()

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
    
    # Sentiment tracking
    text = user_message_json.get("text", "")
    if text:
        _track_sentiment('user', text)
            
    return user_message_json

@hook
def after_cat_recalls_memories(cat):
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
