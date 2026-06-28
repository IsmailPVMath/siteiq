"""Buildable area — soft constraint (vegetation) handling."""

from pvmath_workflow.buildable_engine import compute_layout_exclusion_rings


def _square_ring(ref_lat: float, ref_lon: float, half: float):
    return [
        [
            (ref_lat - half, ref_lon - half),
            (ref_lat - half, ref_lon + half),
            (ref_lat + half, ref_lon + half),
            (ref_lat + half, ref_lon - half),
        ]
    ]


def _forest_fc(ref_lat: float, ref_lon: float):
    lat, lon = ref_lat, ref_lon
    return {
        "forests": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"category": "forests"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon - 0.0002, lat - 0.0002],
                                [lon + 0.0002, lat - 0.0002],
                                [lon + 0.0002, lat + 0.0002],
                                [lon - 0.0002, lat + 0.0002],
                                [lon - 0.0002, lat - 0.0002],
                            ]
                        ],
                    },
                }
            ],
        }
    }


def test_ignore_soft_constraints_skips_forests():
    ref_lat, ref_lon = 17.0, 78.0
    rings = _square_ring(ref_lat, ref_lon, 0.002)
    layers = _forest_fc(ref_lat, ref_lon)
    with_forests = compute_layout_exclusion_rings(
        rings,
        layers,
        setbacks_m={"forests": 20.0},
        ignore_soft_constraints=False,
    )
    without_forests = compute_layout_exclusion_rings(
        rings,
        layers,
        setbacks_m={"forests": 20.0},
        ignore_soft_constraints=True,
    )
    assert with_forests
    assert not without_forests
