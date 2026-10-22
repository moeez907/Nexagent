"""
Abstract Base Class for LLM Providers.
Defines strict contracts for structured JSON outputs and text completions.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel


class LLMProvider(ABC):
    """
    Abstract interface for LLM provider operations.
    """

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output from LLM, guaranteed to parse as valid JSON.
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate freeform text completion from LLM.
        """
        pass
