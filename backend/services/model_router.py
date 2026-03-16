"""
Model Router - Groq Primary, Ollama Fallback
Routes to the best available model
"""

from typing import Dict, Optional
import os


class ModelRouter:
    """
    Smart router: Uses Groq (70B) when available, Ollama (1B) as fallback
    """
    
    def __init__(self):
        self.groq_available = bool(os.getenv("GROQ_API_KEY", ""))
        
        self.models = {
            "llama-3.3-70b-versatile": {
                "quality": 9,
                "speed": "fast",
                "provider": "groq",
                "best_for": ["all"]
            },
            "llama3.2:1b": {
                "quality": 4,
                "speed": "very_fast",
                "provider": "ollama",
                "best_for": ["fallback"]
            }
        }
        
        self.default_model = "llama-3.3-70b-versatile" if self.groq_available else "llama3.2:1b"
    
    def choose_model(
        self,
        query: str = "",
        has_search_results: bool = False,
        has_files: bool = False,
        context_length: int = 0,
        user_preference: Optional[str] = None,
        force_model: Optional[str] = None
    ) -> Dict:
        
        if force_model and force_model in self.models:
            return self._build_response(force_model, "User override")
        
        if self.groq_available:
            return self._build_response("llama-3.3-70b-versatile", "Groq Llama 70B (primary)")
        
        return self._build_response("llama3.2:1b", "Ollama fallback (no Groq key)")
    
    def _build_response(self, model: str, reason: str) -> Dict:
        model_info = self.models.get(model, {})
        return {
            "model": model,
            "reason": reason,
            "quality_score": model_info.get("quality", 4),
            "speed": model_info.get("speed", "fast"),
        }
    
    def get_available_models(self) -> Dict:
        return self.models
    
    def validate_model(self, model_name: str) -> bool:
        return model_name in self.models


model_router = ModelRouter()