class DualStateManager:
    def __init__(self):
        # Unique ID mapping between systems
        self.id_map = {}
        
        # Transaction management
        self.current_transaction = None
        
    def begin_transaction(self):
        # Start atomic operation across both systems
        self.neo4j_tx = self.graph.begin()
        self.qdrant_batch = []
    
    def commit(self):
        try:
            # Two-phase commit
            # 1. Prepare phase
            neo4j_success = self.neo4j_tx.prepare()
            qdrant_success = self.prepare_qdrant_batch()
            
            if neo4j_success and qdrant_success:
                # 2. Commit phase
                self.neo4j_tx.commit()
                self.commit_qdrant_batch()
            else:
                # Rollback both if either fails
                self.rollback()
                
        except Exception as e:
            self.rollback()
            raise e

class ChangeEvent:
       def __init__(self, entity_id, change_type, data):
           self.entity_id = entity_id
           self.timestamp = datetime.now()
           self.change_type = change_type  # 'content', 'relationship', 'metadata'
           self.data = data
           self.status = 'pending'

class UnifiedKnowledgeBase:
    def update_story_element(self, element_type, content, relationships=None):
        with self.state_manager.transaction():
            # Vector embedding for semantic search
            vector_id = self.qdrant.upsert(
                content=content,
                metadata={"type": element_type}
            )
            
            # Graph relationships
            node_id = self.neo4j.create_or_update_node(
                id=vector_id,  # Same ID in both systems
                type=element_type,
                properties={"content_hash": hash(content)}
            )
            
            if relationships:
                for rel in relationships:
                    self.neo4j.create_relationship(
                        source=node_id,
                        target=rel.target_id,
                        type=rel.type
                    )