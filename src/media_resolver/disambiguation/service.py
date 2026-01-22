"""LLM-powered disambiguation service for media candidates."""

import json
import time
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from media_resolver.config import get_config
from media_resolver.disambiguation.llm_provider import create_llm, get_model_info
from media_resolver.models import LLMInteraction, MediaCandidate

logger = structlog.get_logger()


class DisambiguationService:
    """
    Service for disambiguating and ranking media candidates using LLM.

    Uses LangChain with configurable LLM backend to intelligently rank
    and select the best media candidates based on user intent.
    """

    def __init__(self, llm: BaseChatModel | None = None):
        """
        Initialize disambiguation service.

        Args:
            llm: Optional LangChain chat model. If None, creates from config.
        """
        self.log = logger.bind(component="disambiguation")

        if llm is None:
            config = get_config()
            active_backend = config.llm.get_active_backend()
            if not active_backend:
                raise ValueError(
                    "No LLM backend configured. Please configure at least one backend in config.yaml"
                )
            self.llm = create_llm(active_backend)
            self.model_info = get_model_info(active_backend)
        else:
            self.llm = llm
            self.model_info = {"provider": "custom", "model": str(type(llm).__name__)}

        self.log.info("disambiguation_service_initialized", model_info=self.model_info)

    async def disambiguate(
        self,
        query: str,
        candidates: list[MediaCandidate],
        context: dict[str, Any] | None = None,
        top_k: int = 1,
    ) -> tuple[list[MediaCandidate], LLMInteraction | None]:
        """
        Disambiguate and rank candidates using LLM.

        Args:
            query: Original user query
            candidates: List of candidate media items
            context: Optional additional context (e.g., media type, user preferences)
            top_k: Number of top candidates to return

        Returns:
            Tuple of (ranked candidates, LLM interaction details)
        """
        if not candidates:
            return [], None

        if len(candidates) == 1:
            # No disambiguation needed
            self.log.debug("single_candidate_no_disambiguation")
            return candidates, None

        self.log.info(
            "starting_disambiguation",
            query=query,
            num_candidates=len(candidates),
            top_k=top_k,
        )

        start_time = time.time()

        # Build prompt
        system_prompt = self._build_system_prompt(context)
        user_prompt = self._build_user_prompt(query, candidates, top_k)

        # Create messages
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        try:
            # Call LLM
            response = await self.llm.ainvoke(messages)
            latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            reasoning, ranked_candidates = self._parse_llm_response(response.content, candidates)

            # Extract token usage if available
            tokens = {}
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("usage", {})
                if usage:
                    tokens = {
                        "prompt": usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                        "completion": usage.get("completion_tokens", usage.get("output_tokens", 0)),
                    }

            # Create interaction record
            interaction = LLMInteraction(
                provider=self.model_info["provider"],
                model=self.model_info["model"],
                prompt=f"{system_prompt}\n\n{user_prompt}",
                reasoning=reasoning,
                tokens=tokens,
                latency_ms=latency_ms,
            )

            self.log.info(
                "disambiguation_complete",
                latency_ms=latency_ms,
                tokens=tokens,
                top_candidate=ranked_candidates[0].title if ranked_candidates else None,
            )

            return ranked_candidates[:top_k], interaction

        except Exception as e:
            self.log.error("disambiguation_failed", error=str(e), query=query)
            # Fall back to original order
            return candidates[:top_k], None

    def _build_system_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Build system prompt for disambiguation."""
        base_prompt = """You are an expert music and podcast recommendation assistant. Your job is to analyze user queries and candidate media items, then rank the candidates by relevance to the user's intent.

You should consider:
1. Exact matches vs. partial matches
2. Artist/show name matches
3. Popularity and recency (when applicable)
4. Contextual clues in the query
5. Genre and style preferences

Be decisive - if one candidate is clearly the best match, rank it first with high confidence. If multiple candidates are equally good, explain why and rank them accordingly."""

        if context:
            context_str = "\n\nAdditional context:\n"
            for key, value in context.items():
                context_str += f"- {key}: {value}\n"
            base_prompt += context_str

        return base_prompt

    def _build_user_prompt(self, query: str, candidates: list[MediaCandidate], top_k: int) -> str:
        """Build user prompt with query and candidates."""
        # Format candidates as JSON-like structure
        candidates_data = []
        for i, candidate in enumerate(candidates):
            candidates_data.append(
                {
                    "index": i,
                    "title": candidate.title,
                    "subtitle": candidate.subtitle,
                    "kind": candidate.kind.value,
                    "snippet": candidate.snippet,
                    "published": candidate.published,
                }
            )

        candidates_json = json.dumps(candidates_data, indent=2)

        prompt = f"""User query: "{query}"

Candidates:
{candidates_json}

Please analyze these candidates and:
1. Explain your reasoning about which candidate(s) best match the query
2. Rank the candidates by relevance (best first)
3. Indicate your confidence level

Respond in this JSON format:
{{
  "reasoning": "Your detailed reasoning here",
  "ranked_indices": [2, 0, 1, ...],
  "confidence": "high|medium|low"
}}

The ranked_indices should be the indices from the candidates list, ordered from most to least relevant.
Include up to {min(top_k * 2, len(candidates))} ranked indices."""

        return prompt

    def _parse_llm_response(
        self, response_text: str, candidates: list[MediaCandidate]
    ) -> tuple[str, list[MediaCandidate]]:
        """
        Parse LLM response and reorder candidates.

        Args:
            response_text: Raw LLM response
            candidates: Original candidates list

        Returns:
            Tuple of (reasoning, ranked candidates)
        """
        try:
            # Try to parse as JSON
            # Handle markdown code blocks if present
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            data = json.loads(response_text)

            reasoning = data.get("reasoning", "No reasoning provided")
            ranked_indices = data.get("ranked_indices", [])

            # Reorder candidates
            ranked_candidates = []
            used_indices = set()

            for idx in ranked_indices:
                if 0 <= idx < len(candidates) and idx not in used_indices:
                    ranked_candidates.append(candidates[idx])
                    used_indices.add(idx)

            # Add any remaining candidates
            for idx, candidate in enumerate(candidates):
                if idx not in used_indices:
                    ranked_candidates.append(candidate)

            return reasoning, ranked_candidates

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.log.warning("failed_to_parse_llm_response", error=str(e))
            # Return original order
            return f"Failed to parse LLM response: {e}", candidates

    async def should_clarify(
        self, query: str, candidates: list[MediaCandidate], threshold: int = 3
    ) -> tuple[bool, str | None]:
        """
        Determine if clarification is needed.

        Args:
            query: User query
            candidates: List of candidates
            threshold: Minimum number of similar-quality candidates to trigger clarification

        Returns:
            Tuple of (should_clarify, clarification_question)
        """
        if len(candidates) < 2:
            return False, None

        # Use LLM to assess ambiguity
        ranked, interaction = await self.disambiguate(query, candidates, top_k=threshold)

        if not interaction:
            return False, None

        # Simple heuristic: if we have multiple strong candidates, ask for clarification
        if len(candidates) >= threshold:
            # Generate clarification question
            top_titles = [c.title for c in ranked[:threshold]]
            question = f"I found multiple matches for '{query}'. Did you mean: "
            question += ", ".join(f'"{title}"' for title in top_titles) + "?"

            return True, question

        return False, None
