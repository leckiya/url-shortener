from typing import Optional

from openai import AsyncOpenAI

from deps.config import get_config
from log import logger

openai_client: Optional[AsyncOpenAI] = None


def set_client(new_openai_client: AsyncOpenAI):
    global openai_client
    openai_client = new_openai_client


def get_client() -> AsyncOpenAI:
    global openai_client
    if openai_client is None:
        logger.info("initializing openai client")
        config = get_config()
        openai_client = AsyncOpenAI(api_key=config.openai_key)

    return openai_client


async def get_recommendation(url: str) -> str:
    client = get_client()

    chat_completion = await client.chat.completions.create(
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
                "content": "identifier can only container lower and uppercase letter",
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
