from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models import CharacterFeat, Feature
from app.models.feat_model import Feat, FeatAbilityScoreIncrease


class FeatRepository(BaseRepository[Feat]):
    """
    Feat-specific repository built on :class:`BaseRepository`.

    ``ability_score_increases`` is always part of ``FeatResponse``, so
    it's wired up as ``default_load_options`` rather than re-implemented
    via a hand-rolled ``get_all`` override — same reasoning as
    ``RaceRepository``.
    """

    def __init__(self, db: Session):
        super().__init__(
            Feat,
            db,
            default_load_options=[selectinload(Feat.ability_score_increases)],
            search_fields=["name"],
        )

    def get_by_name(self, name: str) -> Feat | None:
        return self.db.query(Feat).filter(Feat.name == name).first()

    def is_in_use(self, feat_id: int) -> bool:
        """
        Check whether the feat is currently granted to any character
        (character_feats.feat_id) or referenced by a Feature
        (features.feat_id), either of which would block deletion at the
        DB level via ON DELETE RESTRICT/CASCADE respectively.
        """
        granted = self.db.query(CharacterFeat).filter(CharacterFeat.feat_id == feat_id).first() is not None
        referenced = self.db.query(Feature).filter(Feature.feat_id == feat_id).first() is not None
        return granted or referenced

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
