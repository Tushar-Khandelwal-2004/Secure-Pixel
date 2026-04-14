import numpy as np
import faiss
import json
import os

class FaissManager:
    def __init__(self, dimension=512, index_path="faiss.index", id_map_path="faiss_id_map.json"):
        self.dimension = dimension
        self.index_path = index_path
        self.id_map_path = id_map_path

        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
            if os.path.exists(self.id_map_path):
                with open(self.id_map_path, "r", encoding="utf-8") as f:
                    stored_id_map = json.load(f)
                self.id_map = {int(k): v for k, v in stored_id_map.items()}
            else:
                self.id_map = {}
        else:
            self.index = faiss.IndexFlatIP(self.dimension)
            self.id_map = {}

        self.current_id = max(self.id_map.keys(), default=-1) + 1

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.id_map_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self.id_map.items()}, f)

    def sync_database(self, items):
        self.index.reset()
        self.id_map = {}
        self.current_id = 0
        if not items:
            self._save()
            return
        
        vectors = []
        for item in items:
            vectors.append(item['embedding'])
            self.id_map[self.current_id] = item['image_id']
            self.current_id += 1
            
        vectors_np = np.array(vectors).astype('float32')
        faiss.normalize_L2(vectors_np)
        self.index.add(vectors_np)
        self._save()

    def add_vector(self, image_id: str, embedding: list):
        vector_np = np.array([embedding]).astype('float32')
        faiss.normalize_L2(vector_np)
        self.index.add(vector_np)
        self.id_map[self.current_id] = image_id
        self.current_id += 1
        self._save()

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
faiss_db = FaissManager(
    index_path=os.getenv("FAISS_INDEX_PATH", "faiss.index"),
    id_map_path=os.getenv("FAISS_ID_MAP_PATH", "faiss_id_map.json")
)
