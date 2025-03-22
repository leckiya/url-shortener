import json
from typing import Annotated, List, Optional

from fastapi import Depends
from openai import AsyncOpenAI
from pydantic import BaseModel

from deps.config import Config

openai_client: Optional[AsyncOpenAI] = None


class Suggestion(BaseModel):
    key: str
    reason: str
    score: float


class OpenAIClient:
    client: AsyncOpenAI

    def __init__(self, config: Annotated[Config, Depends(Config)]) -> None:
        self.client = AsyncOpenAI(api_key=config.openai_key)

    async def get_recommendation(self, url: str) -> List[Suggestion]:
        chat_completion = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "you are a helpful but brief ai assistant to shorten a url."
                        "you only answer with the suggested identifier for human"
                        "to easily remember and the reason you choose that identifier."
                        "consider the content of the website."
                        "give 3 suggestions."
                        "the score is from 0 to 10"
                        "the json respose format is: "
                        '[{"key": <identifier>, "reason": <reason>, "score": <score>}]'
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "identifier can only contain lower and uppercase letter"
                    ),
                },
                {
                    "role": "user",
                    "content": f"what is the best identifier for this url? {url}",
                },
            ],
            temperature=1,
            model="gpt-4o-mini",
        )

        response = chat_completion.choices[0].message.content
        if response is None:
            return []

        response = json.loads(response)
        return list(map(lambda s: Suggestion(**s), response))
