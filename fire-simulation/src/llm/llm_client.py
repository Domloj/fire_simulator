import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
import aiohttp
import requests

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Client for interacting with LLM APIs (OpenAI-compatible).
    HARD REQUIREMENT: no mock responses. If LLM is misconfigured, calls
    fail with logs and return empty/None instead of fake content.
    """
    
    def __init__(
        self, 
        model: str             = "gpt-4o-mini", 
        api_key: Optional[str] = None,
        base_url: str          = "https://api.openai.com/v1"
    ):
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self._session = None 

    def complete(self, prompt: str, system_prompt: str = "You are a helpful fire agent.") -> str:
        """
        Synchronous completion for agents.
        NO MOCKS: if LLM is not available, returns empty string.
        """
        if not self.api_key:
            # LLM is disabled - this is expected when OPENAI_API_KEY is not set, so use debug level
            logger.debug("LLMClient: complete() called but OPENAI_API_KEY is not set; LLM is disabled")
            return ""

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 100  # Reduced from 500 for faster responses
            }
            
            # Use a reasonable timeout - connection timeout 3s, read timeout 5s
            # This allows the request to start quickly but gives time for response
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=(3, 5)  # (connect timeout, read timeout) - 3s to connect, 5s to read response
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM API Error ({response.status_code}): {response.text}")
                return ""
                
        except requests.exceptions.Timeout as e:
            # Timeout is expected when LLM is slow - use debug level, not error
            logger.debug(f"LLM request timeout (expected for slow responses): {e}")
            return ""
        except Exception as e:
            # Other errors (network, API errors) - log at debug level to avoid spam
            logger.debug(f"LLM Sync request failed: {e}")
            return ""
    
    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs: Any) -> Optional[str]:
        """
        Async chat completion for agents (used by LLMAgentBrain).
        
        NO MOCKS: if LLM is not available, returns None.
        """
        if not self.api_key:
            # LLM is disabled - this is expected when OPENAI_API_KEY is not set, so use debug level
            logger.debug("LLMClient: chat_completion() called but OPENAI_API_KEY is not set; LLM is disabled")
            return None
        
        try:
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.3),
            }

            response_format = kwargs.get("response_format")
            if response_format:
                payload["response_format"] = response_format
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=20,
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"LLM async API error ({resp.status}): {text}")
                        return None
                    data = await resp.json()
                    try:
                        return data["choices"][0]["message"]["content"]
                    except Exception as e:
                        logger.error(f"Unexpected LLM async response format: {e} | data={data}", exc_info=True)
                        return None
        except Exception as e:
            logger.error(f"LLM async chat_completion failed: {e}", exc_info=True)
            return None
