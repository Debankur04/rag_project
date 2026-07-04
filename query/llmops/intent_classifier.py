from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import os

class IntentClassifier:
    def __init__(self, model_name="llama-3.1-8b-instant"):
        self.client = ChatGroq(model=model_name, api_key=os.getenv("GROQ_API_KEY"))
        self.system_prompt = SystemMessage(
            content="You are an intent classifier. Return strictly 'True' if the user query is a simple factual question or greeting (e.g., asking for weather, definitions). Return strictly 'False' if it is a complex query requiring multi-step planning, reasoning, or external data processing (e.g., travel planning, complex searches). Output nothing else but True or False."
        )

    def classify(self, query: str) -> bool:
        """
        Takes the query and checks if it's a simple request.
        Returns True for simple, False for complex.
        """
        try:
            prompt = [self.system_prompt, HumanMessage(content=query)]
            response = self.client.invoke(prompt)
            result = response.content.strip().lower()
            return "true" in result
        except Exception as e:
            print(f"Classifier error: {e}")
            return False
