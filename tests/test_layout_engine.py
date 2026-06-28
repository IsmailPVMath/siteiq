"""Layout engine — string packing and N-S access blocks."""

from layoutiq.engine import count_strings_in_length, run_layout


def test_count_strings_whole_only():
    # 28 × 1.038 m strings, 0.5 m gap
    n = count_strings_in_length(
        100.0,
        modules_per_string=28,
        module_w=1.038,
        inter_string_gap_m=0.5,
    )
    assert n == 3
    # Partial 4th string does not fit
    assert n * 28 * 1.038 + (n - 1) * 0.5 < 100.0


def test_roads_reduce_row_count():
    # 500 m × 800 m site in local coords (approx rectangle via lat/lon box)
    ref_lat, ref_lon = 32.0, -96.5
    dlat, dlon = 0.004, 0.004
    ring = [
        (ref_lat, ref_lon),
        (ref_lat + dlat, ref_lon),
        (ref_lat + dlat, ref_lon + dlon),
        (ref_lat, ref_lon + dlon),
    ]
    dense = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        rows_per_block=0,
        block_gap_m=0.0,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    with_roads_legacy_bands = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        rows_per_block=2,
        block_gap_m=5.0,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    with_roads_ns = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        rows_per_block=16,
        ns_gap_1_m=0.0,
        block_gap_m=5.0,
        cols_per_block=50,
        ew_gap_m=6.0,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    assert dense and with_roads_legacy_bands and with_roads_ns
    assert with_roads_legacy_bands["total_modules"] < dense["total_modules"]
    assert with_roads_ns["total_modules"] < dense["total_modules"]
    assert with_roads_ns["total_rows"] < dense["total_rows"]


def test_tracker_units_respect_options_around_obstruction():
    # Trackers are rigid: a clipped 6/5/4/3-string unit must be dropped whole,
    # never left as a 1- or 2-string stub, even when a restriction (tree) and an
    # irregular boundary clip the rows.
    ref_lat, ref_lon = 17.0, 78.0

    def square(half):
        return [
            (ref_lat - half, ref_lon - half),
            (ref_lat - half, ref_lon + half),
            (ref_lat + half, ref_lon + half),
            (ref_lat + half, ref_lon - half),
        ]

    options = [6, 5, 4, 3]
    layout = run_layout(
        square(0.0027),
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.0,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        tracker_string_options=options,
        max_tracker_length_m=260.0,
        restriction_latlons=[square(0.0008)],
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    assert layout
    for row in layout["rows_data"]:
        units = row.get("tracker_units") or []
        # Every placed tracker unit is one of the selected options.
        assert all(u in options for u in units)
        # Strings map exactly to whole units (no clipped stubs, no partials).
        assert row["partial_modules"] == 0
        assert row["n_strings"] == sum(units)


def test_prune_isolated_blocks_flag():
    ref_lat, ref_lon = 32.0, -96.5
    dlat, dlon = 0.004, 0.004
    ring = [
        (ref_lat, ref_lon),
        (ref_lat + dlat, ref_lon),
        (ref_lat + dlat, ref_lon + dlon),
        (ref_lat, ref_lon + dlon),
    ]
    dense = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
        prune_isolated_blocks=True,
    )
    assert dense
    assert dense["total_modules"] > 0
