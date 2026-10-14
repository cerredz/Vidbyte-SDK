"""FILE: tests/features/prebuilt_tools/prebuilt_parameter_data.py

PURPOSE: Hand-copied parameter table of every prebuilt tool from spec Appendix A and the §9.2 shorthand types: names in order, JSON type, length caps, item caps, and defaults.
ROLE IN CODEBASE: Expected values for the schema contract test in tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py; it imports nothing from vidbyte.
ARCHITECTURE NOTE: Each entry is (parameter, json type, maxLength or maxItems, item maxLength, default). The item field is a TextListsShape instead of an int for the one list whose items are themselves lists (A.24 intersect_lists, list[TextList]). The type is a JSON Schema type, a JSON Schema format (date, date-time, time), utc_offset for the §9.2 UtcOffset string, or enum:<EnumName>.
FUNCTION INVENTORY: Data only: the REQUIRED sentinel, the TextListsShape record with its one value LIST_OF_TEXT_LISTS, and TOOL_PARAMETERS.
COMMON MODIFICATION PATTERNS: When an Appendix A parameters cell changes, edit its entry here in the same commit as the spec.
WHAT NOT TO DO IN THIS FILE: 1. Do not read FunctionTool schemas to fill this table; it must stay an independent transcription. 2. Do not add helpers here.
KNOWN EDGE CASES: A utc_offset parameter carries both the §9.2 UtcOffset pattern and the spec r4 cap PREBUILT_MAX_UTC_OFFSET_CHARS (6). The weekend_days cap of 7 is a literal in the rows, not a constant. intersect_lists.lists is list[TextList] len 2..PREBUILT_MAX_LISTS, so its items are arrays of at most 10,000 strings of at most 10,000 characters each, not strings (S3-3). Spec r6 lowers find_substring_positions.substring to PREBUILT_MAX_SEARCH_STRING_CHARS (500) (R-10, EC-50). Enum defaults are written as their value strings and tuple defaults as lists, which is how the JSON schema shows them.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A, §9.2 item 2)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py
"""

from __future__ import annotations

from types import MappingProxyType
from typing import NamedTuple

REQUIRED = "<required>"


class TextListsShape(NamedTuple):
    """The parts of a list[TextList] parameter that its outer maxItems does not state: the least number of lists, and each list's §9.2 TextList caps."""

    min_lists: int
    list_items: int
    item_chars: int


LIST_OF_TEXT_LISTS = TextListsShape(min_lists=2, list_items=10000, item_chars=10000)

ParameterRow = tuple[str, str, object, object, object]

TOOL_PARAMETERS: MappingProxyType[str, tuple[ParameterRow, ...]] = MappingProxyType(
    {
        # A.1 exact_arithmetic
        'decimal_arithmetic': (('left', 'string', 4002, None, REQUIRED), ('right', 'string', 4002, None, REQUIRED), ('operation', 'enum:ArithmeticOperation', None, None, REQUIRED), ('decimal_places', 'integer', None, None, 28)),
        'round_decimal': (('value', 'string', 4002, None, REQUIRED), ('decimal_places', 'integer', None, None, 0), ('mode', 'enum:RoundingMode', None, None, 'half_even')),
        'round_significant_figures': (('value', 'string', 4002, None, REQUIRED), ('significant_figures', 'integer', None, None, REQUIRED), ('mode', 'enum:RoundingMode', None, None, 'half_even')),
        'sum_decimal_list': (('values', 'array', 10000, 4002, REQUIRED),),
        'fraction_arithmetic': (('left', 'string', 8002, None, REQUIRED), ('right', 'string', 8002, None, REQUIRED), ('operation', 'enum:ArithmeticOperation', None, None, REQUIRED)),
        'decimal_to_fraction': (('value', 'string', 4002, None, REQUIRED), ('max_denominator', 'integer', None, None, None)),
        'repeating_decimal_to_fraction': (('value', 'string', 1000, None, REQUIRED),),
        'fraction_to_decimal': (('fraction', 'string', 8002, None, REQUIRED),),
        'integer_square_root': (('value', 'string', 4001, None, REQUIRED),),
        'solve_quadratic_equation': (('a', 'number', None, None, REQUIRED), ('b', 'number', None, None, REQUIRED), ('c', 'number', None, None, REQUIRED)),
        # A.2 number_theory
        'is_prime': (('value', 'string', 4001, None, REQUIRED),),
        'prime_factorize': (('value', 'integer', None, None, REQUIRED),),
        'list_primes_in_range': (('start', 'integer', None, None, REQUIRED), ('end', 'integer', None, None, REQUIRED)),
        'nth_prime': (('n', 'integer', None, None, REQUIRED),),
        'next_prime': (('value', 'string', 4001, None, REQUIRED), ('direction', 'enum:SearchDirection', None, None, 'next')),
        'greatest_common_divisor': (('values', 'array', 10000, 4001, REQUIRED),),
        'least_common_multiple': (('values', 'array', 10000, 4001, REQUIRED),),
        'list_divisors': (('value', 'integer', None, None, REQUIRED),),
        'modular_exponentiation': (('base', 'string', 2001, None, REQUIRED), ('exponent', 'string', 2001, None, REQUIRED), ('modulus', 'string', 2001, None, REQUIRED)),
        'modular_inverse': (('value', 'string', 4001, None, REQUIRED), ('modulus', 'string', 4001, None, REQUIRED)),
        # A.3 number_formatting
        'convert_number_base': (('value', 'string', 4001, None, REQUIRED), ('from_base', 'integer', None, None, REQUIRED), ('to_base', 'integer', None, None, REQUIRED)),
        'number_to_english_words': (('value', 'string', 4001, None, REQUIRED), ('ordinal', 'boolean', None, None, False)),
        'english_words_to_number': (('words', 'string', 1000, None, REQUIRED),),
        'parse_abbreviated_number': (('text', 'string', 200, None, REQUIRED),),
        'format_number_with_separators': (('value', 'string', 4002, None, REQUIRED), ('style', 'enum:SeparatorStyle', None, None, 'comma_period'), ('decimal_places', 'integer', None, None, None)),
        'parse_formatted_number': (('text', 'string', 200, None, REQUIRED), ('style', 'enum:SeparatorStyle', None, None, 'comma_period')),
        'to_scientific_notation': (('value', 'string', 4002, None, REQUIRED), ('significant_figures', 'integer', None, None, None), ('style', 'enum:NotationStyle', None, None, 'scientific')),
        # A.4 descriptive_statistics
        'summarize_numbers': (('values', 'array', 10000, None, REQUIRED),),
        'compute_mode': (('values', 'array', 10000, None, REQUIRED),),
        'compute_percentile': (('values', 'array', 10000, None, REQUIRED), ('percentile', 'number', None, None, REQUIRED), ('method', 'enum:PercentileMethod', None, None, 'linear')),
        'compute_quartiles': (('values', 'array', 10000, None, REQUIRED), ('method', 'enum:QuartileMethod', None, None, 'exclusive')),
        'weighted_mean': (('values', 'array', 10000, None, REQUIRED), ('weights', 'array', 10000, None, REQUIRED)),
        'pearson_correlation': (('x', 'array', 10000, None, REQUIRED), ('y', 'array', 10000, None, REQUIRED)),
        'spearman_rank_correlation': (('x', 'array', 10000, None, REQUIRED), ('y', 'array', 10000, None, REQUIRED)),
        'linear_regression_fit': (('x', 'array', 10000, None, REQUIRED), ('y', 'array', 10000, None, REQUIRED)),
        'moving_average': (('values', 'array', 10000, None, REQUIRED), ('window', 'integer', None, None, REQUIRED)),
        'detect_outliers_iqr': (('values', 'array', 10000, None, REQUIRED), ('multiplier', 'number', None, None, 1.5)),
        'rank_values': (('values', 'array', 10000, None, REQUIRED), ('method', 'enum:RankMethod', None, None, 'average'), ('descending', 'boolean', None, None, False)),
        # A.5 probability
        'count_combinations': (('n', 'integer', None, None, REQUIRED), ('k', 'integer', None, None, REQUIRED), ('with_repetition', 'boolean', None, None, False)),
        'count_permutations': (('n', 'integer', None, None, REQUIRED), ('k', 'integer', None, None, None), ('with_repetition', 'boolean', None, None, False)),
        'exact_factorial': (('n', 'integer', None, None, REQUIRED),),
        'binomial_probability': (('trials', 'integer', None, None, REQUIRED), ('successes', 'integer', None, None, REQUIRED), ('probability', 'number', None, None, REQUIRED), ('tail', 'enum:ProbabilityTail', None, None, 'exactly')),
        'poisson_probability': (('rate', 'number', None, None, REQUIRED), ('occurrences', 'integer', None, None, REQUIRED), ('tail', 'enum:ProbabilityTail', None, None, 'exactly')),
        'normal_distribution_probability': (('lower', 'number', None, None, None), ('upper', 'number', None, None, None), ('mean', 'number', None, None, 0.0), ('standard_deviation', 'number', None, None, 1.0)),
        'normal_quantile': (('probability', 'number', None, None, REQUIRED), ('mean', 'number', None, None, 0.0), ('standard_deviation', 'number', None, None, 1.0)),
        'birthday_collision_probability': (('items', 'integer', None, None, REQUIRED), ('possible_values', 'integer', None, None, REQUIRED)),
        'list_combinations': (('items', 'array', 20, 200, REQUIRED), ('size', 'integer', None, None, REQUIRED), ('with_repetition', 'boolean', None, None, False)),
        # A.6 seeded_random
        'seeded_random_integers': (('seed', 'integer', None, None, REQUIRED), ('count', 'integer', None, None, REQUIRED), ('minimum', 'integer', None, None, REQUIRED), ('maximum', 'integer', None, None, REQUIRED), ('unique', 'boolean', None, None, False)),
        'seeded_shuffle_list': (('items', 'array', 10000, 10000, REQUIRED), ('seed', 'integer', None, None, REQUIRED)),
        'seeded_sample_list': (('items', 'array', 10000, 10000, REQUIRED), ('size', 'integer', None, None, REQUIRED), ('seed', 'integer', None, None, REQUIRED)),
        'seeded_weighted_choice': (('items', 'array', 10000, 10000, REQUIRED), ('weights', 'array', 10000, None, REQUIRED), ('seed', 'integer', None, None, REQUIRED), ('picks', 'integer', None, None, 1)),
        'roll_dice_notation': (('notation', 'string', 200, None, REQUIRED), ('seed', 'integer', None, None, REQUIRED)),
        'generate_seeded_uuid4': (('seed', 'integer', None, None, REQUIRED), ('count', 'integer', None, None, 1)),
        # A.7 finance
        'compound_interest_future_value': (('principal', 'number', None, None, REQUIRED), ('annual_rate_percent', 'number', None, None, REQUIRED), ('years', 'number', None, None, REQUIRED), ('compounding', 'enum:CompoundingFrequency', None, None, 'monthly')),
        'loan_payment_amount': (('principal', 'number', None, None, REQUIRED), ('annual_rate_percent', 'number', None, None, REQUIRED), ('term_months', 'integer', None, None, REQUIRED)),
        'amortization_schedule': (('principal', 'number', None, None, REQUIRED), ('annual_rate_percent', 'number', None, None, REQUIRED), ('term_months', 'integer', None, None, REQUIRED)),
        'net_present_value': (('rate_percent', 'number', None, None, REQUIRED), ('cash_flows', 'array', 10000, None, REQUIRED)),
        'internal_rate_of_return': (('cash_flows', 'array', 600, None, REQUIRED),),
        'compound_annual_growth_rate': (('start_value', 'number', None, None, REQUIRED), ('end_value', 'number', None, None, REQUIRED), ('years', 'number', None, None, REQUIRED)),
        'percentage_change': (('old_value', 'number', None, None, REQUIRED), ('new_value', 'number', None, None, REQUIRED)),
        'percentage_breakdown': (('labels', 'array', 10000, 10000, REQUIRED), ('values', 'array', 10000, None, REQUIRED), ('decimal_places', 'integer', None, None, 1)),
        'allocate_amount': (('amount', 'string', 4002, None, REQUIRED), ('weights', 'array', 10000, None, REQUIRED), ('decimal_places', 'integer', None, None, 2)),
        'split_tax_inclusive_amount': (('gross_amount', 'string', 4002, None, REQUIRED), ('tax_rate_percent', 'number', None, None, REQUIRED)),
        # A.8 unit_conversion
        'convert_length': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:LengthUnit', None, None, REQUIRED), ('to_unit', 'enum:LengthUnit', None, None, REQUIRED)),
        'convert_mass': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:MassUnit', None, None, REQUIRED), ('to_unit', 'enum:MassUnit', None, None, REQUIRED)),
        'convert_temperature': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:TemperatureUnit', None, None, REQUIRED), ('to_unit', 'enum:TemperatureUnit', None, None, REQUIRED)),
        'convert_volume': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:VolumeUnit', None, None, REQUIRED), ('to_unit', 'enum:VolumeUnit', None, None, REQUIRED)),
        'convert_area': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:AreaUnit', None, None, REQUIRED), ('to_unit', 'enum:AreaUnit', None, None, REQUIRED)),
        'convert_speed': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:SpeedUnit', None, None, REQUIRED), ('to_unit', 'enum:SpeedUnit', None, None, REQUIRED)),
        'convert_duration': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:DurationUnit', None, None, REQUIRED), ('to_unit', 'enum:DurationUnit', None, None, REQUIRED)),
        'convert_energy': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:EnergyUnit', None, None, REQUIRED), ('to_unit', 'enum:EnergyUnit', None, None, REQUIRED)),
        'convert_fuel_economy': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:FuelEconomyUnit', None, None, REQUIRED), ('to_unit', 'enum:FuelEconomyUnit', None, None, REQUIRED)),
        'convert_data_size': (('value', 'number', None, None, REQUIRED), ('from_unit', 'enum:DataSizeUnit', None, None, REQUIRED), ('to_unit', 'enum:DataSizeUnit', None, None, REQUIRED)),
        # A.9 dates
        'days_between_dates': (('start_date', 'date', None, None, REQUIRED), ('end_date', 'date', None, None, REQUIRED), ('include_end_date', 'boolean', None, None, False)),
        'add_to_date': (('start_date', 'date', None, None, REQUIRED), ('amount', 'integer', None, None, REQUIRED), ('unit', 'enum:DateUnit', None, None, REQUIRED)),
        'years_months_days_between': (('start_date', 'date', None, None, REQUIRED), ('end_date', 'date', None, None, REQUIRED)),
        'day_of_week': (('target_date', 'date', None, None, REQUIRED),),
        'iso_week_number': (('target_date', 'date', None, None, REQUIRED),),
        'nth_weekday_of_month': (('year', 'integer', None, None, REQUIRED), ('month', 'integer', None, None, REQUIRED), ('weekday', 'enum:Weekday', None, None, REQUIRED), ('occurrence', 'enum:WeekdayOccurrence', None, None, REQUIRED)),
        'next_weekday': (('start_date', 'date', None, None, REQUIRED), ('weekday', 'enum:Weekday', None, None, REQUIRED), ('direction', 'enum:SearchDirection', None, None, 'next'), ('include_start', 'boolean', None, None, False)),
        'resolve_relative_date_phrase': (('phrase', 'string', 200, None, REQUIRED), ('reference_date', 'date', None, None, REQUIRED), ('week_starts_on', 'enum:Weekday', None, None, 'monday')),
        'parse_date_to_iso': (('text', 'string', 200, None, REQUIRED), ('day_first', 'boolean', None, None, False)),
        'fiscal_quarter': (('target_date', 'date', None, None, REQUIRED), ('fiscal_year_start_month', 'integer', None, None, 1)),
        # A.10 scheduling
        'business_days_between': (('start_date', 'date', None, None, REQUIRED), ('end_date', 'date', None, None, REQUIRED), ('holidays', 'array', 1000, None, []), ('weekend_days', 'array', 7, None, ['saturday', 'sunday'])),
        'add_business_days': (('start_date', 'date', None, None, REQUIRED), ('business_days', 'integer', None, None, REQUIRED), ('holidays', 'array', 1000, None, []), ('weekend_days', 'array', 7, None, ['saturday', 'sunday'])),
        'list_dates_in_range': (('start_date', 'date', None, None, REQUIRED), ('end_date', 'date', None, None, REQUIRED), ('step_days', 'integer', None, None, 1), ('weekdays', 'array', 7, None, [])),
        'count_weekday_occurrences': (('start_date', 'date', None, None, REQUIRED), ('end_date', 'date', None, None, REQUIRED), ('weekday', 'enum:Weekday', None, None, REQUIRED)),
        'generate_recurring_dates': (('start_date', 'date', None, None, REQUIRED), ('frequency', 'enum:RecurrenceFrequency', None, None, REQUIRED), ('repeat_every', 'integer', None, None, 1), ('occurrences', 'integer', None, None, None), ('until_date', 'date', None, None, None)),
        'merge_time_intervals': (('starts', 'array', 10000, None, REQUIRED), ('ends', 'array', 10000, None, REQUIRED), ('output_offset', 'utc_offset', 6, None, '+00:00')),
        'find_common_free_slots': (('busy_starts', 'array', 10000, None, REQUIRED), ('busy_ends', 'array', 10000, None, REQUIRED), ('window_start', 'date-time', None, None, REQUIRED), ('window_end', 'date-time', None, None, REQUIRED), ('minimum_minutes', 'number', None, None, 30), ('output_offset', 'utc_offset', 6, None, '+00:00')),
        'sort_date_strings': (('dates', 'array', 10000, 200, REQUIRED), ('day_first', 'boolean', None, None, False), ('descending', 'boolean', None, None, False)),
        # A.11 timestamps_durations
        'unix_timestamp_to_datetime': (('timestamp', 'number', None, None, REQUIRED), ('unit', 'enum:TimestampUnit', None, None, 'seconds'), ('utc_offset', 'utc_offset', 6, None, '+00:00')),
        'datetime_to_unix_timestamp': (('moment', 'date-time', None, None, REQUIRED), ('unit', 'enum:TimestampUnit', None, None, 'seconds')),
        'convert_utc_offset': (('moment', 'date-time', None, None, REQUIRED), ('to_offset', 'utc_offset', 6, None, REQUIRED)),
        'duration_between_datetimes': (('start', 'date-time', None, None, REQUIRED), ('end', 'date-time', None, None, REQUIRED)),
        'add_duration_to_datetime': (('moment', 'date-time', None, None, REQUIRED), ('days', 'integer', None, None, 0), ('hours', 'integer', None, None, 0), ('minutes', 'integer', None, None, 0), ('seconds', 'number', None, None, 0)),
        'format_duration': (('seconds', 'number', None, None, REQUIRED), ('style', 'enum:DurationStyle', None, None, 'compact')),
        'parse_duration_text': (('text', 'string', 200, None, REQUIRED),),
        'minutes_between_times': (('start_time', 'time', None, None, REQUIRED), ('end_time', 'time', None, None, REQUIRED)),
        # A.12 text_counting
        'count_characters': (('text', 'string', 1000000, None, REQUIRED),),
        'count_character_occurrences': (('text', 'string', 1000000, None, REQUIRED), ('character', 'string', 1, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        'find_substring_positions': (('text', 'string', 1000000, None, REQUIRED), ('substring', 'string', 500, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True), ('allow_overlap', 'boolean', None, None, True)),
        'count_words': (('text', 'string', 1000000, None, REQUIRED),),
        'count_sentences': (('text', 'string', 1000000, None, REQUIRED),),
        'count_lines': (('text', 'string', 1000000, None, REQUIRED),),
        'word_frequencies': (('text', 'string', 1000000, None, REQUIRED), ('case_sensitive', 'boolean', None, None, False), ('top', 'integer', None, None, 50)),
        'character_frequencies': (('text', 'string', 1000000, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True), ('include_whitespace', 'boolean', None, None, False), ('top', 'integer', None, None, 100)),
        'ngram_frequencies': (('text', 'string', 1000000, None, REQUIRED), ('n', 'integer', None, None, 2), ('unit', 'enum:NgramUnit', None, None, 'words'), ('case_sensitive', 'boolean', None, None, False), ('top', 'integer', None, None, 50)),
        'character_at_position': (('text', 'string', 1000000, None, REQUIRED), ('position', 'integer', None, None, REQUIRED)),
        'readability_scores': (('text', 'string', 1000000, None, REQUIRED),),
        'count_syllables': (('text', 'string', 1000000, None, REQUIRED),),
        # A.13 text_transform
        'reverse_text': (('text', 'string', 1000000, None, REQUIRED), ('unit', 'enum:TextUnit', None, None, 'characters')),
        'convert_identifier_case': (('text', 'string', 10000, None, REQUIRED), ('target', 'enum:IdentifierCase', None, None, REQUIRED)),
        'shorten_text': (('text', 'string', 1000000, None, REQUIRED), ('max_length', 'integer', None, None, REQUIRED), ('unit', 'enum:TextUnit', None, None, 'characters'), ('ellipsis', 'string', 200, None, '…'), ('break_on_word', 'boolean', None, None, True)),
        'replace_all_occurrences': (('text', 'string', 1000000, None, REQUIRED), ('find', 'string', 10000, None, REQUIRED), ('replacement', 'string', 10000, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True), ('max_replacements', 'integer', None, None, None)),
        'deduplicate_lines': (('text', 'string', 1000000, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True), ('ignore_surrounding_whitespace', 'boolean', None, None, False)),
        'sort_text_lines': (('text', 'string', 1000000, None, REQUIRED), ('mode', 'enum:SortMode', None, None, 'text'), ('descending', 'boolean', None, None, False), ('unique', 'boolean', None, None, False)),
        'strip_html_tags': (('html_text', 'string', 1000000, None, REQUIRED),),
        'split_text_into_chunks': (('text', 'string', 1000000, None, REQUIRED), ('chunk_size', 'integer', None, None, REQUIRED), ('overlap', 'integer', None, None, 0)),
        'extract_line_range': (('text', 'string', 1000000, None, REQUIRED), ('start_line', 'integer', None, None, REQUIRED), ('end_line', 'integer', None, None, None), ('number_lines', 'boolean', None, None, False)),
        'fill_text_template': (('template', 'string', 1000000, None, REQUIRED), ('values_json', 'string', 1000000, None, REQUIRED), ('missing', 'enum:MissingPlaceholderPolicy', None, None, 'error')),
        # A.14 unicode
        'unicode_character_info': (('text', 'string', 200, None, REQUIRED),),
        'find_unicode_character': (('name_query', 'string', 200, None, REQUIRED),),
        'apply_unicode_normalization': (('text', 'string', 1000000, None, REQUIRED), ('form', 'enum:UnicodeForm', None, None, REQUIRED)),
        'remove_diacritics': (('text', 'string', 1000000, None, REQUIRED),),
        'find_invisible_characters': (('text', 'string', 1000000, None, REQUIRED),),
        'find_non_ascii_characters': (('text', 'string', 1000000, None, REQUIRED),),
        'detect_scripts_in_text': (('text', 'string', 1000000, None, REQUIRED),),
        'count_bytes_in_encoding': (('text', 'string', 1000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'sms_segment_count': (('text', 'string', 10000, None, REQUIRED),),
        'repair_mojibake_text': (('text', 'string', 1000000, None, REQUIRED),),
        # A.15 regex
        'regex_find_all': (('pattern', 'string', 1000, None, REQUIRED), ('text', 'string', 100000, None, REQUIRED), ('flags', 'array', 5, None, [])),
        'regex_match': (('pattern', 'string', 1000, None, REQUIRED), ('text', 'string', 100000, None, REQUIRED), ('flags', 'array', 5, None, []), ('mode', 'enum:RegexMatchMode', None, None, 'full')),
        'regex_replace': (('pattern', 'string', 1000, None, REQUIRED), ('replacement', 'string', 10000, None, REQUIRED), ('text', 'string', 100000, None, REQUIRED), ('flags', 'array', 5, None, []), ('max_replacements', 'integer', None, None, None)),
        'regex_split': (('pattern', 'string', 1000, None, REQUIRED), ('text', 'string', 100000, None, REQUIRED), ('flags', 'array', 5, None, []), ('max_splits', 'integer', None, None, None)),
        'verify_regex_pattern': (('pattern', 'string', 1000, None, REQUIRED), ('flags', 'array', 5, None, [])),
        'regex_test_samples': (('pattern', 'string', 1000, None, REQUIRED), ('should_match', 'array', 100, 10000, REQUIRED), ('should_not_match', 'array', 100, 10000, []), ('flags', 'array', 5, None, []), ('mode', 'enum:RegexMatchMode', None, None, 'full')),
        'wildcard_match_names': (('pattern', 'string', 1000, None, REQUIRED), ('names', 'array', 10000, 10000, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        # A.16 text_comparison
        'unified_diff_text': (('original', 'string', 1000000, None, REQUIRED), ('modified', 'string', 1000000, None, REQUIRED), ('context_lines', 'integer', None, None, 3), ('original_label', 'string', 200, None, 'original'), ('modified_label', 'string', 200, None, 'modified')),
        'diff_words': (('original', 'string', 100000, None, REQUIRED), ('modified', 'string', 100000, None, REQUIRED)),
        'levenshtein_distance': (('first', 'string', 1000, None, REQUIRED), ('second', 'string', 1000, None, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        'closest_string_matches': (('query', 'string', 100, None, REQUIRED), ('candidates', 'array', 1000, 100, REQUIRED), ('top', 'integer', None, None, 5), ('minimum_score', 'number', None, None, 0.0), ('case_sensitive', 'boolean', None, None, False)),
        'longest_common_substring': (('first', 'string', 2000, None, REQUIRED), ('second', 'string', 2000, None, REQUIRED)),
        'jaccard_similarity': (('first', 'string', 1000000, None, REQUIRED), ('second', 'string', 1000000, None, REQUIRED), ('unit', 'enum:NgramUnit', None, None, 'words'), ('n', 'integer', None, None, 1), ('case_sensitive', 'boolean', None, None, False)),
        # A.17 json_data
        'verify_json_syntax': (('json_text', 'string', 1000000, None, REQUIRED),),
        'format_json': (('json_text', 'string', 1000000, None, REQUIRED), ('indent', 'integer', None, None, 2), ('sort_keys', 'boolean', None, None, False), ('ensure_ascii', 'boolean', None, None, False)),
        'json_get_value': (('json_text', 'string', 1000000, None, REQUIRED), ('pointer', 'string', 10000, None, REQUIRED)),
        'json_set_value': (('json_text', 'string', 1000000, None, REQUIRED), ('pointer', 'string', 10000, None, REQUIRED), ('value_json', 'string', 1000000, None, REQUIRED), ('create_missing', 'boolean', None, None, False)),
        'list_json_paths': (('json_text', 'string', 1000000, None, REQUIRED), ('leaves_only', 'boolean', None, None, True)),
        'diff_json_documents': (('original_json', 'string', 1000000, None, REQUIRED), ('modified_json', 'string', 1000000, None, REQUIRED)),
        'apply_json_patch': (('json_text', 'string', 1000000, None, REQUIRED), ('patch_json', 'string', 1000000, None, REQUIRED)),
        'summarize_json_structure': (('json_text', 'string', 1000000, None, REQUIRED),),
        'extract_json_from_text': (('text', 'string', 100000, None, REQUIRED),),
        # A.18 json_records
        'filter_records': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED), ('operator', 'enum:FilterOperator', None, None, REQUIRED), ('value', 'string', 10000, None, '')),
        'pluck_field': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED)),
        'group_records_by_field': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED)),
        'aggregate_field': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED), ('function', 'enum:AggregateFunction', None, None, REQUIRED)),
        'group_and_aggregate_records': (('records_json', 'string', 1000000, None, REQUIRED), ('group_by_field', 'string', 200, None, REQUIRED), ('value_field', 'string', 200, None, REQUIRED), ('function', 'enum:AggregateFunction', None, None, REQUIRED)),
        'sort_records': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED), ('descending', 'boolean', None, None, False)),
        'count_field_values': (('records_json', 'string', 1000000, None, REQUIRED), ('field', 'string', 200, None, REQUIRED), ('top', 'integer', None, None, 100)),
        'join_records': (('left_json', 'string', 1000000, None, REQUIRED), ('right_json', 'string', 1000000, None, REQUIRED), ('left_field', 'string', 200, None, REQUIRED), ('right_field', 'string', 200, None, REQUIRED), ('kind', 'enum:JoinKind', None, None, 'inner')),
        'records_to_csv': (('records_json', 'string', 1000000, None, REQUIRED), ('columns', 'array', 500, 200, []), ('delimiter', 'enum:CsvDelimiter', None, None, 'comma')),
        # A.19 csv_tables
        'csv_to_records': (('csv_text', 'string', 1000000, None, REQUIRED), ('delimiter', 'enum:CsvDelimiter', None, None, None), ('infer_types', 'boolean', None, None, False)),
        'detect_csv_dialect': (('csv_text', 'string', 1000000, None, REQUIRED),),
        'profile_csv_columns': (('csv_text', 'string', 1000000, None, REQUIRED), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_filter_rows': (('csv_text', 'string', 1000000, None, REQUIRED), ('column', 'string', 200, None, REQUIRED), ('operator', 'enum:FilterOperator', None, None, REQUIRED), ('value', 'string', 10000, None, ''), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_sort_rows': (('csv_text', 'string', 1000000, None, REQUIRED), ('column', 'string', 200, None, REQUIRED), ('mode', 'enum:SortMode', None, None, 'natural'), ('descending', 'boolean', None, None, False), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_aggregate_column': (('csv_text', 'string', 1000000, None, REQUIRED), ('column', 'string', 200, None, REQUIRED), ('function', 'enum:AggregateFunction', None, None, REQUIRED), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_group_by': (('csv_text', 'string', 1000000, None, REQUIRED), ('group_column', 'string', 200, None, REQUIRED), ('value_column', 'string', 200, None, REQUIRED), ('function', 'enum:AggregateFunction', None, None, REQUIRED), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_join_tables': (('left_csv', 'string', 1000000, None, REQUIRED), ('right_csv', 'string', 1000000, None, REQUIRED), ('left_column', 'string', 200, None, REQUIRED), ('right_column', 'string', 200, None, REQUIRED), ('kind', 'enum:JoinKind', None, None, 'inner'), ('delimiter', 'enum:CsvDelimiter', None, None, None)),
        'csv_to_markdown_table': (('csv_text', 'string', 1000000, None, REQUIRED), ('delimiter', 'enum:CsvDelimiter', None, None, None), ('alignment', 'enum:TableAlignment', None, None, 'left')),
        # A.20 structured_formats
        'xml_to_json': (('xml_text', 'string', 1000000, None, REQUIRED),),
        'verify_xml_wellformed': (('xml_text', 'string', 1000000, None, REQUIRED),),
        'xml_find_elements': (('xml_text', 'string', 1000000, None, REQUIRED), ('path', 'string', 1000, None, REQUIRED)),
        'ini_to_json': (('ini_text', 'string', 1000000, None, REQUIRED),),
        'toml_to_json': (('toml_text', 'string', 1000000, None, REQUIRED),),
        'parse_url': (('url', 'string', 10000, None, REQUIRED),),
        'resolve_relative_url': (('base_url', 'string', 10000, None, REQUIRED), ('reference', 'string', 10000, None, REQUIRED)),
        'parse_query_string': (('query', 'string', 100000, None, REQUIRED),),
        'parse_dotenv_text': (('dotenv_text', 'string', 1000000, None, REQUIRED),),
        # A.21 encoding
        'base64_encode': (('text', 'string', 1000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8'), ('url_safe', 'boolean', None, None, False), ('padding', 'boolean', None, None, True)),
        'base64_decode': (('data', 'string', 2000000, None, REQUIRED), ('url_safe', 'boolean', None, None, None), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'hex_encode': (('text', 'string', 1000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8'), ('separator', 'enum:HexSeparator', None, None, 'none'), ('uppercase', 'boolean', None, None, False)),
        'hex_decode': (('hex_text', 'string', 2000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'url_encode': (('text', 'string', 100000, None, REQUIRED), ('mode', 'enum:UrlEncodingMode', None, None, 'component')),
        'url_decode': (('text', 'string', 100000, None, REQUIRED), ('mode', 'enum:UrlEncodingMode', None, None, 'component')),
        'html_unescape': (('text', 'string', 1000000, None, REQUIRED),),
        'decode_jwt_payload': (('jwt_text', 'string', 100000, None, REQUIRED),),
        'escape_json_string': (('text', 'string', 1000000, None, REQUIRED), ('ensure_ascii', 'boolean', None, None, False)),
        'unescape_json_string': (('escaped', 'string', 1000000, None, REQUIRED),),
        # A.22 hashing
        'hash_text': (('text', 'string', 1000000, None, REQUIRED), ('algorithm', 'enum:HashAlgorithm', None, None, 'sha256'), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8'), ('digest_format', 'enum:DigestFormat', None, None, 'hex')),
        'hash_base64_content': (('data_base64', 'string', 2000000, None, REQUIRED), ('algorithm', 'enum:HashAlgorithm', None, None, 'sha256'), ('digest_format', 'enum:DigestFormat', None, None, 'hex')),
        'compute_hmac': (('message', 'string', 1000000, None, REQUIRED), ('key', 'string', 10000, None, REQUIRED), ('key_format', 'enum:KeyFormat', None, None, 'text'), ('algorithm', 'enum:HashAlgorithm', None, None, 'sha256'), ('digest_format', 'enum:DigestFormat', None, None, 'hex')),
        'verify_hash': (('text', 'string', 1000000, None, REQUIRED), ('expected_digest', 'string', 200, None, REQUIRED), ('algorithm', 'enum:HashAlgorithm', None, None, 'sha256'), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'crc32_checksum': (('text', 'string', 1000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'git_blob_hash': (('content', 'string', 1000000, None, REQUIRED), ('text_encoding', 'enum:TextEncoding', None, None, 'utf_8')),
        'assign_stable_bucket': (('key', 'string', 10000, None, REQUIRED), ('buckets', 'integer', None, None, REQUIRED), ('salt', 'string', 10000, None, '')),
        # A.23 identifiers
        'verify_luhn_checksum': (('number', 'string', 200, None, REQUIRED),),
        'verify_isbn': (('isbn', 'string', 200, None, REQUIRED),),
        'verify_iban': (('iban', 'string', 200, None, REQUIRED),),
        'verify_gtin_barcode': (('code', 'string', 200, None, REQUIRED),),
        'verify_email_syntax': (('email', 'string', 1000, None, REQUIRED),),
        'verify_url_syntax': (('url', 'string', 10000, None, REQUIRED), ('allowed_schemes', 'array', 100, 200, ['http', 'https'])),
        'verify_uuid': (('value', 'string', 200, None, REQUIRED),),
        'generate_name_based_uuid': (('name', 'string', 10000, None, REQUIRED), ('namespace', 'string', 200, None, REQUIRED), ('version', 'enum:UuidNameVersion', None, None, 'v5')),
        'compare_semantic_versions': (('first', 'string', 1000, None, REQUIRED), ('second', 'string', 1000, None, REQUIRED)),
        # A.24 lists
        'count_item_frequencies': (('items', 'array', 10000, 10000, REQUIRED), ('case_sensitive', 'boolean', None, None, True), ('top', 'integer', None, None, 100)),
        'find_duplicate_items': (('items', 'array', 10000, 10000, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        'compare_two_lists': (('first', 'array', 10000, 10000, REQUIRED), ('second', 'array', 10000, 10000, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        'intersect_lists': (('lists', 'array', 100, LIST_OF_TEXT_LISTS, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
        'find_missing_integers': (('values', 'array', 10000, None, REQUIRED), ('start', 'integer', None, None, None), ('end', 'integer', None, None, None)),
        'compress_integer_ranges': (('values', 'array', 10000, None, REQUIRED),),
        'expand_integer_ranges': (('text', 'string', 100000, None, REQUIRED),),
        # A.25 graphs
        'topological_sort': (('sources', 'array', 10000, 200, REQUIRED), ('targets', 'array', 10000, 200, REQUIRED), ('nodes', 'array', 10000, 200, [])),
        'find_graph_cycle': (('sources', 'array', 10000, 200, REQUIRED), ('targets', 'array', 10000, 200, REQUIRED), ('nodes', 'array', 10000, 200, [])),
        'shortest_path': (('sources', 'array', 10000, 200, REQUIRED), ('targets', 'array', 10000, 200, REQUIRED), ('start', 'string', 200, None, REQUIRED), ('goal', 'string', 200, None, REQUIRED), ('directed', 'boolean', None, None, True)),
        'shortest_weighted_path': (('sources', 'array', 10000, 200, REQUIRED), ('targets', 'array', 10000, 200, REQUIRED), ('weights', 'array', 10000, None, REQUIRED), ('start', 'string', 200, None, REQUIRED), ('goal', 'string', 200, None, REQUIRED), ('directed', 'boolean', None, None, True)),
        'connected_components': (('sources', 'array', 10000, 200, REQUIRED), ('targets', 'array', 10000, 200, REQUIRED), ('nodes', 'array', 10000, 200, [])),
        'critical_path_schedule': (('tasks', 'array', 1000, 200, REQUIRED), ('durations', 'array', 10000, None, REQUIRED), ('dependency_sources', 'array', 10000, 200, []), ('dependency_targets', 'array', 10000, 200, [])),
        # A.26 geometry
        'haversine_distance': (('latitude1', 'number', None, None, REQUIRED), ('longitude1', 'number', None, None, REQUIRED), ('latitude2', 'number', None, None, REQUIRED), ('longitude2', 'number', None, None, REQUIRED), ('unit', 'enum:LengthUnit', None, None, 'kilometer')),
        'initial_bearing': (('latitude1', 'number', None, None, REQUIRED), ('longitude1', 'number', None, None, REQUIRED), ('latitude2', 'number', None, None, REQUIRED), ('longitude2', 'number', None, None, REQUIRED)),
        'destination_point': (('latitude', 'number', None, None, REQUIRED), ('longitude', 'number', None, None, REQUIRED), ('bearing_degrees', 'number', None, None, REQUIRED), ('distance', 'number', None, None, REQUIRED), ('unit', 'enum:LengthUnit', None, None, 'kilometer')),
        'dms_to_decimal_degrees': (('dms', 'string', 200, None, REQUIRED),),
        'decimal_degrees_to_dms': (('decimal_degrees', 'number', None, None, REQUIRED), ('axis', 'enum:CoordinateAxis', None, None, REQUIRED), ('seconds_decimal_places', 'integer', None, None, 1)),
        'polygon_area': (('x', 'array', 10000, None, REQUIRED), ('y', 'array', 10000, None, REQUIRED)),
        'point_in_polygon': (('point_x', 'number', None, None, REQUIRED), ('point_y', 'number', None, None, REQUIRED), ('polygon_x', 'array', 10000, None, REQUIRED), ('polygon_y', 'array', 10000, None, REQUIRED)),
        # A.27 bits_bytes
        'parse_data_size': (('text', 'string', 200, None, REQUIRED),),
        'format_bytes_human': (('size_bytes', 'integer', None, None, REQUIRED), ('standard', 'enum:SizeStandard', None, None, 'iec'), ('decimal_places', 'integer', None, None, 1)),
        'bitwise_operation': (('left', 'string', 4001, None, REQUIRED), ('operation', 'enum:BitwiseOperation', None, None, REQUIRED), ('right', 'string', 4001, None, None), ('width', 'integer', None, None, None)),
        'integer_to_twos_complement': (('value', 'string', 4001, None, REQUIRED), ('width', 'integer', None, None, REQUIRED)),
        'twos_complement_to_integer': (('bits', 'string', 10000, None, REQUIRED), ('bit_format', 'enum:BitStringFormat', None, None, 'binary'), ('width', 'integer', None, None, None)),
        'convert_unix_permissions': (('permissions', 'string', 200, None, REQUIRED),),
        # A.28 markdown_html
        'extract_markdown_headings': (('markdown', 'string', 1000000, None, REQUIRED),),
        'extract_markdown_tasks': (('markdown', 'string', 1000000, None, REQUIRED),),
        'parse_markdown_table': (('markdown', 'string', 1000000, None, REQUIRED), ('table_index', 'integer', None, None, 0)),
        'extract_markdown_links': (('markdown', 'string', 1000000, None, REQUIRED),),
        'extract_fenced_code_blocks': (('markdown', 'string', 1000000, None, REQUIRED), ('language', 'string', 200, None, None)),
        'html_table_to_records': (('html_text', 'string', 1000000, None, REQUIRED), ('table_index', 'integer', None, None, 0)),
        'extract_html_links': (('html_text', 'string', 1000000, None, REQUIRED), ('base_url', 'string', 10000, None, None)),
        # A.29 text_extraction
        'extract_urls': (('text', 'string', 1000000, None, REQUIRED),),
        'extract_email_addresses': (('text', 'string', 1000000, None, REQUIRED),),
        'extract_numbers': (('text', 'string', 1000000, None, REQUIRED),),
        'extract_dates': (('text', 'string', 1000000, None, REQUIRED), ('day_first', 'boolean', None, None, False)),
        'extract_ip_addresses': (('text', 'string', 1000000, None, REQUIRED),),
        'extract_money_amounts': (('text', 'string', 1000000, None, REQUIRED),),
        'extract_key_value_pairs': (('text', 'string', 1000000, None, REQUIRED), ('separator', 'enum:KeyValueSeparator', None, None, 'auto')),
        'extract_sentences': (('text', 'string', 1000000, None, REQUIRED), ('contains', 'string', 10000, None, None)),
        # A.30 code_analysis
        'verify_python_syntax': (('source', 'string', 200000, None, REQUIRED),),
        'list_python_functions': (('source', 'string', 200000, None, REQUIRED),),
        'list_python_classes': (('source', 'string', 200000, None, REQUIRED),),
        'list_python_imports': (('source', 'string', 200000, None, REQUIRED),),
        'count_lines_of_code': (('source', 'string', 200000, None, REQUIRED), ('language', 'enum:CodeLanguage', None, None, 'python')),
        'get_python_function_signature': (('source', 'string', 200000, None, REQUIRED), ('name', 'string', 200, None, REQUIRED)),
        'find_python_name_usages': (('source', 'string', 200000, None, REQUIRED), ('name', 'string', 200, None, REQUIRED)),
        'python_literal_to_json': (('literal', 'string', 200000, None, REQUIRED),),
        'shell_split_command': (('command', 'string', 100000, None, REQUIRED),),
        'shell_quote_arguments': (('arguments', 'array', 10000, 10000, REQUIRED),),
        # A.31 network_addresses
        'verify_ip_address': (('address', 'string', 200, None, REQUIRED),),
        'cidr_network_details': (('cidr', 'string', 200, None, REQUIRED), ('strict', 'boolean', None, None, False)),
        'ip_in_networks': (('address', 'string', 200, None, REQUIRED), ('networks', 'array', 10000, 200, REQUIRED)),
        'split_cidr_into_subnets': (('cidr', 'string', 200, None, REQUIRED), ('new_prefix_length', 'integer', None, None, REQUIRED)),
        'ip_range_to_cidrs': (('first_address', 'string', 200, None, REQUIRED), ('last_address', 'string', 200, None, REQUIRED)),
        'classify_ip_address': (('address', 'string', 200, None, REQUIRED),),
        'convert_ip_address_integer': (('value', 'string', 200, None, REQUIRED), ('version', 'enum:IpVersion', None, None, 'ipv4')),
        'convert_ipv4_netmask': (('value', 'string', 200, None, REQUIRED),),
    }
)
