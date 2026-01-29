"""Prompt complexity classification for intelligent routing."""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ComplexityLevel(Enum):
    """Prompt complexity levels."""

    SIMPLE = 1  # Basic Q&A, greetings, simple lookups
    MODERATE = 2  # Multi-step reasoning, summarization
    COMPLEX = 3  # Analysis, code generation, creative writing
    EXPERT = 4  # Research, multi-domain, long context


@dataclass
class ComplexityFeatures:
    """Features extracted for complexity classification."""

    token_count: int = 0
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    question_count: int = 0
    code_blocks: int = 0
    technical_terms: int = 0
    reasoning_indicators: int = 0
    multi_step_indicators: int = 0
    domain_count: int = 0


@dataclass
class ComplexityResult:
    """Result of complexity classification."""

    level: ComplexityLevel
    confidence: float
    features: ComplexityFeatures
    suggested_profile_adjustments: dict[str, float] = field(default_factory=dict)

    @property
    def level_name(self) -> str:
        return self.level.name.lower()


class ComplexityClassifier:
    """
    Classifies prompt complexity to optimize model routing.

    Uses heuristic feature extraction to estimate task difficulty
    and suggest routing profile adjustments.
    """

    # Patterns for feature detection
    QUESTION_PATTERNS = [
        r"\?",
        r"^(what|who|where|when|why|how|which|can|could|would|should|is|are|do|does)\b",
    ]

    REASONING_KEYWORDS = [
        "analyze",
        "compare",
        "contrast",
        "evaluate",
        "explain",
        "synthesize",
        "critique",
        "assess",
        "interpret",
        "justify",
    ]

    MULTI_STEP_KEYWORDS = [
        "step by step",
        "first",
        "then",
        "finally",
        "afterwards",
        "next",
        "following",
        "procedure",
        "process",
        "workflow",
    ]

    TECHNICAL_DOMAINS = {
        "programming": ["code", "function", "api", "database", "algorithm", "debug", "compile", "syntax"],
        "science": ["hypothesis", "experiment", "data", "research", "theory", "analysis"],
        "math": ["equation", "calculate", "formula", "probability", "statistics", "derivative"],
        "legal": ["contract", "liability", "compliance", "regulation", "statute"],
        "medical": ["diagnosis", "symptom", "treatment", "patient", "clinical"],
        "finance": ["investment", "portfolio", "roi", "valuation", "market"],
    }

    CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|`[^`]+`")

    def __init__(
        self,
        simple_threshold: int = 50,
        moderate_threshold: int = 200,
        complex_threshold: int = 500,
    ) -> None:
        """
        Initialize classifier with token thresholds.

        Args:
            simple_threshold: Max tokens for SIMPLE
            moderate_threshold: Max tokens for MODERATE
            complex_threshold: Max tokens for COMPLEX
        """
        self._simple_threshold = simple_threshold
        self._moderate_threshold = moderate_threshold
        self._complex_threshold = complex_threshold

    def _count_tokens(self, text: str) -> int:
        """Rough token count (words * 1.3 approximation)."""
        words = len(text.split())
        return int(words * 1.3)

    def _extract_features(self, text: str) -> ComplexityFeatures:
        """Extract classification features from text."""
        text_lower = text.lower()

        # Basic counts
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences)
        token_count = self._count_tokens(text)
        avg_sentence_length = token_count / max(sentence_count, 1)

        # Question detection
        question_count = sum(
            1 for pattern in self.QUESTION_PATTERNS
            for _ in re.finditer(pattern, text_lower, re.MULTILINE | re.IGNORECASE)
        )

        # Code blocks
        code_blocks = len(self.CODE_BLOCK_PATTERN.findall(text))

        # Reasoning indicators
        reasoning_indicators = sum(
            1 for keyword in self.REASONING_KEYWORDS
            if keyword in text_lower
        )

        # Multi-step indicators
        multi_step_indicators = sum(
            1 for keyword in self.MULTI_STEP_KEYWORDS
            if keyword in text_lower
        )

        # Technical terms and domains
        detected_domains = set()
        technical_terms = 0
        for domain, terms in self.TECHNICAL_DOMAINS.items():
            for term in terms:
                if term in text_lower:
                    detected_domains.add(domain)
                    technical_terms += 1

        return ComplexityFeatures(
            token_count=token_count,
            sentence_count=sentence_count,
            avg_sentence_length=avg_sentence_length,
            question_count=question_count,
            code_blocks=code_blocks,
            technical_terms=technical_terms,
            reasoning_indicators=reasoning_indicators,
            multi_step_indicators=multi_step_indicators,
            domain_count=len(detected_domains),
        )

    def _calculate_complexity_score(self, features: ComplexityFeatures) -> float:
        """Calculate weighted complexity score (0-100)."""
        score = 0.0

        # Token count contribution (0-30 points)
        if features.token_count > self._complex_threshold:
            score += 30
        elif features.token_count > self._moderate_threshold:
            score += 20
        elif features.token_count > self._simple_threshold:
            score += 10

        # Reasoning indicators (0-20 points)
        score += min(features.reasoning_indicators * 5, 20)

        # Multi-step indicators (0-15 points)
        score += min(features.multi_step_indicators * 3, 15)

        # Technical depth (0-15 points)
        score += min(features.technical_terms * 2, 10)
        score += min(features.domain_count * 2.5, 5)

        # Code presence (0-10 points)
        score += min(features.code_blocks * 5, 10)

        # Question complexity (0-10 points)
        if features.question_count > 3:
            score += 10
        elif features.question_count > 1:
            score += 5

        return min(score, 100)

    def _score_to_level(self, score: float) -> ComplexityLevel:
        """Convert complexity score to level."""
        if score >= 70:
            return ComplexityLevel.EXPERT
        elif score >= 45:
            return ComplexityLevel.COMPLEX
        elif score >= 20:
            return ComplexityLevel.MODERATE
        else:
            return ComplexityLevel.SIMPLE

    def _get_profile_adjustments(
        self, level: ComplexityLevel
    ) -> dict[str, float]:
        """Get suggested routing profile weight adjustments."""
        adjustments = {
            ComplexityLevel.SIMPLE: {
                "quality_weight": -0.1,  # Lower quality need
                "latency_weight": 0.2,  # Prioritize speed
                "cost_weight": 0.1,  # Cost-conscious
            },
            ComplexityLevel.MODERATE: {
                # Balanced, no adjustments
            },
            ComplexityLevel.COMPLEX: {
                "quality_weight": 0.15,  # Higher quality
                "latency_weight": -0.1,  # Accept slower
            },
            ComplexityLevel.EXPERT: {
                "quality_weight": 0.25,  # Maximum quality
                "latency_weight": -0.15,
                "context_weight": 0.1,  # May need larger context
            },
        }
        return adjustments.get(level, {})

    def classify(self, text: str) -> ComplexityResult:
        """
        Classify prompt complexity.

        Args:
            text: The prompt text to classify

        Returns:
            ComplexityResult with level, confidence, and suggestions
        """
        features = self._extract_features(text)
        score = self._calculate_complexity_score(features)
        level = self._score_to_level(score)

        # Confidence based on feature clarity
        confidence = min(0.5 + (score / 200), 0.95)

        adjustments = self._get_profile_adjustments(level)

        logger.debug(
            f"Classified prompt as {level.name} "
            f"(score={score:.1f}, confidence={confidence:.2f})"
        )

        return ComplexityResult(
            level=level,
            confidence=confidence,
            features=features,
            suggested_profile_adjustments=adjustments,
        )

    def classify_messages(self, messages: list[dict[str, str]]) -> ComplexityResult:
        """
        Classify complexity from a list of chat messages.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts

        Returns:
            ComplexityResult based on combined message content
        """
        # Combine user messages for analysis
        user_content = " ".join(
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "user"
        )
        return self.classify(user_content)


# Default classifier instance
default_complexity_classifier = ComplexityClassifier()
