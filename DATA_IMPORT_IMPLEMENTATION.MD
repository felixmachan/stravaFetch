# DATA IMPORT IMPLEMENTATION PLAN (Strava Summary + Detail + Streams)

## 1. Cel es hatokor

Cel: a Strava import ugy mukodjon, hogy az activity-k teljes adata (summary + detail + streams) gyorsan bekeruljon, es a user az oldalon mar teljes metrikakkal lassa az edzeseit (achievement, power, cadence, effort adatok).

Fokusz:
- `GET /athlete/activities` (summary lista)
- `GET /activities/{id}` (reszletes activity)
- `GET /activities/{id}/streams` (idoalapu meresi adatok)
- regisztracios import date-hatarral
- onboarding allapotkezeles (elso 10 legfrissebb teljesen kesz)

Nem-cel (elso korben):
- segment leaderboard kulon UI
- teljes AI feature-engineering ujratervezes

## 2. Frissitett uzleti elv (a te pontositasod alapjan)

Fontos szabalyok:
1. Ha pollolasnal uj activity jon, akkor **azonnal** menjen ra detail + streams lekeres is.
2. Egy activity-t normal esetben **egyszer** toltsunk fel teljesen; utana ne frissitgessuk periodikusan.
3. A user mire belep, lehetoleg mar teljes adatot lasson.
4. Regisztraciokor az onboarding befejezes feltetele: a **legfrissebb 10 activity** teljesen be van toltve (summary+detail+streams).
5. Regisztracios importnal ne fix utolso 30 legyen, hanem legyen egy `legkorabbi import datum` input.

Technikai megjegyzes:
- Idempotencia itt azt jelenti, hogy ha ugyanarra az activity-re megis ujra lefut a folyamat (pl. timeout, retry), nem keletkezik duplikalt sor. Ez csak vedohalo, nem periodikus refresh-strategia.

## 3. Jelenlegi allapot (repo alapjan)

Backend:
- `sync_now_for_user` jelenleg max 30 summary activity-t huz (`core/tasks.py`).
- `sync_streams_for_activity` letezik, de csak reszleges detail+stream mezoket ment.
- `Activity.raw_payload` vegyes tarolo.
- `ActivityStream.raw_streams` JSON tarolo.

Frontend:
- Activity lista: alap summary statok.
- Activity detail: map + HR/elevation/pace/splits.
- Achievement/power/cadence/detailed effort UI hianyzik.

## 4. Cel architektura (egyszeri teljes feltoltes uj activity-re)

### 4.1 Poll/import folyamat

1. `GET /athlete/activities` lista lehuzasa (paginggel).
2. Minden activity summary upsert.
3. Ha activity uj (vagy hianyos) -> azonnal detail lekeres (`/activities/{id}`).
4. Ugyanerre az activity-re azonnal streams lekeres (`/activities/{id}/streams`).
5. Activity allapot `fully_synced=true`, ha summary+detail+streams sikeres.

### 4.2 Nincs folyamatos periodikus refetch

- Nem vezetunk be altalanos “mindig frissits mindent” mechanizmust.
- On-demand ujrasync csak opcionisan (debug/admin endpoint), nem normal user flow.

## 5. Regisztracios import bovites (uj kovetelmeny)

## 5.1 Onboarding input

UI mezõ:
- `import_from_date` (datum input, pl. `2024-01-01`)

Viselkedes:
- Ha user kitolti, akkor csak az ettol a datumtol ujabb/egyenlo activity-ket importaljuk.
- Ha nincs kitoltve, backend default (pl. 12 honap) vagy rendszer alapertelmezett.

API/Backend valtozas:
- onboarding/regisztracios endpoint fogadja az `import_from_date` mezot.
- Ervenyesites: ISO datum, nem lehet jovo datum.

### 5.2 Onboarding completion logika

Onboarding csak akkor legyen `full_sync_complete=true`, ha:
- a legfrissebb 10 activity (amennyi elerheto, max 10) `fully_synced=true`.

Javasolt mezo az onboarding statuszban:
- `recent_10_total`
- `recent_10_fully_synced`
- `ready` (`recent_10_fully_synced == recent_10_total`)

## 6. DB schema valtozasok

### 6.1 Activity modell bovites

Uj oszlopok:
- `sport_type` (CharField)
- `start_date_local` (DateTimeField null=True)
- `timezone_name` (CharField)
- `average_cadence` (FloatField null=True)
- `average_watts` (FloatField null=True)
- `weighted_average_watts` (FloatField null=True)
- `max_watts` (FloatField null=True)
- `kilojoules` (FloatField null=True)
- `description` (TextField blank=True)
- `device_name` (CharField)
- `trainer` (BooleanField default=False)
- `commute` (BooleanField default=False)
- `manual` (BooleanField default=False)
- `average_temp` (FloatField null=True)
- `elev_high` / `elev_low` (FloatField null=True)
- `achievement_count` (IntegerField default=0)
- `kudos_count` / `comment_count` (IntegerField default=0)
- `gear_id` (CharField)
- `detail_synced_at` (DateTimeField null=True)
- `streams_synced_at` (DateTimeField null=True)
- `fully_synced` (BooleanField default=False)
- `sync_error` (CharField/TextField)

Megjegyzes:
- `best_efforts`, `segment_efforts`, `splits_*` mehet `raw_payload` ala strukturaltan.

### 6.2 ActivityStream modell bovites

Uj flag-ek:
- `has_power`
- `has_temp`
- `has_velocity`
- `has_grade`
- `has_moving`
- `sample_count` (Integer)

## 7. Strava API mapping reszletesen

### 7.1 Summary (`/athlete/activities`)

Mentendo uj summary mezok:
- `type`, `sport_type`, `start_date`, `start_date_local`, `timezone`
- `distance`, `moving_time`, `elapsed_time`, `total_elevation_gain`
- `average_speed`, `max_speed`
- `average_heartrate`, `max_heartrate`
- `average_cadence`, `average_watts`, `weighted_average_watts`
- `suffer_score`, `kudos_count`, `comment_count`, `achievement_count`
- `map.summary_polyline`, `device_name`, `trainer`, `commute`, `manual`

### 7.2 Detail (`/activities/{id}`)

Mentendo detail mezok:
- `description`, `calories`, `gear_id`
- `splits_standard`, `splits_metric`
- `best_efforts`, `segment_efforts`
- `average_temp`, `elev_high`, `elev_low`
- `average_cadence`, `average_heartrate`, `max_heartrate`
- `average_watts`, `max_watts`, `kilojoules`

### 7.3 Streams (`/activities/{id}/streams`)

Keys:
- `time,latlng,distance,altitude,velocity_smooth,heartrate,cadence,watts,temp,moving,grade_smooth`

Tarolas:
- `ActivityStream.raw_streams` JSON
- `has_*` flag-ek + `sample_count`

## 8. Import pipeline implementacios terv

### 8.1 `sync_now_for_user` atalakitas

Mostani helyett:
1. lekeri az activity listat paginggel
2. summary upsert minden elemre
3. uj/hianyos activity-kre inline meghivja az `sync_activity_detail_and_streams(...)` fuggvenyt
4. siker eseten `fully_synced=true`
5. onboarding status frissitese (`recent_10_fully_synced`)

### 8.2 Uj service fuggveny

`sync_activity_detail_and_streams(user, activity, token)`:
- detail fetch
- detail mapping mentes
- streams fetch
- streams mapping mentes
- derived metrikak frissites
- `fully_synced` beallitas

### 8.3 Retry csak tranziensekre

- 401: token refresh + egyszeri ujraproba
- 429/timeout: korlatozott retry
- retry celja: egyszeri feltoltes befejezese, nem periodikus adatfrissites

## 9. API valtozasok

### 9.1 GET `/activities`

Bovitett summary mezok + sync allapot:
- `achievement_count`, `kudos_count`, `comment_count`
- `average_watts`, `average_cadence`
- `device_name`, `trainer`, `commute`, `manual`
- `fully_synced`

### 9.2 GET `/activities/{id}`

Bovitett detail response:
- `best_efforts`, `segment_efforts`, `splits_*`
- power/cadence/temp/elevation advanced mezok
- `streams_available`

### 9.3 Onboarding endpoint

Uj input mezok:
- `import_from_date`

Uj output mezok:
- `recent_10_total`
- `recent_10_fully_synced`
- `full_sync_complete`

## 10. Frontend terv

### 10.1 Regisztracio/onboarding

- uj datum input: "Legkorabbi import datum"
- helper text: "Ettol a datumtol importaljuk az edzeseidet"
- validacio: datum formatum + ne legyen jovo datum

### 10.2 Activity lista

- achievement badge
- kudos/comment mini stat
- power/cadence preview
- `fully_synced` status badge

### 10.3 Activity detail

Uj panelek:
- Achievements (best efforts/PR)
- Power (avg/max/weighted + chart)
- Cadence (avg + chart)
- Temp/Grade (ha van stream)

## 11. Teszteles

Unit:
- summary mapping
- detail mapping
- streams mapping
- `fully_synced` allapot beallitasa
- onboarding completion (`recent_10_fully_synced`)

Integration:
- onboarding `import_from_date` filter tenylegesen hat
- uj activity teljesen bekerul egy sync korben
- `/activities/{id}` visszaadja az uj detail adatokat

Frontend:
- onboarding date input validacio
- activity badge/power/cadence render
- hianyzo streamnel stabil fallback

## 12. Sprint bontas (frissitett)

### Sprint 1

1. Schema bovites (`Activity`, `ActivityStream`, onboarding statusz mezok).
2. Summary + detail + streams mapping teljesitese backendben.
3. `fully_synced` allapotbeallitas.

### Sprint 2

1. Onboarding `import_from_date` backend+frontend implementacio.
2. Onboarding completion logika: legfrissebb 10 teljes szinkron.
3. Poll/sync flow stabilizalas (retry, hibalog).

### Sprint 3

1. Activities lista uj mezokkel.
2. Activity detail uj panelek (achievement/power/cadence/temp/grade).
3. Tesztek + QA.

## 13. Minimum elfogadasi kriterium (MVP)

1. Pollolasnal az ujonnan megtalalt activity ugyanabban a sync runban detail+streams adatokkal bekerul.
2. Activity sor `fully_synced=true` sikeres teljes import utan.
3. Onboardingnal beallithato a `legkorabbi import datum`.
4. Onboarding akkor kesz, ha a legfrissebb 10 activity teljesen importalt.
5. UI-ban latszik achievement + power + cadence, ahol adat elerheto.

## 14. Konkret kodteruletek a repoban

Backend:
- `apps/backend/core/models.py`
- `apps/backend/core/migrations/*`
- `apps/backend/core/tasks.py`
- `apps/backend/core/views.py`
- `apps/backend/core/serializers.py`

Frontend:
- `apps/web/src/pages/login-page.tsx` (ha onboarding itt fut)
- `apps/web/src/pages/integrations-page.tsx` vagy onboarding page
- `apps/web/src/lib/analytics.ts`
- `apps/web/src/pages/activities-page.tsx`
- `apps/web/src/pages/activity-detail-page.tsx`

## 15. Kovetkezo konkret implementacios lepes

1. `Activity`/`ActivityStream` migration megiras (`fully_synced` + uj mezo-halmazon).
2. `sync_now_for_user` refactor: summary utan azonnali detail+stream sync uj activity-re.
3. Onboarding API bovites `import_from_date` parammal.
4. Frontenden datum input bekotese es onboarding progress kijelzes (`recent_10_fully_synced`).
