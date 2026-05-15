from nexus_pipeline.cdc import normalize_debezium_event, run_cdc
from nexus_pipeline.models import CdcOperation, IngestionMode


def test_normalize_debezium_update_event():
    record = normalize_debezium_event(
        {
            "payload": {
                "op": "u",
                "after": {"order_id": "o1", "amount": 25},
                "before": {"order_id": "o1", "amount": 20},
                "ts_ms": 1_778_025_600_000,
            }
        }
    )

    assert record == {
        "order_id": "o1",
        "amount": 25,
        "source_ts_ms": 1_778_025_600_000,
        "_cdc_operation": CdcOperation.UPDATE,
    }


def test_normalize_debezium_delete_uses_before_image():
    record = normalize_debezium_event(
        {
            "payload": {
                "op": "d",
                "after": None,
                "before": {"order_id": "o1"},
                "source": {"ts_ms": 1_778_025_600_000},
            }
        }
    )

    assert record["order_id"] == "o1"
    assert record["_cdc_operation"] == CdcOperation.DELETE
    assert record["source_ts_ms"] == 1_778_025_600_000


def test_run_cdc_sets_event_operations(make_source):
    source = make_source(
        mode=IngestionMode.CDC,
        connector="debezium",
        primary_key="order_id",
        event_time_field="source_ts_ms",
        required_fields=["order_id", "source_ts_ms"],
    )

    events = run_cdc(
        "erp_orders",
        source,
        [
            {
                "payload": {
                    "op": "c",
                    "after": {"order_id": "o1"},
                    "ts_ms": 1_778_025_600_000,
                }
            },
            {
                "payload": {
                    "op": "d",
                    "before": {"order_id": "o2"},
                    "ts_ms": 1_778_025_700_000,
                }
            },
        ],
    )

    assert [event.operation for event in events] == [CdcOperation.INSERT, CdcOperation.DELETE]
    assert [event.primary_key for event in events] == ["o1", "o2"]

