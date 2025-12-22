# Chat Analytics

[![Chat Analytics](https://custom-icon-badges.demolab.com/static/v1?label=&message=awesome+plugin&color=F4F4F5&style=for-the-badge&logo=cheshire_cat_black)](https://)

A comprehensive analytics plugin for the Cheshire Cat AI that exposes Prometheus metrics about chat usage, sentiment, token usage, and RAG performance.

## Description

**Chat Analytics** integrates the Cheshire Cat with Prometheus to provide real-time insights into how your chatbot is being used. It tracks message volume, user sentiment, session statistics, token usage, and document retrieval usage.

This plugin is essential for monitoring the health, engagement, and quality of your AI service.

## Features

- **Prometheus Endpoint**: Exposes a `/custom/metrics` endpoint compatible with Prometheus.
- **Sentiment Analysis**: Automatically analyzes the sentiment of user messages using a multilingual Transformer model.
- **Token Usage**: Tracks input and output tokens per LLM model.
- **RAG Tracking**: Tracks which documents are being retrieved from memory (with source clustering).
- **Session Stats**: Monitors active sessions and message depth.

## Metrics Explained

Detailed breakdown of the metrics exposed by this plugin:

### 1. Message Volume
**Metric Name:** `chat_messages_total`
**Type:** Counter
**Labels:** 
- `sender`: Who sent the message (`user`).

**Description:**
Counts the total number of messages sent by users.

### 2. Sentiment Analysis
**Metric Name:** `chat_sentiment_score`
**Type:** Histogram
**Labels:** 
- `sender`: Who sent the message (`user`).

**Description:**
Measures the sentiment polarity of messages (-1.0 to 1.0). Used to calculate average sentiment.

**Metric Name:** `chat_sentiment_counts`
**Type:** Counter
**Labels:**
- `sender`: Who sent the message (`user`).
- `type`: Sentiment category (`happy`, `sad`, `neutral`).

**Description:**
Counts the number of messages falling into each sentiment category:
- **Sad**: Score < -0.2
- **Neutral**: -0.2 <= Score <= 0.2
- **Happy**: Score > 0.2

**How it works:**
This plugin uses the `lxyuan/distilbert-base-multilingual-cased-sentiments-student` Transformer model. It is a lightweight, multilingual model optimized for CPU usage.

### 3. Token Usage
**Metric Name:** `llm_input_tokens_total` / `llm_output_tokens_total`
**Type:** Counter
**Labels:**
- `model`: The name of the LLM model used.

**Description:**
Total number of tokens sent to (input) and received from (output) the LLM.

**Metric Name:** `llm_input_tokens_avg` / `llm_output_tokens_avg`
**Type:** Gauge
**Labels:**
- `model`: The name of the LLM model used.

**Description:**
Average number of tokens per interaction.

### 4. New Sessions
**Metric Name:** `chat_sessions_total`
**Type:** Counter

**Description:**
Counts the number of unique users/sessions that have started a conversation since the last restart.

### 5. RAG Usage
**Metric Name:** `rag_documents_retrieved_total`
**Type:** Counter
**Labels:** 
- `source`: The source metadata of the retrieved document (clustered by path).

**Description:**
Tracks how often documents are retrieved from the vector memory. Sources are clustered (e.g., `example.com/services/s1` -> `example.com/services`) to provide better aggregation.

### 6. Conversation Depth
**Metric Name:** `chat_messages_per_chat_avg`
**Type:** Gauge

**Description:**
The average number of messages per chat session (since restart).

**Metric Name:** `chat_messages_per_chat_max`
**Type:** Gauge

**Description:**
The maximum number of messages in a single chat session.

## Configuration

You can enable or disable specific groups of metrics via the Cheshire Cat Admin UI:

- **Enable Message Metrics**: Tracks total messages, sessions, and conversation depth.
- **Enable Sentiment Analysis**: Tracks sentiment of messages.
- **Enable RAG Metrics**: Tracks retrieved documents from memory.

## Requirements

- Cheshire Cat AI
- Prometheus (for data collection)
- Grafana (recommended for visualization)
- `transformers` and `torch` python packages (installed automatically if missing, but recommended to pre-install).

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
| `import_error` | Logged when transformers/torch are missing | `message` |
| `model_load_start` | Logged when starting to load the model | `model_name` |
| `model_load_success` | Logged when model is successfully loaded | `model_name` |
| `model_load_error` | Logged when model load fails | `error` |
| `sentiment_analysis_error` | Logged when sentiment analysis fails | `error` |
| `rag_metrics_error` | Logged when RAG metrics tracking fails | `error` |
| `token_tracking_error` | Logged when token tracking fails | `error` |

---

Author: OpenCity Labs

LinkedIn: https://www.linkedin.com/company/opencity-italia/

