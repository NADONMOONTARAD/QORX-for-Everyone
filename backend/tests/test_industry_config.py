from backend.src.analysis_engine.valuation.industry_config import (
    DEFAULT_CONFIG,
    INDUSTRY_OVERRIDES,
    SECTOR_CONFIG,
    get_dcf_config,
)


def test_get_dcf_config_prefers_industry_override_case_insensitively():
    config = get_dcf_config("technology", "software - infrastructure")

    assert config["metric"] == "HYPERSCALER_FCF"
    assert config["base_mode"] == "LATEST"
    assert config["growth_mode"] == "MEDIAN_3Y"
    assert config["growth_cap"] == 0.25
    assert config["base_metric_label"] == "Free Cash Flow (Hyperscaler Mode)"


def test_get_dcf_config_falls_back_to_sector_defaults():
    config = get_dcf_config("Financial Services", "Unknown Industry")

    assert config["metric"] == "NET_INCOME"
    assert config["base_mode"] == "AVG_5Y"
    assert config["growth_mode"] == "MEDIAN_5Y"
    assert config["growth_cap"] == 0.12
    assert config["base_metric_label"] == "Net Income"


def test_get_dcf_config_uses_default_when_no_match_exists():
    config = get_dcf_config("", "")

    assert config["metric"] == DEFAULT_CONFIG["metric"]
    assert config["base_mode"] == DEFAULT_CONFIG["base_mode"]
    assert config["growth_mode"] == DEFAULT_CONFIG["growth_mode"]
    assert config["growth_cap"] == DEFAULT_CONFIG["growth_cap"]
    assert config["base_metric_label"] == "Free Cash Flow"


def test_all_industry_overrides_have_valid_supported_values():
    valid_metrics = {"FCF", "NET_INCOME", "HYPERSCALER_FCF"}
    valid_base_modes = {"LATEST", "AVG_3Y", "AVG_5Y"}
    valid_growth_modes = {"MEDIAN_3Y", "MEDIAN_5Y"}

    assert INDUSTRY_OVERRIDES, "INDUSTRY_OVERRIDES should not be empty"

    for industry, config in INDUSTRY_OVERRIDES.items():
        assert config["metric"] in valid_metrics, industry
        assert config["base_mode"] in valid_base_modes, industry
        assert config["growth_mode"] in valid_growth_modes, industry
        assert 0.0 <= float(config["growth_cap"]) <= 1.0, industry


def test_all_sector_configs_have_valid_supported_values():
    valid_metrics = {"FCF", "NET_INCOME", "HYPERSCALER_FCF"}
    valid_base_modes = {"LATEST", "AVG_3Y", "AVG_5Y"}
    valid_growth_modes = {"MEDIAN_3Y", "MEDIAN_5Y"}

    assert SECTOR_CONFIG, "SECTOR_CONFIG should not be empty"

    for sector, config in SECTOR_CONFIG.items():
        assert config["metric"] in valid_metrics, sector
        assert config["base_mode"] in valid_base_modes, sector
        assert config["growth_mode"] in valid_growth_modes, sector
        assert 0.0 <= float(config["growth_cap"]) <= 1.0, sector


def test_get_dcf_config_resolves_every_known_industry_override_exactly():
    for industry, expected in INDUSTRY_OVERRIDES.items():
        config = get_dcf_config("Unknown Sector", industry)

        assert config["metric"] == expected["metric"], industry
        assert config["base_mode"] == expected["base_mode"], industry
        assert config["growth_mode"] == expected["growth_mode"], industry
        assert config["growth_cap"] == expected["growth_cap"], industry


def test_representative_sector_strategies_cover_distinct_analysis_modes():
    hyperscaler = get_dcf_config("Technology", "Software - Infrastructure")
    bank = get_dcf_config("Financial Services", "Banks - Regional")
    insurance = get_dcf_config("Financial Services", "Insurance - Life")
    reit = get_dcf_config("Real Estate", "REIT - Industrial")
    shell_company = get_dcf_config("Financial Services", "Shell Companies")
    fund = get_dcf_config("Financial Services", "Exchange Traded Fund")

    assert hyperscaler["metric"] == "HYPERSCALER_FCF"
    assert bank["metric"] == "NET_INCOME"
    assert insurance["metric"] == "NET_INCOME"
    assert reit["metric"] == "FCF"
    assert shell_company["growth_cap"] == 0.0
    assert fund["metric"] == "NET_INCOME"
