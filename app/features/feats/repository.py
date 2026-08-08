"""Feat repository: base CRUD plus ASI-choice management and in-use guard."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models import CharacterFeature, Feature
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import Feat, FeatAbilityScoreIncrease


class FeatRepository(BaseRepository[Feat]):
    """
    Feat-specific repository built on :class:`BaseRepository`.

    ``ability_score_increases`` and ``features`` are always part of
    ``FeatResponse``, so they're wired up as ``default_load_options``
    rather than re-implemented via a hand-rolled ``get_all`` override —
    same reasoning as ``RaceRepository``.
    """

    def __init__(self, db: Session):
        super().__init__(
            Feat,
            db,
            default_load_options=[
                selectinload(Feat.ability_score_increases),
                selectinload(Feat.features),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def is_in_use(self, feat_id: int) -> bool:
        """
        Check whether the feat is currently granted to any character
        (``character_feats.feat_id``) or any of its features is currently
        granted to a character (``character_features``), either of which
        blocks deletion.

        Note: a plain ``Feature`` row referencing the feat does NOT block
        deletion anymore — deleting the feat cascades to its features, which
        is exactly how a feat's own benefits are meant to be removed.
        """
        granted = self.db.query(CharacterFeat).filter(CharacterFeat.feat_id == feat_id).first() is not None
        if granted:
            return True

        feature_ids = [row[0] for row in self.db.query(Feature.id).filter(Feature.feat_id == feat_id)]
        if not feature_ids:
            return False
        return self.db.query(CharacterFeature).filter(CharacterFeature.feature_id.in_(feature_ids)).first() is not None

    def set_ability_score_increases(self, feat: Feat, increases: list[dict], *, commit: bool = True) -> Feat:
        """
        Replace all ASI choices for a feat with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a feat + its ASI choices together) defer the commit
        and flush instead, without duplicating this method.
        """

        self.db.query(FeatAbilityScoreIncrease).filter(FeatAbilityScoreIncrease.feat_id == feat.id).delete()

        for item in increases:
            self.db.add(FeatAbilityScoreIncrease(feat_id=feat.id, ability=item["ability"], amount=item["amount"]))

        if commit:
            self.db.commit()
            self.db.refresh(feat)
        else:
            self.db.flush()

        return feat
