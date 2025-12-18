import json
from typing import Any, Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


class Summarizer:
    def __init__(self, api_key: str, model: str) -> None:
        self.llm = ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=0.2,
        )
        self.parser = StrOutputParser()
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Summarize Slack firefighter threads. Return ONLY JSON array of Slack "
                        "blocks (header/context/section/divider). Keep title short, include date "
                        "YYYY-MM-DD, keep recap concise with bold or code spans as needed, list "
                        "participants by name. Validate JSON; do not wrap in markdown."
                    ),
                ),
                (
                    "human",
                    (
                        "Timestamp: {timestamp}\n"
                        "Thread:\n{thread_text}\n\n"
                        "Participants: {participants}\n"
                        "Constraints: Keep summary under 120 words."
                    ),
                ),
            ]
        )

    def summarize(self, timestamp: str, thread_text: str, participants: List[str]) -> List[Dict[str, Any]]:
        chain = self.prompt | self.llm | self.parser
        raw = chain.invoke(
            {
                "timestamp": timestamp,
                "thread_text": thread_text,
                "participants": ", ".join(participants),
            }
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [
                {"type": "header", "text": {"type": "plain_text", "text": f"Firefighter {timestamp}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": raw.strip()}},
            ]
        if isinstance(parsed, list):
            return parsed
        return [parsed] if isinstance(parsed, dict) else []

