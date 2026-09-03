"""Bounded, relation-aware graph expansion independent of storage technology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .interfaces import AcademicGraphRepository
from .models import Entity, GraphPath, Relationship


@dataclass(frozen=True, slots=True)
class TraversalConfig:
    max_hops: int = 2
    max_entities: int = 50
    max_relationships: int = 100
    max_neighbors_per_node: int = 20
    minimum_relationship_confidence: float = 0.5
    allowed_relation_types: tuple[str, ...] = (
        "AUTHORED",
        "AFFILIATED_WITH",
        "ABOUT",
        "CITES",
    )

    def __post_init__(self) -> None:
        if self.max_hops < 0:
            raise ValueError("max_hops cannot be negative")
        if self.max_entities <= 0 or self.max_relationships <= 0:
            raise ValueError("Graph budgets must be positive")
        if self.max_neighbors_per_node <= 0:
            raise ValueError("max_neighbors_per_node must be positive")
        if not 0.0 <= self.minimum_relationship_confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    entities: tuple[Entity, ...]
    relationships: tuple[Relationship, ...]
    paths: Mapping[str, GraphPath]
    truncated: bool


class BoundedGraphExpander:
    def expand(
        self,
        repository: AcademicGraphRepository,
        seed_ids: Sequence[str],
        config: TraversalConfig,
    ) -> ExpansionResult:
        unique_seeds = tuple(dict.fromkeys(seed_ids))
        seed_entities = repository.get_entities(unique_seeds[: config.max_entities])
        entity_by_id = {entity.id: entity for entity in seed_entities}
        paths: dict[str, GraphPath] = {
            entity.id: GraphPath(seed_id=entity.id, target_id=entity.id, relationship_ids=())
            for entity in seed_entities
        }
        selected_relationships: dict[str, Relationship] = {}
        frontier = [entity.id for entity in seed_entities]
        truncated = len(unique_seeds) > len(seed_entities)

        for _hop in range(config.max_hops):
            next_frontier: list[str] = []
            for current_id in frontier:
                edges = sorted(
                    repository.get_relationships(
                        (current_id,),
                        relation_types=config.allowed_relation_types,
                    ),
                    key=lambda item: item.id,
                )
                neighbor_count = 0
                for edge in edges:
                    if edge.confidence < config.minimum_relationship_confidence:
                        continue
                    other_id = edge.target_id if edge.source_id == current_id else edge.source_id
                    other_entities = repository.get_entities((other_id,))
                    if not other_entities:
                        continue
                    neighbor_count += 1
                    if neighbor_count > config.max_neighbors_per_node:
                        truncated = True
                        break
                    if edge.id not in selected_relationships:
                        if len(selected_relationships) >= config.max_relationships:
                            truncated = True
                            continue
                        selected_relationships[edge.id] = edge
                    if other_id in entity_by_id:
                        continue
                    if len(entity_by_id) >= config.max_entities:
                        truncated = True
                        continue
                    other = other_entities[0]
                    entity_by_id[other_id] = other
                    previous = paths[current_id]
                    paths[other_id] = GraphPath(
                        seed_id=previous.seed_id,
                        target_id=other_id,
                        relationship_ids=(*previous.relationship_ids, edge.id),
                    )
                    next_frontier.append(other_id)
            frontier = list(dict.fromkeys(next_frontier))
            if not frontier:
                break

        return ExpansionResult(
            entities=tuple(entity_by_id.values()),
            relationships=tuple(selected_relationships.values()),
            paths=paths,
            truncated=truncated,
        )

