# ADR NNNN: Decision title

- Status: `proposed`
- Date: YYYY-MM-DD
- Owners/reviewers:
- Affected repositories: `ok-script` / `ok-wuthering-waves`
- Related issue/PR/ADR:

## Context

Describe the problem, current behavior, triggering evidence, and why the existing normative constraints or architecture are insufficient.

## Scope boundary

State what this decision changes and what remains explicitly out of scope. Identify any effect on foreground-only operation, public API policy, fail-closed behavior, repository ownership, and Windows compatibility.

## Decision

Describe the selected architecture and its externally observable behavior. Include interfaces, state transitions, lifecycle, and failure behavior where relevant.

## Alternatives considered

For each serious alternative, record:

- design summary;
- benefits;
- risks and limitations;
- reason rejected or deferred.

## Public API and platform-policy review

Confirm whether the decision uses only public Apple APIs. List frameworks/APIs involved. Explicitly address private APIs, `CGEvent.postToPid`, virtual displays, injection/hooks, anti-cheat interaction, root requirements, and TCC modification even when the answer is “not used.”

## Security, permission, and fail-closed analysis

Describe:

- Screen Recording and Accessibility effects;
- packaged-app identity/entitlement effects;
- foreground/focus checks;
- held-input and `release_all()` behavior;
- stale frame/geometry behavior;
- shutdown, target loss, permission loss, and partial-failure handling;
- data, logging, credential, and privacy impact.

## Repository ownership and dependency impact

Explain why the implementation belongs in the selected repository. Record companion changes and the development/editable versus final immutable dependency relationship.

## Windows and other-provider regression impact

List affected Windows, ADB, browser, headless, Qt, or web paths and the compatibility behavior that must remain unchanged.

## Test and acceptance plan

List exact automated contracts and manual/hardware gates. Use the capability states:

1. `not-implemented`
2. `unit-tested`
3. `hardware-validated`
4. `packaged-app-validated`

State which level is required before merge and before public release.

## Migration and rollout

Describe config/schema changes, compatibility adapters, feature flags, staged enablement, documentation, and how existing users move to the new behavior.

## Rollback

Describe the safe code/config/dependency rollback order. A rollback must preserve fail-closed behavior and must identify which evidence gates become invalid.

## External source and license review

For adopted code or design from an external branch, PR, package, article, or sample, record URL/reference, author, license, modifications, and compatibility conclusion. Write “none” when not applicable.

## Consequences and known limitations

Record positive consequences, costs, deferred work, unsupported cases, and operational burden.

## Approval record

Record who accepted/rejected the decision, on what date, and links to the durable review record.
