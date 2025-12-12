from pydantic import BaseModel, Field
from cat.mad_hatter.decorators import plugin

class AnalyticsSettings(BaseModel):
    enable_message_metrics: bool = Field(
        title="Enable Message Metrics",
        default=True,
        description="Track total messages, sessions, and conversation depth."
    )
    enable_sentiment_metrics: bool = Field(
        title="Enable Sentiment Analysis",
        default=True,
        description="Analyze and track sentiment of messages (requires TextBlob)."
    )
    enable_rag_metrics: bool = Field(
        title="Enable RAG Metrics",
        default=True,
        description="Track retrieved documents from memory."
    )

@plugin
def settings_model():
    return AnalyticsSettings
