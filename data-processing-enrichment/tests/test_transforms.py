from nexus_processing.config import TransformConfig
from nexus_processing.transforms import normalize_case, transform_record


def test_transform_record_trims_renames_defaults_and_normalizes_case():
    config = TransformConfig(
        trim_strings=True,
        rename_fields={"customer_name": "name"},
        default_values={"lifecycle_stage": "unknown"},
        normalize_case_fields={"status": "lower"},
    )

    record = transform_record(
        {"customer_id": "c001", "customer_name": " Acme ", "status": " ACTIVE "},
        config,
    )

    assert record == {
        "customer_id": "c001",
        "name": "Acme",
        "status": "active",
        "lifecycle_stage": "unknown",
    }


def test_normalize_case_rejects_unknown_mode():
    try:
        normalize_case("value", "sentence")
    except ValueError as exc:
        assert "Unsupported case" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

