"""Runtime acceptance policy, separate from the measured geometry and score."""
from .variants import VARIANTS, PART_NAMES


def accept_five_parts(result, profile):
    if profile.get('schema_version') != 2:
        return result
    result['strict_passed'] = result['passed']
    result['acceptance_policy'] = 'five_detected_parts'
    observed = {p['name']: p for p in result['parts'] if p.get('color')}
    minimum_fraction = profile['thresholds']['color_fraction']
    matches = [variant for variant, colors in VARIANTS.items()
               if len(observed) >= 5 and all(
                   part['color'] == dict(zip(PART_NAMES, colors))[name]
                   and part.get('color_fractions', {}).get(part['color'], 0) >= minimum_fraction
                   for name, part in observed.items())]
    # Never resolve missing/ambiguous color evidence using the order as a guess.
    variant = matches[0] if len(matches) == 1 else None
    result['detected_variant'] = variant
    result['passed'] = (result['found_count'] >= 5 and variant is not None
                        and result.get('expected_variant') in (None, variant))
    return result
