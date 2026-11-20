# Flutter app — development conventions

## API calls

- Use **`ApiClient`** (`lib/core/network/api_client.dart`) for all authenticated API traffic.
- Do **not** create standalone `Dio` instances for save/submit flows (they skip save-nonce and the saving overlay).

## Saves & transactions (automatic)

`ApiClient` already provides:

| Feature | Implementation |
|---------|----------------|
| Save-once token | `SaveNonceStorage` + `X-Save-Nonce` header |
| Token refresh from API | `save_nonce` in JSON responses |
| Blocking overlay | `TransactionOverlayController` + `LoadingOverlay` in `main.dart` |

Applied to: **POST**, **PUT**, **PATCH**, **DELETE** (except auth login/refresh/logout).

### Adding a new save screen

1. Add API method on a `*Service` class that uses `_apiClient.dio.post/put/patch/delete`.
2. Call it from a repository/provider.
3. Optionally set `isSubmitting = true` to disable buttons — **do not** add another full-screen save overlay.
4. Handle 409 / `replay_blocked` via `apiErrorMessage` if you show errors to the user.

### Login / session

- `AuthService.login` stores initial `save_nonce`.
- `AuthRepository.logout` clears tokens and save nonce.
- Tenant switch and token refresh also rotate `save_nonce`.

## Backend pairing

Every mobile mutation endpoint must use `require_save_nonce` and `oracle_transaction` on the server. See:

`Nexa_Dynamics_FastAPI/mobile_backend/MUTATIONS.md`

## Cursor rule

Project AI guidance: `.cursor/rules/nexa-save-and-transactions.mdc`

## Branding (logo, launcher, splash)

- Source logo: `assets/images/nexus-erp-logo.png` (copy from ERP `static/img/nexus-erp-logo.png`)
- UI widget: `lib/widgets/nexus_erp_logo.dart`

Regenerate Android home-screen icon and launch splash after changing the logo:

```powershell
python tool/generate_launch_assets.py
flutter clean
flutter run
```

Uninstall the old app from the device if the launcher icon does not refresh.
