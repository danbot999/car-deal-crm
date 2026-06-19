from __future__ import annotations

from check_marketplace_availability import classify_detail_text
from check_marketplace_availability import update_listing


def assert_status(name: str, expected: str, **kwargs: object) -> None:
    result = classify_detail_text(**kwargs)  # type: ignore[arg-type]
    if result.status != expected:
        raise AssertionError(
            f"{name}: expected {expected}, got {result.status} ({result.reason})"
        )


def main() -> None:
    assert_status(
        "active_h1",
        "ACTIVE",
        page_title="2008 Toyota Corolla | Facebook Marketplace | Facebook",
        body_text="Marketplace listing $4,500 Seller information Auckland",
        h1_values=["2008 Toyota Corolla"],
        open_graph_titles=[],
    )
    assert_status(
        "sold_signal",
        "SOLD",
        page_title="Facebook Marketplace",
        body_text="This item has been marked as sold by the seller.",
        h1_values=[],
        open_graph_titles=[],
    )
    assert_status(
        "unavailable_signal",
        "UNAVAILABLE",
        page_title="This content isn't available",
        body_text="This listing isn't available anymore.",
        h1_values=[],
        open_graph_titles=[],
    )
    assert_status(
        "login_blocked",
        "UNKNOWN",
        page_title="Facebook",
        body_text="Log in to Facebook to continue.",
        h1_values=[],
        open_graph_titles=[],
    )

    sold_result = classify_detail_text(
        page_title="Facebook Marketplace",
        body_text="This item has been marked as sold by the seller.",
        h1_values=[],
        open_graph_titles=[],
    )
    first_check = update_listing(
        _DryRunConnection(),
        {
            "id": "test",
            "title": "2008 Toyota Corolla",
            "availabilityStatus": "ACTIVE",
            "unavailableCheckCount": 0,
            "consecutiveUnavailableChecks": 0,
            "unavailableSince": None,
        },
        sold_result,
        failure_threshold=2,
        dry_run=True,
    )
    if first_check["nextStatus"] != "POSSIBLY_SOLD":
        raise AssertionError(
            "first sold signal should become POSSIBLY_SOLD, "
            f"got {first_check['nextStatus']}"
        )

    second_check = update_listing(
        _DryRunConnection(),
        {
            "id": "test",
            "title": "2008 Toyota Corolla",
            "availabilityStatus": "POSSIBLY_SOLD",
            "unavailableCheckCount": 1,
            "consecutiveUnavailableChecks": 1,
            "unavailableSince": "2026-06-18T00:00:00+00:00",
        },
        sold_result,
        failure_threshold=2,
        dry_run=True,
    )
    if second_check["nextStatus"] != "CONFIRMED_SOLD":
        raise AssertionError(
            "second sold signal should become CONFIRMED_SOLD, "
            f"got {second_check['nextStatus']}"
        )

    print("[TEST] availability classifier checks passed")


class _DryRunConnection:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run update should not execute SQL")


if __name__ == "__main__":
    main()
