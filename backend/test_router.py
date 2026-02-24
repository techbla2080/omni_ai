"""
Test Model Router
Verify intelligent model selection works correctly
"""

from services.model_router import model_router


def test_router():
    print("=" * 60)
    print("🧪 TESTING MODEL ROUTER")
    print("=" * 60)
    print()
    
    test_cases = [
        {
            "name": "Simple greeting",
            "query": "Hi",
            "has_search": False,
            "expected": "Should use default model"
        },
        {
            "name": "Search query",
            "query": "What's the latest AI news?",
            "has_search": True,
            "expected": "Should use llama3.1:8b (search requires quality)"
        },
        {
            "name": "Complex explanation",
            "query": "Explain quantum computing in detail with examples and step by step breakdown of how qubits work and their applications",
            "has_search": False,
            "expected": "Should use llama3.1:8b (complex query)"
        },
        {
            "name": "Simple question",
            "query": "What is Python?",
            "has_search": False,
            "expected": "Should use default model"
        },
        {
            "name": "Code generation",
            "query": "Write a Python function to calculate fibonacci numbers with memoization and explain how it works step by step",
            "has_search": False,
            "expected": "Should use llama3.1:8b (code + complex)"
        },
        {
            "name": "Medium question",
            "query": "How do I install Docker on Ubuntu?",
            "has_search": False,
            "expected": "Could use 3b or 8b"
        },
        {
            "name": "Very short query",
            "query": "Hello!",
            "has_search": False,
            "expected": "Should use default model"
        },
        {
            "name": "Search with short query",
            "query": "Bitcoin price",
            "has_search": True,
            "expected": "Should use llama3.1:8b (search)"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"  Query: '{test['query'][:60]}{'...' if len(test['query']) > 60 else ''}'")
        print(f"  Has search: {test['has_search']}")
        
        selection = model_router.choose_model(
            query=test['query'],
            has_search_results=test['has_search']
        )
        
        print(f"  ✅ Model: {selection['model']}")
        print(f"  📝 Reason: {selection['reason']}")
        print(f"  ⭐ Quality: {selection['quality_score']}/10")
        print(f"  ⚡ Speed: {selection['speed']}")
        print(f"  💾 RAM: {selection['ram_required']}GB")
        print(f"  Expected: {test['expected']}")
        
        # Basic validation
        if test['has_search'] and selection['model'] != 'llama3.1:8b':
            print(f"  ⚠️  WARNING: Search queries should use llama3.1:8b!")
            failed += 1
        else:
            passed += 1
        
        print()
    
    print("=" * 60)
    print(f"✅ Tests passed: {passed}/{len(test_cases)}")
    if failed > 0:
        print(f"⚠️  Tests with warnings: {failed}/{len(test_cases)}")
    print("=" * 60)
    print()
    
    # Test model validation
    print("Testing model validation...")
    print(f"  'llama3.1:8b' valid: {model_router.validate_model('llama3.1:8b')}")
    print(f"  'llama3.2:3b' valid: {model_router.validate_model('llama3.2:3b')}")
    print(f"  'gpt-4' valid: {model_router.validate_model('gpt-4')}")
    print()
    
    # Test available models
    print("Available models:")
    models = model_router.get_available_models()
    for model_name, specs in models.items():
        print(f"  {model_name}:")
        print(f"    Quality: {specs['quality']}/10")
        print(f"    Speed: {specs['speed']}")
        print(f"    RAM: {specs['ram_gb']}GB")
        print(f"    Best for: {', '.join(specs['best_for'])}")
    
    print()
    print("=" * 60)
    print("🎉 ALL ROUTER TESTS COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    test_router()