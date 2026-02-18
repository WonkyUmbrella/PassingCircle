# Passing Circle - Authentication Problem Analysis

**Date**: 2026-02-15
**Status**: Post-rollback, system functional with UX issues

---

## Executive Summary

The Passing Circle authentication system is **functionally working** but has several UX issues that create user confusion. Previous attempts to fix these issues introduced critical regressions, teaching us important lessons about the architectural constraints.

**Current State**:
- ✅ New user enrollment works end-to-end
- ✅ Passkey registration and authentication functional
- ✅ OIDC integration between Authentik and Synapse working
- ❌ Several UX issues remain (detailed below)

---

## Problem Spaces

### Problem 1: Element "Homeserver Forgotten" Error Popup

**Severity**: P3 (Cosmetic)
**Status**: Unresolved

**Symptoms**:
- After successful authentication, Element shows error popup: "We couldn't log you in"
- Popup mentions homeserver being forgotten from browser storage
- Despite popup, authentication succeeds and user can dismiss and continue
- Sometimes requires clicking "Sign In" again, but then works

**What We Know**:
- Backend authentication is working correctly:
  - Authentik generates OIDC token ✅
  - Synapse validates token ✅
  - LoginToken is created ✅
  - Element receives loginToken in URL ✅
  - Element processes loginToken successfully ✅
- The error appears to be an Element Web localStorage timing issue
- Error is cosmetic - doesn't prevent functionality
- May be related to Element checking homeserver state before/during SSO callback

**What We Tried**:
- ❌ Adding `disable_custom_urls: true` to Element config
  - **Result**: Broke enrollment - users no longer logged in after registration
  - **Root Cause**: Conflicted with loginToken processing, caused Element to load `/welcome.html` instead
  - **Rollback**: Reverted this change

**Technical Constraints**:
- Element Web config options designed for different use cases (corporate lockdown vs. our OIDC callback flow)
- SSO redirect options conflict with loginToken-based authentication
- Element localStorage management not fully documented for OIDC flows

**Potential Paths Forward**:
1. **Accept the issue**: Cosmetic only, doesn't block users
2. **Element Web customization**: Fork and modify SSO handling code
3. **Session cookie domain**: Investigate shared domain cookies between auth.chat.local and chat.local
4. **Pre-populate localStorage**: Have landing page inject homeserver config before redirect

**Recommendation**: Accept for now (P3 priority), focus on functional issues first

---

### Problem 2: No Passwordless/Passkey Autofill on Login

**Severity**: P1 (Functional UX issue)
**Status**: Unresolved, architectural constraint identified

**Symptoms**:
- When existing user tries to login, they see identification stage with username field
- User must manually type their username
- No browser passkey picker/autofill appears
- After submitting username, passkey authentication works correctly

**What We Know**:
- Authentik authentication flow architecture:
  ```
  Stage 1: Identification (username input) → lookup user
  Stage 2: WebAuthn Validation (passkey auth) → verify credential
  Stage 3: User Login → create session
  ```
- This is **username-first** authentication (industry standard for passkey fallback)
- Browser passkey autofill requires **usernameless** authentication (WebAuthn Conditional UI)
- Authentik identification stage doesn't implement conditional UI JavaScript patterns
- Our passkeys ARE discoverable credentials (resident keys) - server has enough data for usernameless
- The limitation is in Authentik's flow design, not our configuration

**What We Tried**:
- ❌ Adding `passwordless_field` to Authentik identification stage
  - **Result**: No change in behavior, field still required username typing
  - **Root Cause**: `passwordless_field` enables a different feature (passwordless identifier selection), not conditional UI autofill
  - **Rollback**: Reverted this change

**Technical Constraints**:
- Authentik's identification stage is fundamentally username-first
- WebAuthn Conditional UI requires:
  - JavaScript calling `navigator.credentials.get()` with `mediation: 'conditional'`
  - Input field marked with `autocomplete="webauthn"`
  - Browser support (Chrome 108+, Safari 16+)
- Authentik doesn't implement this pattern in identification stage
- Would require custom stage development or Authentik core modification

**User Requirement Clarification**:
- User stated: "THIS IS NOT A VALID USECASE, we should not support this and when we get passkeys we will remove the username field"
- Goal: **True usernameless authentication** - no username field at all
- Current compromise: Username field exists but could potentially support autofill

**Potential Paths Forward**:
1. **Custom Authentik Stage**: Develop custom identification stage with conditional UI
2. **Bypass Identification**: Create alternative auth flow that skips stage 1
   - Problem: Authentik requires user lookup before WebAuthn validation
3. **Authentik Feature Request**: Request conditional UI support upstream
4. **Alternative IdP**: Evaluate other OIDC providers with native usernameless WebAuthn
5. **Direct Integration**: Skip Authentik, integrate WebAuthn directly into custom landing page
   - Would lose OIDC benefits, increase complexity

**Recommendation**: Research custom Authentik stage development or alternative IdP solutions

---

### Problem 3: "Use Security Key" Button Redirect Loop

**Severity**: P2 (Alternative flow broken)
**Status**: Unresolved, likely separate bug

**Symptoms**:
- On Authentik identification stage, there's a "Use Security Key" button
- Clicking button redirects back to same page (infinite loop)
- This is the alternative to typing username for passkey auth

**What We Know**:
- This button is part of Authentik's identification stage
- Likely intended to skip username entry and go directly to WebAuthn
- Button behavior suggests misconfiguration or bug in Authentik flow
- Not related to our attempted fixes (existed before changes)

**Technical Constraints**:
- Button behavior controlled by Authentik identification stage configuration
- May require specific device_classes or flow configuration we don't have
- Limited documentation on this specific feature

**Potential Paths Forward**:
1. **Review Authentik Docs**: Research proper configuration for "Use Security Key" button
2. **Inspect Network Traffic**: See where button redirect goes, why it loops
3. **Authentik Logs**: Check for errors when button is clicked
4. **Remove Button**: If unfixable, consider hiding via CSS or flow configuration

**Recommendation**: Low priority - investigate after P1 issues resolved

---

### Problem 4: No Auto-Login for Returning Users

**Severity**: P1 (UX issue)
**Status**: Unresolved, architectural challenge

**Symptoms**:
- User enrolls, completes passkey registration, gets logged in
- User closes browser
- User returns to https://chat.passingcircle.com/ and clicks "Start Chatting"
- User sees Element login screen (not automatically logged in)
- User must click "Sign In" and go through authentication flow again

**Expected Behavior**:
- If user has active Authentik session (SSO session), should be instantly logged into Element
- "Magic" auto-login experience - click "Start Chatting" → already in chat

**What We Know**:
- Element doesn't check for active SSO sessions on load
- Element requires explicit "Sign In" click to initiate OIDC flow
- Authentik session cookies are on different domain (auth.chat.passingcircle.com)
- Element session is separate from Authentik session
- SSO session reuse requires Element to proactively check or be redirected

**What We Tried**:
- ❌ Adding `sso_redirect_options` with `on_welcome_page: true`
  - **Result**: Broke enrollment loginToken processing
  - **Root Cause**: Redirect options conflict with OIDC callback handling
  - **Rollback**: Reverted this change

**Technical Constraints**:
- Element designed to show login screen by default
- SSO redirect requires user action (button click) for security/UX reasons
- Automatic redirects on page load considered poor UX (user loses control)
- Cross-domain session sharing requires careful cookie/domain configuration

**Architectural Flow Currently**:
```
User → chat.passingcircle.com → Element UI → Click "Sign In"
→ Synapse → Redirect to auth.passingcircle.com → Authentik
→ (If session exists: instant auth) → Redirect back → Element logged in
```

**Desired Flow**:
```
User → chat.passingcircle.com → Element UI → (Auto-detect session)
→ Auto-redirect to Synapse SSO → Authentik session valid → Instant login
```

**Potential Paths Forward**:
1. **Element Config**: Research `default_hs_url` + auto-redirect on first load
   - Risk: Same issues as previous SSO redirect attempts
2. **Landing Page Logic**: Landing page checks Authentik session before redirecting to Element
   - Requires cross-domain session detection (CORS, cookies)
3. **Session Cookie Domain**: Configure shared cookie domain for auth + chat
   - Current: `auth.passingcircle.com` (Authentik) ≠ `chat.passingcircle.com` (Element/Synapse)
   - Could use: `.passingcircle.com` (shared parent domain)
   - Security implications to consider
4. **Element localStorage Pre-population**: Landing page injects session data before loading Element
   - Complex, may violate Element's security model
5. **Accept Current Behavior**: One extra click ("Sign In") is acceptable UX
   - If Authentik session exists, auth is instant after click
   - Not truly "passwordless" UX but functional

**Recommendation**: Investigate session cookie domain sharing + landing page session detection

---

## Architectural Constraints

### Hard Constraints (Cannot Change Without Major Rework)

1. **Authentik Flow Architecture**: Username-first authentication is core design
2. **Element Web OIDC**: Limited configuration options, designed for specific use cases
3. **Domain Separation**: auth.passingcircle.com (Authentik) vs chat.passingcircle.com (Element/Synapse)
4. **OIDC Spec**: loginToken delivery via URL parameter, can't be modified
5. **WebAuthn Spec**: Conditional UI requires specific JavaScript patterns

### Soft Constraints (Can Change With Effort)

1. **Element Config**: Can fork/customize Element Web if needed
2. **Authentik Stages**: Can develop custom stages with Python
3. **Landing Page**: Full control to add session detection logic
4. **Cookie Domains**: Can configure shared parent domain
5. **DNS/Routing**: Can adjust subdomain structure if needed

---

## Lessons Learned from Failed Attempts

### What Went Wrong

**Failed Attempt 1**: Added `disable_custom_urls: true` to Element config
- **Assumption**: Would prevent localStorage homeserver state issues
- **Reality**: Broke loginToken processing, users not logged in after enrollment
- **Lesson**: Element config options have hidden interactions with OIDC callback flow

**Failed Attempt 2**: Added `passwordless_field` to Authentik identification stage
- **Assumption**: Would enable browser passkey autofill
- **Reality**: No effect, field still required manual username entry
- **Lesson**: Configuration option names can be misleading - `passwordless_field` ≠ passwordless autofill

**Meta-Lesson**: Making multiple simultaneous changes makes it impossible to identify which change caused which problem. Test one change at a time.

### What We Validated

✅ **Authentik Backend**: Creating users, registering passkeys, OIDC tokens - all working correctly
✅ **Synapse OIDC**: Token validation, Matrix user creation - working correctly
✅ **Element OIDC**: LoginToken processing - working correctly (when not interfered with)
✅ **WebAuthn**: Passkey registration and authentication - working correctly
✅ **Discoverable Credentials**: Resident keys properly configured

### Critical Insights

1. **Cosmetic vs Functional**: The Element error popup is annoying but doesn't break the system
2. **Config vs Code**: Some problems require code changes, not just configuration
3. **Documentation Gaps**: Official docs don't cover all edge cases (especially OIDC callback + custom configs)
4. **Rollback is Victory**: Recognizing failure early and rolling back prevented worse issues
5. **User Requirements**: "No username field" is not the same as "autofill username field" - clarify goals upfront

---

## Testing Gaps

### What We Haven't Tested Yet

1. **Session Timeout Behavior**: What happens when Authentik session expires but Element still open?
2. **Multiple Devices**: Does user enrollment on device A allow login on device B?
   - Answer: Probably not - passkeys are device-bound by default
   - Need to test passkey sync via cloud (Apple/Google)
3. **Browser Compatibility**: Only tested on one browser (which one?)
4. **Passkey Deletion**: What happens if user deletes passkey from device?
5. **Account Recovery**: No password fallback - how do users recover access?

### Test Scenarios Needed

- [ ] Fresh browser, new user enrollment → verify all steps
- [ ] Fresh browser, existing user login → verify passkey works
- [ ] Returning user with expired Element session, valid Authentik session → verify behavior
- [ ] User with multiple passkeys registered → verify selection flow
- [ ] Cross-browser passkey sync (Chrome → Safari with Apple Keychain)

---

## Recommendations: What to Do Next

### Option 1: Accept Current State (Conservative)

**What**: Declare current system "good enough" for MVP
**Pros**:
- System is functional
- No risk of breaking working features
- Can iterate based on real user feedback
**Cons**:
- UX issues remain (error popup, manual username entry, no auto-login)
- User confusion likely

**Best For**: Getting to production quickly, testing with real users

---

### Option 2: Focus on Auto-Login (Quick Win Potential)

**What**: Investigate session cookie domain sharing
**Steps**:
1. Review current cookie configuration (Authentik, Synapse, NGINX)
2. Test setting cookie domain to `.passingcircle.com` (parent domain)
3. Add session detection logic to landing page
4. Test auto-redirect flow

**Pros**:
- Could solve Problem 4 (auto-login) without touching Element config
- Might also help with Problem 1 (error popup) via shared session state
**Cons**:
- Security implications of shared cookie domain
- May not work due to CORS/SameSite restrictions

**Best For**: Improving returning user experience with minimal risk

---

### Option 3: Research Usernameless WebAuthn (Long-term Solution)

**What**: Deep dive into implementing true usernameless authentication
**Approaches**:
- Custom Authentik stage with WebAuthn Conditional UI
- Alternative OIDC provider (e.g., Auth0, Okta with usernameless)
- Custom landing page with direct WebAuthn + Synapse integration

**Pros**:
- Achieves user's stated goal (remove username field entirely)
- Modern, clean UX
- Aligns with "passkey-only" vision
**Cons**:
- Significant development effort
- May require forking Authentik or replacing it
- Complex integration work

**Best For**: Long-term architectural improvement, ideal UX

---

### Option 4: Element Web Customization (High Risk)

**What**: Fork Element Web and modify SSO handling
**Changes**:
- Fix error popup via custom localStorage handling
- Add auto-redirect on page load for SSO users
- Improve OIDC callback processing

**Pros**:
- Full control over Element behavior
- Could solve multiple problems at once
**Cons**:
- Fork maintenance burden
- Must track upstream Element updates
- Risk of breaking Matrix protocol compliance

**Best For**: If all other options fail and Element behavior is critical

---

## Open Questions

1. **What browser(s) are users expected to use?**
   - Affects WebAuthn Conditional UI support
   - Chrome 108+, Safari 16+ required for autofill

2. **Is the error popup a blocker for launch?**
   - If yes: Must investigate Element Web fork or alternative
   - If no: Can accept and move forward

3. **How important is true usernameless authentication?**
   - If critical: Need custom Authentik stage or alternative IdP
   - If nice-to-have: Can live with username-first flow

4. **What's the target deployment timeline?**
   - Affects which approach to take (quick fixes vs proper solutions)

5. **Are users expected to use passkeys across multiple devices?**
   - Affects enrollment flow (need to explain passkey sync)
   - May need multi-passkey enrollment

6. **What happens if a user loses their passkey?**
   - Need account recovery mechanism
   - Admin reset? Email recovery? Security questions?

---

## References

### Documentation Reviewed
- Authentik: Flows, Stages, Expression Policies, WebAuthn stages
- Element Web: config.json options, SSO configuration
- Synapse: OIDC provider integration
- WebAuthn: Conditional UI, discoverable credentials (resident keys)

### Code Files
- `/home/swherdman/code/passingcircle/services/authentik/templates/01-flow-auth.yaml.j2` - Auth flow
- `/home/swherdman/code/passingcircle/services/authentik/templates/02-flow-enrollment.yaml.j2` - Enrollment flow
- `/home/swherdman/code/passingcircle/services/element/templates/config.json.j2` - Element config
- `/home/swherdman/code/passingcircle/docs/architecture.md` - Overall system architecture

### Key Discoveries
- Element `disable_custom_urls` conflicts with OIDC loginToken callbacks
- Authentik `passwordless_field` doesn't enable passkey autofill
- WebAuthn Conditional UI requires JavaScript implementation, not just config
- Authentik identification stage is username-first by design

---

**Next Steps**: Discuss priorities with stakeholders, choose approach based on timeline and criticality of each issue.
