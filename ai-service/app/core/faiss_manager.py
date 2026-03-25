import numpy as np
import faiss

class FaissManager:
    def __init__(self, dimension=512):
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(self.dimension)
        self.id_map = {} # Maps FAISS internal int IDs to your string image_ids
        self.current_id = 0

    def sync_database(self, items):
        self.index.reset()
        self.id_map = {}
        self.current_id = 0
        if not items:
            return
        
        vectors = []
        for item in items:
            vectors.append(item['embedding'])
            self.id_map[self.current_id] = item['image_id']
            self.current_id += 1
            
        vectors_np = np.array(vectors).astype('float32')
        faiss.normalize_L2(vectors_np)
        self.index.add(vectors_np)

    def add_vector(self, image_id: str, embedding: list):
        vector_np = np.array([embedding]).astype('float32')
        faiss.normalize_L2(vector_np)
        self.index.add(vector_np)
        self.id_map[self.current_id] = image_id
        self.current_id += 1

    def search(self, embedding: list, k=3):
        if self.index.ntotal == 0:
            return []
            
        vector_np = np.array([embedding]).astype('float32')
        faiss.normalize_L2(vector_np)
        distances, indices = self.index.search(vector_np, k)
        
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx != -1:
                results.append({
                    "image_id": self.id_map[idx],
                    "score": float(distances[0][i])
                })
        return results

# Singleton instance
faiss_db = FaissManager()