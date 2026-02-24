"""
LLM Service - Ollama Integration
Connect to your local Llama model!
NOW WITH STREAMING SUPPORT!
"""

import logging
import httpx
import json
from typing import Optional, AsyncGenerator

from utils.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM Service using Ollama
    Connects to your local Llama models
    """
    
    def __init__(self):
        self.base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model_name = settings.MODEL_NAME
        self.initialized = False
        
    async def initialize(self):
        """Check if Ollama is running and model is available"""
        if self.initialized:
            return
        
        logger.info(f"🤖 Initializing LLM service with model: {self.model_name}")
        
        try:
            # Check if Ollama is running
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=5.0
                )
                
                if response.status_code != 200:
                    raise RuntimeError("❌ Ollama is not running")
                
                # Check if our model is available
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                if not any(self.model_name in name for name in model_names):
                    logger.error(f"❌ Model {self.model_name} not found!")
                    logger.error(f"Available models: {model_names}")
                    raise RuntimeError(f"Model {self.model_name} not found")
                
                logger.info(f"✅ Ollama connected! Model: {self.model_name}")
                logger.info(f"📊 Available models: {len(models)}")
                
                self.initialized = True
                
        except httpx.ConnectError:
            logger.error("❌ Cannot connect to Ollama!")
            logger.error("Make sure Ollama is running: ollama serve")
            raise RuntimeError(
                "Ollama not running. Start it with: ollama serve"
            )
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        model: Optional[str] = None
    ) -> str:
        """
        Generate AI response (non-streaming)
        
        Args:
            prompt: User's message
            system_prompt: Optional system instructions
            temperature: Creativity (0-1)
            max_tokens: Max response length
            model: Optional model override (if None, uses default)
            
        Returns:
            AI generated response
        """
        if not self.initialized:
            await self.initialize()
        
        # Use provided model or default
        model_to_use = model if model else self.model_name
        
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            logger.info(f"🤔 Generating response for: {prompt[:50]}...")
            
            # Call Ollama API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
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
                
                logger.info(f"✅ Response generated ({len(generated_text)} chars)")
                
                return generated_text
                
        except httpx.ReadTimeout:
            logger.error("⏱️ Request timeout (>60s)")
            raise RuntimeError("AI response timeout - try shorter prompts")
        except Exception as e:
            logger.error(f"❌ Generation failed: {e}")
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming AI response (yields tokens as they arrive)
        
        Args:
            prompt: User's message
            system_prompt: Optional system instructions
            temperature: Creativity (0-1)
            max_tokens: Max response length
            model: Optional model override
            
        Yields:
            Tokens of text as they're generated
        """
        if not self.initialized:
            await self.initialize()
        
        model_to_use = model if model else self.model_name
        
        logger.info(f"🌊 Streaming response for: {prompt[:50]}...")
        
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            # Call Ollama API with streaming
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model_to_use,
                        "messages": messages,
                        "stream": True,  # Enable streaming
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
                    
                    # Stream response chunks
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                
                                # Ollama returns token in "message.content" field
                                if "message" in data and "content" in data["message"]:
                                    token = data["message"]["content"]
                                    if token:
                                        yield token
                                
                                # Check if done
                                if data.get("done", False):
                                    logger.info("✅ Stream complete")
                                    break
                                    
                            except json.JSONDecodeError:
                                continue
        
        except Exception as e:
            logger.error(f"❌ Streaming error: {e}")
            yield json.dumps({"error": str(e)})


# Global LLM service instance
llm_service = LLMService()


async def get_llm() -> LLMService:
    """Dependency to get LLM service"""
    if not llm_service.initialized:
        await llm_service.initialize()
    return llm_service


# Test function
async def test_llm():
    """Test the LLM service"""
    print("🧪 Testing LLM Service...")
    print("=" * 50)
    
    try:
        await llm_service.initialize()
        print("✅ LLM initialized successfully!")
        
        # Test 1: Non-streaming generation
        print("\n🤖 Test 1: Non-streaming (default model)")
        response = await llm_service.generate(
            prompt="Say hello and introduce yourself in one sentence.",
            temperature=0.7
        )
        print(f"   AI: {response}")
        
        # Test 2: Streaming generation
        print("\n🌊 Test 2: Streaming response")
        print("   AI: ", end="", flush=True)
        async for token in llm_service.generate_stream(
            prompt="Count from 1 to 5 slowly.",
            temperature=0.7
        ):
            print(token, end="", flush=True)
        print()  # New line after stream
        
        # Test 3: Specific model
        print("\n🤖 Test 3: Specific model (llama3.2:3b)")
        response = await llm_service.generate(
            prompt="What is 2+2?",
            model="llama3.2:3b",
            temperature=0.7
        )
        print(f"   AI: {response}")
        
        print("\n✅ All LLM tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_llm())