"""Canonical JSON determinism tests (§21, §31.1)."""

from __future__ import annotations

import json

import pytest

from gstarcad_mcp.util.json import assert_wire_safe, canonical_dumps, request_hash


class TestCanonicalDumps:
    def test_key_order_is_normalized(self):
        a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
        b = {"c": {"y": 2, "z": 1}, "a": 2, "b": 1}
        assert canonical_dumps(a) == canonical_dumps(b)

    def test_compact_separators(self):
        text = canonical_dumps({"a": 1, "b": [1, 2]})
        assert text == '{"a":1,"b":[1,2]}'

    def test_ascii_escaped(self):
        text = canonical_dumps({"name": "图层"})
        assert "图层" not in text
        assert json.loads(text) == {"name": "图层"}

    def test_nested_insertion_order_irrelevant(self):
        a = {"actions": [{"op": "x", "id": 1}, {"id": 2, "op": "y"}]}
        b = {"actions": [{"id": 1, "op": "x"}, {"op": "y", "id": 2}]}
        assert canonical_dumps(a) == canonical_dumps(b)


class TestRequestHash:
    def test_stable_across_key_order(self):
        assert request_hash({"a": 1, "b": 2}) == request_hash({"b": 2, "a": 1})

    def test_changes_with_values(self):
        assert request_hash({"a": 1}) != request_hash({"a": 2})

    def test_changes_with_structure(self):
        assert request_hash({"a": [1, 2]}) != request_hash({"a": [2, 1]})

    def test_hex_digest(self):
        digest = request_hash({"x": "y"})
        int(digest, 16)  # must parse as hex
        assert len(digest) == 64  # sha256


class TestWireSafety:
    def test_plain_json_values_pass(self):
        value = {"s": "text", "i": 1, "f": 1.5, "b": True, "n": None, "l": [1, "two"]}
        assert assert_wire_safe(value) is value

    def test_non_string_keys_rejected(self):
        with pytest.raises(TypeError):
            assert_wire_safe({1: "one"})

    def test_com_like_objects_rejected(self):
        class FakeComObject:
            def __repr__(self) -> str:
                return "<FakeComObject AcDbLine 1F>"

        with pytest.raises(TypeError):
            assert_wire_safe({"entity": FakeComObject()})

    def test_nested_com_object_rejected(self):
        class Handle:
            pass

        with pytest.raises(TypeError):
            assert_wire_safe({"entities": [{"raw": Handle()}]})

    def test_non_finite_floats_rejected(self):
        with pytest.raises(TypeError):
            assert_wire_safe({"x": float("nan")})
        with pytest.raises(TypeError):
            assert_wire_safe({"x": float("inf")})

    def test_tuples_treated_as_lists(self):
        assert_wire_safe((1, 2, 3))
