"""
Model Router - Always Use 1B Model
Configured to always use llama3.2:1b for speed and reliability
"""

from typing import Dict, Optional


class ModelRouter:
    """
    Simple router that always uses llama3.2:1b
    Fast, lightweight, reliable
    """
    
    def __init__(self):
        # Available models and their characteristics
        self.models = {
            "llama3.2:1b": {
                "quality": 4,
                "speed": "very_fast",
                "ram_gb": 2,
                "cost": 0,
                "best_for": ["all"]
            },
            "llama3.2:3b": {
                "quality": 6,
                "speed": "fast",
                "ram_gb": 4,
                "cost": 0,
                "best_for": ["simple", "quick"]
            },
            "llama3.1:8b": {
                "quality": 7,
                "speed": "medium",
                "ram_gb": 8,
                "cost": 0,
                "best_for": ["search", "complex", "reasoning"]
            }
        }
        
        # Default model - ALWAYS 1B
        self.default_model = "llama3.2:1b"
    
    
    def choose_model(
        self,
        query: str,
        has_search_results: bool = False,
        has_files: bool = False,
        context_length: int = 0,
        user_preference: Optional[str] = None,
        force_model: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Always returns llama3.2:1b for maximum speed
        
        Args:
            query: User's message (ignored)
            has_search_results: Whether query has web search results (ignored)
            has_files: Whether files are attached (ignored)
            context_length: Length of conversation context (ignored)
            user_preference: User's preferred model (ignored)
            force_model: Force specific model (only this is respected)
        
        Returns:
            {
                "model": "llama3.2:1b",
                "reason": "Always using fast 1B model",
                "quality_score": 4,
                "speed": "very_fast"
            }
        """
        
        # Force model if specified (for testing)
        if force_model and force_model in self.models:
            return self._build_response(force_model, "User override")
        
        # ALWAYS USE 1B - fastest and most reliable
        return self._build_response("llama3.2:1b", "Always using fast 1B model")
    
    
    def _assess_complexity(self, query: str) -> str:
        """
        Not used anymore - always returns simple
        Kept for compatibility
        """
        return "simple"
    
    
    def _build_response(self, model: str, reason: str) -> Dict[str, any]:
        """Build model selection response"""
        
        model_info = self.models.get(model, self.models[self.default_model])
        
        return {
            "model": model,
            "reason": reason,
            "quality_score": model_info["quality"],
            "speed": model_info["speed"],
            "ram_required": model_info["ram_gb"]
        }
    
    
    def get_available_models(self) -> Dict:
        """Return list of available models"""
        return self.models
    
    
    def validate_model(self, model_name: str) -> bool:
        """Check if model is valid"""
        return model_name in self.models


# Initialize router
model_router = ModelRouter()