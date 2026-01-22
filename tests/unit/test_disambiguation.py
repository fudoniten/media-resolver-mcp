"""Unit tests for disambiguation service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from media_resolver.disambiguation.service import DisambiguationService
from media_resolver.models import MediaCandidate, MediaKind


@pytest.mark.asyncio
class TestDisambiguationService:
    """Tests for DisambiguationService."""

    async def test_disambiguate_single_candidate(self):
        """Test disambiguation with single candidate returns immediately."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        candidate = MediaCandidate(id="test:1", kind=MediaKind.TRACK, title="Test Track", score=1.0)

        ranked, interaction = await service.disambiguate("test", [candidate])

        assert len(ranked) == 1
        assert interaction is None  # No LLM call needed
        mock_llm.ainvoke.assert_not_called()

    async def test_disambiguate_empty_candidates(self):
        """Test disambiguation with no candidates."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        ranked, interaction = await service.disambiguate("test", [])

        assert len(ranked) == 0
        assert interaction is None

    async def test_disambiguate_multiple_candidates(self):
        """Test disambiguation with multiple candidates."""
        mock_llm = AsyncMock()

        # Mock LLM response
        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {
                "reasoning": "Candidate 1 is the best match because it's an exact match",
                "ranked_indices": [1, 0, 2],
                "confidence": "high",
            }
        )
        llm_response.response_metadata = {"usage": {"input_tokens": 150, "output_tokens": 50}}

        mock_llm.ainvoke.return_value = llm_response
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A", score=0.8),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B", score=0.9),
            MediaCandidate(id="2", kind=MediaKind.TRACK, title="Track C", score=0.7),
        ]

        ranked, interaction = await service.disambiguate("track", candidates, top_k=2)

        assert len(ranked) == 2
        # Should be reordered per LLM response: [1, 0, 2]
        assert ranked[0].id == "1"  # Track B
        assert ranked[1].id == "0"  # Track A

        # Check interaction
        assert interaction is not None
        assert interaction.reasoning == "Candidate 1 is the best match because it's an exact match"
        assert interaction.tokens["prompt"] == 150
        assert interaction.tokens["completion"] == 50
        assert interaction.latency_ms > 0

    async def test_disambiguate_with_markdown_json(self):
        """Test parsing LLM response with markdown code blocks."""
        mock_llm = AsyncMock()

        llm_response = MagicMock()
        llm_response.content = """```json
{
  "reasoning": "Test reasoning",
  "ranked_indices": [0, 1],
  "confidence": "high"
}
```"""
        llm_response.response_metadata = {"usage": {}}

        mock_llm.ainvoke.return_value = llm_response
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
        ]

        ranked, interaction = await service.disambiguate("test", candidates)

        assert len(ranked) == 1
        assert ranked[0].id == "0"
        assert interaction.reasoning == "Test reasoning"

    async def test_disambiguate_parse_error_fallback(self):
        """Test fallback to original order on parse error."""
        mock_llm = AsyncMock()

        llm_response = MagicMock()
        llm_response.content = "This is not valid JSON"
        llm_response.response_metadata = {}

        mock_llm.ainvoke.return_value = llm_response
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
        ]

        ranked, interaction = await service.disambiguate("test", candidates, top_k=2)

        # Should fall back to original order
        assert len(ranked) == 2
        assert ranked[0].id == "0"
        assert ranked[1].id == "1"

    async def test_disambiguate_llm_exception(self):
        """Test handling LLM exceptions."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = Exception("LLM API error")

        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
        ]

        # Should not raise, should return original order
        ranked, interaction = await service.disambiguate("test", candidates)

        assert len(ranked) == 1  # top_k defaults to 1
        assert interaction is None

    async def test_should_clarify_few_candidates(self):
        """Test should_clarify with few candidates."""
        mock_llm = AsyncMock()

        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {"reasoning": "Test", "ranked_indices": [0, 1], "confidence": "high"}
        )
        llm_response.response_metadata = {}

        mock_llm.ainvoke.return_value = llm_response
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
        ]

        should_clarify, question = await service.should_clarify("test", candidates)

        assert should_clarify is False
        assert question is None

    async def test_should_clarify_many_candidates(self):
        """Test should_clarify with many similar candidates."""
        mock_llm = AsyncMock()

        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {
                "reasoning": "Multiple good matches",
                "ranked_indices": [0, 1, 2],
                "confidence": "medium",
            }
        )
        llm_response.response_metadata = {}

        mock_llm.ainvoke.return_value = llm_response
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Smith - Song A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Smith - Song B"),
            MediaCandidate(id="2", kind=MediaKind.TRACK, title="Smith - Song C"),
        ]

        should_clarify, question = await service.should_clarify("smith", candidates, threshold=3)

        assert should_clarify is True
        assert question is not None
        assert "smith" in question.lower()
        assert "Smith - Song A" in question


class TestDisambiguationPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_system_prompt_basic(self):
        """Test building basic system prompt."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        prompt = service._build_system_prompt()

        assert "music and podcast recommendation" in prompt.lower()
        assert "rank the candidates" in prompt.lower()

    def test_build_system_prompt_with_context(self):
        """Test building system prompt with context."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        context = {"media_type": "music", "user_preference": "rock"}

        prompt = service._build_system_prompt(context)

        assert "media_type" in prompt
        assert "rock" in prompt

    def test_build_user_prompt(self):
        """Test building user prompt with candidates."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(
                id="0",
                kind=MediaKind.TRACK,
                title="Test Track",
                subtitle="Test Artist",
                snippet="From Test Album",
            ),
        ]

        prompt = service._build_user_prompt("test query", candidates, top_k=1)

        assert "test query" in prompt
        assert "Test Track" in prompt
        assert "Test Artist" in prompt
        assert "ranked_indices" in prompt

    def test_parse_llm_response_valid_json(self):
        """Test parsing valid LLM JSON response."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
            MediaCandidate(id="2", kind=MediaKind.TRACK, title="Track C"),
        ]

        response_json = json.dumps(
            {"reasoning": "B is best match", "ranked_indices": [1, 2, 0], "confidence": "high"}
        )

        reasoning, ranked = service._parse_llm_response(response_json, candidates)

        assert reasoning == "B is best match"
        assert len(ranked) == 3
        assert ranked[0].id == "1"  # Track B
        assert ranked[1].id == "2"  # Track C
        assert ranked[2].id == "0"  # Track A

    def test_parse_llm_response_invalid_json(self):
        """Test parsing invalid JSON falls back to original order."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
        ]

        response_text = "This is not JSON"

        reasoning, ranked = service._parse_llm_response(response_text, candidates)

        assert "Failed to parse" in reasoning
        assert len(ranked) == 2
        assert ranked[0].id == "0"  # Original order preserved

    def test_parse_llm_response_out_of_bounds_indices(self):
        """Test parsing with out-of-bounds indices."""
        mock_llm = AsyncMock()
        service = DisambiguationService(llm=mock_llm)

        candidates = [
            MediaCandidate(id="0", kind=MediaKind.TRACK, title="Track A"),
            MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track B"),
        ]

        response_json = json.dumps(
            {
                "reasoning": "Test",
                "ranked_indices": [1, 5, 0, -1],  # 5 and -1 are out of bounds
                "confidence": "low",
            }
        )

        reasoning, ranked = service._parse_llm_response(response_json, candidates)

        # Should only include valid indices
        assert len(ranked) == 2
        assert ranked[0].id == "1"
        assert ranked[1].id == "0"
