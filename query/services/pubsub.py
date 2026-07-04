import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import redis
from rag_project.config.settings import settings

logger = logging.getLogger(__name__)

# Commenting out Google Pub/Sub for local development
# try:
#     from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
# except ImportError:
#     PublisherClient = None
#     SubscriberClient = None


class PubSub(ABC):
    @abstractmethod
    def publish(self, topic: str, data: dict) -> None:
        pass

    @abstractmethod
    def subscribe(self, subscription_name: str, callback) -> None:
        pass


class DemoPubSub(PubSub):
    def publish(self, topic: str, data: dict) -> None:
        logger.info("[DEMO PUB/SUB] Publishing to topic '%s': %s", topic, json.dumps(data))
        print(f"\n[DEMO PUB/SUB] Publishing to topic '{topic}':")
        print(json.dumps(data, indent=2))
        print("-------------------------------------------\n")

    def subscribe(self, subscription_name: str, callback) -> None:
        logger.warning("Demo Pub/Sub subscribe called for '%s'. No real subscriber is configured.", subscription_name)


class LocalPubSub(PubSub):
    """
    A local queue model using Redis for development purposes.
    """
    def __init__(self, redis_url: str):
        self.redis_client = redis.from_url(redis_url)
        self.pubsub_instance = self.redis_client.pubsub()
        logger.info("[LOCAL PUB/SUB] Initialized with Redis: %s", redis_url)

    def publish(self, topic: str, data: dict) -> None:
        self.redis_client.publish(topic, json.dumps(data))
        logger.info("[LOCAL PUB/SUB] Published to topic '%s'", topic)

    def subscribe(self, subscription_name: str, callback) -> None:
        # In Redis, we subscribe to the topic (which we'll treat as subscription_name for simplicity)
        def redis_callback(message):
            if message['type'] == 'message':
                data = json.loads(message['data'])
                # Create a mock message object similar to Google Pub/Sub
                class MockMessage:
                    def __init__(self, data):
                        self.data = json.dumps(data).encode('utf-8')
                    def ack(self):
                        pass
                callback(MockMessage(data))

        self.pubsub_instance.subscribe(**{subscription_name: redis_callback})
        self.pubsub_instance.run_in_thread(sleep_time=0.01)
        logger.info("[LOCAL PUB/SUB] Subscribed to topic '%s'", subscription_name)


# class GooglePubSub(PubSub):
#     def __init__(self, project_id: Optional[str], credentials_path: Optional[str] = None):
#         self.project_id = project_id
#         self.credentials_path = credentials_path
#         self.publisher = None
#         self.subscriber = None
#         self._init_clients()
# 
#     def _init_clients(self) -> None:
#         if not self.project_id or PublisherClient is None:
#             return
# 
#         if self.credentials_path:
#             import os
#             os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
# 
#         self.publisher = PublisherClient()
#         if SubscriberClient is not None:
#             self.subscriber = SubscriberClient()
# 
#     def publish(self, topic: str, data: dict) -> None:
#         if not self.publisher:
#             raise RuntimeError("Google Pub/Sub is not configured. Install google-cloud-pubsub and set PUBSUB_PROJECT_ID.")
# 
#         topic_path = self.publisher.topic_path(self.project_id, topic)
#         future = self.publisher.publish(topic_path, json.dumps(data).encode("utf-8"))
#         future.result(timeout=10)
#         logger.info("Published message to %s", topic_path)
# 
#     def subscribe(self, subscription_name: str, callback) -> None:
#         if not self.subscriber:
#             raise RuntimeError("Google Pub/Sub Subscriber is not available.")
# 
#         subscription_path = self.subscriber.subscription_path(self.project_id, subscription_name)
#         self.subscriber.subscribe(subscription_path, callback)
#         logger.info("Subscribed to %s", subscription_path)


def _make_pubsub_client() -> PubSub:
    # Use LocalPubSub for development
    if settings.REDIS_URL:
        return LocalPubSub(settings.REDIS_URL)
    
    # Fallback to Demo if Redis is not available (though settings has a default)
    # if settings.PUBSUB_PROJECT_ID and PublisherClient is not None:
    #     return GooglePubSub(settings.PUBSUB_PROJECT_ID, settings.PUBSUB_CREDENTIALS_PATH)
    return DemoPubSub()


pubsub = _make_pubsub_client()
