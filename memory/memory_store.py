#This enables multi-turn conversation
class MemoryStore:

    def __init__(self):
        self.history = []

    def add(self, role, content):
        self.history.append({
            "role": role,
            "content": content
        })

    def get(self):
        return self.history
