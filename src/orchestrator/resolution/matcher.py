"""Similarity matching using Levenshtein distance."""

from dataclasses import dataclass


@dataclass
class MatchResult:
    """Result of a similarity match."""

    candidate: str
    """The candidate string that was matched."""

    score: float
    """Similarity score from 0.0 (no match) to 1.0 (exact match)."""

    distance: int
    """Raw Levenshtein edit distance."""

    def __repr__(self) -> str:
        return f"MatchResult({self.candidate!r}, score={self.score:.3f})"


class SimilarityMatcher:
    """
    Similarity matcher using Levenshtein distance.

    Calculates edit distance between strings and normalizes
    to a 0.0-1.0 similarity score.
    """

    def __init__(self, threshold: float = 0.8) -> None:
        """
        Initialize the matcher.

        Args:
            threshold: Minimum similarity score to consider a match
        """
        self._threshold = threshold

    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """
        Calculate Levenshtein edit distance between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Number of edits (insertions, deletions, substitutions)
        """
        if len(s1) < len(s2):
            s1, s2 = s2, s1

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost is 0 if characters match, 1 otherwise
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def similarity_score(self, s1: str, s2: str) -> float:
        """
        Calculate normalized similarity score between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Score from 0.0 (completely different) to 1.0 (identical)
        """
        if s1 == s2:
            return 1.0

        if not s1 or not s2:
            return 0.0

        distance = self.levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))

        # Normalize: 1 - (distance / max_length)
        return 1.0 - (distance / max_len)

    def match(self, query: str, candidate: str) -> MatchResult:
        """
        Check if query matches candidate.

        Args:
            query: String to match
            candidate: Candidate to match against

        Returns:
            MatchResult with score and distance
        """
        distance = self.levenshtein_distance(query, candidate)
        max_len = max(len(query), len(candidate), 1)
        score = 1.0 - (distance / max_len)

        return MatchResult(
            candidate=candidate,
            score=score,
            distance=distance,
        )

    def find_best_match(
        self,
        query: str,
        candidates: list[str],
        min_score: float | None = None,
    ) -> MatchResult | None:
        """
        Find the best matching candidate for a query.

        Args:
            query: String to match
            candidates: List of candidates to search
            min_score: Minimum score threshold (uses instance threshold if None)

        Returns:
            Best match or None if no match above threshold
        """
        if not candidates:
            return None

        threshold = min_score if min_score is not None else self._threshold
        best_match: MatchResult | None = None

        for candidate in candidates:
            result = self.match(query, candidate)
            if result.score >= threshold:
                if best_match is None or result.score > best_match.score:
                    best_match = result

        return best_match

    def find_all_matches(
        self,
        query: str,
        candidates: list[str],
        min_score: float | None = None,
        max_results: int | None = None,
    ) -> list[MatchResult]:
        """
        Find all matching candidates above threshold.

        Args:
            query: String to match
            candidates: List of candidates to search
            min_score: Minimum score threshold
            max_results: Maximum number of results to return

        Returns:
            List of matches sorted by score (highest first)
        """
        threshold = min_score if min_score is not None else self._threshold
        matches: list[MatchResult] = []

        for candidate in candidates:
            result = self.match(query, candidate)
            if result.score >= threshold:
                matches.append(result)

        # Sort by score descending
        matches.sort(key=lambda x: x.score, reverse=True)

        if max_results:
            matches = matches[:max_results]

        return matches

    @property
    def threshold(self) -> float:
        """Get the current match threshold."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        """Set the match threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        self._threshold = value
