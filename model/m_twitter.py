from pydantic import BaseModel, Field


class TwitterNote(BaseModel):
    tweet_id: str = Field(title="Tweet ID")
    user_id: str = Field(title="User ID")
    text: str = Field(title="Tweet text")
    created_at: str = Field(title="Creation time")
