import os

from langchain_core.tools import tool

from app.config import settings

# Mock data — replace with real DB/API calls in production
_PRODUCTS = {
    "P001": {"name": "Widget Pro", "price": "$49.99", "description": "Professional-grade widget with 2-year warranty."},
    "P002": {"name": "Gadget Basic", "price": "$19.99", "description": "Entry-level gadget for everyday use."},
}

_ORDERS = {
    "ORD-1001": {"status": "Shipped", "estimated_delivery": "2024-12-25"},
    "ORD-1002": {"status": "Processing", "estimated_delivery": "2024-12-28"},
}


def make_search_tool(vector_store, tenant_id: str, top_k: int, threshold: float | None = None):
    """Return a search_documents tool bound to a specific tenant's vector store.

    Chunks whose relevance score is below ``threshold`` (default
    ``settings.RELEVANCE_THRESHOLD``) are dropped, so an off-topic query returns
    "No relevant documents found." instead of the k nearest weak matches.
    """
    min_score = settings.RELEVANCE_THRESHOLD if threshold is None else threshold
    # Citation counter shared across every search call in a single chat turn, so each
    # chunk gets a turn-unique [N] id the model can cite (see cite-as-you-go in agent.py).
    counter = {"n": 0}

    @tool
    def search_documents(query: str) -> str:
        """Search the knowledge base for relevant information."""
        docs = vector_store.search(tenant_id, query, top_k)
        # Keep only sufficiently relevant chunks. A missing score (backend didn't
        # provide one) is treated as passing so we never silently drop everything.
        relevant = [d for d in docs if d.metadata.get("score", 1.0) >= min_score]
        if not relevant:
            return "No relevant documents found."
        blocks = []
        for d in relevant:
            counter["n"] += 1
            blocks.append(
                f"[{counter['n']}] [Source: {os.path.basename(d.metadata.get('source', 'unknown'))}, "
                f"page {d.metadata.get('page', '?')}, score {d.metadata.get('score', 1.0):.2f}]\n{d.page_content}"
            )
        return "\n\n---\n\n".join(blocks)

    return search_documents


@tool
def get_product_info(product_id: str) -> str:
    """Get product details from the product catalog."""
    p = _PRODUCTS.get(product_id.upper())
    if not p:
        return f"Product '{product_id}' not found."
    return f"Name: {p['name']}\nPrice: {p['price']}\nDescription: {p['description']}"


@tool
def get_order_status(order_id: str) -> str:
    """Get the current status of a customer order."""
    o = _ORDERS.get(order_id.upper())
    if not o:
        return f"Order '{order_id}' not found."
    return f"Status: {o['status']}\nEstimated delivery: {o['estimated_delivery']}"
