from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages import ToolMessage as LCToolMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

import os
import re
import time

from google.genai.errors import ServerError

from app.config import settings

# Transient Gemini failures (503 high-demand / overloaded) are retried with backoff.
_LLM_MAX_ATTEMPTS = 3
_LLM_BACKOFF_SECONDS = 1.5


def _friendly_title(filename: str) -> str:
    """Turn a raw filename into a human-readable title for end users.

    e.g. "how-to-rebuild-trust-in-a-relationship.md" -> "How To Rebuild Trust In A Relationship"
    """
    stem = os.path.splitext(filename)[0]
    words = stem.replace("-", " ").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words) if words else filename

def _extract_citations(answer: str) -> tuple[str, set[int] | None]:
    """Strip the trailing "CITATIONS: ..." line and return (clean_answer, cited_ids).

    Returns cited_ids=None when no CITATIONS line is present (model didn't comply),
    an empty set for "CITATIONS: none", or the set of cited numbers otherwise.
    """
    matches = list(_CITATION_RE.finditer(answer))
    if not matches:
        return answer.strip(), None
    last = matches[-1]
    ids = {int(n) for n in re.findall(r"\d+", last.group(1))}
    clean = (answer[: last.start()] + answer[last.end():]).strip()
    return clean, ids


_SYSTEM_PROMPT = (
    "You are a helpful virtual assistant. Answer questions using ONLY the information "
    "from the provided tools. If you cannot find the answer in the available context, "
    "say \"I don't have information about that.\" "
    "Write a clean, conversational answer for an end user on a website chat widget. "
    "Do NOT mention document names, file names, file extensions, or page numbers in your "
    "answer — the source documents are tracked and shown separately by the application. "
    "Each search result is labelled with a citation number like [1], [2]. After your "
    "answer, on a separate final line, list ONLY the citation numbers of the results you "
    "actually used to write the answer, in the exact format: CITATIONS: 1, 3. If you used "
    "no search results, write: CITATIONS: none. Do not put citation numbers anywhere else."
)

# Matches the trailing "CITATIONS: 1, 3" / "CITATIONS: none" line the model is told to emit.
_CITATION_RE = re.compile(r"(?im)^\s*CITATIONS:\s*(.*?)\s*$")


def build_agent(tools: list[BaseTool]) -> Any:
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0,
    )
    return create_react_agent(llm, tools, prompt=_SYSTEM_PROMPT)


def run_agent(
    executor: Any,
    message: str,
    history: list[dict],
) -> dict:
    messages: list[Any] = []
    for turn in history:
        messages.append(HumanMessage(content=turn["human"]))
        messages.append(AIMessage(content=turn["assistant"]))
    messages.append(HumanMessage(content=message))

    result = None
    for attempt in range(_LLM_MAX_ATTEMPTS):
        try:
            result = executor.invoke({"messages": messages})
            break
        except ServerError:
            if attempt == _LLM_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_LLM_BACKOFF_SECONDS * (attempt + 1))

    output = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            if isinstance(content, list):
                output = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            else:
                output = content
            break

    # Map every retrieved chunk to its turn-unique citation id [N].
    tools_used: list[str] = []
    by_id: dict[int, dict] = {}
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
        if isinstance(msg, LCToolMessage) and msg.name == "search_documents":
            for block in str(msg.content).split("---"):
                if "[Source:" not in block:
                    continue
                try:
                    header = block.strip().splitlines()[0]
                    # Header format: "[N] [Source: file, page P, score X.XX]"
                    cid = int(header.split("[Source:")[0].strip().lstrip("[").rstrip("]"))
                    fields = header.split("[Source:")[1].rstrip("]").split(",")
                    file_part = fields[0].strip()
                    page_part = fields[1].replace("page", "").strip() if len(fields) > 1 else ""
                    page = int(page_part) if page_part.isdigit() else None
                    score_part = fields[2].replace("score", "").strip() if len(fields) > 2 else ""
                    score = float(score_part) if score_part else None
                    by_id[cid] = {
                        "file": file_part,
                        "title": _friendly_title(file_part),
                        "page": page,
                        "score": score,
                    }
                except (IndexError, ValueError):
                    pass

    # Cite-as-you-go: keep only the chunks the model says it used. If the model didn't
    # emit a CITATIONS line at all (non-compliance), fall back to all retrieved chunks
    # so we never lose attribution entirely.
    output, cited_ids = _extract_citations(output)
    if cited_ids is None:
        chosen = list(by_id.values())
    else:
        chosen = [by_id[i] for i in cited_ids if i in by_id]

    # De-dup by (file, page), keeping the best score, then sort most-relevant first.
    sources: list[dict] = []
    seen_sources: set[tuple] = set()
    for src in chosen:
        key = (src["file"], src["page"])
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append(src)
    sources.sort(key=lambda s: s.get("score") if s.get("score") is not None else -1.0, reverse=True)

    return {"answer": output, "sources": sources, "tools_used": tools_used}
