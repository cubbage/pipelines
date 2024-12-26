import sys
import os
import time
import requests
from typing import Dict
import neo4j

sys.path.append(os.path.join(os.path.dirname(__file__), "../../pipelines/examples/pipelines/rag"))
from novel_writing_pipeline import NovelWritingPipeline

def test_connections():
    """Test connections to Neo4j and Qdrant before proceeding."""
    print("Testing database connections...")
    
    # Test Neo4j connection
    try:
        driver = neo4j.GraphDatabase.driver(
            "neo4j://localhost:7687",
            auth=("neo4j", "buddyai_neo4j_pass")
        )
        driver.verify_connectivity()
        print("✓ Neo4j connection successful")
    except Exception as e:
        print(f"✗ Neo4j connection failed: {str(e)}")
        raise

    # Test Qdrant connection
    try:
        response = requests.get("http://localhost:6333/collections")
        if response.status_code == 200:
            print("✓ Qdrant connection successful")
        else:
            print(f"✗ Qdrant connection failed with status code: {response.status_code}")
            raise Exception(f"Qdrant API returned: {response.text}")
    except requests.RequestException as e:
        print(f"✗ Qdrant connection failed: {str(e)}")
        raise

def test_pipeline():
    print("Initializing Novel Writing Pipeline...")
    
    # Test connections first
    test_connections()
    
    # Initialize pipeline with retries for Ollama
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            pipeline = NovelWritingPipeline(
                workspace_dir=os.path.dirname(os.path.abspath(__file__)),
                ollama_host="http://localhost:11434"
            )
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Failed to initialize pipeline after {max_retries} attempts: {str(e)}")
                raise
            print(f"Attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    # Test story chunk creation
    print("\nAdding story chunk...")
    story_chunk = """
    Sarah entered the dimly lit room, her hand gripping the ancient key tightly. 
    The musty air carried whispers of secrets long forgotten. As she moved deeper 
    into the shadows, her footsteps echoed against the stone floor.
    """
    metadata = {
        "scene": "introduction",
        "location": "mysterious_room",
        "time": "night",
        "atmosphere": "tense"
    }
    try:
        chunk_id = pipeline.add_manuscript_chunk(story_chunk, metadata)
        print(f"✓ Story chunk added with ID: {chunk_id}")
    except Exception as e:
        print(f"✗ Failed to add story chunk: {str(e)}")
        raise

    # Test character state management
    print("\nUpdating character state...")
    character_state = {
        "name": "Sarah",
        "status": "active",
        "inventory": ["ancient key"],
        "current_location": "mysterious_room",
        "emotional_state": "anxious",
        "goals": ["discover the room's secret"]
    }
    try:
        pipeline.update_character_state(
            "Sarah",
            character_state,
            "Main character introduced in opening scene"
        )
        print("✓ Character state updated successfully")
    except Exception as e:
        print(f"✗ Failed to update character state: {str(e)}")
        raise

    # Test retrieval
    print("\nTesting retrieval functionality...")
    query = "What items does Sarah have?"
    try:
        result = pipeline.query_story_state(query)
        print(f"✓ Query successful")
        print(f"Query result: {result}")
    except Exception as e:
        print(f"✗ Query failed: {str(e)}")
        raise

    print("\n✓ All tests completed successfully!")

if __name__ == "__main__":
    try:
        test_pipeline()
    except Exception as e:
        print(f"Error during pipeline test: {str(e)}")
        sys.exit(1)

