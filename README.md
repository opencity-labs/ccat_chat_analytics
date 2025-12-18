# Chat Analytics

[![Chat Analytics](https://custom-icon-badges.demolab.com/static/v1?label=&message=awesome+plugin&color=F4F4F5&style=for-the-badge&logo=cheshire_cat_black)](https://)

A comprehensive analytics plugin for the Cheshire Cat AI that exposes Prometheus metrics about chat usage, sentiment, and RAG performance.

## Description

**Chat Analytics** integrates the Cheshire Cat with Prometheus to provide real-time insights into how your chatbot is being used. It tracks message volume, user sentiment, session statistics, and document retrieval usage.

This plugin is essential for monitoring the health, engagement, and quality of your AI service.

## Features

- **Prometheus Endpoint**: Exposes a `/custom/metrics` endpoint compatible with Prometheus.
- **Sentiment Analysis**: Automatically analyzes the sentiment of both user and bot messages.
- **RAG Tracking**: Tracks which documents are being retrieved from memory.
- **Session Stats**: Monitors active sessions and message depth.

## Metrics Explained

Detailed breakdown of the metrics exposed by this plugin:

### 1. Message Volume
**Metric Name:** `chat_messages_total`
**Type:** Counter
**Labels:** 
- `sender`: Who sent the message (`user` or `bot`).

**Description:**
Counts the total number of messages exchanged. Use this to track overall traffic and load.
*Example Query:* `sum(rate(chat_messages_total[5m]))` to see message rate.

### 2. Sentiment Analysis
**Metric Name:** `chat_sentiment_score`
**Type:** Histogram
**Labels:** 
- `sender`: Who sent the message.

**Description:**
Measures the sentiment polarity of messages.

**How it works:**
This plugin uses [spaCy](https://spacy.io/) with the `xx_sent_ud_sm` multilingual model and the `spacytextblob` pipeline. It automatically downloads the necessary model on the first run. This allows for sentiment analysis across multiple languages, not just English.

**Interpreting the Score:**
The score is a float value ranging from **-1.0** to **1.0**:
- **-1.0**: Very Negative (e.g., "This is terrible", "I hate this")
- **0.0**: Neutral (e.g., "The sky is blue", "What time is it?")
- **+1.0**: Very Positive (e.g., "This is amazing", "I love this")

*Example Query:* `histogram_quantile(0.5, sum(rate(chat_sentiment_score_bucket[1h])) by (le))` to see the median sentiment over time.

### 3. New Sessions
**Metric Name:** `chat_sessions_total`
**Type:** Counter

**Description:**
Counts the number of unique users/sessions that have started a conversation since the last restart.
*Example Query:* `increase(chat_sessions_total[1d])` to see daily active users.

### 4. RAG Usage
**Metric Name:** `rag_documents_retrieved_total`
**Type:** Counter
**Labels:** 
- `source`: The source metadata of the retrieved document.

**Description:**
Tracks how often documents are retrieved from the vector memory. This helps identify which knowledge base sources are most useful.
*Example Query:* `topk(5, sum(rate(rag_documents_retrieved_total[1h])) by (source))` to see the top 5 most used sources.

### 5. Conversation Depth
**Metric Name:** `chat_messages_per_chat_avg`
**Type:** Gauge

**Description:**
The average number of messages per chat session (since restart). High numbers indicate engaging conversations.

### 6. Max Conversation Depth
**Metric Name:** `chat_messages_per_chat_max`
**Type:** Gauge

**Description:**
The maximum number of messages in a single chat session.

## Configuration

You can enable or disable specific groups of metrics via the Cheshire Cat Admin UI:

- **Enable Message Metrics**: Tracks total messages, sessions, and conversation depth.
- **Enable Sentiment Analysis**: Tracks sentiment of messages (uses `spaCy` multilingual model).
- **Enable RAG Metrics**: Tracks retrieved documents from memory.

## Requirements

- Cheshire Cat AI
- Prometheus (for data collection)
- Grafana (recommended for visualization)

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
| `spacy_check` | Logged when checking for SpaCy availability | `available` |
| `model_download_start` | Logged when starting to download a SpaCy model | `model_name` |
| `model_download_success` | Logged when a SpaCy model is successfully downloaded | `model_name` |
| `model_download_error` | Logged when a SpaCy model download fails | `model_name`, `error` |
| `model_load_success` | Logged when a SpaCy model is successfully loaded | `model_name` |
| `model_load_error` | Logged when a SpaCy model load fails | `model_name`, `error` |
| `sentiment_analysis_error` | Logged when sentiment analysis fails | `error` |
| `rag_metrics_error` | Logged when RAG metrics tracking fails | `error` |

---

Author: OpenCity Labs

LinkedIn: https://www.linkedin.com/company/opencity-italia/

