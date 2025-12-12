import time
import subprocess
import sys
from cat.mad_hatter.decorators import hook, endpoint
from cat.log import log
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Global variables for SpaCy models to avoid repeated loading
_spacy_models = {}
_spacy_available = None

def _check_spacy_availability() -> bool:
    """Check if SpaCy is available."""
    global _spacy_available
    if _spacy_available is not None:
        return _spacy_available
    
    try:
        import spacy
        _spacy_available = True
    except ImportError:
        log.warning("SpaCy not installed. Install with: pip install spacy")
        _spacy_available = False
    
    return _spacy_available

def _download_model(model_name: str) -> bool:
    """Download a SpaCy model if not present."""
    try:
        log.info(f"Downloading SpaCy model: {model_name}")
        result = subprocess.run([
            sys.executable, "-m", "spacy", "download", model_name
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            log.info(f"Successfully downloaded {model_name}")
            return True
        else:
            log.error(f"Failed to download {model_name}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"Timeout downloading {model_name}")
        return False
    except Exception as e:
        log.error(f"Error downloading {model_name}: {e}")
        return False

def _get_spacy_model(model_name: str):
    """Get or load a SpaCy model, downloading if necessary."""
    global _spacy_models
    
    if model_name in _spacy_models:
        return _spacy_models[model_name]
    
    if not _check_spacy_availability():
        return None

    try:
        import spacy
        from spacytextblob.spacytextblob import SpacyTextBlob
        from spacy.language import Language
        
        # Register spacytextblob factory if not present (required for some languages/setups)
        if not Language.has_factory("spacytextblob"):
            @Language.factory("spacytextblob")
            def create_spacytextblob(nlp, name):
                return SpacyTextBlob(nlp)
        
        # First try to load the model
        try:
            nlp = spacy.load(model_name)
        except OSError:
            # Model not found, try to download it
            log.info(f"SpaCy model '{model_name}' not found, attempting to download...")
            if _download_model(model_name):
                # Try loading again after download
                try:
                    nlp = spacy.load(model_name)
                    log.info(f"Successfully loaded downloaded model: {model_name}")
                except OSError:
                    log.error(f"Failed to load model '{model_name}' even after download")
                    return None
            else:
                log.error(f"Failed to download model '{model_name}'")
                return None
        
        # Add spacytextblob to the pipeline if not already present
        if "spacytextblob" not in nlp.pipe_names:
            nlp.add_pipe("spacytextblob")
            
        _spacy_models[model_name] = nlp
        log.info(f"Loaded SpaCy model: {model_name} with spacytextblob")
        return nlp

    except ImportError as e:
        log.error(f"Error importing SpaCy or spacytextblob: {e}")
        return None

def analyze_sentiment(text: str):
    """Analyze sentiment using SpaCy + spacytextblob."""
    # Use a multilingual model
    model_name = "xx_sent_ud_sm" 
    nlp = _get_spacy_model(model_name)
    
    if nlp:
        try:
            doc = nlp(text)
            return doc._.blob.polarity
        except Exception as e:
            log.error(f"Error in sentiment analysis: {e}")
            return 0.0
    return 0.0

# Metrics
MESSAGE_COUNTER = Counter('chat_messages_total', 'Total number of messages', ['sender'])
SENTIMENT_SCORE = Histogram('chat_sentiment_score', 'Sentiment score of messages', ['sender'])
NEW_SESSIONS = Counter('chat_sessions_total', 'Total number of new chat sessions')
RAG_DOCUMENTS_RETRIEVED = Counter('rag_documents_retrieved_total', 'Total number of documents retrieved from RAG', ['source'])
AVG_MESSAGES_PER_CHAT = Gauge('chat_messages_per_chat_avg', 'Average number of messages per chat')
MAX_MESSAGES_PER_CHAT = Gauge('chat_messages_per_chat_max', 'Maximum number of messages in a single chat')

# Global state for simple tracking (Note: this resets on restart and grows with unique users)
USER_MESSAGE_COUNTS = {}

@hook
def before_cat_reads_message(user_message_json, cat):
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
            sentiment = analyze_sentiment(text)
            SENTIMENT_SCORE.labels(sender='user').observe(sentiment)
            
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
                RAG_DOCUMENTS_RETRIEVED.labels(source=source).inc()
        except Exception as e:
            log.error(f"Error tracking RAG metrics: {e}")

@hook
def before_cat_sends_message(message, cat):
    settings = cat.mad_hatter.get_plugin().load_settings()

    if settings.get("enable_message_metrics", True):
        # Track bot message
        MESSAGE_COUNTER.labels(sender='bot').inc()

    # Sentiment
    if settings.get("enable_sentiment_metrics", True):
        text = message.get("content", "")
        if text:
            sentiment = analyze_sentiment(text)
            SENTIMENT_SCORE.labels(sender='bot').observe(sentiment)
        
    return message

@endpoint.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
