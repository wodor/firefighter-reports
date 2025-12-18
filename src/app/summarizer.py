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
                        "Create a short summary to insert into daily fireghter report.\n"
                        "Summarise this slack request for help to fireghter (person who takes care of urgent tech requests in the organisation) \n"
                        "`<!subteam^S074GEYMPAQ>` - this is the mention of firefigther \n"
                        "`Is it ok for <@user-id> to run the following` is a req for permission to run a script. \n"
                        "Show date in human friendly way YYYY-mm-dd H:i\n"
                        "Format this as slack blocks \n"
                        "Template:\n"
                        "[\n"
                        '  {{ "type": "header", "text": {{ "type": "plain_text", "text": "<Incident Title>", "emoji": true }} }},\n'
                        '  {{ "type": "context", "elements": [ {{ "type": "plain_text", "text": "<YYYY-MM-DD HH:mm>", "emoji": true }} ] }},\n'
                        '  {{ "type": "section", "text": {{ "type": "mrkdwn", "text": "<Incident problem and solution>" }} }},\n'
                        '  {{ "type": "divider" }},\n'
                        '  {{ "type": "context", "elements": [ {{ "type": "mrkdwn", "text": "*Participants:* <Name1, Name2>" }} ] }}\n'
                        "]\n"
                        "Constraints:\n"
                        "Title: Short, clear summary.\n"
                        "Timestamp: human readable YYYY-mm-dd.\n"
                        "Incident problem and solution: Clearly define what was the issue and summarise actions taken to solve it. Use \"Problem:\" and \"Solution:\" paragraph prefixes. Include any links from the thread. Do not loose important details, be concise. Keep it under 120 words\n"
                        "Participants: List by name.\n"
                        "Use only these blocks: header, context, section, divider.\n"
                        "Validate JSON for Slack\n"
                        "return only json"
                    ),
                ),
                (
                    "human",
                    (
                        "Timestamp: {timestamp}\n"
                        "Thread:\n{thread_text}\n\n"
                        "Participants: {participants}\n"
                    ),
                ),
            ]
        )

    def summarize(self, timestamp: str, thread_text: str, participants: List[str]) -> List[Dict[str, Any]]:
        chain = self.prompt | self.llm | self.parser
        raw: str = chain.invoke(
            {
                "timestamp": timestamp,
                "thread_text": thread_text,
                "participants": ", ".join(participants),
            }
        )
        parsed = self._parse_blocks(raw)
        if isinstance(parsed, list):
            return parsed
        return [parsed] if isinstance(parsed, dict) else [
            {"type": "header", "text": {"type": "plain_text", "text": f"Firefighter {timestamp}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": raw.strip()}},
        ]

    @staticmethod
    def _strip_code_fences(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def _parse_blocks(self, raw: str) -> Any:
        text = self._strip_code_fences(raw)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

