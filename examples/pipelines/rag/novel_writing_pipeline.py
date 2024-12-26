import os
import json
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from datetime import datetime
from enum import Enum

from neo4j import GraphDatabase
from llama_index import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Document,
    ServiceContext,
    StorageContext,
)
## from llama_index.vector_stores import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms import Ollama
class MemoryType(Enum):
    """Memory types based on Agent-S architecture"""
    EPISODIC = "episodic"     # Specific events/experiences
    NARRATIVE = "narrative"    # Story patterns and themes
    PROCEDURAL = "procedural"  # Writing techniques and rules
class NovelWritingPipeline:
    """A pipeline for managing an AI-assisted novel writing environment."""
    
    def __init__(self, workspace_dir: str, neo4j_uri: str = "bolt://localhost:7687", 
                neo4j_user: str = "neo4j", neo4j_password: str = "buddyai_neo4j_pass"):
        """Initialize the novel writing environment.
        
        Args:
            workspace_dir: Root directory for all story-related files
            neo4j_uri: URI for Neo4j connection
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
        """
        # Initialize workspace directories
        self.workspace_dir = Path(workspace_dir)
        self.manuscripts_dir = self.workspace_dir / "manuscripts"
        self.characters_dir = self.workspace_dir / "characters"
        self.metadata_dir = self.workspace_dir / "metadata"
        
        # Create necessary directories
        for directory in [self.manuscripts_dir, self.characters_dir, self.metadata_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize LLM
        self.llm = Ollama(model="llama2")
        service_context = ServiceContext.from_defaults(llm=self.llm)
        
        # Initialize Neo4j for relationship tracking
        self.graph_db = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )
        
        # Initialize vector store for semantic search
        # Initialize vector store with HTTP client
        self.vector_store = QdrantVectorStore(
            url="http://localhost:6333",
            collection_name="novel_writing",
            prefer_grpc=False
        )
        
        # Initialize storage context
        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )
        
        # Create indices for different memory types
        self.memory_indices = {
            MemoryType.EPISODIC: VectorStoreIndex.from_documents(
                [], service_context=service_context, storage_context=storage_context
            ),
            MemoryType.NARRATIVE: VectorStoreIndex.from_documents(
                [], service_context=service_context, storage_context=storage_context
            ),
            MemoryType.PROCEDURAL: VectorStoreIndex.from_documents(
                [], service_context=service_context, storage_context=storage_context
            )
        }
        
        # Initialize character and manuscript indices
        self.manuscript_index = VectorStoreIndex.from_documents(
            [], service_context=service_context, storage_context=storage_context
        )
        self.character_index = VectorStoreIndex.from_documents(
            [], service_context=service_context, storage_context=storage_context
        )

        # Create Neo4j constraints and indices
        with self.graph_db.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Character) REQUIRE c.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:Character) ON (c.name)")
        def add_memory(self, memory_type: MemoryType, content: str, 
                    metadata: Dict[str, Any] = None) -> str:
            """Add a new memory of specified type.
            
            Args:
                memory_type: Type of memory (EPISODIC, NARRATIVE, PROCEDURAL)
                content: The memory content
                metadata: Additional metadata about the memory
            
            Returns:
                str: ID of the added memory
            """
            # Create document with metadata
            doc = Document(
                text=content,
                metadata=metadata or {},
                excluded_llm_metadata_keys=["timestamp"]
            )
            
            # Add timestamp and memory type to metadata
            doc.metadata.update({
                "timestamp": datetime.now().isoformat(),
                "memory_type": memory_type.value
            })
            
            # Index the memory
            self.memory_indices[memory_type].insert(doc)
            
            return doc.doc_id

        def add_manuscript_chunk(self, content: str, metadata: Dict[str, Any] = None) -> str:
            """Add a new chunk of manuscript content.
            
            Args:
                content: The new manuscript content
                metadata: Additional metadata about the chunk
            
            Returns:
                str: ID of the added chunk
            """
            # Create document with metadata
            doc = Document(
                text=content,
                metadata=metadata or {},
                excluded_llm_metadata_keys=["timestamp"]
            )
            
            # Add timestamp to metadata
            doc.metadata["timestamp"] = datetime.now().isoformat()
            
            # Index the new content
            self.manuscript_index.insert(doc)
            
            # Create event node in Neo4j
            with self.graph_db.session() as session:
                session.run(
                    """
                    CREATE (e:Event {
                        id: $doc_id,
                        content: $content,
                        timestamp: $timestamp
                    })
                    """,
                    doc_id=doc.doc_id,
                    content=content,
                    timestamp=doc.metadata["timestamp"]
                )
            
            # Add to episodic memory
            self.add_memory(
                MemoryType.EPISODIC,
                content,
                {"doc_id": doc.doc_id, "type": "manuscript_chunk"}
            )
            
            return doc.doc_id

        def update_character_state(self, character_name: str, updates: Dict[str, Any],
                            context: str = "") -> None:
            """Update a character's state based on story developments.
            
            Args:
                character_name: Name of the character to update
                updates: Dictionary of state updates
                context: Story context causing the update
            """
            character_file = self.characters_dir / f"{character_name}.json"
            
            # Load existing character data or create new
            if character_file.exists():
                current_state = json.loads(character_file.read_text())
            else:
                current_state = {"name": character_name, "history": []}
            
            # Add new state update with context
            timestamp = datetime.now().isoformat()
            update_entry = {
                "timestamp": timestamp,
                "changes": updates,
                "context": context
            }
            current_state["history"].append(update_entry)
            
            # Update current state
            for key, value in updates.items():
                current_state[key] = value
            
            # Save updated character state
            character_file.write_text(json.dumps(current_state, indent=2))
            
            # Update Neo4j
            with self.graph_db.session() as session:
                # Create or update character node
                session.run(
                    """
                    MERGE (c:Character {name: $name})
                    SET c += $properties
                    """,
                    name=character_name,
                    properties=current_state
                )
                
                # Create update event and relationship
                session.run(
                    """
                    CREATE (e:Event {
                        timestamp: $timestamp,
                        type: 'character_update',
                        context: $context
                    })
                    WITH e
                    MATCH (c:Character {name: $character_name})
                    CREATE (c)-[:UPDATED_BY]->(e)
                    """,
                    timestamp=timestamp,
                    context=context,
                    character_name=character_name
                )
            
            # Index character update in vector store
            doc = Document(
                text=f"Character Update: {character_name}\n{json.dumps(update_entry, indent=2)}",
                metadata={"character": character_name, "type": "character_update"}
            )
            self.character_index.insert(doc)
            
            # Add to episodic memory
            self.add_memory(
                MemoryType.EPISODIC,
                f"Character {character_name} updated: {context}",
                {"character": character_name, "type": "character_update"}
            )
    
    def query_story_state(self, query: str) -> str:
        """Query the current story state using natural language.
        
        Args:
            query: Natural language query about the story
        
        Returns:
            str: Response based on current story state
        """
        # Combine results from both indices
        manuscript_results = self.manuscript_index.as_query_engine().query(query)
        character_results = self.character_index.as_query_engine().query(query)
        
        # Combine and process results
        combined_response = (
            f"From manuscript analysis:\n{manuscript_results.response}\n\n"
            f"From character analysis:\n{character_results.response}"
        )
        
        return combined_response
    
    def get_character_timeline(self, character_name: str) -> List[Dict[str, Any]]:
        """Retrieve a character's complete timeline.
        
        Args:
            character_name: Name of the character
        
        Returns:
            List[Dict]: Timeline of character events and changes
        """
        character_file = self.characters_dir / f"{character_name}.json"
        if not character_file.exists():
            return []
        
        character_data = json.loads(character_file.read_text())
        return character_data.get("history", [])

