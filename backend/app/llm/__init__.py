"""Three-tier LLM layer: local model -> free API -> paid API.

Public surface:
    router.generate(...) / router.stream(...)   tier-aware completion
    router.status()                            per-tier health for the UI
"""
