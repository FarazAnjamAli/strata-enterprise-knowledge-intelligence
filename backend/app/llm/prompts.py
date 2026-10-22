"""System prompts. Every tier receives the same prompts, so falling back to
a different model never loosens the grounding rules."""

from app.config import get_settings

NO_ANSWER_IN_CONTEXT = "NO_ANSWER_IN_CONTEXT"
NO_ANSWER = "NO_ANSWER"
USED_MARKER = "USED_DOCUMENTS"


def rag_system() -> str:
    name = get_settings().app_name
    return (
        f"You are {name}, an enterprise knowledge assistant. Answer the user's "
        "question using ONLY the provided context excerpts from the organization's "
        "documents. Quote figures exactly as they appear. If the context does not "
        f"contain the answer, reply with exactly: {NO_ANSWER_IN_CONTEXT}. Never "
        "invent facts, sources, names or figures.\n"
        "Attribute names, roles and titles with care: only state that a person "
        "holds a title when the context pairs them explicitly (e.g. 'Approved by: "
        "<name>, CFO'). Single letters around names in flattened tables are usually "
        "responsibility-matrix codes, not titles.\n"
        "If the user asks what a document contains or is about, summarize the "
        f"excerpts - that is an answer, never {NO_ANSWER_IN_CONTEXT}.\n"
        "Write in Markdown: short paragraphs, bullet lists for enumerations, a "
        "table for tabular data, bold for key figures. Answer directly; do not "
        "mention 'the context' or repeat excerpts verbatim.\n"
        "End with one final line exactly of the form:\n"
        f"{USED_MARKER}: <name1>, <name2>\n"
        "listing the names from the [Document: ...] headers of ONLY the excerpts "
        "you actually used."
    )


def general_system() -> str:
    name = get_settings().app_name
    return (
        f"You are {name}, an enterprise assistant. No internal document matched "
        "this question, so answer from general knowledge, concisely and in "
        "Markdown. If you do not know the answer or it depends on internal "
        f"company information you don't have, reply with exactly: {NO_ANSWER}. "
        "Do not guess or fabricate."
    )


_HISTORY_MESSAGES = 6
_HISTORY_CHARS = 400


def history_block(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = "\n".join(f"{m['role']}: {m['content'][:_HISTORY_CHARS]}" for m in history[-_HISTORY_MESSAGES:])
    return f"Conversation so far (use only to resolve references):\n{lines}\n\n"


def rag_prompt(question: str, context_blocks: list[str], history: list[dict] | None) -> str:
    context = "\n\n---\n\n".join(context_blocks)
    return (
        f"{history_block(history)}"
        f"Context excerpts:\n\n{context}\n\n"
        f"Question (answer from the excerpts above only):\n{question}"
    )


def general_prompt(question: str, history: list[dict] | None) -> str:
    return f"{history_block(history)}Question:\n{question}"
