import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client import OpenAIClient, LLMConfig
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from trajectory_entity_types import get_entity_types

load_dotenv()

# Token tracking class
class TokenTracker:
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0
    
    def add_usage(self, usage):
        """Add token usage from an OpenAI API response"""
        if hasattr(usage, 'total_tokens'):
            self.total_tokens += usage.total_tokens
            self.prompt_tokens += usage.prompt_tokens
            self.completion_tokens += usage.completion_tokens
            self.call_count += 1
            
            print(f"📊 API Call #{self.call_count}:")
            print(f"   📝 Input tokens: {usage.prompt_tokens}")
            print(f"   💬 Output tokens: {usage.completion_tokens}")
            print(f"   🔢 Call total: {usage.total_tokens}")
            print(f"   📈 Running total: {self.total_tokens}")
    
    def print_summary(self):
        """Print final token usage summary"""
        print("\n" + "="*50)
        print("📊 FINAL TOKEN USAGE SUMMARY")
        print("="*50)
        print(f"🔥 Total API calls: {self.call_count}")
        print(f"📝 Total input tokens: {self.prompt_tokens}")
        print(f"💬 Total output tokens: {self.completion_tokens}")
        print(f"🔢 Total tokens used: {self.total_tokens}")
        
        # Calculate approximate cost (rough estimates)
        # GPT-4o pricing: ~$2.50/1M input, ~$10/1M output tokens
        input_cost = (self.prompt_tokens / 1_000_000) * 2.50
        output_cost = (self.completion_tokens / 1_000_000) * 10.00
        total_cost = input_cost + output_cost
        
        print(f"💰 Estimated cost: ${total_cost:.4f}")
        print("   (Input: ${:.4f} + Output: ${:.4f})".format(input_cost, output_cost))
        print("="*50)

# Custom OpenAI client with token tracking
class TrackedOpenAIClient(OpenAIClient):
    def __init__(self, config, token_tracker):
        super().__init__(config)
        self.token_tracker = token_tracker
        
    async def _create_completion(self, model, messages, temperature, max_tokens, response_model=None):
        response = await super()._create_completion(model, messages, temperature, max_tokens, response_model)
        
        # Track token usage if available
        if hasattr(response, 'usage'):
            self.token_tracker.add_usage(response.usage)
        
        return response
    
    async def _create_structured_completion(self, model, messages, temperature, max_tokens, response_model):
        response = await super()._create_structured_completion(model, messages, temperature, max_tokens, response_model)
        
        # Track token usage if available
        if hasattr(response, 'usage'):
            self.token_tracker.add_usage(response.usage)
        
        return response

async def main():
    # OpenAI Configuration
    api_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_MODEL', 'gpt-4o')
    base_url = os.getenv('OPENAI_API_BASE', '')

    # Neo4j Configuration
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD')
    neo4j_database = os.getenv('NEO4J_DATABASE', 'neo4j')

    # Validate required environment variables
    if not api_key:
        raise ValueError('OPENAI_API_KEY must be set in the environment.')
    
    if not neo4j_password:
        raise ValueError('NEO4J_PASSWORD must be set in the environment.')

    print(f"Connecting to Neo4j at: {neo4j_uri}")
    print(f"Using database: {neo4j_database}")
    print(f"Using OpenAI model: {model}")

    # Initialize token tracker
    token_tracker = TokenTracker()
    
    # Create Neo4j driver with custom database name
    neo4j_driver = Neo4jDriver(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        database=neo4j_database
    )

    llm_config = LLMConfig(
        api_key=api_key,
        model=model,
        base_url=base_url if base_url else None,
        max_tokens=4096,
        temperature=0.1,
    )
    llm_client = TrackedOpenAIClient(config=llm_config, token_tracker=token_tracker)

    embedder_config = OpenAIEmbedderConfig(
        api_key=api_key,
        base_url=base_url if base_url else None,
        embedding_model="text-embedding-3-small"
    )
    embedder = OpenAIEmbedder(config=embedder_config)

    graphiti = Graphiti(
        graph_driver=neo4j_driver,
        llm_client=llm_client,
        embedder=embedder
    )

    try:
        await graphiti.build_indices_and_constraints()
        print("Database indices and constraints initialized.")

        input_text = """
        Web Trajectory Analysis Data:

        GOAL: What is traffic like on I-5 on the way to the SeaTac Airport

        PLATFORM: Google Maps (https://maps.google.com)

        TASK TYPE: Check Traffic

        TRAJECTORY ID: calendar_2d2a0c25-5df1-4bad-a921-866dc7ebe03c

        HIGH-LEVEL INSTRUCTION: Determine traffic condition on the I-5 when navigating to SeaTac Airport

        DETAILED STEPS:
        1. Navigate to Google Maps website at https://maps.google.com
        2. Click on the 'Directions' button to start setting the route
        3. Fill in the destination with 'SeaTac Airport' and press Enter to continue setting the route
        4. Set the starting point for the route by filling in 'Your location' in the starting point textbox and press Enter
        5. Review traffic conditions on the generated I-5 route

        PYTHON/PLAYWRIGHT CODE ACTIONS:
        - page.get_by_role('button', name='Directions').click()
        - page.get_by_label('Choose destination...').fill('SeaTac Airport'); page.keyboard.press('Enter')
        - page.get_by_role('textbox', name='Choose starting point, or click on the map...').fill('Your location'); page.keyboard.press('Enter')

        USER INTERACTIONS:
        - Clicked interface elements (Directions button)
        - Typed destination and starting point text
        - Used Google Maps directions functionality
        - Analyzed traffic visualization and route information

        PLATFORM FEATURES UTILIZED:
        - Directions planning system
        - Location search and autocomplete
        - Traffic condition visualization
        - Route optimization algorithms
        - Real-time traffic data integration

        EXECUTION RESULTS:
        - Success Status: Completed successfully
        - Total Steps: 3 navigation actions
        - Runtime: 23.9 seconds
        - Final Output: Traffic on I-5 is marked as 'some traffic, as usual' for a 27-minute route
        - Browser Context: macOS, 1280x720 viewport
        - Total Tokens Used: 15,234

        TASK COMPLEXITY: Low to Medium - Simple directions query with traffic analysis
        NAVIGATION PATTERN: Linear task flow with form-filling interactions
        PLATFORM SPECIALIZATION: Location-based services and traffic monitoring capabilities
        """

        print("Ingesting text into Graphiti...")
        # Get your custom entity types
        entity_types = get_entity_types()

        # Use them in add_episode - that's it!
        result = await graphiti.add_episode(
            name="Traffic Check",
            episode_body=input_text,
            source=EpisodeType.text,
            entity_types=entity_types,  # 👈 This is all you need!
            reference_time=datetime.now(timezone.utc)
        )

        print(f"Successfully ingested episode: {result.episode.name}")
        print(f"Extracted {len(result.nodes)} nodes and {len(result.edges)} edges")

        if result.nodes:
            print("\nExtracted entities:")
            for i, node in enumerate(result.nodes[:10]):
                print(f"{i}. {node.name}")
            if len(result.nodes) > 10:
                print(f"... and {len(result.nodes) - 10} more")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Print token usage summary
        token_tracker.print_summary()
        
        # Properly close the connection
        await graphiti.close()
        print("Connection closed.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 