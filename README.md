# Chat Analytics

[![Chat Analytics](https://custom-icon-badges.demolab.com/static/v1?label=&message=awesome+plugin&color=F4F4F5&style=for-the-badge&logo=cheshire_cat_black)](https://)

A comprehensive analytics plugin for the Cheshire Cat AI that exposes Prometheus metrics about chat usage, sentiment, token usage, and RAG performance.

## Description

**Chat Analytics** integrates the Cheshire Cat with Prometheus to provide real-time insights into how your chatbot is being used. It tracks message volume, user sentiment, session statistics, token usage, and document retrieval usage.

This plugin is essential for monitoring the health, engagement, and quality of your AI service.

## Features

- **Prometheus Endpoint**: Exposes a `/custom/metrics` endpoint compatible with Prometheus.
- **Sentiment Analysis**: Automatically analyzes the sentiment of user messages using spaCy with multilingual support.
- **Token Usage**: Tracks input and output tokens per LLM model.
- **RAG Tracking**: Tracks which documents are being retrieved from memory (with source clustering).
- **Response Time**: Tracks average and max response times (excluding default messages).
- **Missed Context**: Tracks when no relevant memory is found (requires Context Guardian).
- **Session Stats**: Monitors active sessions and message depth.

## Metrics Explained

Detailed breakdown of the metrics exposed by this plugin:

### 1. Message Volume
**Metric Name:** `chatbot_chat_messages_total`
**Type:** Counter
**Labels:** 
- `sender`: Who sent the message (`user`).

**Description:**
Counts the total number of messages sent by users.

### 2. Sentiment Analysis
**Metric Name:** `chatbot_chat_sentiment_score`
**Type:** Histogram
**Labels:** 
- `sender`: Who sent the message (`user`).

**Description:**
Measures the sentiment polarity of messages (-1.0 to 1.0). Used to calculate average sentiment.

**Metric Name:** `chatbot_chat_sentiment_counts`
**Type:** Counter
**Labels:**
- `sender`: Who sent the message (`user`).
- `type`: Sentiment category (`positive`, `neutral`, `negative`).

**Description:**
Counts the number of messages falling into each sentiment category:
- **Negative**: Polarity < -0.05
- **Neutral**: -0.05 <= Polarity <= 0.05
- **Positive**: Polarity > 0.05

**How it works:**
This plugin uses spaCy with the `xx_sent_ud_sm` multilingual model and `spacytextblob` for sentiment analysis. The model provides polarity scores ranging from -1 (very negative) to 1 (very positive), making it lightweight and efficient for CPU usage across multiple languages.

### 3. Token Usage
**Metric Name:** `chatbot_llm_input_tokens_total` / `chatbot_llm_output_tokens_total`
**Type:** Counter
**Labels:**
- `model`: The name of the LLM model used.

**Description:**
Total number of tokens sent to (input) and received from (output) the LLM.

**Metric Name:** `chatbot_llm_input_tokens_avg` / `chatbot_llm_output_tokens_avg`
**Type:** Gauge
**Labels:**
- `model`: The name of the LLM model used.

**Description:**
Average number of tokens per interaction.

### 4. New Sessions
**Metric Name:** `chatbot_chat_sessions_total`
**Type:** Counter

**Description:**
Counts the number of unique users/sessions that have started a conversation since the last restart.

### 5. RAG Usage
**Metric Name:** `chatbot_rag_documents_retrieved_total`
**Type:** Counter
**Labels:** 
- `source`: The source metadata of the retrieved document (clustered by path).

**Description:**
Tracks how often documents are retrieved from the vector memory. Sources are clustered (e.g., `example.com/services/s1` -> `example.com/services`) to provide better aggregation.

### 6. Conversation Depth
**Metric Name:** `chatbot_chat_messages_per_chat_avg`
**Type:** Gauge

**Description:**
The average number of messages per chat session (since restart).

**Metric Name:** `chatbot_chat_messages_per_chat_max`
**Type:** Gauge

**Description:**
The maximum number of messages in a single chat session.
**Type:** Gauge

**Description:**
The maximum number of messages in a single chat session.

### 7. Response Time
**Metric Name:** `chatbot_chat_response_time_seconds_sum` / `chatbot_chat_response_time_seconds_count`
**Type:** Counter

**Description:**
Used to calculate the average response time of the bot (excluding fast replies/default messages).
*Example Query:* `rate(chatbot_chat_response_time_seconds_sum[1h]) / rate(chatbot_chat_response_time_seconds_count[1h])`

**Metric Name:** `chatbot_chat_response_time_seconds_max`
**Type:** Gauge

**Description:**
The maximum response time recorded.

### 8. Missed Context
**Metric Name:** `chatbot_chat_no_relevant_memory_total`
**Type:** Counter

**Description:**
Counts how many times the bot could not find relevant memories and sent the default fallback message (requires `ccat_context_guardian_enricher`).

### 9. Version Info
**Metric Name:** `chatbot_instance_info`
**Type:** Gauge
**Labels:**
- `core_version`: The version of the Cheshire Cat Core.
- `frontend_version`: The version of the Admin UI (if available).

**Description:**
Tracks the version of the running instance. Always set to 1.

**Metric Name:** `chatbot_plugin_info`
**Type:** Gauge
**Labels:**
- `plugin_id`: The ID of the plugin.
- `version`: The version of the plugin.

**Description:**
Tracks the version of all installed plugins. Always set to 1.

## Configuration

You can enable or disable specific groups of metrics via the Cheshire Cat Admin UI:

- **Enable Message Metrics**: Tracks total messages, sessions, and conversation depth.
- **Enable Sentiment Analysis**: Tracks sentiment of messages.
- **Enable RAG Metrics**: Tracks retrieved documents from memory.

## Requirements

- Cheshire Cat AI
- Prometheus (for data collection)
- Grafana (recommended for visualization)
- `spacy` and `spacytextblob` python packages (installed automatically if missing, but recommended to pre-install).
- spaCy language model `xx_sent_ud_sm` (automatically downloaded on first use).

## Log Schema

This plugin uses structured JSON logging to facilitate monitoring and debugging. All logs follow this base structure:

```json
{
  "component": "ccat_oc_analytics",
  "event": "<event_name>",
  "data": {
    ... <event_specific_data>
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
| `token_tracking_error` | Logged when token tracking fails | `error` |
| `response_time_error` | Logged when response time tracking fails | `error` |
| `fast_reply_check_error` | Logged when checking for fast reply fails | `error` |
| `core_version_error` | Logged when core version retrieval fails | `error` |
| `plugin_version_error` | Logged when plugin version retrieval fails | `error` |

---

Author: OpenCity Labs

LinkedIn: https://www.linkedin.com/company/opencity-italia/

