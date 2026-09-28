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

"""KafkaSource: safe configuration, at-least-once commits, record decoding."""

import json

import pytest

from nexus_processing.kafka import KafkaRecord, KafkaSettings, KafkaSource, KafkaSourceError, decode


class Msg:
    def __init__(self, topic, partition, offset, value, key=None, error=None):
        self._t, self._p, self._o, self._v, self._k, self._e = (
            topic,
            partition,
            offset,
            value,
            key,
            error,
        )

    def error(self):
        return self._e

    def topic(self):
        return self._t

    def partition(self):
        return self._p

    def offset(self):
        return self._o

    def value(self):
        return self._v

    def key(self):
        return self._k

    def timestamp(self):
        return (1, 1_700_000_000_000)

    def headers(self):
        return None


class FakeConsumer:
    def __init__(self, config, batches):
        self.config, self.batches, self.commits, self.subscribed = config, list(batches), [], None

    def subscribe(self, topics, **callbacks):
        self.subscribed, self.callbacks = topics, callbacks

    def consume(self, num_messages, timeout):
        return self.batches.pop(0) if self.batches else []

    def commit(self, offsets, asynchronous):
        assert asynchronous is False
        self.commits.append(sorted(offsets))

    def close(self):
        pass


def _settings(**kw):
    base = dict(
        bootstrap_servers="b1:9093",
        topics=["telemetry"],
        group_id="nexora-ops",
        username="svc",
        password="pw",
    )
    return KafkaSettings(**{**base, **kw})


def test_secure_defaults_and_validation():
    config = _settings().consumer_config()
    assert config["enable.auto.commit"] is False and config["enable.auto.offset.store"] is False
    assert config["isolation.level"] == "read_committed"
    assert config["security.protocol"] == "SASL_SSL" and config["sasl.mechanism"] == "SCRAM-SHA-512"
    with pytest.raises(KafkaSourceError, match="unencrypted"):
        _settings(security_protocol="PLAINTEXT").consumer_config()
    assert _settings(security_protocol="PLAINTEXT", allow_plaintext=True).consumer_config()
    with pytest.raises(KafkaSourceError, match="username and password"):
        _settings(password=None).consumer_config()
    with pytest.raises(KafkaSourceError, match="topic"):
        _settings(topics=[]).consumer_config()


def test_commits_next_offset_per_partition_after_apply():
    batch = [
        Msg("telemetry", 0, 10, b"{}"),
        Msg("telemetry", 0, 11, b"{}"),
        Msg("telemetry", 1, 5, b"{}"),
    ]
    holder = {}

    def factory(config):
        holder["c"] = FakeConsumer(config, [batch, []])
        return holder["c"]

    source = KafkaSource(_settings(), factory)
    it = source.batches()
    records = next(it)
    assert [r.offset for r in records] == [10, 11, 5] and holder["c"].subscribed == ["telemetry"]
    assert holder["c"].commits == []  # nothing committed until the caller has applied the batch
    source.commit(records)
    assert holder["c"].commits == [[("telemetry", 0, 12), ("telemetry", 1, 6)]]
    assert next(it) == []  # idle tick


def test_transient_errors_are_skipped_and_fatal_ones_raise():
    class Err:
        def __init__(self, fatal):
            self._fatal = fatal

        def fatal(self):
            return self._fatal

        def __str__(self):
            return "broker error"

    ok = KafkaSource(
        _settings(),
        lambda c: FakeConsumer(
            c, [[Msg("t", 0, 1, None, error=Err(False)), Msg("t", 0, 2, b"{}")]]
        ),
    )
    assert [r.offset for r in next(ok.batches())] == [2]
    bad = KafkaSource(
        _settings(), lambda c: FakeConsumer(c, [[Msg("t", 0, 1, None, error=Err(True))]])
    )
    with pytest.raises(KafkaSourceError, match="fatal"):
        next(bad.batches())


def test_decode_debezium_json_and_tombstones():
    envelope = {
        "schema": {},
        "payload": {
            "op": "u",
            "before": None,
            "after": {"acid": "LA1", "dpd": 3},
            "source": {"db": "core", "table": "loans"},
            "ts_ms": 1,
        },
    }
    rec = KafkaRecord(
        "bank.core.loans",
        0,
        1,
        json.dumps({"payload": {"acid": "LA1"}}).encode(),
        json.dumps(envelope).encode(),
    )
    (event,) = decode(rec)
    assert event.operation == "UPDATE" and event.table == "loans" and event.key == "LA1"
    tomb = KafkaRecord("bank.core.loans", 0, 2, json.dumps({"acid": "LA2"}).encode(), None)
    (deleted,) = decode(tomb)
    assert deleted.is_delete and deleted.key == "LA2" and deleted.database == "core"
    telemetry = KafkaRecord(
        "telemetry", 0, 3, b"P-101", json.dumps({"asset_id": "P-101", "vibration": 2.4}).encode()
    )
    assert decode(telemetry, "json") == [{"asset_id": "P-101", "vibration": 2.4}]
    with pytest.raises(KafkaSourceError, match="not JSON"):
        decode(KafkaRecord("t", 0, 4, None, b"not json"), "json")


class TP:
    def __init__(self, topic, partition, offset=-1001):
        self.topic, self.partition, self.offset = topic, partition, offset


def test_commit_skips_partitions_revoked_by_a_rebalance():
    holder = {}

    def factory(config):
        holder["c"] = FakeConsumer(config, [[Msg("t", 0, 1, b"{}"), Msg("t", 1, 7, b"{}")]])
        return holder["c"]

    source = KafkaSource(_settings(topics=["t"]), factory)
    records = next(source.batches())
    callbacks = holder["c"].callbacks
    callbacks["on_assign"](holder["c"], [TP("t", 0), TP("t", 1)])
    callbacks["on_revoke"](holder["c"], [TP("t", 1)])  # the group moved partition 1 elsewhere
    assert source.commit(records) is False  # partial: partition 1 will be redelivered
    assert holder["c"].commits == [[("t", 0, 2)]]
    callbacks["on_lost"](holder["c"], [TP("t", 0)])
    assert source.commit(records) is False and len(holder["c"].commits) == 1


def test_commit_during_rebalance_is_not_fatal_but_other_errors_are():
    class KafkaErr:
        def __init__(self, name, retriable=False):
            self._n, self._r = name, retriable

        def name(self):
            return self._n

        def retriable(self):
            return self._r

    class Failing(FakeConsumer):
        def commit(self, offsets, asynchronous):
            raise RuntimeError(self.error)

    for error, fatal in (
        (KafkaErr("REBALANCE_IN_PROGRESS"), False),
        (KafkaErr("TOPIC_AUTHORIZATION_FAILED"), True),
    ):
        consumer = Failing({}, [])
        consumer.error = error
        source = KafkaSource(_settings(), lambda c, consumer=consumer: consumer)
        batch = [KafkaRecord("telemetry", 0, 3, None, b"{}")]
        if fatal:
            with pytest.raises(RuntimeError):
                source.commit(batch)
        else:
            assert source.commit(batch) is False


def test_check_and_lag_never_join_the_group():
    class Meta:
        def __init__(self):
            self.topics = {"telemetry": type("T", (), {"partitions": {0: None, 1: None}})()}
            self.brokers = {1: None}

    class Client(FakeConsumer):
        def list_topics(self, timeout):
            return Meta()

        def committed(self, partitions, timeout):
            return [TP(p[0], p[1], 90 if p[1] == 0 else -1001) for p in partitions]

        def get_watermark_offsets(self, tp, timeout, cached):
            return (10, 100)

    made = []

    def factory(config):
        made.append(Client(config, []))
        return made[-1]

    source = KafkaSource(_settings(), factory)
    assert source.check()["topics"] == {"telemetry": 2}
    lag = source.lag()
    assert lag["lag"] == 10 + 90 and lag["partitions_without_commit"] == 1
    assert (
        all(c.subscribed is None for c in made) and len(made) == 1
    )  # one client, never subscribed


def test_mutual_tls_and_hostname_verification():
    config = _settings(
        security_protocol="SSL",
        username=None,
        password=None,
        ssl_ca_location="/certs/ca.pem",
        ssl_certificate_location="/certs/client.pem",
        ssl_key_location="/certs/client.key",
        ssl_key_password="k",
    ).consumer_config()
    assert (
        config["ssl.certificate.location"] == "/certs/client.pem"
        and config["ssl.key.password"] == "k"
    )
    assert config["ssl.endpoint.identification.algorithm"] == "https"
    with pytest.raises(KafkaSourceError, match="both the client certificate and its key"):
        _settings(security_protocol="SSL", ssl_certificate_location="/c.pem").consumer_config()


def test_schema_registry_values_and_keys_use_the_decoder():
    def decoder(data, topic, is_key):  # stands in for avro_decoder (wire format: magic byte 0)
        assert data[:1] == b"\x00"
        return (
            {"acid": "LA9"}
            if is_key
            else {
                "op": "c",
                "before": None,
                "after": {"acid": "LA9", "dpd": 0},
                "source": {"db": "core", "table": "loans"},
                "ts_ms": 5,
            }
        )

    (event,) = decode(
        KafkaRecord("bank.core.loans", 0, 1, b"\x00key", b"\x00value"), decoder=decoder
    )
    assert event.operation == "INSERT" and event.key == "LA9" and event.record["dpd"] == 0
