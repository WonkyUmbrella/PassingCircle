# Authentik Flows - Side by Side

## Authentication Flow (`passingcircle-auth`)              Enrollment Flow (`passingcircle-enrollment`)

```
┌─────────────────────────────────────────────┐            ┌─────────────────────────────────────────────┐
│  1. Passkey Authentication                  │            │  1. Collect Username                        │
│     - User clicks "Login with Passkey"      │            │     - Auto-generates username (e.g.,        │
│     - Browser prompts for passkey selection │            │       "swift-fox-1234")                     │
│     - Validates passkey credential          │            │     - User can edit/customize               │
│     - Verifies user identity via biometric  │            │     - Submits chosen username               │
└──────────────────┬──────────────────────────┘            └──────────────────┬──────────────────────────┘
                   │                                                           │
                   ▼                                                           ▼
┌─────────────────────────────────────────────┐            ┌─────────────────────────────────────────────┐
│  2. Create SSO Session                      │            │  2. Derive User Attributes                  │
│     - Establishes Authentik SSO session     │            │     - Reads submitted username              │
│     - Generates OIDC authorization token    │            │     - Generates email: {username}@domain    │
│     - Redirects back to application         │            │     - Sets display name to username         │
└─────────────────────────────────────────────┘            │     - Prepares data for account creation    │
                                                            └──────────────────┬──────────────────────────┘
                                                                               │
                                                                               ▼
                                                            ┌─────────────────────────────────────────────┐
                                                            │  3. Create User Account                     │
                                                            │     - Creates new user in Authentik         │
                                                            │     - Sets username, email, display name    │
                                                            └──────────────────┬──────────────────────────┘
                                                                               │
                                                                               ▼
                                                            ┌─────────────────────────────────────────────┐
                                                            │  4. Register Passkey                        │
                                                            │     - Prompts for passkey enrollment        │
                                                            │     - User provides biometric/security key  │
                                                            │     - Stores passkey credential             │
                                                            └──────────────────┬──────────────────────────┘
                                                                               │
                                                                               ▼
                                                            ┌─────────────────────────────────────────────┐
                                                            │  5. Establish SSO Session                   │
                                                            │     - Logs in newly created user            │
                                                            │     - Creates Authentik SSO session         │
                                                            │     - Generates OIDC token for application  │
                                                            │     - Redirects to complete login           │
                                                            └─────────────────────────────────────────────┘
```
