# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Apache Kafka as a source: at-least-once batches of records.

``KafkaSource`` wraps a confluent-kafka consumer (librdkafka; ``pip install
veloxs-nexus[kafka]``) the way a durable pipeline needs it:

  * auto-commit and automatic offset storage are off; the caller applies a batch durably
    and then calls ``commit(batch)``, which commits the next offset of every partition in
    the batch (synchronously). A crash in between replays the batch, never skips it.
  * rebalance-safe: partitions assigned to this consumer are tracked through the rebalance
    callbacks; ``commit`` only commits partitions it still owns and returns ``False`` when
    the group moved on (the new owner re-reads those records, so the apply must be
    idempotent — which at-least-once requires anyway)
  * ``isolation.level=read_committed``: records of aborted producer transactions are never seen
  * TLS is on by default (``SASL_SSL`` with SCRAM-SHA-512) with broker hostname verification;
    mutual TLS with a client certificate is supported; ``PLAINTEXT`` must be allowed
    explicitly (local development only)
  * ``check()`` and ``lag()`` use a separate client that never joins the consumer group, so
    a connection test or a health probe cannot trigger a rebalance of a running stream
  * ``decode`` turns a record into CDC ``ChangeEvent`` objects (Debezium, Maxwell, generic
    JSON) with the Kafka key used for keyed deletes, or returns the JSON document itself
    (``format="json"``) for event streams such as telemetry; values in Confluent Schema
    Registry wire format (Avro) are decoded with ``avro_decoder`` (``[kafka-avro]``)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

SECURITY_PROTOCOLS = ("SASL_SSL", "SSL", "SASL_PLAINTEXT", "PLAINTEXT")
SASL_MECHANISMS = ("SCRAM-SHA-512", "SCRAM-SHA-256", "PLAIN")
FORMATS = ("debezium", "json")
# Commit errors after which the records are simply redelivered to whoever owns the partition now.
_REBALANCE_ERRORS = {
    "REBALANCE_IN_PROGRESS",
    "ILLEGAL_GENERATION",
    "UNKNOWN_MEMBER_ID",
    "_ASSIGNMENT_LOST",
    "_NO_OFFSET",
    "_STATE",
    "FENCED_INSTANCE_ID",
}

ValueDecoder = Callable[[bytes, str, bool], Any]  # (data, topic, is_key) -> decoded value


class KafkaSourceError(RuntimeError):
    """The consumer could not be configured or reported a fatal error."""


@dataclass
class KafkaRecord:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None
    timestamp_ms: int = 0
    headers: dict[str, bytes] = field(default_factory=dict)


@dataclass
class KafkaSettings:
    bootstrap_servers: str
    topics: list[str]
    group_id: str
    security_protocol: str = "SASL_SSL"
    sasl_mechanism: str = "SCRAM-SHA-512"
    username: str | None = None
    password: str | None = None
    ssl_ca_location: str | None = None
    ssl_certificate_location: str | None = None  # mutual TLS: client certificate (PEM, with chain)
    ssl_key_location: str | None = None
    ssl_key_password: str | None = None
    client_id: str = "nexus"
    auto_offset_reset: str = "earliest"
    allow_plaintext: bool = False

    def validate(self) -> None:
        if not self.bootstrap_servers.strip():
            raise KafkaSourceError("bootstrap servers are required (host:port[,host:port])")
        if not self.topics:
            raise KafkaSourceError("at least one topic is required")
        if not self.group_id.strip():
            raise KafkaSourceError("a consumer group id is required")
        if self.security_protocol not in SECURITY_PROTOCOLS:
            raise KafkaSourceError(f"security protocol must be one of {SECURITY_PROTOCOLS}")
        if "PLAINTEXT" in self.security_protocol and not self.allow_plaintext:
            raise KafkaSourceError(
                "unencrypted Kafka is only allowed with allow_plaintext=True "
                "(local development); use SASL_SSL or SSL"
            )
        if self.security_protocol.startswith("SASL"):
            if self.sasl_mechanism not in SASL_MECHANISMS:
                raise KafkaSourceError(f"SASL mechanism must be one of {SASL_MECHANISMS}")
            if not (self.username and self.password):
                raise KafkaSourceError("SASL needs a username and password")
        if bool(self.ssl_certificate_location) != bool(self.ssl_key_location):
            raise KafkaSourceError("mutual TLS needs both the client certificate and its key")
        if self.ssl_certificate_location and "PLAINTEXT" in self.security_protocol:
            raise KafkaSourceError("a client certificate needs SSL or SASL_SSL")
        if self.auto_offset_reset not in ("earliest", "latest"):
            raise KafkaSourceError("auto_offset_reset must be 'earliest' or 'latest'")

    def client_config(self) -> dict[str, Any]:
        """Connection and security settings (shared by the consumer and the metadata client)."""
        self.validate()
        config: dict[str, Any] = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": self.client_id,
            "security.protocol": self.security_protocol,
        }
        if self.security_protocol.startswith("SASL"):
            config.update(
                {
                    "sasl.mechanism": self.sasl_mechanism,
                    "sasl.username": self.username,
                    "sasl.password": self.password,
                }
            )
        if self.security_protocol in ("SSL", "SASL_SSL"):
            config["ssl.endpoint.identification.algorithm"] = "https"  # verify the broker's name
        if self.ssl_ca_location:
            config["ssl.ca.location"] = self.ssl_ca_location
        if self.ssl_certificate_location:
            config["ssl.certificate.location"] = self.ssl_certificate_location
            config["ssl.key.location"] = self.ssl_key_location
            if self.ssl_key_password:
                config["ssl.key.password"] = self.ssl_key_password
        return config

    def consumer_config(self) -> dict[str, Any]:
        return {
            **self.client_config(),
            "group.id": self.group_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": self.auto_offset_reset,
            "isolation.level": "read_committed",
            "session.timeout.ms": 45000,
            "max.poll.interval.ms": 600000,
        }


def _default_factory(config: dict[str, Any]) -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise KafkaSourceError("Kafka support needs: pip install 'veloxs-nexus[kafka]'") from exc
    return Consumer(config)


def _error_name(exc: Exception) -> str:
    err = exc.args[0] if exc.args else None
    name = getattr(err, "name", None)
    return str(name() if callable(name) else "") or type(exc).__name__


class KafkaSource:
    def __init__(
        self,
        settings: KafkaSettings,
        consumer_factory: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.settings = settings
        self._factory = consumer_factory or _default_factory
        self._consumer: Any = None
        self._meta: Any = None
        self.assigned: set[tuple[str, int]] = set()
        self._assignment_known = False  # before the first assignment callback, trust the batch

    # -- rebalance callbacks (called by librdkafka inside consume) -------------------
    def _on_assign(self, consumer: Any, partitions: list[Any]) -> None:
        self._assignment_known = True
        self.assigned |= {(p.topic, p.partition) for p in partitions}
        log.info("kafka: assigned %s", sorted(self.assigned))

    def _on_revoke(self, consumer: Any, partitions: list[Any]) -> None:
        self.assigned -= {(p.topic, p.partition) for p in partitions}
        log.info("kafka: revoked %d partition(s)", len(partitions))

    @property
    def consumer(self) -> Any:
        if self._consumer is None:
            self._consumer = self._factory(self.settings.consumer_config())
            self._consumer.subscribe(
                list(self.settings.topics),
                on_assign=self._on_assign,
                on_revoke=self._on_revoke,
                on_lost=self._on_revoke,
            )
        return self._consumer

    def _metadata_client(self) -> Any:
        """A consumer that never subscribes: metadata and committed offsets only."""
        if self._meta is None:
            self._meta = self._factory(self.settings.consumer_config())
        return self._meta

    def batches(self, max_records: int = 500, timeout: float = 1.0) -> Iterator[list[KafkaRecord]]:
        """Yield batches forever; an empty list means nothing arrived within ``timeout``."""
        while True:
            messages = self.consumer.consume(num_messages=max_records, timeout=timeout) or []
            batch: list[KafkaRecord] = []
            for m in messages:
                error = m.error()
                if error is not None:
                    if getattr(error, "fatal", lambda: False)():
                        raise KafkaSourceError(f"fatal Kafka error: {error}")
                    continue  # e.g. partition EOF or a transient broker error; librdkafka retries
                ts = m.timestamp()
                batch.append(
                    KafkaRecord(
                        topic=m.topic(),
                        partition=m.partition(),
                        offset=m.offset(),
                        key=m.key(),
                        value=m.value(),
                        timestamp_ms=ts[1] if isinstance(ts, tuple) and ts[0] else 0,
                        headers={k: v for k, v in (m.headers() or [])},
                    )
                )
            yield batch

    def commit(self, batch: list[KafkaRecord]) -> bool:
        """Commit after the batch is durably applied: the next offset of each partition seen.

        Returns False when some partitions were revoked meanwhile (their records will be
        redelivered to the new owner); raises only for errors a retry cannot fix.
        """
        if not batch:
            return True
        from_types = _topic_partition()
        latest: dict[tuple[str, int], int] = {}
        for r in batch:
            latest[(r.topic, r.partition)] = max(latest.get((r.topic, r.partition), -1), r.offset)
        owned = {
            tp: o for tp, o in latest.items() if not self._assignment_known or tp in self.assigned
        }
        if not owned:
            return False
        offsets = [from_types(t, p, o + 1) for (t, p), o in owned.items()]
        try:
            result = self.consumer.commit(offsets=offsets, asynchronous=False)
        except Exception as exc:  # confluent_kafka.KafkaException
            name = _error_name(exc)
            retriable = getattr(exc.args[0] if exc.args else None, "retriable", lambda: False)
            if name in _REBALANCE_ERRORS or (callable(retriable) and retriable()):
                log.warning("kafka: commit skipped (%s); records will be redelivered", name)
                return False
            raise
        failed = [tp for tp in result or [] if getattr(tp, "error", None)]
        return len(owned) == len(latest) and not failed

    def check(self, timeout: float = 10.0) -> dict[str, Any]:
        """Connection test: the topics exist and have partitions (does not join the group)."""
        metadata = self._metadata_client().list_topics(timeout=timeout)
        found = {
            name: len(t.partitions)
            for name, t in metadata.topics.items()
            if name in self.settings.topics
        }
        missing = sorted(set(self.settings.topics) - set(found))
        return {"brokers": len(metadata.brokers), "topics": found, "missing_topics": missing}

    def lag(self, timeout: float = 10.0) -> dict[str, Any]:
        """Records not yet committed by this consumer group, per topic (does not join the group)."""
        from_types = _topic_partition()
        client = self._metadata_client()
        metadata = client.list_topics(timeout=timeout)
        partitions = [
            from_types(name, p, -1001)
            for name, t in metadata.topics.items()
            if name in self.settings.topics
            for p in t.partitions
        ]
        committed = client.committed(partitions, timeout=timeout) if partitions else []
        by_topic: dict[str, int] = {}
        uncommitted = 0
        for tp in committed:
            low, high = client.get_watermark_offsets(tp, timeout=timeout, cached=False)
            if tp.offset < 0:  # the group has not committed on this partition yet
                uncommitted += 1
                behind = high - low
            else:
                behind = max(0, high - tp.offset)
            by_topic[tp.topic] = by_topic.get(tp.topic, 0) + behind
        return {
            "group_id": self.settings.group_id,
            "lag": sum(by_topic.values()),
            "by_topic": by_topic,
            "partitions": len(committed),
            "partitions_without_commit": uncommitted,
        }

    def close(self) -> None:
        for name in ("_consumer", "_meta"):
            client = getattr(self, name)
            if client is not None:
                try:
                    client.close()
                finally:
                    setattr(self, name, None)


def _topic_partition() -> Callable[[str, int, int], Any]:
    try:
        from confluent_kafka import TopicPartition

        return TopicPartition
    except ImportError:  # tests / fakes: a plain tuple is enough
        return lambda topic, partition, offset: (topic, partition, offset)


def avro_decoder(
    url: str,
    username: str | None = None,
    password: str | None = None,
    ssl_ca_location: str | None = None,
) -> ValueDecoder:
    """Decode Confluent Schema Registry wire format (magic byte 0, schema id, Avro body).

    The writer's schema is fetched from the registry by id and cached. Needs
    ``pip install 'veloxs-nexus[kafka-avro]'``.
    """
    try:
        from confluent_kafka.schema_registry import SchemaRegistryClient
        from confluent_kafka.schema_registry.avro import AvroDeserializer
        from confluent_kafka.serialization import MessageField, SerializationContext
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise KafkaSourceError(
            "Avro support needs: pip install 'veloxs-nexus[kafka-avro]'"
        ) from exc
    if not url.startswith("https://") and not url.startswith("http://localhost"):
        raise KafkaSourceError("the schema registry URL must use https")
    conf: dict[str, Any] = {"url": url}
    if username:
        conf["basic.auth.user.info"] = f"{username}:{password or ''}"
    if ssl_ca_location:
        conf["ssl.ca.location"] = ssl_ca_location
    deserializer = AvroDeserializer(SchemaRegistryClient(conf))

    def decode_value(data: bytes, topic: str, is_key: bool) -> Any:
        if not data or data[0] != 0:
            raise KafkaSourceError(f"{topic}: not in schema registry wire format")
        field_ = MessageField.KEY if is_key else MessageField.VALUE
        return deserializer(data, SerializationContext(topic, field_))

    return decode_value


def _key(record: KafkaRecord, decoder: ValueDecoder | None = None) -> Any:
    if not record.key:
        return None
    if decoder is not None and record.key[:1] == b"\x00":
        key = decoder(record.key, record.topic, True)
        return key.get("payload", key) if isinstance(key, dict) else key
    try:
        key = json.loads(record.key)
    except ValueError:
        return record.key.decode("utf-8", "replace")
    return key.get("payload", key) if isinstance(key, dict) else key


def decode(
    record: KafkaRecord, fmt: str = "debezium", decoder: ValueDecoder | None = None
) -> list[Any]:
    """Records to ChangeEvents (CDC formats) or to plain documents (``json``).

    Values are JSON unless a ``decoder`` is given (e.g. ``avro_decoder`` for Schema Registry
    Avro). Debezium topics are named ``<server>.<schema>.<table>``; a tombstone (null value)
    for a keyed record becomes a delete of that key.
    """
    from .cdc import normalize_change_event

    key = _key(record, decoder)
    if record.value is None:
        if fmt == "debezium" and key is not None:
            parts = record.topic.split(".")
            source = {"table": parts[-1], "db": parts[-2] if len(parts) >= 2 else ""}
            before = key if isinstance(key, dict) else {"id": key}
            return [
                normalize_change_event({"op": "d", "before": before, "source": source, "key": key})
            ]
        return []
    if decoder is not None:
        document = decoder(record.value, record.topic, False)
    else:
        try:
            document = json.loads(record.value)
        except ValueError as exc:
            raise KafkaSourceError(
                f"{record.topic}[{record.partition}]@{record.offset} is not JSON"
            ) from exc
    if fmt == "json":
        return document if isinstance(document, list) else [document]
    documents = document if isinstance(document, list) else [document]
    return [
        normalize_change_event({**d, "key": key} if isinstance(d, dict) and key is not None else d)
        for d in documents
    ]
