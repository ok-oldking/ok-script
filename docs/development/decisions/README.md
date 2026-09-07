# Architecture Decision Records

Use an ADR when a proposed macOS foreground-port change deliberately departs from a normative constraint, changes a cross-repository contract, introduces a new security/permission assumption, or selects between materially different platform architectures.

## When an ADR is required

Examples include:

- weakening or changing foreground/focus behavior;
- changing the public-API-only policy;
- changing repository ownership between `ok-script` and OK-WW;
- selecting a capture/input approach that differs from the accepted ScreenCaptureKit/Quartz architecture;
- introducing a new packaged-app identity, entitlement, signing, or permission model;
- changing the coordinate or frame contract;
- removing or incompatibly changing an existing Windows public behavior;
- adopting substantial implementation from an external branch or historical PR;
- changing the final cross-repository dependency/release strategy.

Routine implementation details that remain within the existing contract do not require an ADR.

## File naming

Use:

```text
NNNN-short-kebab-title.md
```

Start with `0001`. Keep `0000-template.md` unchanged as the template.

## Status values

- `proposed`
- `accepted`
- `rejected`
- `superseded`

A proposed ADR does not authorize runtime implementation that violates current constraints. The decision must be accepted by the relevant project owners/maintainers first.

本 contributor 集成分支的用户可以明确授权其分支内的设计决定；ADR 必须注明授权范围，不代表 upstream 接受。最终上游审查和验收门槛不变。

当前配套决策：[ADR 0002：consumer 打包最低版本与框架设计基线分离](0002-consumer-packaged-minimum-version.md)。OK-WW packaged MVP 收窄为 macOS 15+，框架公开 API 设计与 host gate 保留 13+。

## Required review

An ADR must identify:

- affected repository or repositories;
- companion ADR/PR when the decision spans repositories;
- product and safety constraints affected;
- Windows regression impact;
- tests, hardware evidence, packaging evidence, migration, and rollback;
- source attribution and license review for adopted external code.

Superseded ADRs remain in the repository and link to their replacement.
