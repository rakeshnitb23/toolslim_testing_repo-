from toolslim.tokenizers.base import TokenCounter, tool_text
from toolslim.tokenizers.tiktoken_counter import TiktokenCounter


def get_counter(spec: str) -> TokenCounter:
    """``o200k_base`` / ``cl100k_base`` / ``tiktoken:<enc>`` / ``anthropic[:<model>]``."""
    if spec.startswith("anthropic"):
        from toolslim.tokenizers.anthropic_counter import AnthropicCounter

        _, _, model = spec.partition(":")
        return AnthropicCounter(model) if model else AnthropicCounter()
    return TiktokenCounter(spec.removeprefix("tiktoken:"))


__all__ = ["TiktokenCounter", "TokenCounter", "get_counter", "tool_text"]
