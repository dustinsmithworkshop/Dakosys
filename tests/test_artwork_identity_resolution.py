from artwork.identity_resolution import (
    resolve_duplicate_tvdb_candidates,
)
from artwork.inventory import (
    ShowInventory,
)
from tv_metadata.models import (
    ShowIdentity,
)


def _inventory(
    rating_key,
    canonical,
    candidates,
):
    return ShowInventory(
        identity=ShowIdentity(
            title=f"Show {rating_key}",
            year=2024,
            library="Anime",
            plex_rating_key=str(
                rating_key
            ),
            tvdb_id=canonical,
            tvdb_id_candidates=tuple(
                candidates
            ),
        ),
        seasons=(),
    )


def _resolved_ids(
    inventories,
):
    return {
        inventory.identity.plex_rating_key:
            inventory.identity.tvdb_id
        for inventory
        in inventories
    }


def test_unique_collision_assignment_is_resolved():
    result = (
        resolve_duplicate_tvdb_candidates(
            (
                _inventory(
                    "a",
                    188551,
                    (
                        188551,
                        436780,
                    ),
                ),
                _inventory(
                    "b",
                    188551,
                    (
                        188551,
                    ),
                ),
            )
        )
    )

    assert _resolved_ids(
        result
    ) == {
        "a": 436780,
        "b": 188551,
    }


def test_symmetric_collision_remains_ambiguous():
    result = (
        resolve_duplicate_tvdb_candidates(
            (
                _inventory(
                    "a",
                    100,
                    (
                        100,
                        200,
                    ),
                ),
                _inventory(
                    "b",
                    100,
                    (
                        100,
                        200,
                    ),
                ),
            )
        )
    )

    assert _resolved_ids(
        result
    ) == {
        "a": 100,
        "b": 100,
    }


def test_collision_without_alternative_remains_unchanged():
    result = (
        resolve_duplicate_tvdb_candidates(
            (
                _inventory(
                    "a",
                    100,
                    (100,),
                ),
                _inventory(
                    "b",
                    100,
                    (100,),
                ),
            )
        )
    )

    assert _resolved_ids(
        result
    ) == {
        "a": 100,
        "b": 100,
    }


def test_non_conflicting_canonical_identity_is_reserved():
    result = (
        resolve_duplicate_tvdb_candidates(
            (
                _inventory(
                    "a",
                    100,
                    (
                        100,
                        200,
                    ),
                ),
                _inventory(
                    "b",
                    100,
                    (100,),
                ),
                _inventory(
                    "c",
                    200,
                    (200,),
                ),
            )
        )
    )

    # 200 already belongs canonically to c, so it cannot be borrowed to
    # manufacture a resolution for the 100 collision.
    assert _resolved_ids(
        result
    ) == {
        "a": 100,
        "b": 100,
        "c": 200,
    }


def test_non_conflicting_item_keeps_first_valid_canonical():
    original = _inventory(
        "a",
        100,
        (
            100,
            200,
        ),
    )

    result = (
        resolve_duplicate_tvdb_candidates(
            (
                original,
            )
        )
    )

    assert result == (
        original,
    )

    assert (
        result[0]
        .identity.tvdb_id
        == 100
    )


def test_independent_unique_collision_components_both_resolve():
    result = (
        resolve_duplicate_tvdb_candidates(
            (
                _inventory(
                    "a",
                    100,
                    (
                        100,
                        101,
                    ),
                ),
                _inventory(
                    "b",
                    100,
                    (100,),
                ),
                _inventory(
                    "c",
                    200,
                    (
                        200,
                        201,
                    ),
                ),
                _inventory(
                    "d",
                    200,
                    (200,),
                ),
            )
        )
    )

    assert _resolved_ids(
        result
    ) == {
        "a": 101,
        "b": 100,
        "c": 201,
        "d": 200,
    }
