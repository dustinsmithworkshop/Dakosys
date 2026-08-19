"""Resolve exact Plex TVDB candidate collisions without guessing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace

from artwork.inventory import (
    ShowInventory,
)
from tv_metadata.models import (
    ShowIdentity,
)


def _positive_integer(
    value,
) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _canonical_tvdb_id(
    inventory: ShowInventory,
) -> int | None:
    return _positive_integer(
        getattr(
            inventory.identity,
            "tvdb_id",
            None,
        )
    )


def _tvdb_candidates(
    inventory: ShowInventory,
) -> tuple[int, ...]:
    """Return canonical + exact Plex TVDB candidates, deduplicated."""

    identity = inventory.identity

    values: list[int] = []

    canonical = _positive_integer(
        getattr(
            identity,
            "tvdb_id",
            None,
        )
    )

    if canonical is not None:
        values.append(
            canonical
        )

    for raw_value in (
        getattr(
            identity,
            "tvdb_id_candidates",
            (),
        )
        or ()
    ):
        parsed = _positive_integer(
            raw_value
        )

        if (
            parsed is not None
            and parsed not in values
        ):
            values.append(
                parsed
            )

    return tuple(
        values
    )


def _find_perfect_assignment(
    component: tuple[int, ...],
    candidates: dict[
        int,
        tuple[int, ...],
    ],
    *,
    forbidden: tuple[
        int,
        int,
    ] | None = None,
) -> dict[int, int] | None:
    """Find one injective item -> TVDB assignment for a component."""

    candidate_owner: dict[
        int,
        int,
    ] = {}

    def assign(
        item_index: int,
        seen: set[int],
    ) -> bool:
        for tvdb_id in candidates[
            item_index
        ]:
            if forbidden == (
                item_index,
                tvdb_id,
            ):
                continue

            if tvdb_id in seen:
                continue

            seen.add(
                tvdb_id
            )

            current_owner = (
                candidate_owner.get(
                    tvdb_id
                )
            )

            if (
                current_owner is None
                or assign(
                    current_owner,
                    seen,
                )
            ):
                candidate_owner[
                    tvdb_id
                ] = item_index

                return True

        return False

    ordered = sorted(
        component,
        key=lambda index: (
            len(
                candidates[
                    index
                ]
            ),
            index,
        ),
    )

    for item_index in ordered:
        if not assign(
            item_index,
            set(),
        ):
            return None

    assignment = {
        item_index: tvdb_id
        for (
            tvdb_id,
            item_index,
        ) in candidate_owner.items()
    }

    if (
        len(assignment)
        != len(component)
    ):
        return None

    return assignment


def _unique_perfect_assignment(
    component: tuple[int, ...],
    candidates: dict[
        int,
        tuple[int, ...],
    ],
) -> dict[int, int] | None:
    """Return the assignment only when exactly one perfect match exists."""

    first = _find_perfect_assignment(
        component,
        candidates,
    )

    if first is None:
        return None

    # Any different perfect matching must omit at least one edge from
    # the first matching.  Remove each selected edge in turn; if another
    # perfect matching survives, the component is ambiguous.
    for item_index in sorted(
        first
    ):
        alternative = (
            _find_perfect_assignment(
                component,
                candidates,
                forbidden=(
                    item_index,
                    first[
                        item_index
                    ],
                ),
            )
        )

        if alternative is not None:
            return None

    return first


def _candidate_components(
    collision_indices: set[int],
    candidates: dict[
        int,
        tuple[int, ...],
    ],
) -> tuple[
    tuple[int, ...],
    ...,
]:
    """Build connected collision components through shared TVDB IDs."""

    remaining = set(
        collision_indices
    )

    components: list[
        tuple[int, ...]
    ] = []

    while remaining:
        root = min(
            remaining
        )

        remaining.remove(
            root
        )

        component = {
            root
        }

        pending = [
            root
        ]

        while pending:
            current = pending.pop()

            current_candidates = set(
                candidates[
                    current
                ]
            )

            connected = [
                other
                for other in remaining
                if (
                    current_candidates
                    & set(
                        candidates[
                            other
                        ]
                    )
                )
            ]

            for other in connected:
                remaining.remove(
                    other
                )

                component.add(
                    other
                )

                pending.append(
                    other
                )

        components.append(
            tuple(
                sorted(
                    component
                )
            )
        )

    return tuple(
        components
    )


def _replace_tvdb_identity(
    inventory: ShowInventory,
    *,
    tvdb_id: int,
) -> ShowInventory:
    identity = inventory.identity

    if isinstance(
        identity,
        ShowIdentity,
    ):
        resolved_identity = replace(
            identity,
            tvdb_id=tvdb_id,
        )

    else:
        # Compatibility for identity-like objects used by callers/tests.
        resolved_identity = ShowIdentity(
            title=str(
                getattr(
                    identity,
                    "title",
                )
            ),
            year=getattr(
                identity,
                "year",
                None,
            ),
            library=str(
                getattr(
                    identity,
                    "library",
                )
            ),
            plex_rating_key=str(
                getattr(
                    identity,
                    "plex_rating_key",
                )
            ),
            tmdb_id=getattr(
                identity,
                "tmdb_id",
                None,
            ),
            tvdb_id=tvdb_id,
            imdb_id=getattr(
                identity,
                "imdb_id",
                None,
            ),
            library_roles=tuple(
                getattr(
                    identity,
                    "library_roles",
                    (),
                )
                or ()
            ),
            tmdb_id_candidates=tuple(
                getattr(
                    identity,
                    "tmdb_id_candidates",
                    (),
                )
                or ()
            ),
            tvdb_id_candidates=tuple(
                getattr(
                    identity,
                    "tvdb_id_candidates",
                    (),
                )
                or ()
            ),
            imdb_id_candidates=tuple(
                getattr(
                    identity,
                    "imdb_id_candidates",
                    (),
                )
                or ()
            ),
        )

    return replace(
        inventory,
        identity=resolved_identity,
    )


def resolve_duplicate_tvdb_candidates(
    inventories: Iterable[
        ShowInventory
    ],
) -> tuple[
    ShowInventory,
    ...,
]:
    """Resolve duplicate canonical TVDB IDs only when uniquely provable.

    Normal non-conflicting canonical identities are never changed.

    For items whose canonical TVDB identity already collides:

    - canonical IDs owned by non-conflicting Plex items are reserved;
    - all exact Plex TVDB candidates are considered;
    - collision components are solved independently;
    - a component is rewritten only when exactly one injective assignment
      exists;
    - zero-solution and multi-solution components remain unchanged so
      existing downstream safety checks continue to block rather than
      guess.
    """

    inventory_tuple = tuple(
        inventories
    )

    canonical_ids = tuple(
        _canonical_tvdb_id(
            inventory
        )
        for inventory
        in inventory_tuple
    )

    counts = Counter(
        tvdb_id
        for tvdb_id
        in canonical_ids
        if tvdb_id is not None
    )

    collision_indices = {
        index
        for (
            index,
            tvdb_id,
        ) in enumerate(
            canonical_ids
        )
        if (
            tvdb_id is not None
            and counts[
                tvdb_id
            ] > 1
        )
    }

    if not collision_indices:
        return inventory_tuple

    # Do not steal the canonical identity of a Plex item that is not
    # itself part of a collision.
    reserved_ids = {
        tvdb_id
        for (
            index,
            tvdb_id,
        ) in enumerate(
            canonical_ids
        )
        if (
            index
            not in collision_indices
            and tvdb_id is not None
        )
    }

    candidates = {
        index: tuple(
            tvdb_id
            for tvdb_id
            in _tvdb_candidates(
                inventory_tuple[
                    index
                ]
            )
            if tvdb_id
            not in reserved_ids
        )
        for index
        in collision_indices
    }

    resolved = list(
        inventory_tuple
    )

    for component in (
        _candidate_components(
            collision_indices,
            candidates,
        )
    ):
        assignment = (
            _unique_perfect_assignment(
                component,
                candidates,
            )
        )

        if assignment is None:
            continue

        for (
            index,
            tvdb_id,
        ) in assignment.items():
            if (
                canonical_ids[
                    index
                ]
                == tvdb_id
            ):
                continue

            resolved[
                index
            ] = (
                _replace_tvdb_identity(
                    inventory_tuple[
                        index
                    ],
                    tvdb_id=tvdb_id,
                )
            )

    return tuple(
        resolved
    )
