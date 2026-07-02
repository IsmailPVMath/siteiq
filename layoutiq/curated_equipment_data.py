"""Curated utility-scale module/inverter specs — screening grade (2024–2025 mainstream)."""

from __future__ import annotations

from typing import Any, Dict

CURATED_MODULES: Dict[str, Dict[str, Any]] = {
    "Jinko Tiger Neo N-type 620Wp": {
        "Wp": 620, "Voc": 38.8, "Vmp": 32.4, "Isc": 17.91, "Imp": 16.98,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0028, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Jinko Tiger Neo 575Wp": {
        "Wp": 575, "Voc": 38.2, "Vmp": 31.8, "Isc": 17.2, "Imp": 16.35,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0028, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Jinko Tiger Pro 78TRL 590Wp": {
        "Wp": 590, "Voc": 38.5, "Vmp": 32.1, "Isc": 17.5, "Imp": 16.6,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "LONGi Hi-MO 6 660Wp": {
        "Wp": 660, "Voc": 40.2, "Vmp": 33.9, "Isc": 18.32, "Imp": 17.48,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00045, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "LONGi Hi-MO 7 650Wp": {
        "Wp": 650, "Voc": 39.8, "Vmp": 33.5, "Isc": 18.0, "Imp": 17.2,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00045, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "LONGi Hi-MO X6 615Wp": {
        "Wp": 615, "Voc": 38.9, "Vmp": 32.6, "Isc": 17.7, "Imp": 16.85,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00044, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Trina Vertex S+ 695Wp": {
        "Wp": 695, "Voc": 40.9, "Vmp": 34.4, "Isc": 19.07, "Imp": 18.17,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00048, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "Trina Vertex N 700Wp": {
        "Wp": 700, "Voc": 41.2, "Vmp": 34.6, "Isc": 19.2, "Imp": 18.3,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00048, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "Trina Vertex 670Wp": {
        "Wp": 670, "Voc": 40.0, "Vmp": 33.8, "Isc": 18.5, "Imp": 17.6,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00047, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "Canadian Solar HiKu7 665Wp": {
        "Wp": 665, "Voc": 40.5, "Vmp": 34.1, "Isc": 18.64, "Imp": 17.72,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0027, "alpha_Isc": 0.00044, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "Canadian Solar TOPHiKu7 690Wp": {
        "Wp": 690, "Voc": 40.8, "Vmp": 34.3, "Isc": 19.0, "Imp": 18.1,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00045, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "Canadian Solar BiHiKu7 655Wp": {
        "Wp": 655, "Voc": 40.0, "Vmp": 33.7, "Isc": 18.3, "Imp": 17.4,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0027, "alpha_Isc": 0.00044, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "JA Solar JAM72D42 580Wp": {
        "Wp": 580, "Voc": 41.8, "Vmp": 34.9, "Isc": 15.59, "Imp": 14.83,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.00040, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "JA Solar JAM72S30 615Wp": {
        "Wp": 615, "Voc": 38.6, "Vmp": 32.5, "Isc": 17.6, "Imp": 16.75,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.00042, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "JA Solar JAM66D45 605Wp": {
        "Wp": 605, "Voc": 38.0, "Vmp": 32.0, "Isc": 17.3, "Imp": 16.5,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.00041, "T_NOCT": 43,
        "cells_in_series": 66, "dimensions_mm": [2187, 1134, 30], "bifacial": True,
    },
    "Risen Titan S 680Wp": {
        "Wp": 680, "Voc": 40.6, "Vmp": 34.0, "Isc": 18.8, "Imp": 17.9,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00046, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "Risen Titan 610Wp": {
        "Wp": 610, "Voc": 38.4, "Vmp": 32.2, "Isc": 17.4, "Imp": 16.6,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00044, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Huasun HS-210-B132DS 715Wp": {
        "Wp": 715, "Voc": 41.5, "Vmp": 35.0, "Isc": 19.5, "Imp": 18.5,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00048, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "Huasun Himalaya G12-670Wp": {
        "Wp": 670, "Voc": 40.3, "Vmp": 33.9, "Isc": 18.6, "Imp": 17.7,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00046, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "Aiko Neostar 2S 640Wp": {
        "Wp": 640, "Voc": 39.5, "Vmp": 33.2, "Isc": 18.0, "Imp": 17.1,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00045, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Qcells Q.PEAK DUO XL-G10.3 590Wp": {
        "Wp": 590, "Voc": 38.3, "Vmp": 31.9, "Isc": 17.4, "Imp": 16.55,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 32], "bifacial": False,
    },
    "Astronergy CHSM72N-HC 615Wp": {
        "Wp": 615, "Voc": 38.7, "Vmp": 32.4, "Isc": 17.6, "Imp": 16.8,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.00042, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Seraphim S8 670Wp": {
        "Wp": 670, "Voc": 40.1, "Vmp": 33.8, "Isc": 18.5, "Imp": 17.6,
        "beta_Voc": -0.0025, "beta_Vmp": -0.0026, "alpha_Isc": 0.00044, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 30], "bifacial": True,
    },
    "TW Solar 700Wp": {
        "Wp": 700, "Voc": 41.0, "Vmp": 34.5, "Isc": 19.1, "Imp": 18.2,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00047, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "GCL N-Type 695Wp": {
        "Wp": 695, "Voc": 40.7, "Vmp": 34.2, "Isc": 19.0, "Imp": 18.0,
        "beta_Voc": -0.0024, "beta_Vmp": -0.0025, "alpha_Isc": 0.00047, "T_NOCT": 42,
        "cells_in_series": 78, "dimensions_mm": [2384, 1134, 35], "bifacial": True,
    },
    "DMEGC 620Wp N-type": {
        "Wp": 620, "Voc": 38.9, "Vmp": 32.5, "Isc": 17.8, "Imp": 16.95,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0028, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 78, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
    "Phono Solar 590Wp": {
        "Wp": 590, "Voc": 38.2, "Vmp": 31.8, "Isc": 17.3, "Imp": 16.5,
        "beta_Voc": -0.0026, "beta_Vmp": -0.0027, "alpha_Isc": 0.0004, "T_NOCT": 43,
        "cells_in_series": 72, "dimensions_mm": [2278, 1134, 30], "bifacial": True,
    },
}

CURATED_INVERTERS: Dict[str, Dict[str, Any]] = {
    "Sungrow SG3125HV-30 (3.125 MW, 1500V)": {
        "type": "central", "Paco_kW": 3125, "Vdcmax": 1500, "Vdco": 1100,
        "Mppt_low": 880, "Mppt_high": 1380, "Idcmax": 3200, "n_mppt": 12, "strings_per_mppt": None,
    },
    "Sungrow SG350HX-20 (352 kW, 1500V)": {
        "type": "string", "Paco_kW": 352, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 500, "Mppt_high": 1500, "Idcmax": 40, "n_mppt": 12, "strings_per_mppt": 2,
    },
    "Sungrow SG250HX (250 kW, 1500V)": {
        "type": "string", "Paco_kW": 250, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 500, "Mppt_high": 1500, "Idcmax": 30, "n_mppt": 10, "strings_per_mppt": 2,
    },
    "Sungrow SG110CX (110 kW, 1500V)": {
        "type": "string", "Paco_kW": 110, "Vdcmax": 1500, "Vdco": 1000,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 18, "n_mppt": 9, "strings_per_mppt": 2,
    },
    "Huawei SUN2000-196KTL (196 kW, 1500V)": {
        "type": "string", "Paco_kW": 196, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 26, "n_mppt": 10, "strings_per_mppt": 2,
    },
    "Huawei SUN2000-215KTL-H3 (215 kW, 1500V)": {
        "type": "string", "Paco_kW": 215, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 28, "n_mppt": 10, "strings_per_mppt": 2,
    },
    "Huawei SUN5000-150K-MG0 (150 kW, 1500V)": {
        "type": "string", "Paco_kW": 150, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 22, "n_mppt": 8, "strings_per_mppt": 2,
    },
    "SMA STP 110-60 (110 kW, 1500V)": {
        "type": "string", "Paco_kW": 110, "Vdcmax": 1500, "Vdco": 1000,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 18, "n_mppt": 6, "strings_per_mppt": 2,
    },
    "SMA Sunny Highpower Peak3 150 (150 kW, 1500V)": {
        "type": "string", "Paco_kW": 150, "Vdcmax": 1500, "Vdco": 1000,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 24, "n_mppt": 6, "strings_per_mppt": 2,
    },
    "SMA Sunny Central 3600-UP (3.6 MW, 1500V)": {
        "type": "central", "Paco_kW": 3600, "Vdcmax": 1500, "Vdco": 1100,
        "Mppt_low": 880, "Mppt_high": 1380, "Idcmax": 3800, "n_mppt": 1, "strings_per_mppt": None,
    },
    "Fronius Tauro ECO 100 kW (1000V)": {
        "type": "string", "Paco_kW": 100, "Vdcmax": 1000, "Vdco": 800,
        "Mppt_low": 200, "Mppt_high": 800, "Idcmax": 22, "n_mppt": 4, "strings_per_mppt": 3,
    },
    "Fronius Tauro 50-60 (50 kW, 1000V)": {
        "type": "string", "Paco_kW": 50, "Vdcmax": 1000, "Vdco": 800,
        "Mppt_low": 200, "Mppt_high": 800, "Idcmax": 12, "n_mppt": 4, "strings_per_mppt": 2,
    },
    "Fimer PVS980-58 (5.8 MW, 1500V)": {
        "type": "central", "Paco_kW": 5800, "Vdcmax": 1500, "Vdco": 1100,
        "Mppt_low": 880, "Mppt_high": 1380, "Idcmax": 5500, "n_mppt": 1, "strings_per_mppt": None,
    },
    "Fimer PVS-100-TL (100 kW, 1100V)": {
        "type": "string", "Paco_kW": 100, "Vdcmax": 1100, "Vdco": 900,
        "Mppt_low": 200, "Mppt_high": 1100, "Idcmax": 20, "n_mppt": 6, "strings_per_mppt": 2,
    },
    "GoodWe GW3600D-NS (3.6 MW, 1500V)": {
        "type": "central", "Paco_kW": 3600, "Vdcmax": 1500, "Vdco": 1100,
        "Mppt_low": 500, "Mppt_high": 1380, "Idcmax": 3800, "n_mppt": 1, "strings_per_mppt": None,
    },
    "GoodWe HT 250kW (250 kW, 1500V)": {
        "type": "string", "Paco_kW": 250, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 500, "Mppt_high": 1500, "Idcmax": 32, "n_mppt": 10, "strings_per_mppt": 2,
    },
    "Growatt MAX 150KTL3 (150 kW, 1500V)": {
        "type": "string", "Paco_kW": 150, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 22, "n_mppt": 8, "strings_per_mppt": 2,
    },
    "Growatt MAX 100KTL3 (100 kW, 1000V)": {
        "type": "string", "Paco_kW": 100, "Vdcmax": 1000, "Vdco": 800,
        "Mppt_low": 200, "Mppt_high": 1000, "Idcmax": 18, "n_mppt": 6, "strings_per_mppt": 2,
    },
    "SolarEdge SE100K (100 kW, 1000V)": {
        "type": "string", "Paco_kW": 100, "Vdcmax": 1000, "Vdco": 850,
        "Mppt_low": 200, "Mppt_high": 1000, "Idcmax": 20, "n_mppt": 3, "strings_per_mppt": 2,
    },
    "Kaco blueplanet 175 TL3 (175 kW, 1500V)": {
        "type": "string", "Paco_kW": 175, "Vdcmax": 1500, "Vdco": 1080,
        "Mppt_low": 200, "Mppt_high": 1500, "Idcmax": 26, "n_mppt": 8, "strings_per_mppt": 2,
    },
}
