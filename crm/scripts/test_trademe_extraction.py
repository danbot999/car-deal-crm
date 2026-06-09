from __future__ import annotations

from value_trademe import (
    calculate_deal_metrics,
    extract_kms,
    extract_number_plate,
    parse_manual_kms,
    parse_manual_plate,
)


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> None:
    plate, confidence = extract_number_plate("Rego: ABC123. Fresh WOF.")
    assert_equal((plate, confidence), ("ABC123", 90), "standard plate")

    plate, confidence = extract_number_plate("number plate ab-12-c on request")
    assert_equal((plate, confidence), ("AB12C", 90), "spaced plate")

    plate, confidence = extract_number_plate("Fresh WOF, rego, tidy daily.")
    assert_equal((plate, confidence), (None, None), "missing plate")

    assert_equal(parse_manual_plate("abc-123"), "ABC123", "manual plate")
    assert_equal(parse_manual_plate("rego"), None, "manual plate stopword")

    kms, confidence = extract_kms("Odometer 181,000 km")
    assert_equal((kms, confidence), (181000, 90), "comma kms")

    kms, confidence = extract_kms("done 181k, very tidy")
    assert_equal((kms, confidence), (181000, 90), "k shorthand")

    kms, confidence = extract_kms("fuel saver (181k) wof rego")
    assert_equal((kms, confidence), (181000, 90), "bare k shorthand")

    kms, confidence = extract_kms("odometer 181000")
    assert_equal((kms, confidence), (181000, 90), "plain odometer")

    kms, confidence = extract_kms("cheap daily driver")
    assert_equal((kms, confidence), (None, None), "missing kms")

    kms, confidence = extract_kms("2008 Mitsubishi Outlander")
    assert_equal((kms, confidence), (None, None), "year is not kms")

    assert_equal(parse_manual_kms("181,000"), 181000, "manual kms")
    assert_equal(parse_manual_kms("181k"), 181000, "manual kms shorthand")
    assert_equal(parse_manual_kms("2008"), None, "manual kms rejects year")

    assert_equal(
        calculate_deal_metrics(500000, 300000),
        (400000, 300000, 100000),
        "deal metrics",
    )

    print("[TEST] Trade Me extraction tests passed.")


if __name__ == "__main__":
    main()
