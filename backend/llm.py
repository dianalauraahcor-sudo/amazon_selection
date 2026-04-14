"""Kimi (Moonshot) LLM client - OpenAI-compatible chat completions."""
import os
import time
import httpx


def chat(prompt: str, max_tokens: int = 2000, temperature: float = 0.3,
         system: str = "", retries: int = 2) -> str:
    """Call LLM with optional system message. Retries on failure."""
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        print("[Kimi LLM] KIMI_API_KEY not set")
        return ""
    base = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
    model = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=90) as c:
                r = c.post(
                    f"{base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            is_rate_limit = "429" in str(e)
            print(f"[Kimi LLM] attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                wait = 10 if is_rate_limit else 2
                print(f"[Kimi LLM] waiting {wait}s before retry...")
                time.sleep(wait)

    print(f"[Kimi LLM] all {retries} attempts failed, last error: {last_err}")
    return ""
