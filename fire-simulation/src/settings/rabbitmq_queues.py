import warnings
from src.messaging.topics import TopicRegistry, get_all_topics

# Backward compatibility aliases
QUEUE_NAMES = get_all_topics()
TOPIC_NAMES = QUEUE_NAMES
