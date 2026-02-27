import tiktoken


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o-mini") -> str:
    enc = tiktoken.encoding_for_model(model)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # Keep first 75% + last 25% to capture intro and conclusion/forecasts
    split = int(max_tokens * 0.75)
    kept = tokens[:split] + tokens[-(max_tokens - split):]
    return enc.decode(kept)
