"""
Test Script for Smart AI IDE
Tests the capability seeding, API endpoints, and chat integration
"""

import requests
import json
from typing import Dict

BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_json(data: Dict):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=2))


def test_capability_list():
    """Test 1: List all capabilities"""
    print_section("TEST 1: List All Capabilities")
    
    response = requests.get(f"{BASE_URL}/api/v1/capabilities")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Found {data['total']} capabilities")
        print(f"✅ Categories: {', '.join(data['categories'])}\n")
        
        # Show first 3
        print("First 3 capabilities:")
        for cap in data['capabilities'][:3]:
            print(f"\n  • {cap['name']} ({cap['category']})")
            print(f"    {cap['description'][:80]}...")
            print(f"    Difficulty: {cap['difficulty_level']}/5")
            print(f"    Examples: {len(cap['example_prompts'])} prompts")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def test_category_filter():
    """Test 2: Filter capabilities by category"""
    print_section("TEST 2: Filter by Category (Email)")
    
    response = requests.get(f"{BASE_URL}/api/v1/capabilities?category=email")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Found {data['total']} email capabilities\n")
        
        for cap in data['capabilities']:
            print(f"  • {cap['name']}")
            print(f"    Example: \"{cap['example_prompts'][0]['prompt']}\"")
    else:
        print(f"❌ Error: {response.status_code}")


def test_capability_search():
    """Test 3: Search capabilities"""
    print_section("TEST 3: Search Capabilities")
    
    search_terms = ["email", "calendar", "task"]
    
    for term in search_terms:
        response = requests.get(
            f"{BASE_URL}/api/v1/capabilities",
            params={"search": term}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search '{term}': found {data['total']} matches")
        else:
            print(f"❌ Search '{term}' failed")


def test_natural_language_search():
    """Test 4: Natural language capability search"""
    print_section("TEST 4: Natural Language Search")
    
    queries = [
        "Can you help me with emails?",
        "What can you do with my calendar?",
        "I need to track expenses"
    ]
    
    for query in queries:
        response = requests.get(
            f"{BASE_URL}/api/v1/capabilities/search/natural",
            params={"query": query}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nQuery: \"{query}\"")
            print(f"  Has capability: {data['has_capability']}")
            print(f"  Matches: {', '.join(data['matched_capabilities'])}")
            print(f"  Suggestion: \"{data['suggested_prompt']}\"")
        else:
            print(f"❌ Query failed: {query}")


def test_chat_capability_trigger():
    """Test 5: Chat endpoint capability detection"""
    print_section("TEST 5: Chat - 'What can you do?' Detection")
    
    test_messages = [
        "What can you do?",
        "Show me your features",
        "Help me discover what's possible",
        "Hello, how are you?"  # Should NOT trigger
    ]
    
    for message in test_messages:
        response = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json={
                "message": message,
                "user_id": "test-user-123"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n📨 Message: \"{message}\"")
            print(f"   Response type: {data['response_type']}")
            print(f"   Latency: {data['latency_ms']}ms")
            
            if data['response_type'] == 'capability_list':
                print(f"   ✅ Capability list triggered!")
                print(f"   Capabilities shown: {len(data.get('capabilities', []))}")
                print(f"   Suggestions: {len(data.get('suggestions', []))}")
            else:
                print(f"   💬 Normal chat response")
        else:
            print(f"❌ Chat failed: {message}")


def test_capability_tracking():
    """Test 6: Track capability discovery and usage"""
    print_section("TEST 6: Capability Discovery & Usage Tracking")
    
    test_user = "test-user-123"
    test_capability = "capability-id-12345"
    
    # Test discovery tracking
    print("Testing discovery tracking...")
    response = requests.post(
        f"{BASE_URL}/api/v1/capabilities/{test_capability}/discover",
        json={
            "user_id": test_user,
            "discovery_method": "browse"
        }
    )
    
    if response.status_code == 200:
        print("✅ Discovery tracked")
    else:
        print(f"❌ Discovery tracking failed: {response.status_code}")
    
    # Test usage tracking
    print("\nTesting usage tracking...")
    for i in range(3):
        response = requests.post(
            f"{BASE_URL}/api/v1/capabilities/{test_capability}/use",
            json={"user_id": test_user}
        )
        
        if response.status_code == 200:
            print(f"✅ Usage {i+1} tracked")
        else:
            print(f"❌ Usage tracking failed")


def test_user_stats():
    """Test 7: Get user statistics"""
    print_section("TEST 7: User Statistics")
    
    test_user = "test-user-123"
    
    response = requests.get(
        f"{BASE_URL}/api/v1/capabilities/user/{test_user}/stats"
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✅ User stats retrieved:\n")
        print(f"  Capabilities discovered: {data['discovered_count']}")
        print(f"  Capabilities used: {data['used_count']}")
        print(f"  Total usage count: {data['total_usage']}")
        print(f"  Completion: {data['completion_percentage']}%")
        
        print("\n  Most used capabilities:")
        for cap in data.get('most_used', [])[:3]:
            print(f"    • {cap['name']}: {cap['usage_count']} times")
    else:
        print(f"❌ Stats retrieval failed: {response.status_code}")


def test_categories_endpoint():
    """Test 8: Get all categories"""
    print_section("TEST 8: Category Statistics")
    
    response = requests.get(f"{BASE_URL}/api/v1/capabilities/categories")
    
    if response.status_code == 200:
        categories = response.json()
        print("✅ Categories retrieved:\n")
        
        for cat in categories:
            print(f"  {cat['category'].upper()}")
            print(f"    Total: {cat['count']} capabilities")
            print(f"    Unlocked: {cat['unlocked_count']}")
    else:
        print(f"❌ Categories retrieval failed: {response.status_code}")


def run_all_tests():
    """Run all tests"""
    print("\n" + "🚀" * 35)
    print("  SMART AI IDE - INTEGRATION TEST SUITE")
    print("🚀" * 35)
    
    tests = [
        test_capability_list,
        test_category_filter,
        test_capability_search,
        test_natural_language_search,
        test_chat_capability_trigger,
        test_capability_tracking,
        test_user_stats,
        test_categories_endpoint
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
    
    print_section("✅ TEST SUITE COMPLETE")
    print("\nNext steps:")
    print("  1. Check the results above")
    print("  2. Fix any failing endpoints")
    print("  3. Test in your browser: http://localhost:8000/docs")
    print("  4. Try the chat interface with 'What can you do?'")


if __name__ == "__main__":
    print("\n⚠️  Make sure your FastAPI server is running on http://localhost:8000")
    print("   Run: python backend/main.py\n")
    
    input("Press ENTER to start tests...")
    
    run_all_tests()