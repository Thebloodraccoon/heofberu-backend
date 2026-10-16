# Public campaigns (`app/features/public_campaigns/`)

Presets / announcements: a pitch and a description any GM writes and everyone reads once published, with tags and
GM-only links to knowledge-base articles. Game campaigns made from a preset (`campaigns.public_campaign_id`) feed its
public showcase: the characters whose owners allowed it and the players' reviews. Mounted at
`/api/v1/public-campaigns`.

## Layout

```
public_campaigns/
├── router.py            # assembles /public-campaigns (one include_router per capability)
├── dependencies.py      # PublicCampaign{Crud,Articles,Showcase}Dep
├── base.py              # can_see_unpublished (any GM), edit rights (author / founder), PublicCampaignScoped*
├── schemas.py           # Pitch, list item / response / article-link schemas, MAX_LINKS
├── exceptions.py        # not found, bad status move, ...
├── crud/                # catalog, by id / slug, create, PATCH, publish / unpublish / archive
├── articles/            # GM-only links to knowledge-base articles (full replace)
└── showcase/            # characters + campaign reviews aggregated over every linked game campaign
```

## Endpoints

| Method | Path | Access | Capability |
| ------ | ---- | ------ | ---------- |
| GET | `/public-campaigns?q=&tag_id=&author_id=&status=` | open | crud — catalog; `status` only for GMs |
| GET | `/public-campaigns/{id}` · `/by-slug/{slug}` | open | crud — guests: published only, no `:::gm`, `articles: null` |
| POST | `/public-campaigns` | GM | crud — a draft authored by the caller |
| PATCH | `/public-campaigns/{id}` | author / founder | crud — the slug never changes on rename |
| POST | `/public-campaigns/{id}/publish` · `/unpublish` · `/archive` | author / founder | crud |
| GET | `/public-campaigns/{id}/articles` | GM | articles |
| PUT | `/public-campaigns/{id}/articles` | author / founder | articles — full replace, at most `MAX_LINKS` |
| GET | `/public-campaigns/{id}/characters` | open | showcase — participation not `removed`, visibility not `hidden` |
| GET | `/public-campaigns/{id}/reviews` | open | showcase — reviews of linked campaigns, minus founder-hidden ones |

## Rules worth knowing

- **Visibility.** Everyone sees `PUBLISHED` presets; a draft or an archived one exists only for its author and
  the founder (`can_see_preset`; other GMs get 404 and don't find it in the catalog). Any GM reads the full text of
  what they can see and the article links (`is_gm_reader`); `:::gm` blocks in the description and pitch are
  stripped for everyone else.
- **Linking is open by design.** Any GM may start a game campaign from any published preset; its players' reviews
  and showcased characters then appear on the preset's page — that is the showcase.
- **Copy, then link.** `POST /campaigns` with `public_campaign_id` copies title/description into the game campaign;
  articles stay links. A draft preset can be used only by its author or the founder (400 otherwise).
- **`campaign_count`** in the catalog comes from one grouped subquery over `campaigns` LEFT JOINed to the page
  (not a correlated count per row); the single preset reads its own count.
- **Slugs** come from `shared/slug.py` (`slugify(title, fallback="campaign")`, `-2`, `-3`, ... on collision); a
  concurrent duplicate is a 409 from the unique index.
- **Showcase edge.** `showcase/` reads `characters/visibility` (`concept_columns`, `PublicCharacterConcept`) so the
  showcase row and the public character card can't drift; it shows no campaign names or campaign data.
- **No cache.** The catalog's `campaign_count`, the showcase and the reviews change with game-campaign writes in
  another feature, so they are read live. If caching is ever added, those writes (and character visibility changes)
  must purge it after commit.
