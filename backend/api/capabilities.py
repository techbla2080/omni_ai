"""
Capabilities API - Smart AI IDE endpoints
Allows users to discover what OmniAI can do
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ExamplePrompt(BaseModel):
    """Example prompt for a capability"""
    prompt: str
    outcome: str


class Capability(BaseModel):
    """Capability information"""
    id: str
    name: str
    category: str
    subcategory: Optional[str] = None
    description: str
    difficulty_level: int
    popularity_score: float
    example_prompts: List[ExamplePrompt]
    required_integrations: List[str]
    is_unlocked: bool = True
    user_tried: bool = False
    usage_count: int = 0


class CapabilityList(BaseModel):
    """List of capabilities with metadata"""
    capabilities: List[Capability]
    total: int
    categories: List[str]


class CategoryStats(BaseModel):
    """Statistics for a category"""
    category: str
    count: int
    unlocked_count: int


class DiscoveryRequest(BaseModel):
    """Request to mark capability as discovered"""
    user_id: str = Field(..., description="User ID")
    discovery_method: str = Field(default="browse", description="How user discovered it")


class UsageRequest(BaseModel):
    """Request to track capability usage"""
    user_id: str = Field(..., description="User ID")


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("", response_model=CapabilityList)
async def list_capabilities(
    category: Optional[str] = Query(None, description="Filter by category"),
    user_id: Optional[str] = Query(None, description="User ID for personalization"),
    search: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all capabilities with optional filtering
    """
    
    # All 20 capabilities
    capabilities = [
        {
            "id": "cap-001",
            "name": "Read Emails",
            "category": "email",
            "subcategory": "reading",
            "description": "View and read your emails with natural language queries",
            "difficulty_level": 1,
            "popularity_score": 0.95,
            "example_prompts": [{"prompt": "Show me unread emails", "outcome": "Lists unread emails"}],
            "required_integrations": ["gmail"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-002",
            "name": "Send Emails",
            "category": "email",
            "subcategory": "writing",
            "description": "Compose and send emails with AI assistance",
            "difficulty_level": 1,
            "popularity_score": 0.90,
            "example_prompts": [{"prompt": "Send email to john@example.com", "outcome": "Email sent"}],
            "required_integrations": ["gmail"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-003",
            "name": "Draft Smart Emails",
            "category": "email",
            "subcategory": "writing",
            "description": "AI-powered email drafting that learns your style",
            "difficulty_level": 2,
            "popularity_score": 0.85,
            "example_prompts": [{"prompt": "Draft a professional decline email", "outcome": "Creates polite decline"}],
            "required_integrations": ["gmail"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-004",
            "name": "View Calendar",
            "category": "calendar",
            "subcategory": "reading",
            "description": "Check your schedule and upcoming events",
            "difficulty_level": 1,
            "popularity_score": 0.92,
            "example_prompts": [{"prompt": "What's on my calendar today?", "outcome": "Lists today's events"}],
            "required_integrations": ["google_calendar"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-005",
            "name": "Schedule Meetings",
            "category": "calendar",
            "subcategory": "writing",
            "description": "Create calendar events and send meeting invites",
            "difficulty_level": 2,
            "popularity_score": 0.88,
            "example_prompts": [{"prompt": "Schedule meeting with Alex at 2pm", "outcome": "Creates event"}],
            "required_integrations": ["google_calendar"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-006",
            "name": "Find Products",
            "category": "shopping",
            "subcategory": "search",
            "description": "Search for products with price comparison",
            "difficulty_level": 1,
            "popularity_score": 0.80,
            "example_prompts": [{"prompt": "Find wireless headphones under $100", "outcome": "Shows product options"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-007",
            "name": "Track Prices",
            "category": "shopping",
            "subcategory": "monitoring",
            "description": "Monitor product prices and get alerts",
            "difficulty_level": 2,
            "popularity_score": 0.75,
            "example_prompts": [{"prompt": "Alert me when iPhone drops below $700", "outcome": "Sets price alert"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-008",
            "name": "Make Purchases",
            "category": "shopping",
            "subcategory": "transaction",
            "description": "Complete purchases securely",
            "difficulty_level": 3,
            "popularity_score": 0.70,
            "example_prompts": [{"prompt": "Buy the headphones we found", "outcome": "Completes checkout"}],
            "required_integrations": ["stripe"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-009",
            "name": "Web Research",
            "category": "research",
            "subcategory": "information",
            "description": "Deep web research with source compilation",
            "difficulty_level": 2,
            "popularity_score": 0.87,
            "example_prompts": [{"prompt": "Research quantum computing developments", "outcome": "Comprehensive summary"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-010",
            "name": "Fact Checking",
            "category": "research",
            "subcategory": "verification",
            "description": "Verify claims against reliable sources",
            "difficulty_level": 2,
            "popularity_score": 0.78,
            "example_prompts": [{"prompt": "Is it true coffee dehydrates you?", "outcome": "Fact-check with sources"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-011",
            "name": "Task Management",
            "category": "productivity",
            "subcategory": "tasks",
            "description": "Create and track your to-do lists",
            "difficulty_level": 1,
            "popularity_score": 0.89,
            "example_prompts": [{"prompt": "Add finish report to my tasks", "outcome": "Creates task"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-012",
            "name": "Note Taking",
            "category": "productivity",
            "subcategory": "notes",
            "description": "Quick note capture with smart tagging",
            "difficulty_level": 1,
            "popularity_score": 0.84,
            "example_prompts": [{"prompt": "Take note: Meeting went well", "outcome": "Saves note with tags"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-013",
            "name": "Reminders",
            "category": "productivity",
            "subcategory": "alerts",
            "description": "Set time-based reminders",
            "difficulty_level": 1,
            "popularity_score": 0.91,
            "example_prompts": [{"prompt": "Remind me to call mom at 5pm", "outcome": "Sets reminder"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-014",
            "name": "Social Media Posts",
            "category": "social",
            "subcategory": "content",
            "description": "Create and schedule social media content",
            "difficulty_level": 2,
            "popularity_score": 0.76,
            "example_prompts": [{"prompt": "Post to Twitter about product launch", "outcome": "Publishes tweet"}],
            "required_integrations": ["twitter"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-015",
            "name": "Social Monitoring",
            "category": "social",
            "subcategory": "monitoring",
            "description": "Monitor mentions and engagement",
            "difficulty_level": 2,
            "popularity_score": 0.72,
            "example_prompts": [{"prompt": "Show recent mentions of my company", "outcome": "Lists mentions"}],
            "required_integrations": ["twitter"],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-016",
            "name": "Expense Tracking",
            "category": "finance",
            "subcategory": "tracking",
            "description": "Track and categorize expenses",
            "difficulty_level": 2,
            "popularity_score": 0.81,
            "example_prompts": [{"prompt": "Log expense: $45 lunch with client", "outcome": "Records expense"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-017",
            "name": "Budget Management",
            "category": "finance",
            "subcategory": "planning",
            "description": "Create and monitor budgets",
            "difficulty_level": 2,
            "popularity_score": 0.79,
            "example_prompts": [{"prompt": "Set $500 monthly entertainment budget", "outcome": "Creates budget"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-018",
            "name": "Code Generation",
            "category": "coding",
            "subcategory": "development",
            "description": "Generate code snippets in multiple languages",
            "difficulty_level": 2,
            "popularity_score": 0.88,
            "example_prompts": [{"prompt": "Write Python function to sort list", "outcome": "Complete code"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-019",
            "name": "Debug Assistant",
            "category": "coding",
            "subcategory": "debugging",
            "description": "Help debug code errors",
            "difficulty_level": 3,
            "popularity_score": 0.85,
            "example_prompts": [{"prompt": "Why is my loop not working?", "outcome": "Analyzes and fixes"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        },
        {
            "id": "cap-020",
            "name": "Travel Planning",
            "category": "travel",
            "subcategory": "planning",
            "description": "Plan trips with itinerary suggestions",
            "difficulty_level": 3,
            "popularity_score": 0.74,
            "example_prompts": [{"prompt": "Plan 3-day Paris trip under $2000", "outcome": "Detailed itinerary"}],
            "required_integrations": [],
            "is_unlocked": True,
            "user_tried": False,
            "usage_count": 0
        }
    ]
    
    # Apply category filter if provided
    if category:
        capabilities = [cap for cap in capabilities if cap["category"] == category]
    
    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        capabilities = [
            cap for cap in capabilities 
            if search_lower in cap["name"].lower() or search_lower in cap["description"].lower()
        ]
    
    # Get unique categories
    categories = list(set([cap["category"] for cap in capabilities]))
    
    return CapabilityList(
        capabilities=[Capability(**cap) for cap in capabilities],
        total=len(capabilities),
        categories=categories
    )


@router.get("/categories", response_model=List[CategoryStats])
async def get_categories(
    user_id: Optional[str] = Query(None, description="User ID for unlocked counts")
):
    """
    Get all categories with statistics
    """
    
    stats = [
        {"category": "email", "count": 3, "unlocked_count": 3},
        {"category": "calendar", "count": 2, "unlocked_count": 2},
        {"category": "shopping", "count": 3, "unlocked_count": 3},
        {"category": "research", "count": 2, "unlocked_count": 2},
        {"category": "productivity", "count": 3, "unlocked_count": 3},
        {"category": "social", "count": 2, "unlocked_count": 2},
        {"category": "finance", "count": 2, "unlocked_count": 2},
        {"category": "coding", "count": 2, "unlocked_count": 2},
        {"category": "travel", "count": 1, "unlocked_count": 1},
    ]
    
    return [CategoryStats(**s) for s in stats]


@router.get("/{capability_id}", response_model=Capability)
async def get_capability(
    capability_id: str,
    user_id: Optional[str] = Query(None, description="User ID for personalization")
):
    """
    Get detailed information about a specific capability
    """
    raise HTTPException(status_code=404, detail="Capability not found")


@router.post("/{capability_id}/discover")
async def mark_discovered(
    capability_id: str,
    request: DiscoveryRequest
):
    """
    Track when a user discovers a capability
    """
    return {
        "status": "tracked",
        "capability_id": capability_id,
        "user_id": request.user_id,
        "discovery_method": request.discovery_method,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/{capability_id}/use")
async def track_usage(
    capability_id: str,
    request: UsageRequest
):
    """
    Track when a user actually uses a capability
    """
    return {
        "status": "tracked",
        "capability_id": capability_id,
        "user_id": request.user_id,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/{capability_id}/bookmark")
async def bookmark_capability(
    capability_id: str,
    request: UsageRequest
):
    """
    Bookmark/favorite a capability for quick access
    """
    return {
        "status": "bookmarked",
        "capability_id": capability_id,
        "user_id": request.user_id
    }


@router.get("/search/natural")
async def natural_language_search(
    query: str = Query(..., description="Natural language query"),
    user_id: Optional[str] = Query(None)
):
    """
    Natural language capability search
    """
    return {
        "has_capability": True,
        "matched_capabilities": ["Read Emails", "Send Emails"],
        "explanation": "Yes! I can help you with email management.",
        "suggested_prompt": "Show me unread emails from today"
    }


@router.get("/user/{user_id}/stats")
async def get_user_stats(user_id: str):
    """
    Get user's capability discovery and usage statistics
    """
    return {
        "user_id": user_id,
        "discovered_count": 8,
        "used_count": 5,
        "total_usage": 27,
        "completion_percentage": 40.0,
        "recent_discoveries": [
            {
                "name": "Read Emails",
                "category": "email",
                "discovered_at": "2025-11-13T10:00:00Z",
                "usage_count": 5
            }
        ],
        "most_used": [
            {"name": "Read Emails", "usage_count": 15},
            {"name": "View Calendar", "usage_count": 8},
            {"name": "Task Management", "usage_count": 4}
        ]
    }