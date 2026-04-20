"""
OpenRouter LLM client for SEO content generation.
Uses Minimax model (free on OpenRouter).
"""
import os
import json
import requests
from typing import Optional

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def call_llm(
    prompt: str,
    model: str = "minimax/minimax-m2.5:free",
    max_tokens: int = 7500,
    temperature: float = 0.7,
) -> Optional[str]:
    """
    Call LLM via OpenRouter API.
    
    Args:
        prompt: The prompt to send to the model
        model: Model identifier (default: minimax models)
        max_tokens: Max tokens in response
        temperature: Creativity vs precision (0.0-1.0)
    
    Returns:
        LLM response text or None on error
    """
    if not OPENROUTER_API_KEY:
        print("Warning: OPENROUTER_API_KEY not set. Set it in environment variables.")
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://onyxcad.com",
        "X-Title": "OnyxCAD SEO Content Generator",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        
        if response.status_code != 200:
            print(f"OpenRouter API error: {response.status_code} - {response.text}")
            return None
        
        data = response.json()
        
        if "choices" not in data or len(data["choices"]) == 0:
            print("No choices in response")
            return None
        
        return data["choices"][0]["message"]["content"]
        
    except requests.exceptions.Timeout:
        print("OpenRouter API timeout")
        return None
    except Exception as e:
        print(f"OpenRouter API error: {e}")
        return None


def generate_with_minimax(prompt: str) -> Optional[str]:
    """Generate content using Minimax M2.5 Free model via OpenRouter."""
    return call_llm(
        prompt=prompt,
        model="minimax/minimax-m2.5:free",
        max_tokens=7500,
        temperature=0.7,
    )


def generate_with_deepseek(prompt: str) -> Optional[str]:
    """Generate content using DeepSeek via OpenRouter (alternative)."""
    return call_llm(
        prompt=prompt,
        model="deepseek/deepseek-chat",
        max_tokens=4000,
        temperature=0.7,
    )
