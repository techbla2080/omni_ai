"""
LLM Service - Groq API (Primary) + Ollama (Fallback)
Groq provides free Llama 70B inference
Ollama as local fallback if Groq is unavailable
"""

import logging
import httpx
import json
import os
from typing import Optional, AsyncGenerator

from utils.config import settings

logger = logging.getLogger(__name__)

# Groq API settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", getattr(settings, "GROQ_API_KEY", ""))
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class LLMService:
    """
    LLM Service - Groq API primary, Ollama fallback
    """

    def __init__(self):
        # Ollama settings (fallback)
        self.ollama_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.ollama_model = settings.MODEL_NAME
        
        # Groq settings (primary)
        self.groq_api_key = GROQ_API_KEY
        self.groq_model = GROQ_MODEL
        
        # Provider tracking
        self.provider = "groq" if self.groq_api_key else "ollama"
        self.initialized = False

    async def initialize(self):
        """Initialize the LLM service"""
        if self.initialized:
            return

        # Try Groq first
        if self.groq_api_key:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{GROQ_BASE_URL}/models",
                        headers={"Authorization": f"Bearer {self.groq_api_key}"},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        self.provider = "groq"
                        self.initialized = True
                        logger.info(f"✅ Groq API connected! Model: {self.groq_model}")
                        return
                    else:
                        logger.warning(f"⚠️ Groq API returned {response.status_code}, falling back to Ollama")
            except Exception as e:
                logger.warning(f"⚠️ Groq unavailable ({e}), falling back to Ollama")

        # Fallback to Ollama
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.ollama_url}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    self.provider = "ollama"
                    self.initialized = True
                    logger.info(f"✅ Ollama connected! Model: {self.ollama_model}")
                    return
        except Exception as e:
            logger.error(f"❌ Ollama also unavailable: {e}")

        # If we have Groq key, still mark as initialized (will try on each request)
        if self.groq_api_key:
            self.provider = "groq"
            self.initialized = True
            logger.info("⚡ Using Groq API (connection will be verified per request)")
        else:
            raise RuntimeError("No LLM provider available. Set GROQ_API_KEY or start Ollama.")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None
    ) -> str:
        """Generate AI response"""
        if not self.initialized:
            await self.initialize()

        # Try Groq first
        if self.provider == "groq" or self.groq_api_key:
            try:
                return await self._generate_groq(prompt, system_prompt, temperature, max_tokens, model)
            except Exception as e:
                logger.warning(f"⚠️ Groq failed ({e}), trying Ollama fallback...")

        # Fallback to Ollama
        return await self._generate_ollama(prompt, system_prompt, temperature, max_tokens, model)

    async def _generate_groq(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None
    ) -> str:
        """Generate response using Groq API"""
        model_to_use = model if model else self.groq_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"⚡ Groq generating ({model_to_use}): {prompt[:50]}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                }
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Groq API error {response.status_code}: {error_text}")
                raise RuntimeError(f"Groq API error: {response.status_code}")

            result = response.json()
            generated_text = result["choices"][0]["message"]["content"].strip()
            
            # Log token usage
            usage = result.get("usage", {})
            logger.info(f"✅ Groq response: {len(generated_text)} chars | Tokens: {usage.get('total_tokens', '?')}")

            return generated_text

    async def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        model: Optional[str] = None
    ) -> str:
        """Generate response using Ollama (fallback)"""
        model_to_use = model if model else self.ollama_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"🦙 Ollama generating ({model_to_use}): {prompt[:50]}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.text}")
                raise RuntimeError(f"Ollama API error: {response.status_code}")

            result = response.json()
            generated_text = result["message"]["content"].strip()
            logger.info(f"✅ Ollama response: {len(generated_text)} chars")
            return generated_text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response"""
        if not self.initialized:
            await self.initialize()

        # Try Groq first
        if self.provider == "groq" or self.groq_api_key:
            try:
                async for token in self._stream_groq(prompt, system_prompt, temperature, max_tokens, model):
                    yield token
                return
            except Exception as e:
                logger.warning(f"⚠️ Groq stream failed ({e}), trying Ollama...")

        # Fallback to Ollama streaming
        async for token in self._stream_ollama(prompt, system_prompt, temperature, max_tokens, model):
            yield token

    async def _stream_groq(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response from Groq API"""
        model_to_use = model if model else self.groq_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"⚡ Groq streaming ({model_to_use}): {prompt[:50]}...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True
                }
            ) as response:

                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Groq stream error: {error_text}")
                    raise RuntimeError(f"Groq stream error: {response.status_code}")

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        if data_str.strip() == "[DONE]":
                            logger.info("✅ Groq stream complete")
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue

    async def _stream_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response from Ollama (fallback)"""
        model_to_use = model if model else self.ollama_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"🦙 Ollama streaming ({model_to_use}): {prompt[:50]}...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.ollama_url}/api/chat",
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                }
            ) as response:

                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Ollama error: {error_text}")
                    yield json.dumps({"error": "Generation failed"})
                    return

                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                token = data["message"]["content"]
                                if token:
                                    yield token
                            if data.get("done", False):
                                logger.info("✅ Ollama stream complete")
                                break
                        except json.JSONDecodeError:
                            continue


# Global LLM service instance
llm_service = LLMService()


async def get_llm() -> LLMService:
    """Dependency to get LLM service"""
    if not llm_service.initialized:
        await llm_service.initialize()
    return llm_service