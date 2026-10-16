# Game campaigns (`app/features/campaigns/`)

One GM's table: the characters playing in it, the sessions (schedule, attendance, chronicle), the GM's private
notes and the players' reviews. Mounted at `/api/v1/campaigns` (moderation of reviews at `/api/v1/campaign-reviews`).
The public preset a campaign can be made from lives in `public_campaigns/`.

## Layout

```
campaigns/
├── router.py            # assembles /campaigns and /campaign-reviews (one include_router per capability)
├── dependencies.py      # Campaign{Crud,Characters,Sessions,Notes,Reviews}Dep
├── access.py            # CampaignContext: owner / founder (is_gm), player, outsider — the ONLY permission decision
├── base.py              # player_condition, CampaignAccessMixin (access_row, lock_campaign), CampaignScopedService
├── schemas.py           # bounded field types (CampaignTitle, CampaignText), nested briefs (UserBrief, ...)
├── exceptions.py        # campaign AppErrors (not found, closed, character not free, bad status move, ...)
├── crud/                # create (optionally from a preset), "my campaigns", read, PATCH, archive / restore
├── characters/          # roster, free-character search, add, status change
├── sessions/            # schedule, attendance, chronicle (publish / unpublish), /campaigns/schedule
├── notes/               # GM-private notes
└── reviews/             # campaign + session reviews, founder moderation
```

Every capability service extends `CampaignScopedService` and every repository mixes in `CampaignAccessMixin`, so the
caller's standing is resolved the same way everywhere (`_reader` / `_gm` / `_player`, one `access_row` query).
Writes resolve it inside their `_atomic()` block with `lock=True` (`lock_campaign` first), so the check and the write
see the same state; reads resolve it without a lock.

## Endpoints

| Method | Path | Access | Capability |
| ------ | ---- | ------ | ---------- |
| POST | `/campaigns` | GM role | crud — new campaign, optionally from a `public_campaign_id` |
| GET | `/campaigns?role=gm\|player&include_archived&all_campaigns` | user | crud — "my campaigns" (`all_campaigns`: founder only, not with `role` — 400) |
| GET | `/campaigns/{id}` | GM / player | crud — players get the description without `:::gm` |
| PATCH | `/campaigns/{id}` | GM | crud — closing (`finished`/`abandoned`) retires active characters |
| POST | `/campaigns/{id}/archive` · `/restore` | GM | crud — archive also retires active characters |
| GET | `/campaigns/{id}/characters` | GM / player | characters — the GM also sees `removed` history |
| GET | `/campaigns/{id}/characters/candidates?player=&q=` | GM | characters — free characters, brief card only |
| POST | `/campaigns/{id}/characters` | GM | characters — add a free character (409 if active elsewhere) |
| PATCH | `/campaigns/{id}/characters/{participation_id}` | GM | characters — `active` → `dead`/`retired`/`removed` |
| GET | `/campaigns/schedule?from=&until=&include_cancelled` | user | sessions — dated sessions of my campaigns |
| GET/POST | `/campaigns/{id}/sessions[?status=played]` | GM / player · GM | sessions — `played` = the archive |
| GET/PATCH/DELETE | `/campaigns/{id}/sessions/{session_id}` | GM / player · GM | sessions |
| PUT | `/campaigns/{id}/sessions/{session_id}/attendance` | GM | sessions — who attended (full replace) |
| POST | `/campaigns/{id}/sessions/{session_id}/publish` · `/unpublish` | GM | sessions |
| GET/POST/PATCH/DELETE | `/campaigns/{id}/notes[/{note_id}]` | GM | notes — a player gets 403 |
| GET | `/campaigns/{id}/reviews` | GM / player | reviews |
| PUT/DELETE | `/campaigns/{id}/review` | player, not the GM | reviews — one per player; a hidden one: delete only |
| GET | `/campaigns/{id}/sessions/{session_id}/reviews` | GM / player | reviews — the table sees `visible_to_table` ones |
| PUT/DELETE | `/campaigns/{id}/sessions/{session_id}/review` | player, not the GM | reviews — one per player; 409 until the chronicle is published |
| POST | `/campaign-reviews/{review_id}/hide` · `/unhide` | founder | reviews — moderation |
| POST | `/session-reviews/{review_id}/hide` · `/unhide` | founder | reviews — moderation of session reviews |

"GM" = the campaign's owner or the founder; "player" = has a character in the campaign whose participation isn't
`removed`. Anyone else (other GMs included) gets 404 for everything under `/campaigns/{id}`.

## Rules worth knowing

- **Every list is paged**: `page`/`size` (default 20, at most 100) and the `Page` `{items, total, page, size}`
  envelope, fetched with `core/pagination.fetch_page` — sessions, roster, notes, both review lists, schedule.
- **Roster.** Only the GM adds or changes characters; the player isn't asked and can't leave. A character is
  `ACTIVE` in at most one campaign (`uq_campaign_characters_one_active`, a partial unique index); a lost race is a 409.
  Re-adding after `removed` creates a new participation row (history is kept). Every campaign write locks the
  campaign row (`lock_campaign`), so a character can't land in a campaign that is being closed.
- **Sheet access.** While a character is `ACTIVE` here, the campaign GM manages its sheet: `characters/access.py`
  reads `campaign_characters` directly (`CharacterRepository.is_managed_by`) and never imports this feature.
- **One text, two audiences.** `description_markdown` and `chronicle_markdown` may hold `:::gm` blocks, stripped for
  players with `shared/secrets.strip_gm_blocks`.
- **Sessions = schedule + archive.** Players see every session of their campaign: number, title, status,
  `scheduled_at` and attendance. Only the chronicle waits for publication (`chronicle_markdown: null` for players
  until `published_at` is set). A time sent without an offset is taken as UTC. `GET /campaigns/schedule` lists the
  dated sessions of every non-archived campaign the caller runs or plays in, soonest first (`viewer_role` per row);
  `ix_campaign_sessions_campaign_scheduled` serves it.
- **Attendance** (`campaign_session_attendance`) points at participations, not bare characters, so the archive shows
  who played even after a character died or was removed. Attendees of a whole session list load in one query.
- **Deleting the GM's account** keeps the campaign (`owner_id` → NULL); only the founder acts as its GM afterwards.
- **Reviews** are upserts (`ON CONFLICT DO UPDATE`), so a double-submitted first review can't 409. The campaign's
  own GM never reviews it, even when one of their characters plays there. The founder hides campaign and session
  reviews alike (`hidden_at`; gone from every listing but the founder's); a hidden one can be deleted by its author
  but not edited (409).
- **Time** comes from the services' `clock` attribute (aware UTC by default), so tests can pin `ended_at`,
  `archived_at`, `published_at`, `edited_at` and `hidden_at`. The roster's status rule is the pure
  `characters/service.status_change_allowed` (unit-tested without a database).
- **No cache.** Every read depends on the caller's standing (GM view vs player view), and writes are rare; nothing
  here goes through `app/core/cache`. If a read is ever cached, the key must include the viewer's role.
- Statuses are `native_enum=False` VARCHARs (member NAME), see `app/models/enums.py`.
