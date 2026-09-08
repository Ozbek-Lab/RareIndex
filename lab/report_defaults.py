"""Read TestType report defaults shared by the import commands."""

import re


def parse_report_text_reference(md_text: str) -> dict[str, dict[str, str]]:
    """
    Parse `report_text_field_reference.md` into:
      { "WES": { "positive_report_template": "...", ... }, ... }
    """
    lines = md_text.splitlines()
    parsed: dict[str, dict[str, str]] = {}
    current_test: str | None = None

    key_re = re.compile(r'^`(?P<key>[a-zA-Z0-9_]+)`\s*$')
    section_re = re.compile(r'^##\s+(?P<name>.+)\s*$')
    inline_value_re = re.compile(r'^`(?P<val>[^`]*)`\s*$')

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        sec_m = section_re.match(line)
        if sec_m:
            current_test = sec_m.group("name").strip()
            parsed.setdefault(current_test, {})
            i += 1
            continue

        if current_test is None:
            i += 1
            continue

        key_m = key_re.match(line.strip())
        if not key_m:
            i += 1
            continue

        field_name = key_m.group("key")

        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j >= len(lines):
            raise RuntimeError(f"Unexpected EOF while reading value for {current_test}.{field_name}")

        val_line = lines[j].strip()
        if val_line.startswith("```"):
            j += 1
            content: list[str] = []
            while j < len(lines):
                if lines[j].strip().startswith("```"):
                    break
                content.append(lines[j])
                j += 1
            else:
                raise RuntimeError(f"Missing closing fence for {current_test}.{field_name}")

            value = "\n".join(content).strip("\n")
            parsed[current_test][field_name] = value
            i = j + 1
            continue

        in_m = inline_value_re.match(val_line)
        if in_m:
            parsed[current_test][field_name] = in_m.group("val")
            i = j + 1
            continue

        parsed[current_test][field_name] = val_line
        i = j + 1

    return parsed


def normalize_testtype_report_payload(payload: dict[str, str]) -> dict[str, str]:
    normalized = dict(payload)

    fallback_pairs = (
        ("default_method_text", ("positive_method_text", "negative_method_text")),
        ("default_filtering_text", ("positive_filtering_text", "negative_filtering_text")),
        ("default_limitations_text", ("positive_limitations_text", "negative_limitations_text")),
    )
    for target, candidates in fallback_pairs:
        if target in normalized:
            continue
        for candidate in candidates:
            candidate_value = normalized.get(candidate)
            if candidate_value:
                normalized[target] = candidate_value
                break
        else:
            if any(candidate in normalized for candidate in candidates):
                normalized[target] = ""

    return normalized
