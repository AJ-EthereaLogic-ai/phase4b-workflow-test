"""
Anthropic (Claude) provider adapter re-export.
"""

from adws.providers.implementations.claude import ClaudeCodeProvider as AnthropicProvider

__all__ = ["AnthropicProvider"]
