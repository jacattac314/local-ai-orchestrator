"""Name normalization for model name matching."""

import re
from typing import ClassVar


class NameNormalizer:
    """
    Normalizes model names for consistent matching across sources.

    Handles:
    - Case normalization
    - Version suffix stripping (v1, v2, etc.)
    - Vendor prefix removal (optional)
    - Common variant normalization (chat, instruct, etc.)
    """

    # Common suffixes to strip
    STRIP_SUFFIXES: ClassVar[list[str]] = [
        r"-v\d+(\.\d+)*$",  # -v1, -v1.0, -v2.1.3
        r"_v\d+(\.\d+)*$",  # _v1, _v1.0
        r"-\d{8}$",  # -20240101 (date stamps)
        r"-\d+b$",  # -7b, -70b (parameter counts)
        r"-\d+B$",  # -7B, -70B
    ]

    # Common variant suffixes to normalize
    VARIANT_MAPPINGS: ClassVar[dict[str, str]] = {
        "-chat": "",
        "-instruct": "",
        "-base": "",
        "-hf": "",
        "-gguf": "",
        "-gptq": "",
        "-awq": "",
        "-fp16": "",
        "-bf16": "",
        "-int8": "",
        "-int4": "",
    }

    # Vendor prefixes that may be stripped
    VENDOR_PREFIXES: ClassVar[list[str]] = [
        "openai/",
        "anthropic/",
        "meta-llama/",
        "mistralai/",
        "google/",
        "microsoft/",
        "huggingface/",
        "meta/",
    ]

    def __init__(
        self,
        strip_version: bool = True,
        strip_vendor: bool = False,
        normalize_variants: bool = True,
        lowercase: bool = True,
    ) -> None:
        """
        Initialize the name normalizer.

        Args:
            strip_version: Remove version suffixes
            strip_vendor: Remove vendor prefixes
            normalize_variants: Normalize common variants (chat, instruct)
            lowercase: Convert to lowercase
        """
        self._strip_version = strip_version
        self._strip_vendor = strip_vendor
        self._normalize_variants = normalize_variants
        self._lowercase = lowercase

    def normalize(self, name: str) -> str:
        """
        Normalize a model name.

        Args:
            name: Original model name

        Returns:
            Normalized model name
        """
        result = name.strip()

        # Lowercase first for consistent matching
        if self._lowercase:
            result = result.lower()

        # Strip vendor prefix
        if self._strip_vendor:
            for prefix in self.VENDOR_PREFIXES:
                prefix_lower = prefix.lower() if self._lowercase else prefix
                if result.startswith(prefix_lower):
                    result = result[len(prefix_lower):]
                    break

        # Normalize variants
        if self._normalize_variants:
            for suffix, replacement in self.VARIANT_MAPPINGS.items():
                suffix_check = suffix.lower() if self._lowercase else suffix
                if result.endswith(suffix_check):
                    result = result[:-len(suffix_check)] + replacement

        # Strip version suffixes
        if self._strip_version:
            for pattern in self.STRIP_SUFFIXES:
                result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        # Clean up any double dashes or trailing dashes
        result = re.sub(r"-+", "-", result)
        result = result.strip("-_")

        return result

    def normalize_for_comparison(self, name: str) -> str:
        """
        Aggressively normalize for comparison purposes.

        Strips all common variations to find base model identity.

        Args:
            name: Original model name

        Returns:
            Heavily normalized name for comparison
        """
        # Start with standard normalization
        result = self.normalize(name)

        # Additional aggressive normalization
        # Remove all version-like patterns
        result = re.sub(r"[-_]?\d+(\.\d+)*[-_]?", "", result)

        # Remove common size indicators
        result = re.sub(r"[-_]?(small|medium|large|xl|xxl)[-_]?", "", result, flags=re.IGNORECASE)

        # Remove common architecture indicators
        result = re.sub(r"[-_]?(moe|dense)[-_]?", "", result, flags=re.IGNORECASE)

        return result.strip("-_")

    def extract_vendor(self, name: str) -> str | None:
        """
        Extract vendor prefix from model name.

        Args:
            name: Model name (e.g., "openai/gpt-4")

        Returns:
            Vendor name or None
        """
        if "/" in name:
            return name.split("/")[0].lower()
        
        # Try to match known vendor prefixes
        name_lower = name.lower()
        for prefix in self.VENDOR_PREFIXES:
            vendor = prefix.rstrip("/").lower()
            if name_lower.startswith(vendor):
                return vendor

        return None

    def extract_base_model(self, name: str) -> str:
        """
        Extract the base model name without vendor.

        Args:
            name: Full model name

        Returns:
            Base model name
        """
        if "/" in name:
            return name.split("/", 1)[1]
        return name
