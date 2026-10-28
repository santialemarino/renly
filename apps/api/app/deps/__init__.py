# FastAPI dependencies, imported by routers from their modules:
# - auth: the JWT user (CurrentUser) and the admin gate (AdminUser).
# - api_key_auth: a JWT or an API key (JwtOrApiKeyUser), for endpoints the iOS Shortcut also calls.
# - db: the request, auth and admin database sessions (SessionDep, AuthSessionDep, AdminSessionDep).
# - pagination: the page / page_size query pair (PageQuery).
# - currency: the optional display-currency query param (DisplayCurrency).
