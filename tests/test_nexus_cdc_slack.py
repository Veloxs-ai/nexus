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

import io
import json
import time
import zipfile

from nexus import NexusClient

try:
    from nexus.processing import cdc, slack_export
except (ImportError, ModuleNotFoundError):
    from nexus_processing import cdc, slack_export


def test_debezium_envelope_with_kafka_key_and_delete():
    ev = cdc.normalize_change_event({
        "key": {"payload": {"id": 42}},
        "payload": {"op": "d", "before": {"id": 42, "name": "Ann"}, "after": None,
                    "source": {"db": "shop", "table": "users"}, "ts_ms": 1700000000000},
    })
    assert (ev.operation, ev.source_format, ev.table, ev.key) == ("DELETE", "debezium", "users", "42")
    assert ev.record["name"] == "Ann" and ev.is_delete


def test_maxwell_delete_keeps_row_and_primary_key():
    ev = cdc.normalize_change_event({"database": "shop", "table": "orders", "type": "delete", "ts": 1700000000,
                                     "data": {"order_id": 7, "total": 10}, "primary_key": {"order_id": 7}})
    assert (ev.operation, ev.source_format, ev.key, ev.timestamp_ms) == ("DELETE", "maxwell", "7", 1700000000000)


def test_mongo_partial_update_is_flagged():
    ev = cdc.normalize_change_event({"operationType": "update", "ns": {"db": "app", "coll": "users"},
                                     "documentKey": {"_id": {"$oid": "65a1"}},
                                     "updateDescription": {"updatedFields": {"plan": "pro"}, "removedFields": ["trial"]}})
    assert ev.partial and ev.key == "65a1" and ev.record == {"plan": "pro"} and ev.removed_fields == ["trial"]


def test_batches_and_ndjson():
    body = "\n".join(json.dumps({"op": "insert", "table": "t", "record": {"id": i}}) for i in range(3))
    events = cdc.normalize_change_events(body)
    assert [e.key for e in events] == ["0", "1", "2"]
    assert len(cdc.normalize_change_events({"events": [{"op": "u", "table": "t", "record": {"id": 1}}]})) == 1
    assert "[Table: t | Record: 0] id: 0" == cdc.change_event_text(events[0])


def test_webhook_signature_and_replay_protection():
    body = b'{"op":"insert"}'
    ts = str(int(time.time()))
    sig = cdc.sign_webhook_payload("s3cret", body, ts)
    assert cdc.verify_webhook_signature("s3cret", body, sig, ts)
    assert not cdc.verify_webhook_signature("s3cret", body + b" ", sig, ts)
    assert not cdc.verify_webhook_signature("wrong", body, sig, ts)
    assert not cdc.verify_webhook_signature("s3cret", body, cdc.sign_webhook_payload("s3cret", body, "1000"), "1000")
    assert cdc.verify_webhook_signature("s3cret", body, cdc.sign_webhook_payload("s3cret", body))


def _slack_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("users.json", json.dumps([{"id": "U1", "real_name": "Alice"}, {"id": "U2", "profile": {"display_name": "bob"}}]))
        z.writestr("channels.json", json.dumps([{"name": "eng"}]))
        z.writestr("eng/2026-09-01.json", json.dumps([
            {"ts": "1756720800.0001", "user": "U1", "text": "Deploy blocked by migration <@U2>", "thread_ts": "1756720800.0001", "reply_count": 1},
            {"ts": "1756720860.0002", "user": "U2", "text": "Rolling back, mail ops@acme.io", "thread_ts": "1756720800.0001"},
            {"ts": "1756724400.0003", "user": "U1", "text": "Standup at 10"},
            {"ts": "1756724401.0004", "subtype": "channel_join", "user": "U2", "text": "joined"},
        ]))
    return buf.getvalue()


def test_slack_export_threads_windows_and_names():
    data = _slack_zip()
    assert slack_export.looks_like_slack_export(data, "export.zip")
    chunks, info = slack_export.parse_slack_export(data, "export.zip")
    assert info["channels"] == ["eng"] and info["messages"] == 3
    thread = next(c for c in chunks if c.kind == "thread")
    assert "Alice: Deploy blocked by migration @bob" in thread.text and "bob: Rolling back" in thread.text
    assert thread.participants == ["Alice", "bob"]
    assert any(c.kind == "window" and "Standup at 10" in c.text for c in chunks)
    assert not any("joined" in c.text for c in chunks)


def test_client_process_slack_export_masks_pii():
    doc = NexusClient().process_slack_export("s1", "export.zip", _slack_zip())
    assert doc.file_type == "slack" and len(doc.chunks) == 2
    assert all("ops@acme.io" not in c.text for c in doc.chunks)
    assert doc.chunks[0].metadata["channel"] == "eng"


def test_single_channel_json_export():
    data = json.dumps([{"ts": "1756720800.1", "user": "U9", "text": "hello"}]).encode()
    assert slack_export.looks_like_slack_export(data, "general.json")
    chunks, info = slack_export.parse_slack_export(data, "general.json")
    assert info["channels"] == ["general"] and "U9: hello" in chunks[0].text


def test_slack_signature_v0_and_replay_window():
    import hashlib
    import hmac

    body, ts = b'{"type":"event_callback"}', str(int(time.time()))
    sig = "v0=" + hmac.new(b"shh", b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    assert slack_export.verify_slack_signature("shh", body, ts, sig)
    assert not slack_export.verify_slack_signature("other", body, ts, sig)
    assert not slack_export.verify_slack_signature("shh", body + b" ", ts, sig)
    stale = str(int(time.time()) - 3600)
    stale_sig = "v0=" + hmac.new(b"shh", b"v0:" + stale.encode() + b":" + body, hashlib.sha256).hexdigest()
    assert not slack_export.verify_slack_signature("shh", body, stale, stale_sig)


def test_slack_live_events_map_to_upsert_delete_ignore():
    new = {"type": "message", "ts": "1700000000.1", "user": "U1", "text": "hello", "channel": "C1"}
    assert slack_export.slack_event_message(new)[0] == "upsert"
    edited = {"type": "message", "subtype": "message_changed", "message": {"ts": "1700000000.1", "text": "hi!"}}
    action, msg, _ = slack_export.slack_event_message(edited)
    assert action == "upsert" and msg["text"] == "hi!"
    deleted = {"type": "message", "subtype": "message_deleted", "deleted_ts": "1700000000.1"}
    assert slack_export.slack_event_message(deleted) == ("delete", None, "1700000000.1")
    assert slack_export.slack_event_message({"type": "message", "subtype": "channel_join", "text": "x"})[0] == "ignore"
    assert slack_export.slack_event_message({"type": "reaction_added"})[0] == "ignore"


def test_live_messages_use_the_export_chunker():
    msgs = [{"ts": "1700000000.1", "user": "U1", "text": "Deploy is <@U2|bob> ready"},
            {"ts": "1700000060.2", "user": "U2", "text": "Shipping now"}]
    chunks = slack_export.messages_to_chunks("eng", msgs, {"U1": "ann", "U2": "bob"})
    assert len(chunks) == 1 and "ann: Deploy is @bob ready" in chunks[0].text


def test_release_idle_models_unloads_and_reloads_lazily():
    try:
        from nexus.processing import ml_providers
    except (ImportError, ModuleNotFoundError):
        from nexus_processing import ml_providers

    provider = ml_providers.FasterWhisperTranscriber()
    provider._model = object()  # pretend loaded
    provider._last_used = time.monotonic() - 1000
    ml_providers._shared["test-whisper"] = provider
    try:
        assert "test-whisper" in ml_providers.release_idle_models(max_idle_seconds=600)
        assert provider._model is None
        assert ml_providers.release_idle_models(max_idle_seconds=600) == []
    finally:
        ml_providers._shared.pop("test-whisper", None)
