# Chat Analytics

[![Chat Analytics](https://custom-icon-badges.demolab.com/static/v1?label=&message=awesome+plugin&color=F4F4F5&style=for-the-badge&logo=cheshire_cat_black)](https://)

A comprehensive analytics plugin for the Cheshire Cat AI that exposes Prometheus metrics about chat usage, sentiment, token usage, and RAG performance.

## Description

**Chat Analytics** integrates the Cheshire Cat with Prometheus to provide real-time insights into how your chatbot is being used. It tracks message volume, user sentiment, session statistics, token usage, and document retrieval usage. All metrics are automatically enabled and collected without any configuration needed.

This plugin is essential for monitoring the health, engagement, and quality of your AI service.

## Features

- **Zero Configuration**: All metrics are automatically collected without any setup required.
- **Prometheus Endpoint**: Exposes a `/custom/metrics` endpoint compatible with Prometheus.
- **Sentiment Analysis**: Automatically analyzes the sentiment of user messages using spaCy with multilingual support. --> *in development*
- **Token Usage**: Tracks input and output tokens per LLM model.
- **RAG Tracking**: Tracks which documents are being retrieved from memory (with source clustering).
- **Memory Stats**: Tracks total points and unique sources stored in vector memory.
- **Response Time**: Tracks average and max response times (excluding default messages).
- **Missed Context**: Tracks when no relevant memory is found (requires Context Guardian).
- **Session Stats**: Monitors active sessions and message depth.
- **Version Tracking**: Monitors Core and plugin versions for deployment tracking.

## Metrics Explained

All metrics exposed by this plugin:

| Category | Metric Name | Type | Labels | Description |
|----------|-------------|------|--------|-------------|
| **Messages** | `chatbot_chat_messages_total` | Counter | `sender` (user) | Total messages sent by users |
| **Messages** | `chatbot_chat_messages_by_browser_language_total` | Counter | `lang` | Count of incoming messages grouped by browser language (e.g., `en`, `es`) |
| **Sessions** | `chatbot_chat_sessions_total` | Counter | - | Unique users/sessions since restart |
| **Conversation Depth** | `chatbot_chat_messages_per_chat_avg` | Gauge | - | Average messages per chat session |
| **Conversation Depth** | `chatbot_chat_messages_per_chat_max` | Gauge | - | Maximum messages in a single session |
| **Sentiment** | `chatbot_chat_sentiment_score` | Histogram | `sender` (user) | Sentiment polarity (-1.0 to 1.0) for calculating averages |
| **Sentiment** | `chatbot_chat_sentiment_counts` | Counter | `sender` (user), `type` (positive/neutral/negative) | Count of messages by sentiment category |
| **Tokens** | `chatbot_llm_input_tokens_total` | Counter | `model` | Total input tokens sent to LLM |
| **Tokens** | `chatbot_llm_output_tokens_total` | Counter | `model` | Total output tokens received from LLM |
| **Tokens** | `chatbot_llm_input_tokens_avg` | Gauge | `model` | Average input tokens per interaction |
| **Tokens** | `chatbot_llm_output_tokens_avg` | Gauge | `model` | Average output tokens per interaction |
| **Tokens** | `chatbot_embedding_tokens_total` | Counter | `model` | Total tokens used for embeddings |
| **RAG** | `chatbot_rag_documents_retrieved_total` | Counter | `source` (clustered path) | Documents retrieved from vector memory |
| **Response Time** | `chatbot_chat_response_time_seconds_sum` | Counter | - | Sum of response times (for calculating average) |
| **Response Time** | `chatbot_chat_response_time_seconds_count` | Counter | - | Count of responses (for calculating average) |
| **Response Time** | `chatbot_chat_response_time_seconds_max` | Gauge | - | Maximum response time recorded |
| **Context** | `chatbot_chat_no_relevant_memory_total` | Counter | - | Times no relevant memory found (requires Context Guardian) |
| **Version** | `chatbot_instance_info` | Gauge | `core_version`, `frontend_version` | Core and frontend version info (always 1) |
| **Version** | `chatbot_plugin_info` | Gauge | `plugin_id`, `version` | Plugin version info (always 1) |
| **Memory** | `chatbot_vector_memory_points_total` | Gauge | `collection` | Total points in vector memory |
| **Memory** | `chatbot_vector_memory_sources_total` | Gauge | `collection` | Unique sources in vector memory (declarative only) |
| **Feedback** | `chatbot_feedback_thumb_up_total` | Counter | - | Total positive feedback (thumbs up) |
| **Feedback** | `chatbot_feedback_thumb_down_total` | Counter | - | Total negative feedback (thumbs down) |

### Notes

**Sentiment Analysis**: Uses spaCy's `xx_sent_ud_sm` multilingual model with `spacytextblob` for polarity scoring. Only user messages are analyzed. Categories:
- **Negative**: polarity < -0.05
- **Neutral**: -0.05 ≤ polarity ≤ 0.05  
- **Positive**: polarity > 0.05

**RAG Source Clustering**: Sources are automatically clustered for better aggregation (e.g., `example.com/services/s1` → `example.com/services`)

**Response Time**: Excludes fast replies and default messages. Calculate average with: `rate(chatbot_chat_response_time_seconds_sum[1h]) / rate(chatbot_chat_response_time_seconds_count[1h])`

## Feedback Endpoint

The plugin exposes a `/thumbup` POST endpoint to collect user feedback. This endpoint is designed to work with the `ccat_temporary_chat_authentication` plugin.

**Request:**
- **URL**: `/custom/thumbup`
- **Method**: `POST`
- **Headers**: 
  - `Authorization`: Bearer `<jwt_token_from_temp_auth>`
  - `Content-Type`: `application/json`
- **Body**:
  ```json
  {
      "value": true
  }
  ```
  *(Send `true` for positive feedback, `false` or omit for negative)*

**Validation**:
- The JWT token must be valid and signed by the Cat's configured secret.
- The user ID in the token must start with the `session_prefix` configured in `ccat_temporary_chat_authentication`.

## Requirements

- Cheshire Cat AI
- Prometheus (for data collection)
- Grafana (recommended for visualization)
- Python packages: `spacy`, `spacytextblob`, and `tomli` (automatically installed with the plugin)
- spaCy language model `xx_sent_ud_sm` (automatically downloaded on first use)

## Installation

1. Install the plugin through the Cheshire Cat Admin UI
2. The plugin will automatically start collecting metrics
3. Configure Prometheus to scrape the `/custom/metrics` endpoint
4. (Optional) Set up Grafana dashboards to visualize the metrics

## Log Schema

This plugin uses structured JSON logging to facilitate monitoring and debugging. All logs follow this base structure:

```json
{
  "component": "ccat_oc_analytics",
  "event": "<event_name>",
  "data": {
    // Event-specific data fields
  }
}
```


### Event Types

| Event Name | Description | Data Fields |
|------------|-------------|-------------|
| `import_error` | Logged when spacy/spacytextblob are missing | `message` |
| `model_load_start` | Logged when starting to load the spaCy model | `model_name` |
| `model_load_success` | Logged when model is successfully loaded | `model_name` |
| `model_download_start` | Logged when starting to download the spaCy model | `model_name` |
| `model_download_success` | Logged when model download completes | `model_name` |
| `model_download_error` | Logged when model download fails | `model_name`, `error` |
| `model_download_timeout` | Logged when model download times out | `model_name` |
| `model_not_found` | Logged when model not found locally | `model_name`, `message` |
| `sentiment_component_added` | Logged when spacytextblob component is added to pipeline | `model_name` |
| `spacytextblob_not_found` | Logged when spacytextblob is not installed | `message` |
| `sentiment_analysis_error` | Logged when sentiment analysis fails | `error` |
| `rag_metrics_error` | Logged when RAG metrics tracking fails | `error` |
| `embedding_token_tracking_error` | Logged when embedding token tracking fails | `error` |
| `token_tracking_error` | Logged when token tracking fails | `error` |
| `response_time_error` | Logged when response time tracking fails | `error` |
| `fast_reply_check_error` | Logged when checking for fast reply fails | `error` |
| `core_version_error` | Logged when core version retrieval fails | `error` |
| `plugin_version_error` | Logged when plugin version retrieval fails | `error` |
| `memory_metrics_collection_error` | Logged when memory stats collection fails for a specific collection | `collection`, `error` |
| `memory_metrics_error` | Logged when memory stats update fails globally | `error` |

---

Author: OpenCity Labs

LinkedIn: https://www.linkedin.com/company/opencity-italia/

