"""
Brain — AI Reasoning Engine
Uses Qwen3 via HuggingFace Inference API (free tier)
Handles: thinking, planning, summarizing, deciding
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

HF_API_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen3-8B"
# Alternatively: Qwen/Qwen2.5-7B-Instruct (more stable on HF free tier)
HF_FALLBACK_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B-Instruct"


class Brain:
    """
    The agent's thinking core.
    Calls HuggingFace Qwen3 to reason, plan, summarize, and decide.
    """

    def __init__(self):
        self.api_key = os.getenv("HF_API_KEY", "")
        if not self.api_key:
            logger.warning("HF_API_KEY not set — brain will run in offline mode.")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def think(self, prompt: str, system: str = None, max_tokens: int = 512) -> str:
        """
        Send a prompt to Qwen3 and get a response.
        Falls back to fallback model if primary fails.
        """
        if not self.api_key:
            return "[Brain offline: no HF_API_KEY set]"

        full_prompt = self._build_prompt(system, prompt)

        result = await self._call(HF_API_URL, full_prompt, max_tokens)
        if result.startswith("[ERROR]"):
            logger.warning(f"Primary model failed, trying fallback...")
            result = await self._call(HF_FALLBACK_URL, full_prompt, max_tokens)

        return result

    async def _call(self, url: str, prompt: str, max_tokens: int) -> str:
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": 0.7,
                "do_sample": True,
                "return_full_text": False
            }
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=payload, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        return data[0].get("generated_text", "").strip()
                    return str(data)
                elif resp.status_code == 503:
                    return "[ERROR] Model loading, please retry in 20s"
                else:
                    return f"[ERROR] HF API {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return f"[ERROR] {str(e)}"

    def _build_prompt(self, system: Optional[str], user: str) -> str:
        """Format as Qwen chat template."""
        sys_msg = system or (
            "You are JARVIS, an autonomous AI agent. "
            "You are helpful, intelligent, and always ask the superadmin for permission before taking major actions. "
            "Be concise and clear."
        )
        return (
            f"<|im_start|>system\n{sys_msg}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    async def plan(self, goal: str, context: str = "") -> str:
        """Generate a step-by-step plan for a goal."""
        prompt = f"""Goal: {goal}

Context:
{context}

Create a numbered step-by-step plan to achieve this goal. 
Be specific and practical. Each step should be actionable.
If any step requires external action or could cause harm, mark it with [REQUIRES APPROVAL]."""
        return await self.think(prompt, max_tokens=600)

    async def summarize(self, text: str, max_length: int = 200) -> str:
        """Summarize a piece of text."""
        prompt = f"Summarize the following in under {max_length} characters:\n\n{text}"
        return await self.think(prompt, max_tokens=256)

    async def decide(self, situation: str, options: list[str]) -> str:
        """Choose the best option given a situation."""
        opts = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
        prompt = f"""Situation: {situation}

Options:
{opts}

Which option is best and why? Reply with the option number and a brief reason."""
        return await self.think(prompt, max_tokens=256)
