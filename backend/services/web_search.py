"""
Web Search Service - Serper.dev Integration
"""

import os
from dotenv import load_dotenv

# Load .env file FIRST
load_dotenv()

import httpx
from typing import Dict, Optional
from datetime import datetime


class WebSearchService:
    
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY")
        self.base_url = "https://google.serper.dev/search"
        
        if not self.api_key:
            print("⚠️  SERPER_API_KEY not set")
        else:
            print("✅ Serper initialized")
    
    async def search(self, query: str, count: int = 5, freshness: Optional[str] = None) -> Dict:
        
        if not self.api_key:
            return {"results": [], "error": "No API key", "query": query}
        
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {"q": query, "num": min(count, 10), "gl": "us", "hl": "en"}
        
        if freshness == "pd":
            payload["tbs"] = "qdr:d"
        elif freshness == "pw":
            payload["tbs"] = "qdr:w"
        elif freshness == "pm":
            payload["tbs"] = "qdr:m"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            
            results = []
            if "organic" in data:
                for item in data["organic"][:count]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "description": item.get("snippet", ""),
                        "published": item.get("date", ""),
                        "source": self._extract_domain(item.get("link", ""))
                    })
            
            return {
                "results": results,
                "query": query,
                "timestamp": datetime.utcnow().isoformat(),
                "count": len(results)
            }
            
        except Exception as e:
            print(f"❌ Search error: {e}")
            return {"results": [], "error": str(e), "query": query}
    
    
    def _extract_domain(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except:
            return url
    
    
    def format_results_for_llm(self, search_data: Dict) -> str:
        
        if not search_data.get("results"):
            return "No search results found."
        
        formatted = f"Web Search Results for: '{search_data['query']}'\n\n"
        
        for i, result in enumerate(search_data["results"], 1):
            formatted += f"{i}. {result['title']}\n"
            formatted += f"   Source: {result['source']}\n"
            formatted += f"   {result['description']}\n"
            if result.get('published'):
                formatted += f"   Published: {result['published']}\n"
            formatted += f"   URL: {result['url']}\n\n"
        
        return formatted
    
    
    def should_search(self, message: str) -> bool:
        
        message_lower = message.lower()
        
        triggers = [
            "search for", "google", "look up", "find information",
            "what is happening", "latest", "current", "recent",
            "today", "this week", "news", "price of", "weather",
            "when is"
        ]
        
        for trigger in triggers:
            if trigger in message_lower:
                return True
        
        return False
    
    
    def extract_search_query(self, message: str) -> str:
        
        prefixes = [
            "search for", "google", "look up", "tell me about",
            "what is", "who is", "when is", "where is", "please"
        ]
        
        query = message.lower().strip()
        
        for prefix in prefixes:
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        
        return query.rstrip("?!.").strip()


web_search_service = WebSearchService()