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
