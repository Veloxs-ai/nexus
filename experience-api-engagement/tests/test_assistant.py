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

from nexus_experience.assistant import AssistantSessionStore


def test_start_session_uses_configured_greeting(sample_config):
    store = AssistantSessionStore(sample_config)

    session = store.start_session(user_id="u1")

    assert session.user_id == "u1"
    assert session.greeting == "Hello"


def test_append_message_trims_history(sample_config):
    store = AssistantSessionStore(sample_config)
    session = store.start_session()

    store.append_message(session.session_id, "user", "one")
    store.append_message(session.session_id, "assistant", "two")
    store.append_message(session.session_id, "user", "three")

    assert [message["content"] for message in store.get(session.session_id).history] == [
        "two",
        "three",
    ]
