from __future__ import annotations

import hashlib
from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from difflib import SequenceMatcher

from ..models import NormalizedItem
from .normalize import (
    author_overlap,
    exact_identifiers,
    normalize_text,
    repository_name,
    title_tokens,
)


@dataclass(slots=True, frozen=True)
class LinkEvidence:
    kind: str
    value: str
    score: float


@dataclass(slots=True)
class LinkEdge:
    left_id: str
    right_id: str
    confidence: float
    evidence: list[LinkEvidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "confidence": self.confidence,
            "evidence": [asdict(evidence) for evidence in self.evidence],
        }


@dataclass(slots=True)
class EntityLinkResult:
    generated_at: str
    edges: list[LinkEdge]
    entities: dict[str, list[str]]
    related_items: dict[str, list[str]]

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "generated_at": self.generated_at,
            "links": [edge.to_dict() for edge in self.edges],
            "entities": [
                {"id": entity_id, "items": items}
                for entity_id, items in sorted(self.entities.items())
            ],
            "related_items": {key: value for key, value in sorted(self.related_items.items())},
        }


class EntityLinker:
    def __init__(self, config: dict) -> None:
        self.config = config

    def link(self, items: Iterable[NormalizedItem], *, generated_at: str) -> EntityLinkResult:
        item_list = sorted(items, key=lambda item: item.id)
        by_id = {item.id: item for item in item_list}
        edges: dict[tuple[str, str], LinkEdge] = {}
        self._link_explicit_relations(item_list, by_id, edges)
        self._link_exact_identifiers(item_list, edges)
        self._link_titles(item_list, edges)
        self._link_repositories_to_papers(item_list, edges)
        ordered_edges = sorted(edges.values(), key=lambda edge: (edge.left_id, edge.right_id))
        related = build_related_items(ordered_edges)
        entities = build_entities(by_id, ordered_edges)
        return EntityLinkResult(generated_at, ordered_edges, entities, related)

    def _link_explicit_relations(
        self,
        items: list[NormalizedItem],
        by_id: dict[str, NormalizedItem],
        edges: dict[tuple[str, str], LinkEdge],
    ) -> None:
        for item in items:
            for related_id in item.related_items:
                if related_id in by_id and related_id != item.id:
                    add_edge(
                        edges,
                        item.id,
                        related_id,
                        LinkEvidence("explicit_relation", "source-declared", 1.0),
                    )

    def _link_exact_identifiers(
        self, items: list[NormalizedItem], edges: dict[tuple[str, str], LinkEdge]
    ) -> None:
        index: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for item in items:
            for identifier, origin in exact_identifiers(item, self.config).items():
                index[identifier].append((item.id, origin))

        for identifier, references in index.items():
            unique = sorted(set(references))
            item_ids = sorted({item_id for item_id, _ in unique})
            if len(item_ids) < 2:
                continue
            for left_index, left_id in enumerate(item_ids):
                for right_id in item_ids[left_index + 1 :]:
                    origins = sorted(
                        {origin for item_id, origin in unique if item_id in {left_id, right_id}}
                    )
                    add_edge(
                        edges,
                        left_id,
                        right_id,
                        LinkEvidence(
                            "exact_identifier", f"{identifier} ({','.join(origins)})", 1.0
                        ),
                    )

    def _link_titles(
        self, items: list[NormalizedItem], edges: dict[tuple[str, str], LinkEdge]
    ) -> None:
        papers = [item for item in items if item.kind == "paper"]
        papers_by_id = {item.id: item for item in papers}
        exact_config = self.config["matching"]["exact_title"]
        fuzzy_config = self.config["matching"]["fuzzy_title"]
        normalized_titles = {item.id: normalize_text(item.title) for item in papers}
        exact_index: dict[str, list[NormalizedItem]] = defaultdict(list)
        for item in papers:
            title = normalized_titles[item.id]
            if len(title) >= exact_config["minimum_characters"]:
                exact_index[title].append(item)

        compared: set[tuple[str, str]] = set()
        for title, group in exact_index.items():
            if len(group) < 2:
                continue
            for i, left in enumerate(group):
                for right in group[i + 1 :]:
                    pair = edge_key(left.id, right.id)
                    compared.add(pair)
                    overlap = author_overlap(left.authors, right.authors)
                    if overlap >= exact_config["minimum_author_overlap"]:
                        add_edge(edges, *pair, LinkEvidence("normalized_title", title, 0.98))
                        add_edge(
                            edges, *pair, LinkEvidence("author_overlap", f"{overlap:.3f}", overlap)
                        )

        token_index: dict[str, set[str]] = defaultdict(set)
        token_sets: dict[str, set[str]] = {}
        for item in papers:
            tokens = set(title_tokens(item.title))
            token_sets[item.id] = tokens
            for token in tokens:
                if len(token) >= 3:
                    token_index[token].add(item.id)

        candidates: Counter[tuple[str, str]] = Counter()
        for ids in token_index.values():
            if len(ids) > fuzzy_config["maximum_block_size"]:
                continue
            ordered = sorted(ids)
            for index, left_id in enumerate(ordered):
                for right_id in ordered[index + 1 :]:
                    candidates[(left_id, right_id)] += 1

        for pair, shared_count in candidates.items():
            if pair in compared or shared_count < fuzzy_config["minimum_shared_tokens"]:
                continue
            left = papers_by_id[pair[0]]
            right = papers_by_id[pair[1]]
            similarity = SequenceMatcher(
                None, normalized_titles[left.id], normalized_titles[right.id]
            ).ratio()
            if similarity < fuzzy_config["minimum_similarity"]:
                continue
            overlap = author_overlap(left.authors, right.authors)
            if overlap < fuzzy_config["minimum_author_overlap"]:
                continue
            add_edge(edges, *pair, LinkEvidence("fuzzy_title", f"{similarity:.3f}", similarity))
            add_edge(edges, *pair, LinkEvidence("author_overlap", f"{overlap:.3f}", overlap))

    def _link_repositories_to_papers(
        self, items: list[NormalizedItem], edges: dict[tuple[str, str], LinkEdge]
    ) -> None:
        repository_config = self.config["matching"]["repository_title"]
        generic_names = {
            normalize_text(value).replace(" ", "") for value in repository_config["generic_names"]
        }
        papers = [item for item in items if item.kind == "paper"]
        repositories = [item for item in items if item.kind == "repository"]
        paper_by_id = {item.id: item for item in papers}
        paper_token_index: dict[str, set[str]] = defaultdict(set)
        for paper in papers:
            for token in set(title_tokens(paper.title)):
                paper_token_index[token].add(paper.id)

        for repository in repositories:
            raw_name = repository_name(repository)
            if not raw_name:
                continue
            normalized_name = normalize_text(raw_name)
            compact_name = normalized_name.replace(" ", "")
            if (
                len(compact_name) < repository_config["minimum_name_characters"]
                or compact_name in generic_names
            ):
                continue
            name_tokens = normalized_name.split()
            if not name_tokens:
                continue
            candidate_ids = set(paper_token_index.get(name_tokens[0], set()))
            for token in name_tokens[1:]:
                candidate_ids &= paper_token_index.get(token, set())
            if len(name_tokens) == 1:
                candidate_ids |= paper_token_index.get(compact_name, set())

            for paper_id in sorted(candidate_ids):
                paper = paper_by_id[paper_id]
                if edge_key(repository.id, paper.id) in edges:
                    continue
                paper_title = normalize_text(paper.title)
                paper_tokens = set(paper_title.split())
                phrase_match = normalized_name in paper_title
                compact_token_match = compact_name in paper_tokens
                if not (
                    phrase_match
                    or compact_token_match
                    or all(token in paper_tokens for token in name_tokens)
                ):
                    continue
                topic_overlap = sorted(set(repository.topics) & set(paper.topics))
                if repository_config["require_topic_overlap"] and not topic_overlap:
                    continue
                pair = edge_key(repository.id, paper.id)
                add_edge(edges, *pair, LinkEvidence("repository_name", normalized_name, 0.84))
                if topic_overlap:
                    add_edge(
                        edges, *pair, LinkEvidence("topic_overlap", ",".join(topic_overlap), 0.8)
                    )


def edge_key(left_id: str, right_id: str) -> tuple[str, str]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def add_edge(
    edges: dict[tuple[str, str], LinkEdge], left_id: str, right_id: str, evidence: LinkEvidence
) -> None:
    if left_id == right_id:
        return
    key = edge_key(left_id, right_id)
    edge = edges.setdefault(key, LinkEdge(key[0], key[1], 0.0))
    if evidence not in edge.evidence:
        edge.evidence.append(evidence)
        edge.evidence.sort(key=lambda item: (item.kind, item.value))
    edge.confidence = max(edge.confidence, evidence.score)


def build_related_items(edges: Iterable[LinkEdge]) -> dict[str, list[str]]:
    related: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        related[edge.left_id].add(edge.right_id)
        related[edge.right_id].add(edge.left_id)
    return {item_id: sorted(neighbors) for item_id, neighbors in related.items()}


def build_entities(
    items: dict[str, NormalizedItem], edges: Iterable[LinkEdge]
) -> dict[str, list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.left_id].add(edge.right_id)
        adjacency[edge.right_id].add(edge.left_id)

    entities: dict[str, list[str]] = {}
    visited: set[str] = set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        queue = deque([start])
        component: list[str] = []
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            if current in items:
                component.append(current)
            queue.extend(sorted(adjacency[current] - visited))
        if len(component) < 2:
            continue
        component.sort()
        digest = hashlib.sha256("\n".join(component).encode("utf-8")).hexdigest()[:16]
        entities[f"entity:{digest}"] = component
    return entities


def materialize_related_items(
    items: Iterable[NormalizedItem], result: EntityLinkResult
) -> list[NormalizedItem]:
    materialized: list[NormalizedItem] = []
    for item in items:
        related = sorted(set(item.related_items) | set(result.related_items.get(item.id, [])))
        materialized.append(replace(item, related_items=related))
    return materialized
