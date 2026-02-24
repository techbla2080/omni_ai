import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from services.web_search import web_search_service

async def test():
    print("=" * 60)
    print("🔍 TESTING SERPER API")
    print("=" * 60)
    print()
    
    # Test search
    print("Searching for 'Python programming'...")
    results = await web_search_service.search("Python programming", count=3)
    
    print()
    
    # Check for errors
    if results.get("error"):
        print("❌ FAILED!")
        print(f"Error: {results['error']}")
        print()
        print("Possible reasons:")
        print("1. SERPER_API_KEY not set in .env")
        print("2. API key is invalid")
        print("3. No internet connection")
        print("4. Serper API is down")
        return False
    
    # Success!
    print("✅ SUCCESS! Serper API is working!")
    print()
    print(f"Query: {results['query']}")
    print(f"Results found: {results['count']}")
    print()
    
    if results['results']:
        print("Top result:")
        print(f"  Title: {results['results'][0]['title']}")
        print(f"  Source: {results['results'][0]['source']}")
        print(f"  URL: {results['results'][0]['url']}")
        print()
        print(f"  Description: {results['results'][0]['description'][:100]}...")
    
    print()
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = asyncio.run(test())
    if success:
        print("🎉 Your Serper API is working perfectly!")
    else:
        print("💔 Serper API test failed. Check the errors above.")