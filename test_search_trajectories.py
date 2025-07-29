#!/usr/bin/env python3
"""
Simple test script for GraphRAGClient.search_trajectories function

This script tests the search_trajectories method with complex queries.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the pipeline_2 directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded environment variables from .env file")
except ImportError:
    print("⚠️ python-dotenv not installed. Install with: pip install python-dotenv")
    # Fallback: try to load from setup_env.py
    try:
        from setup_env import setup_test_env
        setup_test_env()
    except ImportError:
        print("⚠️ setup_env.py not found. Please set environment variables manually.")
except Exception as e:
    print(f"⚠️ Could not load .env file: {e}")

from graphRAG.graphrag_client import GraphRAGClient


async def test_complex_queries():
    """Test search_trajectories with complex queries that should trigger Layer 2."""
    
    print("🔍 Testing GraphRAGClient.search_trajectories() - Complex Queries")
    print("=" * 60)
    
    client = GraphRAGClient()
    
    # Complex queries that should trigger LLM task type derivation
    complex_queries = [
        "Add a reminder for mothers day next week",
        "Add a note to my doctor's appointment on August 10 to ask for a sick leave.",
    ]
    
    for i, query in enumerate(complex_queries, 1):
        print(f"\n--- Complex Query {i}: '{query}' ---")
        
        try:
            context = await client.search_trajectories(
                query=query,
                max_results=3,
                max_context_length=2000
            )
            
            if context:
                print(f"✅ Found context ({len(context)} chars)")
                
                # Extract and print DIRECT SEMANTIC MATCHES
                if "DIRECT SEMANTIC MATCHES" in context:
                    print("\n🎯 Layer 1 (Direct Search) was triggered!")
                    print("📄 DIRECT SEMANTIC MATCHES:")
                    print("-" * 40)
                    direct_section = context.split("--- DIRECT SEMANTIC MATCHES ---")[1].split("---")[0] if "--- DIRECT SEMANTIC MATCHES ---" in context else ""
                    if direct_section:
                        # Extract only the instruction/title part (before "Steps:")
                        lines = direct_section.strip().split('\n')
                        for line in lines:
                            if line.strip() and not line.startswith('Steps:') and not line.startswith('Codes:') and not line.startswith('Example'):
                                print(line.strip())
                    print("-" * 40)
                
                # Extract and print TASK TYPE MATCHES
                if "TASK TYPE MATCHES" in context:
                    print("\n🎯 Layer 2 (Task Type Search) was triggered!")
                    print("📄 TASK TYPE MATCHES:")
                    print("-" * 40)
                    task_section = context.split("--- TASK TYPE MATCHES ---")[1].split("---")[0] if "--- TASK TYPE MATCHES ---" in context else ""
                    if task_section:
                        # Extract only the instruction/title part (before "Steps:")
                        lines = task_section.strip().split('\n')
                        for line in lines:
                            if line.strip() and not line.startswith('Steps:') and not line.startswith('Codes:') and not line.startswith('Example') and not line.startswith('Derived Task Type:'):
                                print(line.strip())
                    print("-" * 40)
            else:
                print("ℹ️ No results found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 40)


if __name__ == "__main__":
    print("🚀 Testing GraphRAGClient.search_trajectories() Function")
    print("=" * 70)
    
    # Run the test
    asyncio.run(test_complex_queries())
    
    print("\n✅ Complex queries test completed!") 