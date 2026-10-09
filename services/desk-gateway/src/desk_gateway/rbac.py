"""Attribute-Based & Role-Based Access Control (ABAC/RBAC) policy engine governing tool invocation and operations."""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from desk_gateway.tenant import TenantContext

logger = logging.getLogger("desk_gateway.rbac")


class AccessDecision(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class Role(str, enum.Enum):
    ADMIN = "admin"
    LEAD = "lead"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    AUDITOR = "auditor"
    GUEST = "guest"


@dataclass(frozen=True)
class PolicyEvaluationResult:
    decision: AccessDecision
    reason: str
    rule_id: str | None = None
    role: str | None = None
    seat: str | None = None
    action: str | None = None


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    roles: tuple[Role, ...]
    seats: tuple[str, ...] = ()  # empty means all seats
    actions: tuple[str, ...] = ()  # e.g. "tool:*" or specific tool name
    effect: AccessDecision = AccessDecision.ALLOW
    environments: tuple[str, ...] = ()  # empty means all environments
    require_gates: tuple[str, ...] = ()  # e.g. ["g5", "g6"] requires approval/rollback
    deny_destructive_on_prod: bool = False
    description: str = ""


# Default policy rules establishing zero-trust access boundaries
DEFAULT_RULES: tuple[PolicyRule, ...] = (
    # Admin has unrestricted access
    PolicyRule(
        rule_id="rule-admin-full",
        roles=(Role.ADMIN,),
        description="Full access for desk admin role",
    ),
    # Lead role has broad execution across all seats
    PolicyRule(
        rule_id="rule-lead-all-seats",
        roles=(Role.LEAD,),
        description="Lead seat coordination and tool execution",
    ),
    # Auditor role has read-only inspection
    PolicyRule(
        rule_id="rule-auditor-read-only",
        roles=(Role.AUDITOR,),
        actions=("read", "tool:read_*", "tool:desk_brief", "tool:desk_ownership_resolve"),
        description="Auditor read-only inspection",
    ),
    # Developer role has access to all desk seats and non-destructive tools
    PolicyRule(
        rule_id="rule-developer-standard",
        roles=(Role.DEVELOPER,),
        seats=("systems", "infra", "quality", "web", "android", "ios", "lead"),
        description="Developer seat execution",
    ),
    # Operator role for infrastructure operations
    PolicyRule(
        rule_id="rule-operator-infra",
        roles=(Role.OPERATOR,),
        seats=("infra", "systems", "lead"),
        description="Operator seat execution",
    ),
    # Guest role has minimum read-only access
    PolicyRule(
        rule_id="rule-guest-restricted",
        roles=(Role.GUEST,),
        actions=("tool:desk_brief",),
        description="Guest minimal inspection",
    ),
)


class RBACPolicyEngine:
    """Evaluates fine-grained RBAC/ABAC rules governing tool invocation and API actions."""

    def __init__(
        self,
        rules: Sequence[PolicyRule] | None = None,
        strict_gates: Sequence[str] = (),
    ) -> None:
        self._rules: list[PolicyRule] = list(rules or DEFAULT_RULES)
        self._strict_gates: set[str] = set(strict_gates)

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.insert(0, rule)  # prepend to give higher priority to dynamic rules

    def evaluate(
        self,
        tenant: TenantContext,
        role: Role | str,
        seat: str,
        action: str,  # e.g. "tool:greptime_query" or "api:supervisor_reconstitute"
        *,
        gates: Sequence[str] = (),
        is_destructive: bool = False,
        has_approval: bool = False,
        has_rollback_plan: bool = False,
        resource_attributes: dict[str, Any] | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate access request against RBAC/ABAC policy set."""
        try:
            parsed_role = Role(role) if isinstance(role, str) else role
        except ValueError:
            return PolicyEvaluationResult(
                decision=AccessDecision.DENY,
                reason=f"Unrecognized role: '{role}'",
                role=str(role),
                seat=seat,
                action=action,
            )

        # Gate 5 requirement check: requires approval_id and rollback_plan
        # (Only enforced when explicitly configured in rule requirements or if require_gate_checks is enabled)
        if "g5" in self._strict_gates and "g5" in gates and (not has_approval or not has_rollback_plan):
            return PolicyEvaluationResult(
                decision=AccessDecision.DENY,
                reason="Gate 5 policy violation: write operation requires verified approval_id and rollback_plan",
                role=parsed_role.value,
                seat=seat,
                action=action,
            )

        # Gate 6 requirement check: requires approval_id
        if "g6" in self._strict_gates and "g6" in gates and not has_approval:
            return PolicyEvaluationResult(
                decision=AccessDecision.DENY,
                reason="Gate 6 policy violation: destructive operation requires verified approval_id",
                role=parsed_role.value,
                seat=seat,
                action=action,
            )

        # Evaluate rules in order of definition (first match wins)
        for rule in self._rules:
            # Check role match
            if rule.roles and parsed_role not in rule.roles:
                continue

            # Check environment match
            if rule.environments and tenant.environment not in rule.environments:
                continue

            # Check seat match
            if rule.seats and seat not in rule.seats:
                continue

            # Check action match
            if rule.actions:
                matched_action = False
                for pattern in rule.actions:
                    if pattern == "*" or pattern == action:
                        matched_action = True
                        break
                    if pattern.endswith("*") and action.startswith(pattern[:-1]):
                        matched_action = True
                        break
                if not matched_action:
                    continue

            # Check destructive on prod
            if (
                rule.deny_destructive_on_prod
                and tenant.environment == "prod"
                and (is_destructive or "g6" in gates)
            ):
                return PolicyEvaluationResult(
                    decision=AccessDecision.DENY,
                    reason=f"Policy rule '{rule.rule_id}' forbids destructive action in production environment",
                    rule_id=rule.rule_id,
                    role=parsed_role.value,
                    seat=seat,
                    action=action,
                )

            # Matched rule
            if rule.effect == AccessDecision.ALLOW:
                return PolicyEvaluationResult(
                    decision=AccessDecision.ALLOW,
                    reason=f"Allowed by rule '{rule.rule_id}' ({rule.description})",
                    rule_id=rule.rule_id,
                    role=parsed_role.value,
                    seat=seat,
                    action=action,
                )
            else:
                return PolicyEvaluationResult(
                    decision=AccessDecision.DENY,
                    reason=f"Explicitly denied by rule '{rule.rule_id}' ({rule.description})",
                    rule_id=rule.rule_id,
                    role=parsed_role.value,
                    seat=seat,
                    action=action,
                )

        # Default deny posture
        return PolicyEvaluationResult(
            decision=AccessDecision.DENY,
            reason=f"Default deny: no matching RBAC/ABAC rule permitting role '{parsed_role.value}' for action '{action}' on seat '{seat}' in '{tenant.namespace}'",
            role=parsed_role.value,
            seat=seat,
            action=action,
        )
