"""Test script for GraphRAGRetrieval and OpenAI Agent integration."""

import asyncio
import os
from opponent_simulator import OpponentSimulator
from legal_context import LawyerInfo

async def test_opponent_simulator():
    """Test the integrated OpponentSimulator with GraphRAGRetrieval and OpenAI Agents."""
    
    # Initialize the simulator
    config = {
        "search_strategy": {
            "opposite_outcome_weight": 0.8,
            "counter_argument_weight": 0.7
        },
        "max_precedents": 5,
        "confidence_threshold": 0.65
    }
    
    # Create a mock OpenAI client (the Agent SDK will handle this internally)
    openai_client = None  # Not needed with the new Agent SDK
    
    simulator = OpponentSimulator(
        graphrag_base_url="http://localhost:8000",  # Not used with local GraphRAGRetrieval
        openai_client=openai_client,
        config=config
    )
    
    # Test case 1: Patent infringement argument
    print("\n=== Test Case 1: Patent Infringement ===")
    our_argument = "The defendant's smartphone design infringes our client's registered design patents."
    case_context = {
        "case_type": "Patent Infringement",
        "court": "U.S. District Court",
        "our_role": "plaintiff",
        "jurisdiction": "US",
        "tenant": "default"
    }
    
    opposing_counsel = LawyerInfo(
        id="lawyer_001",
        name="Jane Smith",
        years_experience=15,
        specializations=["Patent Law", "Intellectual Property"],
        win_rate=0.75
    )
    
    try:
        result = await simulator.simulate_opponent_response(
            our_argument=our_argument,
            case_context=case_context,
            opposing_counsel=opposing_counsel,
            our_position="plaintiff"
        )
        
        print(f"\nOpposing Argument:")
        print(f"{result['opposing_argument'][:500]}...")
        print(f"\nStrength Assessment: {result['strength_assessment']['level']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"\nSuggested Counters:")
        for counter in result['suggested_counters'][:2]:
            print(f"- {counter['text'][:150]}...")
        
    except Exception as e:
        print(f"Error in test case 1: {e}")
    
    # Test case 2: Contract breach argument
    print("\n\n=== Test Case 2: Contract Breach ===")
    our_argument = "The defendant violated the service level agreement by exceeding maximum allowed downtime."
    case_context = {
        "case_type": "Contract Breach",
        "court": "Superior Court",
        "our_role": "plaintiff",
        "jurisdiction": "CA",
        "tenant": "default"
    }
    
    try:
        result = await simulator.simulate_opponent_response(
            our_argument=our_argument,
            case_context=case_context,
            opposing_counsel=None,  # No specific opposing counsel
            our_position="plaintiff"
        )
        
        print(f"\nOpposing Argument:")
        print(f"{result['opposing_argument'][:500]}...")
        print(f"\nIdentified Weaknesses:")
        for weakness in result['identified_weaknesses'][:2]:
            print(f"- {weakness['description']}")
        
    except Exception as e:
        print(f"Error in test case 2: {e}")
    
    print("\n=== Tests Complete ===")

if __name__ == "__main__":
    # Set OpenAI API key if not already set
    if not os.getenv("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)
    
    # Run the async tests
    asyncio.run(test_opponent_simulator())