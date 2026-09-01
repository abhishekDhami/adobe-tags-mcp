from __future__ import annotations

from app.adobe.jsonapi import eq_filter, max_revision_number, paginate_meta, parse_latest_revision_number, reactor_page_number, resource_meta


def test_eq_filter() -> None:
    assert eq_filter("development") == "EQ development"


def test_reactor_page_number_is_one_based() -> None:
    assert reactor_page_number(1) == 1
    assert reactor_page_number(2) == 2
    assert reactor_page_number(0) == 1


def test_paginate_meta_has_next_page() -> None:
    meta = paginate_meta(page=1, page_size=25, total_items=90)
    assert meta["totalPages"] == 4
    assert meta["hasNextPage"] is True
    assert meta["hasPreviousPage"] is False

    meta_page2 = paginate_meta(page=2, page_size=25, total_items=90)
    assert meta_page2["hasNextPage"] is True
    assert meta_page2["hasPreviousPage"] is True

    meta_last = paginate_meta(page=4, page_size=25, total_items=90)
    assert meta_last["hasNextPage"] is False


def test_resource_meta_prefers_item_meta() -> None:
    item = {"meta": {"latest_revision_number": 3}}
    payload = {"meta": {"pagination": {"total_count": 1}}}
    assert resource_meta(item, payload)["latest_revision_number"] == 3


def test_parse_latest_revision_number() -> None:
    assert parse_latest_revision_number({"latest_revision_number": 2}) == 2
    assert parse_latest_revision_number({"latest_revision_number": "4"}) == 4
    assert parse_latest_revision_number({}) is None


def test_max_revision_number_from_revisions_list() -> None:
    revisions = [
        {
            "attributes": {"revision_number": 0},
            "meta": {"latest_revision_number": 2},
        },
        {
            "attributes": {"revision_number": 2},
            "meta": {"latest_revision_number": 2},
        },
    ]
    assert max_revision_number(revisions) == 2
