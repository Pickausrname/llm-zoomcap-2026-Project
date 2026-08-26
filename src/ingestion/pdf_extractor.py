"""
First-page field extraction for MOSFET datasheet PDFs.

Adapts the extraction guidance in ``skills/datasheet-1.0.0/SKILL.md`` to
this application's narrower, structured goal (spec.md section 8.3-8.4):
pull exactly six data points out of **page 1 only** of a MOSFET
datasheet. Extraction is defensive end-to-end -- a missing section, an
unreadable PDF, or a completely unrecognized layout degrades to empty
fields instead of raising, so a single malformed datasheet never aborts
an ingestion run (spec.md section 8.5).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Final, TypedDict

import fitz	 # PyMuPDF

logger = logging.getLogger(__name__)

__all__ = ["ExtractedFields", "extract_first_page_fields"]


class ExtractedFields(TypedDict):
	"""The six extracted fields plus the derived `search_text` (spec.md section 8.4)."""

	component_type: str
	manufacturer_name: str
	part_number: str
	descriptions: str
	features: str
	applications: str
	search_text: str


_EMPTY_FIELDS: Final[ExtractedFields] = {
	"component_type": "",
	"manufacturer_name": "",
	"part_number": "",
	"descriptions": "",
	"features": "",
	"applications": "",
	"search_text": "",
}

# Section headings as they typically appear (case-insensitive, colon optional)
# on MOSFET datasheet cover pages. Each canonical field maps to the heading
# variants that may introduce it.
_SECTION_HEADINGS: Final[dict[str, tuple[str, ...]]] = {
	"descriptions": ("description", "general description", "product description"),
	"features": ("features", "key features"),
	"applications": ("applications", "typical applications"),
}

# Union of every heading variant, used to detect where a section ends
# (i.e. the next heading starts), regardless of which field it belongs to.
_ALL_HEADINGS: Final[set[str]] = {
	heading for variants in _SECTION_HEADINGS.values() for heading in variants
}

_COMPONENT_TYPE_PATTERNS: Final[tuple[str, ...]] = (
	r"N-Channel(?:\s+Enhancement\s+Mode)?\s+MOSFET",
	r"P-Channel(?:\s+Enhancement\s+Mode)?\s+MOSFET",
	r"Power\s+MOSFET",
	r"MOSFET",
)

# Manufacturers commonly seen on MOSFET datasheet cover pages. Best-effort
# lookup, not an exhaustive registry -- unmatched names default to "".
_KNOWN_MANUFACTURERS: Final[tuple[str, ...]] = (
	"Infineon",
	"ON Semiconductor",
	"onsemi",
	"Vishay",
	"Toshiba",
	"STMicroelectronics",
	"Nexperia",
	"Alpha & Omega Semiconductor",
	"Diodes Incorporated",
	"Renesas",
	"ROHM",
	"Fairchild Semiconductor",
	"IXYS",
	"Littelfuse",
	"Texas Instruments",
	"Microchip",
	"NXP",
)

# Candidate part-number token: 4-20 chars of letters/digits/dashes,
# containing at least one letter and one digit (rules out plain words
# like "MOSFET" or "FEATURES").
_PART_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
	r"\b(?=[A-Z0-9-]{4,20}\b)(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*[0-9])[A-Z0-9-]{4,20}\b"
)

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def _clean_text(text: str) -> str:
	"""Replace newlines with spaces and collapse whitespace runs, then strip."""
	return _WHITESPACE_RE.sub(" ", text.replace("\n", " ")).strip()


def _extract_section(lines: list[str], headings: tuple[str, ...]) -> str:
	"""
	Return the text following the first line matching one of `headings`,
	stopping at the next line that matches any known section heading.
	"""
	for idx, line in enumerate(lines):
		normalized = line.strip().strip(":").lower()
		if normalized not in headings:
			continue
		captured: list[str] = []
		for later_line in lines[idx + 1 :]:
			later_normalized = later_line.strip().strip(":").lower()
			if later_normalized in _ALL_HEADINGS:
				break
			if later_normalized:
				captured.append(later_line)
		return " ".join(captured)
	return ""


def _extract_component_type(raw_text: str) -> str:
	"""Best-effort component type (e.g. "N-Channel MOSFET") via regex over the page text."""
	for pattern in _COMPONENT_TYPE_PATTERNS:
		match = re.search(pattern, raw_text, flags=re.IGNORECASE)
		if match:
			return match.group(0)
	return ""


def _extract_manufacturer(raw_text: str) -> str:
	"""Best-effort manufacturer name via lookup against `_KNOWN_MANUFACTURERS`."""
	for name in _KNOWN_MANUFACTURERS:
		if re.search(re.escape(name), raw_text, flags=re.IGNORECASE):
			return name
	return ""


def _extract_part_number(lines: list[str]) -> str:
	"""Best-effort part number: scan every line of the page for a plausible token."""
	for line in lines:
		match = _PART_NUMBER_RE.search(line.strip())
		if match:
			return match.group(0)
	return ""


def extract_first_page_fields(pdf_path: Path) -> ExtractedFields:
	"""
	Extract the six MOSFET datasheet fields from **page 1 only** of `pdf_path`.

	Never raises: any failure to open the file, read the first page, or
	locate a given field results in that field (or the whole record)
	defaulting to an empty string, so ingestion can continue past a
	single bad datasheet (spec.md section 8.5).

	Args:
		pdf_path: Path to the source PDF datasheet.

	Returns:
		An `ExtractedFields` dict. `search_text` is the space-joined
		concatenation of whichever of `descriptions`, `features`, and
		`applications` were actually found (spec.md section 8.4).
	"""
	try:
		doc = fitz.open(pdf_path)
	except Exception:
		logger.warning("Failed to open PDF %s; skipping.", pdf_path, exc_info=True)
		return dict(_EMPTY_FIELDS)

	try:
		if doc.page_count == 0:
			logger.warning("PDF %s has no pages; skipping.", pdf_path)
			return dict(_EMPTY_FIELDS)
		page = doc[0]  # STRICT: first page only (spec.md section 8.3)
		raw_text = page.get_text()
	except Exception:
		logger.warning("Failed to read first page of %s; skipping.", pdf_path, exc_info=True)
		return dict(_EMPTY_FIELDS)
	finally:
		doc.close()

	if not raw_text or not raw_text.strip():
		logger.warning("First page of %s produced no extractable text.", pdf_path)
		return dict(_EMPTY_FIELDS)

	lines = raw_text.splitlines()

	section_fields: dict[str, str] = {}
	for field_name, headings in _SECTION_HEADINGS.items():
		section_text = _extract_section(lines, headings)
		if not section_text:
			logger.warning(
				"Section '%s' not found in %s; leaving it blank.", field_name, pdf_path.name
			)
		section_fields[field_name] = _clean_text(section_text)

	component_type = _clean_text(_extract_component_type(raw_text))
	manufacturer_name = _clean_text(_extract_manufacturer(raw_text))
	part_number = _clean_text(_extract_part_number(lines))

	if not component_type:
		logger.warning("component_type not found in %s; defaulting to \"\".", pdf_path.name)
	if not manufacturer_name:
		logger.warning("manufacturer_name not found in %s; defaulting to \"\".", pdf_path.name)
	if not part_number:
		logger.warning("part_number not found in %s; defaulting to \"\".", pdf_path.name)

	# Graceful concatenation: only join sections that were actually found (spec.md section 8.5).
	search_text = " ".join(
		part
		for part in (
			section_fields["descriptions"],
			section_fields["features"],
			section_fields["applications"],
		)
		if part
	)

	return {
		"component_type": component_type,
		"manufacturer_name": manufacturer_name,
		"part_number": part_number,
		"descriptions": section_fields["descriptions"],
		"features": section_fields["features"],
		"applications": section_fields["applications"],
		"search_text": search_text,
	}
