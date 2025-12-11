from cat.mad_hatter.decorators import hook, endpoint
from cat.log import log
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from textblob import TextBlob

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
    text = user_message_json.get("text", "")
    if text:
        try:
            blob = TextBlob(text)
            sentiment = blob.sentiment.polarity
            SENTIMENT_SCORE.labels(sender='user').observe(sentiment)
        except Exception as e:
            log.error(f"Error analyzing sentiment: {e}")
            
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
                RAG_DOCUMENTS_RETRIEVED.labels(source=source).inc()
        except Exception as e:
            log.error(f"Error tracking RAG metrics: {e}")

@hook
def before_cat_sends_message(message, cat):
    # Track bot message
    MESSAGE_COUNTER.labels(sender='bot').inc()

    # Sentiment
    text = message.get("content", "")
    if text:
        try:
            blob = TextBlob(text)
            sentiment = blob.sentiment.polarity
            SENTIMENT_SCORE.labels(sender='bot').observe(sentiment)
        except Exception as e:
            log.error(f"Error analyzing sentiment: {e}")
        
    return message

@endpoint.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
