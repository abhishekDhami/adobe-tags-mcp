from __future__ import annotations

import json

from app.presenters import ViewOptions, present_rule
from app.presenters.common import parse_settings_field, summarize_settings_value
from app.presenters.data_element import present_data_element
from app.presenters.extension import present_extension
from app.presenters.rule import present_rule_index


RULE_ITEM = {
    "id": "RL123",
    "type": "rules",
    "attributes": {
        "name": "Page Load Rule",
        "enabled": True,
        "dirty": False,
        "published": True,
        "published_at": "2026-01-15T10:00:00.000Z",
        "review_status": "approved",
        "created_at": "2025-12-01T08:00:00.000Z",
        "updated_at": "2026-01-15T09:30:00.000Z",
        "created_by_email": "dev@example.com",
        "created_by_display_name": "Dev User",
    },
    "relationships": {
        "property": {"data": {"id": "PR456", "type": "properties"}},
    },
}

EVENT_COMPONENT = {
    "id": "RC1",
    "type": "rule_components",
    "attributes": {
        "name": "Library Loaded",
        "delegate_descriptor_id": "core::events::library-loaded",
        "order": 0,
        "settings": json.dumps({"eventKey": "libraryLoaded"}),
    },
    "relationships": {
        "extension": {"data": {"id": "EX789", "type": "extensions"}},
    },
}


def test_present_rule_index_omits_relationships() -> None:
    view = present_rule_index(RULE_ITEM)
    assert view["resourceType"] == "rule"
    assert view["name"] == "Page Load Rule"
    assert "relationships" not in view
    assert "attributes" not in view
    assert "meta" not in view


def test_present_rule_context_includes_logic_and_audit() -> None:
    extension_lookup = {"EX789": {"id": "EX789", "name": "Core", "installedExtensionVersion": "1.0.0"}}
    view = present_rule(
        RULE_ITEM,
        options=ViewOptions(depth="context"),
        components=[EVENT_COMPONENT],
        extension_lookup=extension_lookup,
        property_summary={"id": "PR456", "name": "My Web Property"},
        version=3,
    )
    assert view["version"] == 3
    assert "dirty" not in view
    assert "revisionNumber" not in view
    assert view["createdBy"]["email"] == "dev@example.com"
    assert view["property"]["name"] == "My Web Property"
    assert len(view["logic"]["events"]) == 1
    event = view["logic"]["events"][0]
    assert event["extension"]["name"] == "Core"
    assert event["settingsSummary"] == "{eventKey=libraryLoaded}"
    assert "relationships" not in view
    assert "attributes" not in view


def test_present_rule_detail_skips_logic() -> None:
    view = present_rule(
        RULE_ITEM,
        options=ViewOptions(depth="detail"),
        components=[EVENT_COMPONENT],
    )
    assert view["version"] == 0
    assert "logic" not in view
    assert view["meta"]["depth"] == "detail"


def test_parse_settings_field_raw_opt_in() -> None:
    raw = '{"account": "prod"}'
    without_raw = parse_settings_field(raw, include_raw=False, include_full=False, max_length=500)
    assert "settingsRaw" not in without_raw
    assert without_raw["settings"]["account"] == "prod"

    with_raw = parse_settings_field(raw, include_raw=True, include_full=True, max_length=500)
    assert with_raw["settingsRaw"] == raw


def test_summarize_settings_value_truncates_large_dict() -> None:
    summary = summarize_settings_value({f"k{i}": i for i in range(12)})
    assert "…" in summary


def test_present_data_element_detail_has_no_raw_adobe_shape() -> None:
    item = {
        "id": "DE1",
        "type": "data_elements",
        "attributes": {
            "name": "Page Name",
            "enabled": True,
            "delegate_descriptor_id": "core::dataElements::custom-code",
            "settings": json.dumps({"source": "title"}),
            "revision_number": 1,
        },
        "relationships": {"property": {"data": {"id": "PR456"}}},
    }
    view = present_data_element(item, options=ViewOptions(depth="detail"), version=2)
    assert view["resourceType"] == "dataElement"
    assert view["version"] == 2
    assert view["settingsSummary"] == "{source=title}"
    assert "revisionNumber" not in view
    assert "relationships" not in view


def test_present_extension_detail() -> None:
    item = {
        "id": "EX1",
        "type": "extensions",
        "attributes": {
            "name": "Adobe Analytics",
            "display_name": "Adobe Analytics",
            "enabled": True,
            "version": "2.0.0",
        },
    }
    view = present_extension(item, options=ViewOptions(depth="detail"), version=4)
    assert view["name"] == "Adobe Analytics"
    assert view["version"] == 4
    assert view["installedExtensionVersion"] == "2.0.0"
    assert view["meta"]["resourceType"] == "extension"
