# Articles (`app/features/articles/`)

The lore wiki: markdown articles in a tree, with tags, typed relations, embedded images, a review workflow,
version history and change proposals. Mounted at `/api/v1/articles`.

## Layout

```
articles/
├── router.py            # assembles /articles (one include_router per capability)
├── dependencies.py      # Article{Crud,Listing,Tree,Workflow,Tags,Relations,Images,Subtypes,Revisions,Proposals}Dep
├── base.py              # ArticleScopedRepository (id lookups, exists_visible, get_write_state), ArticleScopedService
├── cache.py             # namespaces, article_cache_key, invalidate_articles / _all_articles / _article_trees, TREE_PAYLOAD_FIELDS
├── visibility.py        # visibility_conditions(include_hidden, model) — the non-GM row filter
├── access.py            # ArticleActor: who may edit (author or founder)
├── secrets.py           # :::gm block stripping (Python) + gm_stripped_sql (SQL twin)
├── slug.py              # slugify (RU/UK transliteration)
├── exceptions.py        # article AppErrors (cycle, tree depth, transitions, versions, proposals)
├── schema_validators.py # shared pydantic validator bodies
├── crud/                # create / PATCH / delete / restore revision / detail by id or slug
│   └── writer.py        # ArticleWriter — the single write path for an article's fields
├── listing/             # GET /articles + /search, ArticleFilters
├── tree/                # tree writes (lock, path, cycle check) + children/descendants/ancestors
├── workflow/            # submit / publish / reject / archive / restore
├── tags/                # PUT /{id}/tags
├── relations/           # typed directed graph between articles
├── images/              # uploads embedded in body_markdown (Supabase Storage)
├── revisions/           # version history, diff, three-way merge (merge.py), content hash chain
├── proposals/           # change proposals from non-editors (+ /articles/proposals queue)
└── subtypes/            # GM dictionary refining article_type (location → «таверна»)
```

Every repository extends `ArticleScopedRepository`, so no capability inherits another's queries. Services never
import each other's services except two documented edges: `ArticleCrudService` and `ArticleProposalsService` both
use `crud/writer.py:ArticleWriter`, and `ArticleCrudService` uses `images.service.storage_entity` for cleanup.

## Endpoints

| Method | Path | Access | Capability |
| ------ | ---- | ------ | ---------- |
| GET | `/articles` | open | listing — filters, sort, page or cursor |
| GET | `/articles/search?q=` | open | listing — ranked full-text + typo-tolerant title |
| GET | `/articles/{id}` · `/articles/by-slug/{slug}` | open | crud — full article, masked for non-GMs |
| POST | `/articles` | GM | crud — create a draft |
| PATCH | `/articles/{id}` | author / founder | crud — edit (new version on content change) |
| DELETE | `/articles/{id}` | founder | crud — children detached, images removed |
| GET | `/articles/{id}/children` · `/descendants` · `/ancestors` | open | tree |
| POST | `/articles/{id}/submit` | author / founder | workflow — draft → in_review |
| POST | `/articles/{id}/publish?version=` | founder | workflow — in_review → published |
| POST | `/articles/{id}/reject` · `/archive` · `/restore` | founder | workflow |
| PUT | `/articles/{id}/tags` | GM | tags — full replace |
| GET/POST | `/articles/{id}/relations` | open / GM | relations |
| PATCH/DELETE | `/articles/{id}/relations/{relation_id}` | GM | relations |
| GET/POST/DELETE | `/articles/{id}/images[/{image_id}]` | GM | images |
| GET | `/articles/{id}/revisions[/{version}[/diff]]` | GM | revisions |
| POST | `/articles/{id}/revisions/{version}/restore` | author / founder | crud (via revisions router) |
| … | `/articles/{id}/proposals[...]`, `GET /articles/proposals` | GM | proposals |
| GET/POST/PATCH/DELETE | `/articles/subtypes[/{id}]` | open / GM / founder | subtypes |

## Who sees what

- Non-GM readers (anonymous included) see only `status = published` AND `visibility = public`
  (`visibility.visibility_conditions`). Anything else is **404, never 403**, in every read: detail, lists, tree,
  relations, images.
- `:::gm ... :::` blocks in `body_markdown`, `excerpt` and relation `note` are stripped for non-GMs. An unclosed
  block hides everything to the end. Search uses a tsvector built without GM blocks for non-GMs, so a secret can
  neither match nor appear in a snippet.
- Non-GMs also get `images: []` (images reach them only through `![](url)` in the stripped body), `version: null`,
  and `parent_id: null` when the parent is hidden.

## Read path of `GET /articles/{id}`

1. GM → `ArticleCrudService.get_by_id` (cached, TTL 30 min).
2. Non-GM → `ArticleRepository.get_public_state` — **one live query**: is the article visible, and is its parent?
   A stale cache can therefore never keep a withdrawn article public.
3. Then the same cached payload, masked by `ArticleCrudService._reader_view`.

## Write path

All field writes go through `ArticleWriter.apply_changes(article_id, fields, state, editor_id=, reviewer_id=,
change_note=, guard=)` in one transaction:

1. `guard()` (proposals: close the proposal, lock and check the version);
2. `parent_id` → tree lock, cycle check, `set_path` re-roots the subtree;
3. `title` on a never-published article → new unique slug (retried on a concurrent collision);
4. any content field (`REVISED_FIELDS`) → `version + 1` and an immutable `article_revisions` snapshot
   (editor, reviewer, change note, chained content hash);
5. after COMMIT: drop the article's cached payload; drop `article_trees` only if a field a brief shows changed.

Permissions are checked **before** the writer: `ArticleActor.ensure_can_edit` (author or founder) in
`ArticleCrudService.update_article`, reviewer rights in `ArticleProposalsService`.

Status is never part of an edit: only `ArticleWorkflowService.transition` changes it, with one compare-and-set
UPDATE (`ARTICLE_TRANSITIONS`). `publish` also requires the reviewed `version`.

## Transactions

The service owns the transaction: writes run inside `_atomic()` / `atomic(db)` (repositories only flush),
and cache purges registered inside the block run only after COMMIT (dropped on rollback). Image upload is
the deliberate exception in shape, not in rule: two short transactions around the Storage call, so no connection
is held during the upload.

## Cache

| Namespace | Holds | Purged by |
| --------- | ----- | --------- |
| `articles` | one detail payload per article (`cache.article_cache_key`) | point keys on every write to that article; whole namespace on tag rename, user delete/rename, subtype write, mass delete |
| `article_trees` | children / descendants / ancestors / relations lists, per `(article_id, include_hidden)` | edits touching `TREE_PAYLOAD_FIELDS`, transitions, create, delete, subtype writes; a relation write drops only its two ends' relation keys |
| `article_subtypes` | the subtype dictionary per `article_type` | subtype writes |

Listing and search are not cached (they depend on the reader and on every filter).

## Adding a listing filter

1. a field on `listing/filters.py:ArticleFilters`;
2. its query parameter in `listing/router.py:get_article_filters`;
3. its condition in `ArticleListingRepository._filter_conditions`.

List and search pick it up together.

## Gotchas

- **SQL vs Python GM stripping.** SQL can't track nested `:::` containers, so writes reject a `:::gm` block that
  contains another container, and `gm_stripped_sql` cuts any such legacy block to the end of the text. Keep
  `ARTICLE_GM_BLOCK_SQL_PATTERN` (`constants.py`) equivalent to `secrets._scan` for flat blocks.
- **`noload(Article.author)`** on tree/relation briefs leaves `author=None` on those instances for the rest of the
  session. Fine for GET requests; don't build a full `ArticleResponse` from them in the same session.
- **`article_cache_key`** is built from `BaseService.get_by_id` (same name and signature as the decorated
  `ArticleCrudService.get_by_id`, which can't be imported from `cache.py`). `tests/unit/features/articles/
  test_cache_keys.py` guards the equality.
- **Proposals `populate_existing`.** `close` is a bulk UPDATE; `ArticleProposalRepository.get`/`lock` re-read the
  row so the session doesn't serve the stale status.
- **Tree lock** is one global advisory lock: fine for how rarely lore moves; per-subtree locks if that changes.

## Tests

`tests/integration/features/articles/` — one file per capability plus `test_cache.py` (cache keys and purges),
`test_concurrency.py` (slug, cycle, version and transition races, one session per task) and `test_gm_blocks.py`.
Unit: `tests/unit/features/articles/` (slug, GM scanner, merge, revision diff, schemas, cache keys).
