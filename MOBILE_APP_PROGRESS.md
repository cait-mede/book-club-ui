# iOS App Conversion — Progress Notes

Tracking progress on turning book-club-ui into an iOS app. Branch: `claude/book-club-ios-conversion-cezpam`.

## Approach (decided)

- **Mobile**: React Native via Expo.
- **API**: GraphQL layered onto the existing Flask app (Ariadne), additive — the existing Jinja/HTML web app is untouched and keeps working.
- **Auth**: JWT for the mobile client (separate from the existing session-cookie auth used by the web app).
- Full architecture/schema/screen plan lives in this repo's commit history reasoning; the short version is below. (If picking this up in a fresh Claude session, just say "continue the iOS conversion" and point at this file — no need to re-plan from scratch.)

## Done so far

1. **`services.py`** (new) — extracted all external microservice calls (rating/polling/scheduling/invite services + the AI personality service + OpenLibrary search) out of `app.py` into standalone functions. Both the existing Jinja routes and the new GraphQL resolvers call these. No behavior change to the web app.
2. **`graphql_schema.py`** (new) — Ariadne schema-first GraphQL setup. Currently implements:
   - `type User`, `type AuthPayload`
   - `Query.me`
   - `Mutation.signup`, `Mutation.login`
   - JWT issue/verify (`JWT_SECRET` env var, 30-day expiry, `sub` claim must be a string — PyJWT enforces this)
   - `get_context_value(request)` resolves `context.user` from `Authorization: Bearer <token>` header, falling back to the Flask session cookie
3. **`app.py`** — mounts `GET /graphql` (Ariadne's GraphiQL explorer) and `POST /graphql` (query/mutation execution). Everything else in `app.py` is unchanged except calling into `services.py` instead of inlining `requests` calls.
4. **`requirements.txt`** — added `ariadne`, `PyJWT`.
5. Manually smoke-tested via Flask's test client: signup, login, `me` (authed + unauthed), bad-login error path — all working. (Note: Flask-SQLAlchemy resolves the relative `sqlite:///bookclub.db` URI against `instance/bookclub.db`, not repo root — don't be confused if `bookclub.db` at repo root looks empty/missing.)
6. Committed and pushed to `claude/book-club-ios-conversion-cezpam`.

## Not started yet

The React Native/Expo app itself does not exist yet — no `mobile/` directory. Next steps, in order (see full plan reasoning for schema field names and screen breakdown):

1. **Expo app scaffold**: new `mobile/` directory, React Navigation (AuthStack vs AppTabs), Login/Signup screens, `expo-secure-store` for the JWT, `graphql-request` + `@tanstack/react-query` as the GraphQL client (chosen over Apollo/urql — simpler for a first GraphQL project, no normalized-cache complexity needed at this schema size).
2. **Groups**: extend `graphql_schema.py` with `Group`/`Member` types, `myGroups`/`browseGroups`/`group(id)` queries, `createGroup`/`requestToJoinGroup`/`approveMembership` mutations. Then `MyGroupsScreen`, `BrowseGroupsScreen`, `CreateGroupScreen`, `GroupDetailScreen`.
3. **Polls/scheduling/meetings** (biggest remaining stage — touches 3 external services): `Poll`/`Schedule`/`Meeting` types, `dashboard` query, `markBookComplete`. Keep `Group.poll`/`schedule`/`nextMeeting` nullable so one down microservice doesn't null out the whole group (mirrors the try/except tolerance already in `services.py`).
4. **Books/ratings**: `searchBooks`, `myBooks`, `rateBook` + screens.
5. **Personality generator**: `generatePersonality` mutation + Profile screen UI.
6. **Invite flow**: `inviteToGroup` mutation from the app. Email-triggered deep links (`/accept-invite/<token>`, `/approve/<id>`) intentionally stay **web-only** for v1 (Universal Links are a v2 concern) — the one exception is a logged-in group creator approving/declining pending requests in-app via `approveMembership`.

**Explicitly out of scope**: the admin panel (`/admin`, `/admin/switch/<id>`) stays Jinja/session-only, no GraphQL surface for it.

## Known limitations / accepted for v1

- No JWT revocation (logout just clears client-side storage).
- The four external microservices (rating/polling/scheduling/invite) are `localhost`-bound in `services.py`, same as before — fine since only Flask talks to them now, not the phone. But Flask itself needs to be reachable from a physical test device (LAN IP or Expo tunnel) and eventually needs real hosting for TestFlight.
