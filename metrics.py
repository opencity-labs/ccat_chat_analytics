from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# Custom registry to avoid global pollution and control output
registry = CollectorRegistry()

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

MESSAGE_COUNTER = Counter('chatbot_chat_messages_total', 'Total number of messages', ['sender'], registry=registry)
# Custom buckets for sentiment polarity (-1 to 1) from spacytextblob
# Buckets: very negative, negative, slightly negative, neutral, slightly positive, positive, very positive
SENTIMENT_SCORE = Histogram('chatbot_chat_sentiment_score', 'Sentiment polarity score of messages from spacytextblob', ['sender'], 
                            buckets=[-1.0, -0.6, -0.2, -0.05, 0.05, 0.2, 0.6, 1.0], registry=registry)
SENTIMENT_COUNTS = Counter('chatbot_chat_sentiment_counts', 'Sentiment counts (negative, neutral, positive)', ['sender', 'type'], registry=registry)

NEW_SESSIONS = Counter('chatbot_chat_sessions_total', 'Total number of new chat sessions', registry=registry)
RAG_DOCUMENTS_RETRIEVED = Counter('chatbot_rag_documents_retrieved_total', 'Total number of documents retrieved from RAG', ['source'], registry=registry)
AVG_MESSAGES_PER_CHAT = Gauge('chatbot_chat_messages_per_chat_avg', 'Average number of messages per chat', registry=registry)
MAX_MESSAGES_PER_CHAT = Gauge('chatbot_chat_messages_per_chat_max', 'Maximum number of messages in a single chat', registry=registry)

LLM_INPUT_TOKENS_TOTAL = Counter('chatbot_llm_input_tokens_total', 'Total input tokens', ['model'], registry=registry)
LLM_OUTPUT_TOKENS_TOTAL = Counter('chatbot_llm_output_tokens_total', 'Total output tokens', ['model'], registry=registry)
LLM_INPUT_TOKENS_AVG = Gauge('chatbot_llm_input_tokens_avg', 'Average input tokens', ['model'], registry=registry)
LLM_OUTPUT_TOKENS_AVG = Gauge('chatbot_llm_output_tokens_avg', 'Average output tokens', ['model'], registry=registry)

EMBEDDING_TOKENS_TOTAL = Counter('chatbot_embedding_tokens_total', 'Total tokens used for embeddings', ['model'], registry=registry)

NO_RELEVANT_MEMORY_COUNTER = Counter('chatbot_chat_no_relevant_memory_total', 'Total number of times no relevant memory was found', registry=registry)

RESPONSE_TIME_SUM = Counter('chatbot_chat_response_time_seconds_sum', 'Sum of response times in seconds', registry=registry)
RESPONSE_TIME_COUNT = Counter('chatbot_chat_response_time_seconds_count', 'Count of responses for average time calculation', registry=registry)
RESPONSE_TIME_MAX = Gauge('chatbot_chat_response_time_seconds_max', 'Maximum response time in seconds', registry=registry)

CHATBOT_INSTANCE_INFO = Gauge('chatbot_instance_info', 'Global version information (Core and Frontend)', ['core_version', 'frontend_version'], registry=registry)
CHATBOT_PLUGIN_INFO = Gauge('chatbot_plugin_info', 'Plugin version information', ['plugin_id', 'version'], registry=registry)

VECTOR_MEMORY_POINTS_TOTAL = Gauge('chatbot_vector_memory_points_total', 'Total number of points in vector memory', ['collection'], registry=registry)
VECTOR_MEMORY_SOURCES_TOTAL = Gauge('chatbot_vector_memory_sources_total', 'Total number of unique sources in vector memory', ['collection'], registry=registry)
