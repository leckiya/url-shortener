from typing import Annotated, Optional

from fastapi import Depends
from openai import AsyncOpenAI

from deps.config import Config

openai_client: Optional[AsyncOpenAI] = None


class OpenAIClient:
    client: AsyncOpenAI

    def __init__(self, config: Annotated[Config, Depends(Config)]) -> None:
        self.client = AsyncOpenAI(api_key=config.openai_key)

    async def get_recommendation(self, url: str) -> str:
        chat_completion = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "you are a helpful but brief ai assistant to shorten a url."
                        "you only answer with the suggested identifier for human"
                        "to easily remember."
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "identifier can only container lower and uppercase letter"
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
        return response if response is not None else ""
