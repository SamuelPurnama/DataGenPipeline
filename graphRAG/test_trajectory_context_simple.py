#!/usr/bin/env python3
"""
Simple test script for trajectory node context functionality.
"""

import asyncio
import os
from pipeline_trajectory_generation import fetch_trajectory_nodes

async def test_trajectory_node_context():
    """Test the trajectory node context functionality."""
    
    # Test cases
    test_instructions = [
        "Schedule a meeting with John tomorrow at 2pm",
        "Create a new calendar event",
        "Add a reccuring event on mondays"
    ]
    
    print("🧪 Testing Trajectory Node Context Functionality")
    print("=" * 60)
    
    for i, instruction in enumerate(test_instructions, 1):
        print(f"\n📋 Test Case {i}:")
        print(f"Instruction: {instruction}")
        
        try:
            # Test with different context lengths
            for max_length in [3000]:
                print(f"\n🔍 Testing with max_context_length={max_length}")
                context = await fetch_trajectory_nodes(
                    instruction, 
                    max_results=4, 
                    max_context_length=max_length
                )
                
                if context:
                    print(f"✅ Node context fetched successfully")
                    print(f"📏 Context length: {len(context)} characters")
                    print(f"📄 Context content:")
                    print("-" * 40)
                    print(context)
                    print("-" * 40)
                    
                    # Check if truncation occurred
                    if len(context) > max_length:
                        print(f"❌ Context length ({len(context)}) exceeds limit ({max_length})")
                    else:
                        print(f"✅ Context length within limit")
                else:
                    print("ℹ️ No node context found (this is normal if no data exists)")
                    
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("=" * 60)

async def main():
    """Main test function."""
    print("🚀 Starting Trajectory Node Context Tests")
    print("Make sure you have Graphiti configured with:")
    print("- GRAPHITI_URI environment variable")
    print("- GRAPHITI_USER environment variable") 
    print("- GRAPHITI_PASSWORD environment variable")
    print()
    
    await test_trajectory_node_context()
    
    print("\n🎉 Test completed!")

if __name__ == "__main__":
    asyncio.run(main()) 