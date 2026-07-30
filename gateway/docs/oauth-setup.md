# OAuth (Auth0) Setup

How to configure OAuth login for the SDS Gateway using Auth0 as the identity
provider.

+ [OAuth (Auth0) Setup](#oauth-auth0-setup)
    + [Overview](#overview)
    + [Prerequisites](#prerequisites)
    + [Step-by-step setup](#step-by-step-setup)
        + [1. Create an Auth0 application](#1-create-an-auth0-application)
        + [2. Configure callback URLs in Auth0](#2-configure-callback-urls-in-auth0)
        + [3. Set the AUTH0_DOMAIN environment variable](#3-set-the-auth0_domain-environment-variable)
        + [4. Create the SocialApp in Django admin](#4-create-the-socialapp-in-django-admin)
        + [5. (Optional) Disable password authentication](#5-optional-disable-password-authentication)
    + [Troubleshooting](#troubleshooting)

## Overview

The SDS Gateway supports OAuth login via [django-allauth](https://docs.allauth.org/)
with the Auth0 provider. When configured, users can sign in through your Auth0 tenant
instead of (or in addition to) the built-in password login.

The gateway uses:

+ **django-allauth** with `allauth.socialaccount.providers.auth0`
+ PKCE-based OAuth (no client secret exchange required by the SDK, but the secret is
  still stored for server-side flows)
+ Scopes: `openid`, `profile`, `email`
+ A `SocialAccountAdapter` that populates user name/email from the Auth0 profile

By default, both password and OAuth login are available. This can be changed to
OAuth-only via the `SOCIALACCOUNT_ONLY` setting.

## Prerequisites

+ An [Auth0](https://auth0.com/) account (free tier works)
+ Access to the SDS Gateway Django admin panel
+ The `AUTH0_DOMAIN` environment variable set in `django.env`

## Step-by-step setup

### 1. Create an Auth0 application

1. Log in to the [Auth0 Dashboard](https://manage.auth0.com/).
2. Go to **Applications > Applications** and click **Create Application**.
3. Name it (e.g. `SDS Gateway`) and select **Regular Web Applications** as the type.
4. After creation, go to the **Settings** tab.
5. Note the **Domain**, **Client ID**, and **Client Secret** — you'll need them below.

> [!IMPORTANT]
> The **Domain** is your `AUTH0_DOMAIN`. It typically looks like
> `your-tenant.auth0.com`.

### 2. Configure callback URLs in Auth0

In the Auth0 application's **Settings** tab, set:

+ **Allowed Callback URLs**:

    ```text
    http://localhost:8000/accounts/auth0/login/callback/
    https://your-domain.com/accounts/auth0/login/callback/
    ```

    Add all domains the Gateway runs on (local, staging, production).

+ **Allowed Logout URLs**:

    ```text
    http://localhost:8000/
    https://your-domain.com/
    ```

+ **Allowed Web Origins**:

    ```text
    http://localhost:8000
    https://your-domain.com
    ```

> [!TIP]
> For local development, `http://localhost:8000/accounts/auth0/login/callback/` is
> sufficient. Add production URLs when you deploy.

### 3. Set the AUTH0_DOMAIN environment variable

Set `AUTH0_DOMAIN` in the appropriate `django.env` file:

+ **Local**: `.envs/local/django.env`
+ **Production**: `.envs/production/django.env`

```bash
AUTH0_DOMAIN=your-tenant.auth0.com
```

> [!NOTE]
> This value must match the **Domain** from your Auth0 application settings exactly.
> Do not include `https://` or a trailing slash.

### 4. Create the SocialApp in Django admin

The `CLIENT_ID` and `CLIENT_SECRET` are **not** stored as environment variables.
They are configured in the database via the Django admin.

1. Log in to the Django admin (e.g. `localhost:8000/admin/`).
2. Navigate to **Sites > Social applications** (or go directly to
   `/admin/socialaccount/socialapp/`).
3. Click **Add Social application**.
4. Fill in:

    | Field | Value |
    |-------|-------|
    | Provider | `Auth0` |
    | Name | `Auth0` (or any descriptive name) |
    | Client id | Your Auth0 **Client ID** |
    | Secret key | Your Auth0 **Client Secret** |
    | Sites | Select your site (e.g. `example.com`) |

5. Click **Save**.

> [!IMPORTANT]
> The **Sites** field must include the site matching your `ALLOWED_HOSTS` value.
> For local development, this is typically `localhost:8000` or `example.com`
> (Django's default site).

### 5. (Optional) Disable password authentication

To require OAuth login only (removing the password form), set this in `django.env`:

```bash
SOCIALACCOUNT_ONLY=True
```

This removes the email/password fields from the login and signup pages, showing only
the OAuth button. The default is `False` (both methods available).

> [!NOTE]
> When `SOCIALACCOUNT_ONLY=True`, existing password-based accounts can still log in
> via the admin or the API — the change only affects the web login/signup templates.

## Troubleshooting

### `SocialApp.DoesNotExist` error

If users see a server error when clicking the OAuth login button, the `SocialApp`
record is likely missing from the database. The gateway includes a
`SocialAccountFallbackMiddleware` that catches this and redirects to the password
login page, but in older versions or misconfigured deployments you may see the error
directly.

**Fix**: Create the SocialApp in Django admin as described in [step
4](#4-create-the-socialapp-in-django-admin).

### Callback URL mismatch

Auth0 rejects the login with an `invalid_request` or similar error if the callback
URL doesn't match.

**Fix**: Ensure the **Allowed Callback URLs** in Auth0 exactly match your Gateway's
callback URL, including the trailing slash:

```text
http://localhost:8000/accounts/auth0/login/callback/
```

### `AUTH0_DOMAIN` not set

The gateway will fail to start with an environment variable error if `AUTH0_DOMAIN`
is missing.

**Fix**: Add `AUTH0_DOMAIN=your-tenant.auth0.com` to your `django.env` file and
restart the services.

### OAuth button not showing on the login page

If the login page loads but no OAuth button appears:

1. Verify the `SocialApp` exists in Django admin and is linked to the correct site.
2. Verify `AUTH0_DOMAIN` is set and the Auth0 provider is in `INSTALLED_APPS` (it

  is added by default in the gateway settings).

3. Check that `SOCIALACCOUNT_ONLY` is not interfering with the template rendering.

### User not created after OAuth login

The `SocialAccountAdapter` populates user name/email from the Auth0 profile. If
`ACCOUNT_ALLOW_REGISTRATION` is set to `False` in `django.env`, new users cannot
sign up via OAuth.

**Fix**: Set `ACCOUNT_ALLOW_REGISTRATION=True` in `django.env`, or manually create
the user in Django admin and link the social account.
