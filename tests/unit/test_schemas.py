"""Schema strictness tests (guideline §8, §31.1).

Request models are ``StrictModel``s: unknown fields, unknown ops, NaN/Inf, and
malformed geometry must be rejected at validation time.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from support.models import find_model


def _valid_apply_actions_payload() -> dict:
    return {
        "operation_id": "7d5f41dc-2b65-4f49-b64d-1b2bc3a8bf4d",
        "document_id": "3df067c4-61d6-4ee7-a51c-9325263e5035",
        "expected_revision": 0,
        "atomic": True,
        "stop_on_error": True,
        "actions": [
            {
                "op": "create_circle",
                "action_id": "hole-1",
                "center": {"x": 20, "y": 25, "z": 0},
                "radius": 3,
                "layer": "A-OUTLINE",
            }
        ],
    }


class TestStrictModels:
    def test_unknown_field_rejected(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["unexpected_extra"] = True
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_unknown_action_field_rejected(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"][0]["bogus_geometry"] = 12
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_unknown_op_rejected(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"][0] = {
            "op": "create_line",  # not part of the typed action vocabulary
            "start": {"x": 0, "y": 0, "z": 0},
            "end": {"x": 1, "y": 1, "z": 0},
        }
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_nan_rejected_in_geometry(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"][0]["radius"] = float("nan")
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_infinity_rejected_in_geometry(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"][0]["center"] = {"x": math.inf, "y": 0, "z": 0}
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_empty_actions_rejected(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"] = []
        with pytest.raises(ValidationError):
            model.model_validate(payload)


class TestGeometryValidation:
    def _circle(self, **overrides):
        base = {
            "op": "create_circle",
            "action_id": "c1",
            "center": {"x": 0, "y": 0, "z": 0},
            "radius": 5,
            "layer": "0",
        }
        base.update(overrides)
        return base

    def _validate_action(self, action: dict):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        payload["actions"] = [action]
        return model.model_validate(payload)

    def test_zero_radius_rejected(self):
        with pytest.raises(ValidationError):
            self._validate_action(self._circle(radius=0))

    def test_negative_radius_rejected(self):
        with pytest.raises(ValidationError):
            self._validate_action(self._circle(radius=-3))

    def test_valid_circle_accepted(self):
        result = self._validate_action(self._circle())
        assert len(result.actions) == 1

    def test_polyline_needs_at_least_two_vertices(self):
        polyline = {
            "op": "create_polyline",
            "action_id": "pl1",
            "vertices": [{"x": 0, "y": 0, "z": 0}],
        }
        with pytest.raises(ValidationError):
            self._validate_action(polyline)

    def test_polyline_with_two_vertices_accepted(self):
        polyline = {
            "op": "create_polyline",
            "action_id": "pl2",
            "vertices": [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}],
        }
        result = self._validate_action(polyline)
        assert result.actions[0].op == "create_polyline"

    def test_text_over_limit_rejected(self):
        text_action = {
            "op": "create_text",
            "action_id": "t1",
            "position": {"x": 0, "y": 0, "z": 0},
            "text": "x" * 20_001,
            "height": 2.5,
            "layer": "0",
        }
        with pytest.raises(ValidationError):
            self._validate_action(text_action)

    def test_text_at_limit_accepted(self):
        text_action = {
            "op": "create_text",
            "action_id": "t2",
            "position": {"x": 0, "y": 0, "z": 0},
            "text": "x" * 20_000,
            "height": 2.5,
        }
        result = self._validate_action(text_action)
        assert result.actions[0].op == "create_text"

    def test_non_finite_point_rejected(self):
        point3 = find_model("Point3")
        with pytest.raises(ValidationError):
            point3.model_validate({"x": float("nan"), "y": 0})
        with pytest.raises(ValidationError):
            point3.model_validate({"x": 0, "y": float("inf")})
        with pytest.raises(ValidationError):
            point3.model_validate({"x": 0, "y": 0, "z": float("-inf")})


class TestJsonSafety:
    def test_request_round_trips_through_json(self):
        model = find_model("ApplyActionsRequest")
        payload = _valid_apply_actions_payload()
        instance = model.model_validate(payload)
        serialized = instance.model_dump_json()
        assert '"operation_id"' in serialized
        revived = model.model_validate_json(serialized)
        assert revived.operation_id == instance.operation_id

    def test_entity_query_limit_bounds(self):
        query = find_model("EntityQuery")
        base = {"document_id": "3df067c4-61d6-4ee7-a51c-9325263e5035"}
        with pytest.raises(ValidationError):
            query.model_validate({**base, "limit": 0})
        with pytest.raises(ValidationError):
            query.model_validate({**base, "limit": 1001})
        assert query.model_validate({**base, "limit": 1000}).limit == 1000

    def test_get_entities_handle_limit(self):
        model = find_model("GetEntitiesRequest")
        base = {"document_id": "3df067c4-61d6-4ee7-a51c-9325263e5035"}
        with pytest.raises(ValidationError):
            model.model_validate({**base, "handles": []})
        with pytest.raises(ValidationError):
            model.model_validate({**base, "handles": [str(i) for i in range(1001)]})
        ok = model.model_validate({**base, "handles": ["1A", "2B"]})
        assert ok.handles == ["1A", "2B"]
