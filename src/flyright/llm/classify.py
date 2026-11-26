"""Route a question before answering it.

docs       the available documents can answer it
personal   it needs live information or the user's own private data
off_topic  it is not about this product's subject
"""

import re

from flyright.llm.gateway import LLMGateway, LLMResult

LABELS = ("docs", "personal", "off_topic")


def build_messages(prompt: str, question: str) -> list[dict[str, str]]:
    """Instructions go in the system message; user text is passed as data."""
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"<question>\n{question.strip()}\n</question>"},
    ]


def parse_label(reply: str, labels: tuple[str, ...] = LABELS) -> str:
    """Accept exactly one recognized label; otherwise return invalid."""
    text = reply.strip().lower()
    text = re.sub(r"^off[\s-]+topic$", "off_topic", text)

    return text if text in labels else "invalid"


async def classify(
    gateway: LLMGateway, prompt: str, version: str, question: str
) -> tuple[str, LLMResult]:
    result = await gateway.generate(
        build_messages(prompt, question),
        purpose="classify",
        prompt_version=version,
        temperature=0,
    )
    return parse_label(result.text), result


def accuracy(rows: list[dict]) -> float:
    """Calculate accuracy from rows containing label and got fields."""
    return sum(row["got"] == row["label"] for row in rows) / len(rows) if rows else 0.0


def find_leaks(prompt: str, questions: list[str]) -> list[str]:
    """Find test questions accidentally copied into a prompt."""
    text = " ".join(prompt.lower().split())
    return [question for question in questions if " ".join(question.lower().split()) in text]
