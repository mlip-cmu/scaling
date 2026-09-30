"""Small helpers around the Kafka client: topics, producers, consumers, and logging."""

import json
import os
import socket
import time

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
NAME = f"host@{socket.gethostname()[:12]}"


def set_name(component: str) -> None:
    global NAME
    NAME = f"{component}@{socket.gethostname()[:12]}"


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} [{NAME}] {message}", flush=True)


def admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": BOOTSTRAP})


def ensure_topics(topics: dict[str, int]) -> None:
    """Create the topics (name: number of partitions) that do not exist yet."""
    a = admin()
    for _ in range(30):
        try:
            existing = a.list_topics(timeout=5).topics
            break
        except KafkaException:
            time.sleep(1)
    new = [NewTopic(t, n, 1) for t, n in topics.items() if t not in existing]
    if not new:
        return
    for future in a.create_topics(new).values():
        try:
            future.result()
        except KafkaException as e:  # another instance created it at the same time
            if "TOPIC_ALREADY_EXISTS" not in str(e):
                raise


def producer(**conf) -> Producer:
    return Producer({"bootstrap.servers": BOOTSTRAP, "linger.ms": 5, **conf})


def send(p: Producer, topic: str, key, value: dict, partition: int = -1) -> None:
    p.produce(topic, key=str(key), value=json.dumps(value), partition=partition)
    p.poll(0)


def consumer(group: str, topics: list[str], verbose: bool = True, on_assign=None, **conf):
    c = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.offset.store": False,
            **conf,
        }
    )

    def assigned(c, partitions):
        if verbose:
            log(f"assigned partitions: {[f'{p.topic}[{p.partition}]' for p in partitions]}")
        if on_assign:
            on_assign(c, partitions)

    c.subscribe(topics, on_assign=assigned)
    return c


def lag(group: str, topic: str) -> dict[int, int]:
    """Messages per partition that the consumer group has not processed yet."""
    from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition

    a = admin()
    parts = a.list_topics(topic, timeout=5).topics[topic].partitions
    if not parts:
        raise KafkaException(f"topic {topic} does not exist yet")
    tps = [TopicPartition(topic, p) for p in parts]
    req = ConsumerGroupTopicPartitions(group, tps)
    committed = a.list_consumer_group_offsets([req])[group].result().topic_partitions
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "lag-reader"})
    out = {}
    for tp in committed:
        _, high = c.get_watermark_offsets(TopicPartition(topic, tp.partition), timeout=5)
        out[tp.partition] = high - max(tp.offset, 0)
    c.close()
    return out
