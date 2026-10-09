"""
Data models for ingested raw text streams.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

class RawTextItem(BaseModel):
    """
    Represents an unstructured text record ingested from a news feed,
    corporate announcement, or social media post.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str = Field(..., description="'news', 'social', or 'announcement'")
    title: str = Field(..., description="Headline or title")
    text: str = Field(..., description="Full article summary or social post body")
    url: Optional[str] = Field(default=None, description="Original source link")
    author: Optional[str] = Field(default=None, description="Author, handle, or publication")
    published_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    target_ticker: Optional[str] = Field(default=None, description="Pre-identified or resolved ticker")

class IngestionBatch(BaseModel):
    """A batch of ingested raw items ready for NLP processing."""
    source_type: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    items: List[RawTextItem]
