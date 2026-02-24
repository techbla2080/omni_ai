"""
Seed script for OmniAI capabilities
Populates the database with 20 initial capabilities across different categories
"""

import asyncio
import asyncpg
import json
from datetime import datetime

# Database connection string
DATABASE_URL = "postgresql://omniai:omniai@localhost:5432/omniai"


async def seed_capabilities():
    """Seed initial capabilities into the database"""
    
    print("🌱 Starting capability seeding...")
    
    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL)
    
    capabilities = [
        # EMAIL CATEGORY
        {
            "name": "Read Emails",
            "category": "email",
            "subcategory": "reading",
            "description": "View and read your emails with natural language queries. Search by sender, date, or content.",
            "difficulty_level": 1,
            "popularity_score": 0.95,
            "required_integrations": ["gmail"],
            "example_prompts": [
                {
                    "prompt": "Show me unread emails from today",
                    "outcome": "Displays list of unread emails with sender, subject, and preview"
                },
                {
                    "prompt": "What did Sarah say in her last email?",
                    "outcome": "Shows the full content of Sarah's most recent email"
                },
                {
                    "prompt": "Find emails about the project deadline",
                    "outcome": "Searches and displays relevant emails mentioning deadlines"
                }
            ]
        },
        {
            "name": "Send Emails",
            "category": "email",
            "subcategory": "writing",
            "description": "Compose and send emails with AI assistance. Just describe what you want to say.",
            "difficulty_level": 1,
            "popularity_score": 0.90,
            "required_integrations": ["gmail"],
            "example_prompts": [
                {
                    "prompt": "Send an email to john@company.com saying I'll be 10 minutes late",
                    "outcome": "Composes and sends a professional email about being late"
                },
                {
                    "prompt": "Reply to the last email from Mark saying thanks",
                    "outcome": "Finds Mark's email and sends a thank you reply"
                }
            ]
        },
        {
            "name": "Draft Smart Emails",
            "category": "email",
            "subcategory": "writing",
            "description": "AI-powered email drafting that learns your writing style and suggests improvements.",
            "difficulty_level": 2,
            "popularity_score": 0.85,
            "required_integrations": ["gmail"],
            "example_prompts": [
                {
                    "prompt": "Draft a professional email declining the meeting invite",
                    "outcome": "Creates a polite, professional decline email matching your tone"
                }
            ]
        },
        
        # CALENDAR CATEGORY
        {
            "name": "View Calendar",
            "category": "calendar",
            "subcategory": "reading",
            "description": "Check your schedule and upcoming events with natural language.",
            "difficulty_level": 1,
            "popularity_score": 0.92,
            "required_integrations": ["google_calendar"],
            "example_prompts": [
                {
                    "prompt": "What's on my calendar today?",
                    "outcome": "Lists all events scheduled for today with times"
                },
                {
                    "prompt": "When is my next meeting?",
                    "outcome": "Shows the next upcoming meeting with details"
                },
                {
                    "prompt": "Am I free tomorrow afternoon?",
                    "outcome": "Checks calendar and confirms availability"
                }
            ]
        },
        {
            "name": "Schedule Meetings",
            "category": "calendar",
            "subcategory": "writing",
            "description": "Create calendar events and send meeting invites automatically.",
            "difficulty_level": 2,
            "popularity_score": 0.88,
            "required_integrations": ["google_calendar"],
            "example_prompts": [
                {
                    "prompt": "Schedule a 1-hour meeting with Alex tomorrow at 2pm",
                    "outcome": "Creates event and sends invite to Alex"
                },
                {
                    "prompt": "Block my calendar for focus time every morning 9-11am",
                    "outcome": "Creates recurring focus time blocks"
                }
            ]
        },
        
        # SHOPPING CATEGORY
        {
            "name": "Find Products",
            "category": "shopping",
            "subcategory": "search",
            "description": "Search for products across multiple online stores with price comparison.",
            "difficulty_level": 1,
            "popularity_score": 0.80,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Find wireless headphones under $100",
                    "outcome": "Shows top-rated wireless headphones with prices and reviews"
                },
                {
                    "prompt": "What's the best laptop for programming?",
                    "outcome": "Recommends laptops with comparisons and specs"
                }
            ]
        },
        {
            "name": "Track Prices",
            "category": "shopping",
            "subcategory": "monitoring",
            "description": "Monitor product prices and get alerts when they drop.",
            "difficulty_level": 2,
            "popularity_score": 0.75,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Alert me when the iPhone 15 drops below $700",
                    "outcome": "Sets up price tracking and sends notification when condition met"
                }
            ]
        },
        {
            "name": "Make Purchases",
            "category": "shopping",
            "subcategory": "transaction",
            "description": "Complete purchases with saved payment methods securely.",
            "difficulty_level": 3,
            "popularity_score": 0.70,
            "required_integrations": ["stripe", "shopify"],
            "example_prompts": [
                {
                    "prompt": "Buy the wireless headphones we found earlier",
                    "outcome": "Completes checkout with saved payment method"
                }
            ]
        },
        
        # RESEARCH CATEGORY
        {
            "name": "Web Research",
            "category": "research",
            "subcategory": "information",
            "description": "Deep web research with source compilation and summarization.",
            "difficulty_level": 2,
            "popularity_score": 0.87,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Research the latest developments in quantum computing",
                    "outcome": "Provides comprehensive summary with credible sources"
                },
                {
                    "prompt": "Compare pros and cons of React vs Vue",
                    "outcome": "Detailed comparison table with use cases"
                }
            ]
        },
        {
            "name": "Fact Checking",
            "category": "research",
            "subcategory": "verification",
            "description": "Verify claims and fact-check information against reliable sources.",
            "difficulty_level": 2,
            "popularity_score": 0.78,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Is it true that coffee dehydrates you?",
                    "outcome": "Fact-checks claim with scientific sources"
                }
            ]
        },
        
        # PRODUCTIVITY CATEGORY
        {
            "name": "Task Management",
            "category": "productivity",
            "subcategory": "tasks",
            "description": "Create, track, and manage your to-do lists and tasks.",
            "difficulty_level": 1,
            "popularity_score": 0.89,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Add 'finish project report' to my tasks",
                    "outcome": "Creates task with reminder"
                },
                {
                    "prompt": "What tasks do I have for this week?",
                    "outcome": "Lists all pending tasks with deadlines"
                }
            ]
        },
        {
            "name": "Note Taking",
            "category": "productivity",
            "subcategory": "notes",
            "description": "Quick note capture and organization with smart tagging.",
            "difficulty_level": 1,
            "popularity_score": 0.84,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Take a note: Meeting with CEO went well, discussing Q2 goals",
                    "outcome": "Saves note with auto-generated tags and timestamp"
                }
            ]
        },
        {
            "name": "Reminders",
            "category": "productivity",
            "subcategory": "alerts",
            "description": "Set time-based or location-based reminders for important tasks.",
            "difficulty_level": 1,
            "popularity_score": 0.91,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Remind me to call mom at 5pm",
                    "outcome": "Sets reminder with notification at specified time"
                }
            ]
        },
        
        # SOCIAL CATEGORY
        {
            "name": "Social Media Posts",
            "category": "social",
            "subcategory": "content",
            "description": "Create and schedule social media content across platforms.",
            "difficulty_level": 2,
            "popularity_score": 0.76,
            "required_integrations": ["twitter", "linkedin"],
            "example_prompts": [
                {
                    "prompt": "Post to Twitter: Excited to announce our new product launch!",
                    "outcome": "Publishes tweet immediately"
                }
            ]
        },
        {
            "name": "Social Monitoring",
            "category": "social",
            "subcategory": "monitoring",
            "description": "Monitor mentions, trends, and engagement across social platforms.",
            "difficulty_level": 2,
            "popularity_score": 0.72,
            "required_integrations": ["twitter", "linkedin"],
            "example_prompts": [
                {
                    "prompt": "Show me recent mentions of my company",
                    "outcome": "Lists all recent social media mentions"
                }
            ]
        },
        
        # FINANCE CATEGORY
        {
            "name": "Expense Tracking",
            "category": "finance",
            "subcategory": "tracking",
            "description": "Track and categorize expenses automatically.",
            "difficulty_level": 2,
            "popularity_score": 0.81,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Log expense: $45 for lunch with client",
                    "outcome": "Records expense with auto-categorization"
                }
            ]
        },
        {
            "name": "Budget Management",
            "category": "finance",
            "subcategory": "planning",
            "description": "Create and monitor budgets with spending alerts.",
            "difficulty_level": 2,
            "popularity_score": 0.79,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Set a $500 monthly budget for entertainment",
                    "outcome": "Creates budget with tracking and alerts"
                }
            ]
        },
        
        # CODING CATEGORY
        {
            "name": "Code Generation",
            "category": "coding",
            "subcategory": "development",
            "description": "Generate code snippets and full functions in multiple languages.",
            "difficulty_level": 2,
            "popularity_score": 0.88,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Write a Python function to sort a list of dictionaries by a key",
                    "outcome": "Provides complete, tested code with explanation"
                }
            ]
        },
        {
            "name": "Debug Assistant",
            "category": "coding",
            "subcategory": "debugging",
            "description": "Help debug code errors and suggest fixes.",
            "difficulty_level": 3,
            "popularity_score": 0.85,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Why is my for loop not iterating correctly?",
                    "outcome": "Analyzes code and explains the issue with solution"
                }
            ]
        },
        
        # TRAVEL CATEGORY
        {
            "name": "Travel Planning",
            "category": "travel",
            "subcategory": "planning",
            "description": "Plan trips with itinerary suggestions and bookings.",
            "difficulty_level": 3,
            "popularity_score": 0.74,
            "required_integrations": [],
            "example_prompts": [
                {
                    "prompt": "Plan a 3-day trip to Paris under $2000",
                    "outcome": "Creates detailed itinerary with costs and suggestions"
                }
            ]
        }
    ]
    
    # Insert capabilities
    inserted_count = 0
    for cap in capabilities:
        try:
            await conn.execute("""
                INSERT INTO capabilities (
                    name, category, subcategory, description,
                    difficulty_level, popularity_score,
                    example_prompts, required_integrations
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, 
                cap['name'],
                cap['category'],
                cap.get('subcategory'),
                cap['description'],
                cap['difficulty_level'],
                cap['popularity_score'],
                json.dumps(cap['example_prompts']),
                cap.get('required_integrations', [])
            )
            inserted_count += 1
            print(f"✅ Inserted: {cap['name']}")
        except Exception as e:
            print(f"❌ Error inserting {cap['name']}: {e}")
    
    # Close connection
    await conn.close()
    
    print(f"\n🎉 Successfully seeded {inserted_count} capabilities!")
    print("\n📊 Breakdown by category:")
    
    # Count by category
    categories = {}
    for cap in capabilities:
        cat = cap['category']
        categories[cat] = categories.get(cat, 0) + 1
    
    for cat, count in sorted(categories.items()):
        print(f"   {cat}: {count} capabilities")


if __name__ == "__main__":
    asyncio.run(seed_capabilities())