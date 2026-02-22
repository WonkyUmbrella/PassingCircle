# FluffyChat Build Pipeline

## Docker Image

**Image:** `ghcr.io/swherdman/fluffychat:swherdman-auto-sso-redirect`

**Registry:** GitHub Container Registry (GHCR)

**Source:** [github.com/swherdman/fluffychat](https://github.com/swherdman/fluffychat), branch `swherdman/auto-sso-redirect`

This image is a custom build of FluffyChat with the `autoSsoRedirect` config option. See [FluffyChat Auto-SSO](../architecture/fluffychat-auto-sso.md) for details on the feature.

## docker-compose.yml

```yaml
passingcircle-fluffychat:
  container_name: passingcircle-fluffychat
  image: ghcr.io/swherdman/fluffychat:swherdman-auto-sso-redirect
  volumes:
    - ./services/fluffychat/config.json:/usr/share/nginx/html/config.json:ro
  restart: unless-stopped
  networks:
    - backend
```

The container runs NGINX internally (serving the built Flutter web app on port 80). The external NGINX reverse proxy (`passingcircle-nginx`) routes requests from `chat-mobile.passingcircle.com` to this container.

## GitHub Actions Workflow

The image is built via a manually-triggered GitHub Actions workflow in the fork repository.

**Workflow file:** `.github/workflows/docker-publish.yml`

```yaml
name: Build & Publish Docker Image

on:
  workflow_dispatch:
    inputs:
      branch:
        description: 'Branch to build from'
        required: true
        default: 'swherdman/auto-sso-redirect'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v6
        with:
          ref: ${{ github.event.inputs.branch }}

      - name: Read Flutter version
        run: |
          source .github/workflows/versions.env
          echo "FLUTTER_VERSION=$FLUTTER_VERSION" >> $GITHUB_ENV

      - name: Pin Flutter version in Dockerfile
        run: sed -i "s|ghcr.io/cirruslabs/flutter|ghcr.io/cirruslabs/flutter:${{ env.FLUTTER_VERSION }}|" Dockerfile

      - name: Free up space
        uses: ./.github/actions/free_up_space

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata for Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=${{ github.event.inputs.branch == 'main' && 'latest' || github.event.inputs.branch }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

**Key points:**
- **Manual trigger** (`workflow_dispatch`) — not triggered automatically on push
- **Branch input** — defaults to `swherdman/auto-sso-redirect` but can build any branch
- **Image tag** — matches the branch name (e.g. `swherdman-auto-sso-redirect`), or `latest` when building from `main`
- **Flutter version pinning** — reads from `versions.env` and patches the Dockerfile at build time

## Flutter Version Pinning

**File:** `.github/workflows/versions.env`

```
FLUTTER_VERSION=3.41.1
JAVA_VERSION=17
```

The workflow reads this file and substitutes the Flutter base image tag in the Dockerfile. This prevents builds from breaking when a new Flutter version introduces incompatibilities.

To update the Flutter version:
1. Edit `versions.env` with the new version
2. Test the build locally or trigger the workflow
3. Commit the change

## Rebuilding After Upstream Changes

When the upstream FluffyChat repository (krille-chan/fluffychat) releases a new version:

```bash
# In the fork repository
git fetch upstream
git checkout swherdman/auto-sso-redirect

# Rebase the auto-SSO changes onto the latest upstream
git rebase upstream/main

# Resolve any conflicts in the changed files:
#   - lib/config/setting_keys.dart
#   - lib/config/routes.dart
#   - lib/pages/sign_in/sign_in_page.dart
#   - lib/pages/sign_in/view_model/sign_in_view_model.dart
#   - lib/widgets/view_model_builder.dart
#   - web/auth.html

# Push the updated branch
git push --force-with-lease origin swherdman/auto-sso-redirect

# Trigger the GitHub Actions workflow to rebuild the image
# (via GitHub UI: Actions -> Build & Publish Docker Image -> Run workflow)
```

After the new image is published:

```bash
# In the passingcircle repository
docker compose pull passingcircle-fluffychat
docker compose up -d passingcircle-fluffychat
```

## Fork Management

The fork tracks upstream via a standard Git remote:

```bash
git remote -v
# origin    git@github.com:swherdman/fluffychat.git
# upstream  git@github.com:krille-chan/fluffychat.git
```

The `main` branch in the fork contains two additional commits on top of upstream `main`:
1. GitHub Actions workflow for Docker image publishing
2. Flutter version pinning via `versions.env`

The `swherdman/auto-sso-redirect` branch contains the auto-SSO feature commits on top of `main`.
