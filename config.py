"""
Central configuration for the pipeline.

Everything that might change - countries, indicators, URLs, paths - lives here.
Nothing else in the project should hardcode these values. When you want to add a
country or an indicator, this is the only file you touch.
"""

from pathlib import Path

# --- Paths -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# --- Network -----------------------------------------------------------------

REQUEST_TIMEOUT = 60      # seconds before a single request gives up
RETRIES = 3               # attempts per request before failing the run
BACKOFF_SECONDS = 5       # wait between retries

# --- Countries ---------------------------------------------------------------
# WHO uses ISO3 codes, DHS uses its own 2-letter codes. Keep both together so
# they can never drift apart.

COUNTRIES = {
    "Nigeria":      {"iso3": "NGA", "dhs": "NG"},
    "Ghana":        {"iso3": "GHA", "dhs": "GH"},
    "Kenya":        {"iso3": "KEN", "dhs": "KE"},
    "Senegal":      {"iso3": "SEN", "dhs": "SN"},
    "Egypt":        {"iso3": "EGY", "dhs": "EG"},
    "South Africa": {"iso3": "ZAF", "dhs": "ZA"},
}

ISO3_CODES = [c["iso3"] for c in COUNTRIES.values()]
DHS_CODES = [c["dhs"] for c in COUNTRIES.values()]

# --- Source 1: WHO Global Health Observatory ---------------------------------
# Open OData API, no authentication.
# Browse the full catalogue at https://ghoapi.azureedge.net/api/Indicator

WHO_BASE_URL = "https://ghoapi.azureedge.net/api"

WHO_INDICATORS = {
    "WHOSIS_000001":          "life_expectancy_at_birth",
    "MDG_0000000026":         "maternal_mortality_ratio",
    "MDG_0000000007":         "under_five_mortality_rate",
    "WHS4_100":               "dtp3_immunization_coverage",
    "GHED_CHE_pc_US_SHA2011": "health_expenditure_per_capita_usd",
}

# --- Source 2: DHS Program ---------------------------------------------------
# Open REST API for aggregated indicators, no authentication.
# NOTE: this is NOT the microdata. Individual survey records require separate
# registration at dhsprogram.com. This API serves pre-calculated indicators.
# Browse the catalogue at https://api.dhsprogram.com/rest/dhs/indicators?f=json

DHS_BASE_URL = "https://api.dhsprogram.com/rest/dhs"

DHS_INDICATORS = {
    "RH_ANCN_W_N4P": "antenatal_care_4plus_visits",
    "RH_DELP_C_DHF": "delivery_in_health_facility",
    "RH_DELA_C_SKP": "skilled_birth_attendance",
    "CH_VACC_C_BAS": "basic_vaccination_coverage",
    "CN_NUTS_C_HA2": "child_stunting_rate",
    "CM_ECMR_C_U5M": "under_five_mortality_rate_dhs",
    "FP_CUSA_W_MOD": "modern_contraceptive_use",
}
