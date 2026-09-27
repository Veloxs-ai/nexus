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

"""Tests for ML providers, JPEG bug fix, and pluggable content extraction."""

from __future__ import annotations

import struct

import pytest


# =============================================================================
# 1. JPEG Dimension Bug Fix Regression Test
# =============================================================================

def _build_minimal_jpeg(width: int, height: int, channels: int = 3) -> bytes:
    """Builds a minimal JPEG binary with an SOF0 marker containing given dimensions."""
    # SOI marker
    data = b"\xff\xd8"
    # SOF0 marker: FF C0
    # Segment length = 8 + 3*channels (but we just need enough for the struct unpack)
    seg_length = 8 + 3 * channels
    sof_payload = struct.pack(">HBHHB", seg_length, 8, height, width, channels)
    data += b"\xff\xc0" + sof_payload
    # EOI marker
    data += b"\xff\xd9"
    return data


class TestJPEGDimensionBugFix:
    """Regression tests for the JPEG decode_jpeg struct.unpack bug fix."""

    def test_jpeg_640x480_dimensions(self):
        """Verifies JPEG wider than 255px decodes correctly (was broken before fix)."""
        from nexus_processing.images import process_image_binary

        jpeg_data = _build_minimal_jpeg(width=640, height=480)
        result = process_image_binary(jpeg_data, format_hint="jpeg")
        assert result.metadata.width == 640
        assert result.metadata.height == 480

    def test_jpeg_1920x1080_dimensions(self):
        """Verifies Full HD JPEG dimensions decode correctly."""
        from nexus_processing.images import process_image_binary

        jpeg_data = _build_minimal_jpeg(width=1920, height=1080)
        result = process_image_binary(jpeg_data, format_hint="jpeg")
        assert result.metadata.width == 1920
        assert result.metadata.height == 1080

    def test_jpeg_small_image_still_works(self):
        """Verifies small JPEG (< 255px) still works after the fix."""
        from nexus_processing.images import process_image_binary

        jpeg_data = _build_minimal_jpeg(width=100, height=80)
        result = process_image_binary(jpeg_data, format_hint="jpeg")
        assert result.metadata.width == 100
        assert result.metadata.height == 80


# =============================================================================
# 2. ML Provider Protocol Tests
# =============================================================================

class TestMLProviderProtocols:
    """Tests for Protocol interfaces and utility functions."""

    def test_is_package_available_stdlib(self):
        """Verifies is_package_available returns True for stdlib modules."""
        from nexus_processing.ml_providers import is_package_available

        assert is_package_available("json") is True
        assert is_package_available("os") is True
        assert is_package_available("nonexistent_fake_module_xyz") is False

    def test_ocr_provider_protocol_compliance(self):
        """Verifies a custom class implementing extract_text satisfies OCRProvider."""
        from nexus_processing.ml_providers import OCRProvider

        class MockOCR:
            def extract_text(self, image_bytes: bytes) -> str:
                return "hello world"

        provider = MockOCR()
        assert isinstance(provider, OCRProvider)
        assert provider.extract_text(b"fake") == "hello world"

    def test_audio_transcriber_protocol_compliance(self):
        """Verifies a custom class implementing transcribe satisfies AudioTranscriber."""
        from nexus_processing.ml_providers import AudioTranscriber

        class MockTranscriber:
            def transcribe(self, audio_bytes: bytes) -> tuple[str, list[dict]]:
                return "hello", [{"start": 0.0, "end": 1.0, "text": "hello"}]

        transcriber = MockTranscriber()
        assert isinstance(transcriber, AudioTranscriber)
        text, segments = transcriber.transcribe(b"fake")
        assert text == "hello"
        assert len(segments) == 1

    def test_video_demuxer_protocol_compliance(self):
        """Verifies a custom class implementing extract_audio/keyframes satisfies VideoDemuxer."""
        from nexus_processing.ml_providers import VideoDemuxer

        class MockDemuxer:
            def extract_audio(self, video_bytes: bytes) -> bytes | None:
                return b"audio"

            def extract_keyframes(
                self, video_bytes: bytes, max_frames: int = 50
            ) -> list[tuple[float, bytes]]:
                return [(0.0, b"frame")]

        demuxer = MockDemuxer()
        assert isinstance(demuxer, VideoDemuxer)


# =============================================================================
# 3. Graceful Fallback Tests (No ML Dependencies)
# =============================================================================

class TestGracefulFallback:
    """Tests that processors work correctly when ML deps are not installed."""

    def test_image_processes_without_ocr_provider(self):
        """Image processing works without any OCR provider — empty ocr_text, no crash."""
        from nexus_processing.images import process_image_binary

        jpeg_data = _build_minimal_jpeg(width=320, height=240)
        result = process_image_binary(jpeg_data, format_hint="jpeg")
        # Should succeed with empty ocr_text
        assert result.metadata.width == 320
        assert result.metadata.ocr_text == "" or result.metadata.ocr_text is None

    def test_image_with_precomputed_ocr_text(self):
        """Image processing with pre-computed OCR text bypasses any provider."""
        from nexus_processing.images import process_image_binary

        jpeg_data = _build_minimal_jpeg(width=320, height=240)
        result = process_image_binary(
            jpeg_data, format_hint="jpeg", ocr_text="Invoice #12345"
        )
        assert result.metadata.ocr_text == "Invoice #12345"

    def test_image_with_mock_ocr_provider(self):
        """Image processing with a custom OCR provider extracts text."""
        from nexus_processing.images import process_image_binary

        class MockOCR:
            def extract_text(self, image_bytes: bytes) -> str:
                return "Detected text from mock"

        jpeg_data = _build_minimal_jpeg(width=320, height=240)
        result = process_image_binary(
            jpeg_data, format_hint="jpeg", ocr_provider=MockOCR()
        )
        assert result.metadata.ocr_text == "Detected text from mock"

    def test_image_precomputed_takes_priority_over_provider(self):
        """Pre-computed ocr_text takes priority over provider."""
        from nexus_processing.images import process_image_binary

        class MockOCR:
            def extract_text(self, image_bytes: bytes) -> str:
                return "Should NOT appear"

        jpeg_data = _build_minimal_jpeg(width=320, height=240)
        result = process_image_binary(
            jpeg_data, format_hint="jpeg", ocr_text="Pre-computed", ocr_provider=MockOCR()
        )
        assert result.metadata.ocr_text == "Pre-computed"

    def test_audio_processes_without_transcriber(self):
        """Audio processing works without any transcriber — no crash."""
        from nexus_processing.audio import process_audio_binary

        # Minimal WAV: RIFF header + fmt chunk + data chunk (mono, 16-bit, 8000Hz, 0.01s)
        sample_rate = 8000
        num_samples = 80  # 10ms
        bits = 16
        channels = 1
        data_size = num_samples * channels * (bits // 8)
        fmt_chunk = struct.pack(
            "<4sIHHIIHH", b"fmt ", 16, 1, channels, sample_rate,
            sample_rate * channels * (bits // 8), channels * (bits // 8), bits
        )
        data_chunk = b"data" + struct.pack("<I", data_size) + (b"\x00" * data_size)
        wav = b"RIFF" + struct.pack("<I", 4 + len(fmt_chunk) + len(data_chunk)) + b"WAVE"
        wav += fmt_chunk + data_chunk

        result = process_audio_binary(wav)
        assert result.metadata.format == "WAV"
        assert result.metadata.sample_rate == 8000


# =============================================================================
# 4. Client Integration Tests
# =============================================================================

class TestClientMLIntegration:
    """Tests that NexusClient correctly passes ML params through."""

    def test_process_image_with_auto_extract_param(self):
        """NexusClient.process_image accepts auto_extract without error."""
        from nexus.client import NexusClient

        client = NexusClient(in_memory_only=True)
        jpeg_data = _build_minimal_jpeg(width=320, height=240)
        result = client.process_image(
            image_id="test_img",
            name="test.jpg",
            image_bytes=jpeg_data,
            auto_extract=False,  # Explicitly False since we have no ML deps
        )
        assert result.document_id == "test_img"
        assert len(result.chunks) > 0

    def test_process_document_image_routing_with_auto_extract(self):
        """process_document routes images and passes auto_extract kwarg."""
        from nexus.client import NexusClient

        client = NexusClient(in_memory_only=True)
        jpeg_data = _build_minimal_jpeg(width=640, height=480)
        result = client.process_document(
            document_id="doc_img",
            name="photo.jpg",
            text=jpeg_data,
            auto_extract=False,
        )
        assert result.document_id == "doc_img"
        assert len(result.chunks) > 0
