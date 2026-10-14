"""FILE: tests/features/prebuilt_tools/prebuilt_catalogue_data.py

PURPOSE: Hand-copied expected tables from spec Appendix A, §8.5, and §9.2: category order, tool names, category class names, enum vocabularies, and the top-level output keys of every prebuilt tool.
ROLE IN CODEBASE: Expected values for the contract tests in tests/features/prebuilt_tools/; it imports nothing from vidbyte, so every table stays independent of the implementation it checks.
ARCHITECTURE NOTE: Pure data with no logic. The order of CATEGORY_TABLE is the PrebuiltToolCategory declaration order and the order of each name tuple is the Appendix A row order (INV-2).
FUNCTION INVENTORY: Data only: CATEGORY_TABLE, CATEGORY_TOOL_NAMES, ALL_TOOL_NAMES, ENUM_TABLE, RETURN_KEYS.
COMMON MODIFICATION PATTERNS: When a spec revision changes Appendix A or the §9.2 enum table, edit the matching row here in the same commit as the spec.
WHAT NOT TO DO IN THIS FILE: 1. Do not derive these tables from vidbyte code; a copy of the implementation cannot catch its mistakes. 2. Do not add helpers; the harness module owns behavior.
KNOWN EDGE CASES: CompassPoint member names equal their uppercase values; every other enum member name is its value in upper case. The floor of 250 tools (AC-12) is checked against the live catalogue, not against these tables.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A, §8.5, §9.2); tests/features/prebuilt_tools/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools
"""

from __future__ import annotations

from types import MappingProxyType

# One row per PrebuiltToolCategory member, in declaration order: (value, category class name, tool names in row order).
CATEGORY_TABLE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "exact_arithmetic",
        "ExactArithmeticToolFunctions",
        (
            "decimal_arithmetic", "round_decimal", "round_significant_figures", "sum_decimal_list", "fraction_arithmetic",
            "decimal_to_fraction", "repeating_decimal_to_fraction", "fraction_to_decimal", "integer_square_root", "solve_quadratic_equation"
        ),
    ),
    (
        "number_theory",
        "NumberTheoryToolFunctions",
        (
            "is_prime", "prime_factorize", "list_primes_in_range", "nth_prime", "next_prime", "greatest_common_divisor",
            "least_common_multiple", "list_divisors", "modular_exponentiation", "modular_inverse"
        ),
    ),
    (
        "number_formatting",
        "NumberFormattingToolFunctions",
        (
            "convert_number_base", "number_to_english_words", "english_words_to_number", "parse_abbreviated_number",
            "format_number_with_separators", "parse_formatted_number", "to_scientific_notation"
        ),
    ),
    (
        "descriptive_statistics",
        "DescriptiveStatisticsToolFunctions",
        (
            "summarize_numbers", "compute_mode", "compute_percentile", "compute_quartiles", "weighted_mean", "pearson_correlation",
            "spearman_rank_correlation", "linear_regression_fit", "moving_average", "detect_outliers_iqr", "rank_values"
        ),
    ),
    (
        "probability",
        "ProbabilityToolFunctions",
        (
            "count_combinations", "count_permutations", "exact_factorial", "binomial_probability", "poisson_probability",
            "normal_distribution_probability", "normal_quantile", "birthday_collision_probability", "list_combinations"
        ),
    ),
    (
        "seeded_random",
        "SeededRandomToolFunctions",
        (
            "seeded_random_integers", "seeded_shuffle_list", "seeded_sample_list", "seeded_weighted_choice", "roll_dice_notation",
            "generate_seeded_uuid4"
        ),
    ),
    (
        "finance",
        "FinanceToolFunctions",
        (
            "compound_interest_future_value", "loan_payment_amount", "amortization_schedule", "net_present_value",
            "internal_rate_of_return", "compound_annual_growth_rate", "percentage_change", "percentage_breakdown", "allocate_amount",
            "split_tax_inclusive_amount"
        ),
    ),
    (
        "unit_conversion",
        "UnitConversionToolFunctions",
        (
            "convert_length", "convert_mass", "convert_temperature", "convert_volume", "convert_area", "convert_speed", "convert_duration",
            "convert_energy", "convert_fuel_economy", "convert_data_size"
        ),
    ),
    (
        "dates",
        "DatesToolFunctions",
        (
            "days_between_dates", "add_to_date", "years_months_days_between", "day_of_week", "iso_week_number", "nth_weekday_of_month",
            "next_weekday", "resolve_relative_date_phrase", "parse_date_to_iso", "fiscal_quarter"
        ),
    ),
    (
        "scheduling",
        "SchedulingToolFunctions",
        (
            "business_days_between", "add_business_days", "list_dates_in_range", "count_weekday_occurrences", "generate_recurring_dates",
            "merge_time_intervals", "find_common_free_slots", "sort_date_strings"
        ),
    ),
    (
        "timestamps_durations",
        "TimestampsDurationsToolFunctions",
        (
            "unix_timestamp_to_datetime", "datetime_to_unix_timestamp", "convert_utc_offset", "duration_between_datetimes",
            "add_duration_to_datetime", "format_duration", "parse_duration_text", "minutes_between_times"
        ),
    ),
    (
        "text_counting",
        "TextCountingToolFunctions",
        (
            "count_characters", "count_character_occurrences", "find_substring_positions", "count_words", "count_sentences", "count_lines",
            "word_frequencies", "character_frequencies", "ngram_frequencies", "character_at_position", "readability_scores",
            "count_syllables"
        ),
    ),
    (
        "text_transform",
        "TextTransformToolFunctions",
        (
            "reverse_text", "convert_identifier_case", "shorten_text", "replace_all_occurrences", "deduplicate_lines", "sort_text_lines",
            "strip_html_tags", "split_text_into_chunks", "extract_line_range", "fill_text_template"
        ),
    ),
    (
        "unicode",
        "UnicodeToolFunctions",
        (
            "unicode_character_info", "find_unicode_character", "apply_unicode_normalization", "remove_diacritics",
            "find_invisible_characters", "find_non_ascii_characters", "detect_scripts_in_text", "count_bytes_in_encoding",
            "sms_segment_count", "repair_mojibake_text"
        ),
    ),
    (
        "regex",
        "RegexToolFunctions",
        (
            "regex_find_all", "regex_match", "regex_replace", "regex_split", "verify_regex_pattern", "regex_test_samples",
            "wildcard_match_names"
        ),
    ),
    (
        "text_comparison",
        "TextComparisonToolFunctions",
        (
            "unified_diff_text", "diff_words", "levenshtein_distance", "closest_string_matches", "longest_common_substring",
            "jaccard_similarity"
        ),
    ),
    (
        "json_data",
        "JsonDataToolFunctions",
        (
            "verify_json_syntax", "format_json", "json_get_value", "json_set_value", "list_json_paths", "diff_json_documents",
            "apply_json_patch", "summarize_json_structure", "extract_json_from_text"
        ),
    ),
    (
        "json_records",
        "JsonRecordsToolFunctions",
        (
            "filter_records", "pluck_field", "group_records_by_field", "aggregate_field", "group_and_aggregate_records", "sort_records",
            "count_field_values", "join_records", "records_to_csv"
        ),
    ),
    (
        "csv_tables",
        "CsvTablesToolFunctions",
        (
            "csv_to_records", "detect_csv_dialect", "profile_csv_columns", "csv_filter_rows", "csv_sort_rows", "csv_aggregate_column",
            "csv_group_by", "csv_join_tables", "csv_to_markdown_table"
        ),
    ),
    (
        "structured_formats",
        "StructuredFormatsToolFunctions",
        (
            "xml_to_json", "verify_xml_wellformed", "xml_find_elements", "ini_to_json", "toml_to_json", "parse_url", "resolve_relative_url",
            "parse_query_string", "parse_dotenv_text"
        ),
    ),
    (
        "encoding",
        "EncodingToolFunctions",
        (
            "base64_encode", "base64_decode", "hex_encode", "hex_decode", "url_encode", "url_decode", "html_unescape", "decode_jwt_payload",
            "escape_json_string", "unescape_json_string"
        ),
    ),
    (
        "hashing",
        "HashingToolFunctions",
        (
            "hash_text", "hash_base64_content", "compute_hmac", "verify_hash", "crc32_checksum", "git_blob_hash", "assign_stable_bucket"
        ),
    ),
    (
        "identifiers",
        "IdentifiersToolFunctions",
        (
            "verify_luhn_checksum", "verify_isbn", "verify_iban", "verify_gtin_barcode", "verify_email_syntax", "verify_url_syntax",
            "verify_uuid", "generate_name_based_uuid", "compare_semantic_versions"
        ),
    ),
    (
        "lists",
        "ListsToolFunctions",
        (
            "count_item_frequencies", "find_duplicate_items", "compare_two_lists", "intersect_lists", "find_missing_integers",
            "compress_integer_ranges", "expand_integer_ranges"
        ),
    ),
    (
        "graphs",
        "GraphsToolFunctions",
        (
            "topological_sort", "find_graph_cycle", "shortest_path", "shortest_weighted_path", "connected_components",
            "critical_path_schedule"
        ),
    ),
    (
        "geometry",
        "GeometryToolFunctions",
        (
            "haversine_distance", "initial_bearing", "destination_point", "dms_to_decimal_degrees", "decimal_degrees_to_dms",
            "polygon_area", "point_in_polygon"
        ),
    ),
    (
        "bits_bytes",
        "BitsBytesToolFunctions",
        (
            "parse_data_size", "format_bytes_human", "bitwise_operation", "integer_to_twos_complement", "twos_complement_to_integer",
            "convert_unix_permissions"
        ),
    ),
    (
        "markdown_html",
        "MarkdownHtmlToolFunctions",
        (
            "extract_markdown_headings", "extract_markdown_tasks", "parse_markdown_table", "extract_markdown_links",
            "extract_fenced_code_blocks", "html_table_to_records", "extract_html_links"
        ),
    ),
    (
        "text_extraction",
        "TextExtractionToolFunctions",
        (
            "extract_urls", "extract_email_addresses", "extract_numbers", "extract_dates", "extract_ip_addresses", "extract_money_amounts",
            "extract_key_value_pairs", "extract_sentences"
        ),
    ),
    (
        "code_analysis",
        "CodeAnalysisToolFunctions",
        (
            "verify_python_syntax", "list_python_functions", "list_python_classes", "list_python_imports", "count_lines_of_code",
            "get_python_function_signature", "find_python_name_usages", "python_literal_to_json", "shell_split_command",
            "shell_quote_arguments"
        ),
    ),
    (
        "network_addresses",
        "NetworkAddressesToolFunctions",
        (
            "verify_ip_address", "cidr_network_details", "ip_in_networks", "split_cidr_into_subnets", "ip_range_to_cidrs",
            "classify_ip_address", "convert_ip_address_integer", "convert_ipv4_netmask"
        ),
    ),
)

CATEGORY_TOOL_NAMES: MappingProxyType[str, tuple[str, ...]] = MappingProxyType({value: names for value, _, names in CATEGORY_TABLE})

ALL_TOOL_NAMES: tuple[str, ...] = tuple(name for _, _, names in CATEGORY_TABLE for name in names)

# One row per enum in the §9.2 vocabulary table: (class name, module under vidbyte/lib/enums/, values in declaration order).
ENUM_TABLE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "PrebuiltToolCategory",
        "prebuilt_tools",
        (
            "exact_arithmetic", "number_theory", "number_formatting", "descriptive_statistics", "probability", "seeded_random", "finance",
            "unit_conversion", "dates", "scheduling", "timestamps_durations", "text_counting", "text_transform", "unicode", "regex",
            "text_comparison", "json_data", "json_records", "csv_tables", "structured_formats", "encoding", "hashing", "identifiers",
            "lists", "graphs", "geometry", "bits_bytes", "markdown_html", "text_extraction", "code_analysis", "network_addresses"
        ),
    ),
    ("ArithmeticOperation", "prebuilt_tools", ("add", "subtract", "multiply", "divide")),
    ("RoundingMode", "prebuilt_tools", ("half_even", "half_up", "half_down", "up", "down", "ceiling", "floor")),
    ("SeparatorStyle", "prebuilt_tools", ("comma_period", "period_comma", "space_period", "space_comma", "apostrophe_period", "underscore_period")),
    ("NotationStyle", "prebuilt_tools", ("scientific", "engineering")),
    ("PercentileMethod", "prebuilt_tools", ("linear", "lower", "higher", "nearest_rank")),
    ("QuartileMethod", "prebuilt_tools", ("exclusive", "inclusive")),
    ("RankMethod", "prebuilt_tools", ("average", "min", "max", "dense", "ordinal")),
    ("ProbabilityTail", "prebuilt_tools", ("exactly", "at_most", "at_least", "less_than", "greater_than")),
    ("CompoundingFrequency", "prebuilt_tools", ("annually", "semiannually", "quarterly", "monthly", "weekly", "daily", "continuously")),
    ("DateUnit", "prebuilt_tools", ("days", "weeks", "months", "years")),
    ("Weekday", "prebuilt_tools", ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")),
    ("WeekdayOccurrence", "prebuilt_tools", ("first", "second", "third", "fourth", "fifth", "last")),
    ("SearchDirection", "prebuilt_tools", ("next", "previous")),
    ("RecurrenceFrequency", "prebuilt_tools", ("daily", "weekly", "monthly", "yearly")),
    ("TimestampUnit", "prebuilt_tools", ("seconds", "milliseconds", "microseconds", "nanoseconds")),
    ("DurationStyle", "prebuilt_tools", ("compact", "long", "clock", "iso8601")),
    ("TextUnit", "prebuilt_tools", ("characters", "words", "lines")),
    ("NgramUnit", "prebuilt_tools", ("words", "characters")),
    ("IdentifierCase", "prebuilt_tools", ("snake", "screaming_snake", "kebab", "camel", "pascal", "dot", "title")),
    ("SortMode", "prebuilt_tools", ("text", "case_insensitive", "natural", "numeric", "length")),
    ("MissingPlaceholderPolicy", "prebuilt_tools", ("error", "keep", "empty")),
    ("UnicodeForm", "prebuilt_tools", ("nfc", "nfd", "nfkc", "nfkd")),
    ("InvisibleCharacterKind", "prebuilt_tools", ("zero_width", "bidi_control", "format", "unusual_space", "control")),
    ("TextEncoding", "prebuilt_tools", ("utf_8", "utf_16", "utf_16_le", "utf_16_be", "utf_32", "latin_1", "ascii", "cp1252")),
    ("SmsEncoding", "prebuilt_tools", ("gsm_7", "ucs_2")),
    ("RegexFlag", "prebuilt_tools", ("ignore_case", "multiline", "dot_all", "verbose", "ascii")),
    ("RegexMatchMode", "prebuilt_tools", ("full", "prefix", "search")),
    ("DiffOperation", "prebuilt_tools", ("equal", "insert", "delete", "replace")),
    ("JsonType", "prebuilt_tools", ("object", "array", "string", "number", "boolean", "null")),
    ("JsonChangeKind", "prebuilt_tools", ("add", "remove", "replace")),
    (
        "FilterOperator",
        "prebuilt_tools",
        (
            "equals", "not_equals", "greater_than", "greater_or_equal", "less_than", "less_or_equal", "contains", "starts_with",
            "ends_with", "is_empty", "is_not_empty"
        ),
    ),
    ("AggregateFunction", "prebuilt_tools", ("count", "sum", "mean", "min", "max", "median", "distinct_count")),
    ("JoinKind", "prebuilt_tools", ("inner", "left")),
    ("CsvDelimiter", "prebuilt_tools", ("comma", "semicolon", "tab", "pipe")),
    ("ColumnType", "prebuilt_tools", ("integer", "number", "boolean", "date", "text", "empty")),
    ("HexSeparator", "prebuilt_tools", ("none", "space", "colon")),
    ("UrlEncodingMode", "prebuilt_tools", ("component", "path", "form")),
    ("HashAlgorithm", "prebuilt_tools", ("md5", "sha1", "sha224", "sha256", "sha384", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s")),
    ("DigestFormat", "prebuilt_tools", ("hex", "base64", "base64url")),
    ("KeyFormat", "prebuilt_tools", ("text", "hex", "base64")),
    ("UuidNameVersion", "prebuilt_tools", ("v3", "v5")),
    (
        "EmailSyntaxProblem",
        "prebuilt_tools",
        (
            "not_ascii", "missing_at_sign", "multiple_at_signs", "address_too_long", "local_part_empty", "local_part_too_long",
            "local_part_invalid", "domain_too_long", "domain_label_invalid", "domain_needs_two_labels", "top_level_domain_invalid"
        ),
    ),
    (
        "UrlSyntaxProblem",
        "prebuilt_tools",
        (
            "whitespace_or_control", "missing_scheme", "scheme_not_allowed", "missing_host", "invalid_port", "invalid_host"
        ),
    ),
    ("TableAlignment", "prebuilt_tools", ("left", "center", "right", "auto")),
    ("MarkdownLinkKind", "prebuilt_tools", ("inline", "image", "autolink", "reference")),
    (
        "CodeLanguage",
        "prebuilt_tools",
        (
            "python", "javascript", "typescript", "java", "c", "cpp", "csharp", "go", "rust", "kotlin", "swift", "php", "ruby", "shell",
            "sql", "html", "css"
        ),
    ),
    ("PythonParameterKind", "prebuilt_tools", ("positional_only", "positional_or_keyword", "var_positional", "keyword_only", "var_keyword")),
    ("PythonNameUsageKind", "prebuilt_tools", ("definition", "parameter", "import", "load", "store", "delete", "attribute", "keyword")),
    ("CompassPoint", "prebuilt_tools", ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")),
    ("CoordinateAxis", "prebuilt_tools", ("latitude", "longitude")),
    ("PolygonOrientation", "prebuilt_tools", ("counterclockwise", "clockwise", "degenerate")),
    ("SizeStandard", "prebuilt_tools", ("si", "iec")),
    ("BitwiseOperation", "prebuilt_tools", ("and", "or", "xor", "not", "shift_left", "shift_right")),
    ("BitStringFormat", "prebuilt_tools", ("binary", "hex")),
    ("KeyValueSeparator", "prebuilt_tools", ("auto", "colon", "equals")),
    ("IpVersion", "prebuilt_tools", ("ipv4", "ipv6")),
    (
        "IpAddressProblem",
        "prebuilt_tools",
        (
            "invalid_ipv6", "invalid_characters", "ipv4_wrong_part_count", "ipv4_empty_part", "ipv4_leading_zero", "ipv4_octet_out_of_range"
        ),
    ),
    (
        "LengthUnit",
        "units",
        (
            "nanometer", "micrometer", "millimeter", "centimeter", "meter", "kilometer", "inch", "foot", "yard", "mile", "nautical_mile"
        ),
    ),
    ("MassUnit", "units", ("milligram", "gram", "kilogram", "metric_ton", "ounce", "pound", "stone", "short_ton", "long_ton")),
    ("TemperatureUnit", "units", ("celsius", "fahrenheit", "kelvin", "rankine")),
    (
        "VolumeUnit",
        "units",
        (
            "milliliter", "liter", "cubic_centimeter", "cubic_meter", "cubic_inch", "cubic_foot", "us_teaspoon", "us_tablespoon",
            "us_fluid_ounce", "us_cup", "us_pint", "us_quart", "us_gallon", "imperial_fluid_ounce", "imperial_pint", "imperial_quart",
            "imperial_gallon"
        ),
    ),
    (
        "AreaUnit",
        "units",
        (
            "square_millimeter", "square_centimeter", "square_meter", "square_kilometer", "hectare", "square_inch", "square_foot",
            "square_yard", "acre", "square_mile"
        ),
    ),
    ("SpeedUnit", "units", ("meters_per_second", "kilometers_per_hour", "miles_per_hour", "knots", "feet_per_second")),
    ("DurationUnit", "units", ("nanosecond", "microsecond", "millisecond", "second", "minute", "hour", "day", "week")),
    (
        "EnergyUnit",
        "units",
        (
            "joule", "kilojoule", "megajoule", "calorie", "kilocalorie", "watt_hour", "kilowatt_hour", "british_thermal_unit",
            "electronvolt"
        ),
    ),
    ("FuelEconomyUnit", "units", ("miles_per_us_gallon", "miles_per_imperial_gallon", "kilometers_per_liter", "liters_per_100_kilometers")),
    (
        "DataSizeUnit",
        "units",
        (
            "bit", "byte", "kilobyte", "megabyte", "gigabyte", "terabyte", "petabyte", "kibibyte", "mebibyte", "gibibyte", "tebibyte",
            "pebibyte", "kilobit", "megabit", "gigabit"
        ),
    ),
)

# Top-level output keys of every tool, copied from the Appendix A returns column (INV-10).
RETURN_KEYS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        # exact_arithmetic
        "decimal_arithmetic": ("result", "exact"),
        "round_decimal": ("result",),
        "round_significant_figures": ("result",),
        "sum_decimal_list": ("sum", "count"),
        "fraction_arithmetic": ("result", "decimal_approximation"),
        "decimal_to_fraction": ("fraction", "exact"),
        "repeating_decimal_to_fraction": ("fraction",),
        "fraction_to_decimal": ("decimal", "terminates", "repeating_digits", "truncated"),
        "integer_square_root": ("root", "is_perfect_square", "remainder"),
        "solve_quadratic_equation": ("discriminant", "root_count", "roots"),
        # number_theory
        "is_prime": ("is_prime",),
        "prime_factorize": ("factors", "expression"),
        "list_primes_in_range": ("primes", "count", "truncated"),
        "nth_prime": ("prime",),
        "next_prime": ("prime",),
        "greatest_common_divisor": ("gcd",),
        "least_common_multiple": ("lcm",),
        "list_divisors": ("divisors", "count", "sum", "truncated"),
        "modular_exponentiation": ("result",),
        "modular_inverse": ("inverse", "exists"),
        # number_formatting
        "convert_number_base": ("result",),
        "number_to_english_words": ("words",),
        "english_words_to_number": ("value",),
        "parse_abbreviated_number": ("value",),
        "format_number_with_separators": ("formatted",),
        "parse_formatted_number": ("value", "is_percent"),
        "to_scientific_notation": ("mantissa", "exponent", "text"),
        # descriptive_statistics
        "summarize_numbers": ("count", "sum", "mean", "median", "min", "max", "range", "sample_stdev", "population_stdev", "sample_variance", "population_variance"),
        "compute_mode": ("modes", "frequency", "truncated"),
        "compute_percentile": ("percentile", "value"),
        "compute_quartiles": ("q1", "q2", "q3", "iqr"),
        "weighted_mean": ("weighted_mean", "total_weight"),
        "pearson_correlation": ("r", "r_squared", "count"),
        "spearman_rank_correlation": ("rho", "count"),
        "linear_regression_fit": ("slope", "intercept", "r_squared", "count"),
        "moving_average": ("averages",),
        "detect_outliers_iqr": ("q1", "q3", "iqr", "lower_fence", "upper_fence", "outliers", "truncated"),
        "rank_values": ("ranks",),
        # probability
        "count_combinations": ("count",),
        "count_permutations": ("count",),
        "exact_factorial": ("factorial", "digit_count"),
        "binomial_probability": ("probability",),
        "poisson_probability": ("probability",),
        "normal_distribution_probability": ("probability",),
        "normal_quantile": ("x",),
        "birthday_collision_probability": ("probability",),
        "list_combinations": ("combinations", "count", "truncated"),
        # seeded_random
        "seeded_random_integers": ("values",),
        "seeded_shuffle_list": ("items",),
        "seeded_sample_list": ("items", "indices"),
        "seeded_weighted_choice": ("picks",),
        "roll_dice_notation": ("rolls", "modifier", "total"),
        "generate_seeded_uuid4": ("uuids",),
        # finance
        "compound_interest_future_value": ("future_value", "interest_earned"),
        "loan_payment_amount": ("monthly_payment", "final_payment", "total_paid", "total_interest"),
        "amortization_schedule": ("monthly_payment", "schedule"),
        "net_present_value": ("npv",),
        "internal_rate_of_return": ("irr_percent",),
        "compound_annual_growth_rate": ("cagr_percent",),
        "percentage_change": ("change_percent", "difference"),
        "percentage_breakdown": ("total", "shares"),
        "allocate_amount": ("allocations",),
        "split_tax_inclusive_amount": ("net_amount", "tax_amount"),
        # unit_conversion
        "convert_length": ("value", "unit"),
        "convert_mass": ("value", "unit"),
        "convert_temperature": ("value", "unit"),
        "convert_volume": ("value", "unit"),
        "convert_area": ("value", "unit"),
        "convert_speed": ("value", "unit"),
        "convert_duration": ("value", "unit"),
        "convert_energy": ("value", "unit"),
        "convert_fuel_economy": ("value", "unit"),
        "convert_data_size": ("value", "unit"),
        # dates
        "days_between_dates": ("days", "weeks", "remaining_days"),
        "add_to_date": ("date", "clamped"),
        "years_months_days_between": ("years", "months", "days", "negative"),
        "day_of_week": ("weekday", "iso_weekday", "day_of_year"),
        "iso_week_number": ("iso_year", "iso_week", "iso_weekday", "week_label"),
        "nth_weekday_of_month": ("date",),
        "next_weekday": ("date", "days_away"),
        "resolve_relative_date_phrase": ("date", "end_date", "weekday"),
        "parse_date_to_iso": ("date", "ambiguous"),
        "fiscal_quarter": ("fiscal_year", "fiscal_quarter", "quarter_start", "quarter_end"),
        # scheduling
        "business_days_between": ("business_days",),
        "add_business_days": ("date",),
        "list_dates_in_range": ("dates", "count", "truncated"),
        "count_weekday_occurrences": ("count",),
        "generate_recurring_dates": ("dates", "count", "truncated"),
        "merge_time_intervals": ("intervals", "total_minutes"),
        "find_common_free_slots": ("slots", "count", "truncated"),
        "sort_date_strings": ("sorted",),
        # timestamps_durations
        "unix_timestamp_to_datetime": ("datetime", "date", "time", "weekday"),
        "datetime_to_unix_timestamp": ("timestamp",),
        "convert_utc_offset": ("datetime", "date", "time", "day_shift"),
        "duration_between_datetimes": ("total_seconds", "days", "hours", "minutes", "seconds", "negative"),
        "add_duration_to_datetime": ("datetime", "date", "time"),
        "format_duration": ("text",),
        "parse_duration_text": ("total_seconds", "iso8601"),
        "minutes_between_times": ("minutes", "wrapped"),
        # text_counting
        "count_characters": ("characters", "non_whitespace", "letters", "digits", "whitespace", "punctuation", "uppercase", "lowercase"),
        "count_character_occurrences": ("count", "positions", "truncated"),
        "find_substring_positions": ("count", "positions", "truncated"),
        "count_words": ("words", "unique_words", "average_word_length"),
        "count_sentences": ("sentences", "average_words_per_sentence"),
        "count_lines": ("lines", "blank_lines", "non_blank_lines", "longest_line_number", "longest_line_length", "ends_with_newline"),
        "word_frequencies": ("total_words", "unique_words", "frequencies"),
        "character_frequencies": ("total", "frequencies"),
        "ngram_frequencies": ("total_ngrams", "frequencies"),
        "character_at_position": ("character", "code_point", "name", "position", "line", "column"),
        "readability_scores": ("words", "sentences", "syllables", "flesch_reading_ease", "flesch_kincaid_grade"),
        "count_syllables": ("syllables", "words", "per_word", "truncated"),
        # text_transform
        "reverse_text": ("text",),
        "convert_identifier_case": ("text", "words"),
        "shorten_text": ("text", "shortened", "original_length"),
        "replace_all_occurrences": ("text", "replacements"),
        "deduplicate_lines": ("text", "kept", "removed"),
        "sort_text_lines": ("text", "lines"),
        "strip_html_tags": ("text",),
        "split_text_into_chunks": ("chunks", "count", "truncated"),
        "extract_line_range": ("text", "start_line", "end_line", "total_lines"),
        "fill_text_template": ("text", "filled", "missing"),
        # unicode
        "unicode_character_info": ("characters",),
        "find_unicode_character": ("exact", "matches", "truncated"),
        "apply_unicode_normalization": ("text", "changed", "length_before", "length_after"),
        "remove_diacritics": ("text", "changed_characters"),
        "find_invisible_characters": ("count", "findings", "truncated", "cleaned_text"),
        "find_non_ascii_characters": ("count", "characters", "truncated"),
        "detect_scripts_in_text": ("scripts", "mixed_script_words", "truncated"),
        "count_bytes_in_encoding": ("size_bytes", "characters", "encodable", "first_unencodable_position"),
        "sms_segment_count": ("encoding", "segments", "units_used", "units_per_segment", "non_gsm_characters"),
        "repair_mojibake_text": ("text", "repaired", "rounds"),
        # regex
        "regex_find_all": ("count", "matches", "truncated"),
        "regex_match": ("matched", "match", "start", "end", "groups", "named_groups"),
        "regex_replace": ("text", "replacements"),
        "regex_split": ("parts", "count", "truncated"),
        "verify_regex_pattern": ("valid", "error", "error_position", "group_count", "group_names"),
        "regex_test_samples": ("all_passed", "passed", "failed", "failures"),
        "wildcard_match_names": ("matches", "count", "truncated"),
        # text_comparison
        "unified_diff_text": ("diff", "added_lines", "removed_lines", "identical"),
        "diff_words": ("operations", "similarity"),
        "levenshtein_distance": ("distance", "similarity"),
        "closest_string_matches": ("matches",),
        "longest_common_substring": ("substring", "length", "first_position", "second_position"),
        "jaccard_similarity": ("jaccard", "intersection", "union"),
        # json_data
        "verify_json_syntax": ("valid", "error", "line", "column", "position", "top_level_type"),
        "format_json": ("json",),
        "json_get_value": ("found", "value", "type"),
        "json_set_value": ("json", "replaced"),
        "list_json_paths": ("paths", "count", "truncated"),
        "diff_json_documents": ("identical", "changes", "count", "truncated"),
        "apply_json_patch": ("json", "applied_operations"),
        "summarize_json_structure": ("top_level_type", "max_nesting", "value_count", "shape"),
        "extract_json_from_text": ("documents", "count", "truncated"),
        # json_records
        "filter_records": ("records", "matched"),
        "pluck_field": ("values", "missing"),
        "group_records_by_field": ("groups",),
        "aggregate_field": ("result", "values_used", "values_skipped"),
        "group_and_aggregate_records": ("groups",),
        "sort_records": ("records",),
        "count_field_values": ("total", "distinct", "counts"),
        "join_records": ("records", "count", "truncated"),
        "records_to_csv": ("csv", "rows", "columns"),
        # csv_tables
        "csv_to_records": ("records", "columns", "rows"),
        "detect_csv_dialect": ("delimiter", "has_header", "quote_character", "columns", "rows"),
        "profile_csv_columns": ("rows", "columns"),
        "csv_filter_rows": ("csv", "matched"),
        "csv_sort_rows": ("csv", "rows"),
        "csv_aggregate_column": ("result", "values_used", "values_skipped"),
        "csv_group_by": ("groups",),
        "csv_join_tables": ("csv", "rows", "truncated"),
        "csv_to_markdown_table": ("markdown", "rows", "columns"),
        # structured_formats
        "xml_to_json": ("root_tag", "value"),
        "verify_xml_wellformed": ("wellformed", "error", "line", "column", "root_tag"),
        "xml_find_elements": ("elements", "count", "truncated"),
        "ini_to_json": ("sections", "defaults"),
        "toml_to_json": ("value",),
        "parse_url": ("scheme", "username", "has_password", "host", "port", "path", "query", "fragment", "query_parameters", "is_absolute"),
        "resolve_relative_url": ("url",),
        "parse_query_string": ("parameters", "by_name"),
        "parse_dotenv_text": ("variables", "count", "duplicate_keys"),
        # encoding
        "base64_encode": ("base64",),
        "base64_decode": ("text", "is_text", "size_bytes", "hex_preview"),
        "hex_encode": ("hex",),
        "hex_decode": ("text", "is_text", "size_bytes"),
        "url_encode": ("encoded",),
        "url_decode": ("decoded", "had_invalid_sequences"),
        "html_unescape": ("unescaped",),
        "decode_jwt_payload": ("header", "payload", "signature_verified", "has_signature", "claims"),
        "escape_json_string": ("escaped",),
        "unescape_json_string": ("text",),
        # hashing
        "hash_text": ("digest", "algorithm"),
        "hash_base64_content": ("digest", "algorithm", "size_bytes"),
        "compute_hmac": ("digest", "algorithm"),
        "verify_hash": ("matches", "computed_hex"),
        "crc32_checksum": ("crc32_hex", "crc32_decimal", "adler32_hex"),
        "git_blob_hash": ("object_id", "size_bytes"),
        "assign_stable_bucket": ("bucket", "hash_prefix"),
        # identifiers
        "verify_luhn_checksum": ("valid", "digit_count", "expected_check_digit"),
        "verify_isbn": ("valid", "isbn10", "isbn13", "input_length"),
        "verify_iban": ("valid", "country_code", "check_digits", "formatted"),
        "verify_gtin_barcode": ("valid", "digit_count", "expected_check_digit"),
        "verify_email_syntax": ("valid", "reason", "local_part", "domain"),
        "verify_url_syntax": ("valid", "reason", "scheme", "host"),
        "verify_uuid": ("valid", "canonical", "version", "is_rfc_4122"),
        "generate_name_based_uuid": ("uuid",),
        "compare_semantic_versions": ("comparison", "first_is_prerelease", "second_is_prerelease"),
        # lists
        "count_item_frequencies": ("total", "distinct", "frequencies"),
        "find_duplicate_items": ("duplicates", "duplicate_count"),
        "compare_two_lists": ("only_in_first", "only_in_second", "in_both", "only_in_first_count", "only_in_second_count", "in_both_count"),
        "intersect_lists": ("common", "count"),
        "find_missing_integers": ("missing", "count", "truncated"),
        "compress_integer_ranges": ("ranges", "text", "count"),
        "expand_integer_ranges": ("values", "count", "truncated"),
        # graphs
        "topological_sort": ("order", "levels"),
        "find_graph_cycle": ("has_cycle", "cycle"),
        "shortest_path": ("found", "path", "hops"),
        "shortest_weighted_path": ("found", "path", "total_weight"),
        "connected_components": ("components", "count"),
        "critical_path_schedule": ("project_duration", "critical_path", "schedule"),
        # geometry
        "haversine_distance": ("distance", "unit"),
        "initial_bearing": ("bearing_degrees", "compass_point"),
        "destination_point": ("latitude", "longitude"),
        "dms_to_decimal_degrees": ("decimal_degrees", "axis"),
        "decimal_degrees_to_dms": ("dms", "degrees", "minutes", "seconds", "hemisphere"),
        "polygon_area": ("area", "signed_area", "orientation", "perimeter"),
        "point_in_polygon": ("inside", "on_boundary"),
        # bits_bytes
        "parse_data_size": ("size_bytes", "size_bits"),
        "format_bytes_human": ("text", "value", "unit"),
        "bitwise_operation": ("result", "binary", "hex"),
        "integer_to_twos_complement": ("binary", "hex", "unsigned_value"),
        "twos_complement_to_integer": ("signed_value", "unsigned_value", "width"),
        "convert_unix_permissions": ("octal", "symbolic", "owner", "group", "others", "setuid", "setgid", "sticky"),
        # markdown_html
        "extract_markdown_headings": ("headings", "count"),
        "extract_markdown_tasks": ("tasks", "done", "open"),
        "parse_markdown_table": ("columns", "records", "table_count", "alignment"),
        "extract_markdown_links": ("links", "count", "truncated"),
        "extract_fenced_code_blocks": ("blocks", "count"),
        "html_table_to_records": ("columns", "records", "table_count"),
        "extract_html_links": ("links", "count", "truncated"),
        # text_extraction
        "extract_urls": ("urls", "count", "truncated"),
        "extract_email_addresses": ("emails", "count", "truncated"),
        "extract_numbers": ("numbers", "count", "truncated"),
        "extract_dates": ("dates", "count", "truncated"),
        "extract_ip_addresses": ("addresses", "count", "truncated"),
        "extract_money_amounts": ("amounts", "count", "truncated"),
        "extract_key_value_pairs": ("pairs", "count", "truncated"),
        "extract_sentences": ("sentences", "count", "truncated"),
        # code_analysis
        "verify_python_syntax": ("valid", "error", "line", "column", "python_version"),
        "list_python_functions": ("functions", "count"),
        "list_python_classes": ("classes", "count"),
        "list_python_imports": ("imports", "modules"),
        "count_lines_of_code": ("total_lines", "code_lines", "comment_lines", "blank_lines"),
        "get_python_function_signature": ("signature", "parameters", "returns", "docstring", "line"),
        "find_python_name_usages": ("usages", "count", "truncated"),
        "python_literal_to_json": ("json",),
        "shell_split_command": ("arguments", "count"),
        "shell_quote_arguments": ("command",),
        # network_addresses
        "verify_ip_address": ("valid", "version", "compressed", "exploded", "reason"),
        "cidr_network_details": ("network", "network_address", "broadcast_address", "netmask", "hostmask", "prefix_length", "total_addresses", "usable_hosts", "first_usable", "last_usable", "version"),
        "ip_in_networks": ("contained", "matching_networks", "most_specific"),
        "split_cidr_into_subnets": ("subnets", "count", "truncated"),
        "ip_range_to_cidrs": ("cidrs", "count"),
        "classify_ip_address": ("address", "version", "is_private", "is_global", "is_loopback", "is_link_local", "is_multicast", "is_reserved", "is_unspecified", "ipv4_mapped"),
        "convert_ip_address_integer": ("address", "integer", "version", "hex"),
        "convert_ipv4_netmask": ("prefix_length", "netmask", "hostmask"),
    }
)
