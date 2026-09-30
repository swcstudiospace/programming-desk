"""ANDROID and IOS tools: Play Console, App Store Connect, artifact and entitlement evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from desk_gateway.repo import safe_path
from desk_gateway.tools import ToolContext, failure

USAGE_KEYS = re.compile(r"NS[A-Za-z]+UsageDescription")
PRIVATE_API_MARKERS = ("dlopen(", "dlsym(", "NSSelectorFromString", "performSelector", "_UIBackdropView", "objc_msgSend")
STOREKIT_MARKERS = ("StoreKit", "SKProduct", "Product.products", "Transaction.updates")
ACCOUNT_MARKERS = ("deleteAccount", "delete account", "Account deletion", "DeleteAccount")


async def play_track_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    play = ctx.services.play
    if not play.http.configured:
        return {"track": None, **failure("not_configured", "Play Console access token is not configured on the gateway")}
    edit = await play.edit(args["package_name"])
    if edit.get("error"):
        return {"track": None, **edit}
    edit_id = (edit.get("body") or {}).get("id")
    result = await play.track(args["package_name"], edit_id, args["track"])
    if result.get("error"):
        return {"track": None, **result}
    return {"track": result.get("body"), "edit_id": edit_id}


async def play_staged_rollout(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    play = ctx.services.play
    if not play.http.configured:
        return failure("not_configured", "Play Console access token is not configured on the gateway")
    fraction = float(args["user_fraction"])
    if args["track"] == "production" and fraction >= 1.0 and "full" not in args["approval_id"].lower():
        return failure("forbidden", "production at 100 percent needs an approval_id that says full rollout")
    edit = await play.edit(args["package_name"])
    if edit.get("error"):
        return failure(edit["error"], edit.get("reason", "edit failed"))
    edit_id = (edit.get("body") or {}).get("id")
    # A track update is a PUT: whatever it sends *is* the track afterwards. Sending only the
    # release being staged therefore deleted every other release on it — the completed release
    # serving the remaining users among them, which takes the app down for them rather than
    # rolling anything out. Read the track first and put the existing releases back.
    current = await play.track(args["package_name"], edit_id, args["track"])
    if current.get("error"):
        return failure(current["error"], current.get("reason", "track read failed; refusing to write a track we have not read"))
    existing = [r for r in ((current.get("body") or {}).get("releases") or []) if isinstance(r, dict)]
    status = "inProgress" if fraction < 1.0 else "completed"
    release: dict[str, Any] = {"versionCodes": [str(args["version_code"])], "status": status}
    if fraction < 1.0:
        release["userFraction"] = fraction
    releases = _merge_release(existing, release, str(args["version_code"]))
    result = await play.update_track(args["package_name"], edit_id, args["track"], {"track": args["track"], "releases": releases})
    if result.get("error"):
        return failure(result["error"], result.get("reason", "track update failed"))
    commit = await play.commit(args["package_name"], edit_id)
    if commit.get("error"):
        return failure(commit["error"], commit.get("reason", "commit failed"))
    return {
        "ok": True,
        "approval_id": args["approval_id"],
        "halt_threshold": args["halt_threshold"],
        "release": release,
        "releases": releases,
        "preserved_releases": [r.get("name") or r.get("versionCodes") for r in releases if r is not release],
        "edit_id": edit_id,
    }


def _merge_release(existing: list[dict[str, Any]], release: dict[str, Any], version_code: str) -> list[dict[str, Any]]:
    """The track's releases with `release` put in place of the one carrying `version_code`.

    A version code may appear in only one release on a track, so it is removed from the others;
    a release left with none of its own is the one this call replaces. Order is preserved, and
    a release the API gave us with no versionCodes at all (a draft, a rollout by name) is
    passed back untouched — this function never drops a release it was handed.
    """
    merged: list[dict[str, Any]] = []
    placed = False
    for entry in existing:
        codes = [str(c) for c in (entry.get("versionCodes") or [])]
        if not codes:
            merged.append(entry)
            continue
        kept = [c for c in codes if c != version_code]
        if not kept:
            if not placed:
                merged.append(release)
                placed = True
            continue
        merged.append({**entry, "versionCodes": kept})
    if not placed:
        merged.append(release)
    return merged


async def play_halt_rollout(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    play = ctx.services.play
    if not play.http.configured:
        return failure("not_configured", "Play Console access token is not configured on the gateway")
    edit = await play.edit(args["package_name"])
    if edit.get("error"):
        return failure(edit["error"], edit.get("reason", "edit failed"))
    edit_id = (edit.get("body") or {}).get("id")
    current = await play.track(args["package_name"], edit_id, args["track"])
    if current.get("error"):
        return failure(current["error"], current.get("reason", "track read failed"))
    releases = (current.get("body") or {}).get("releases") or []
    changed = False
    for release in releases:
        if release.get("status") == "inProgress":
            release["status"] = "halted"
            changed = True
    if not changed:
        return failure("nothing_to_halt", "no in-progress staged release on that track")
    result = await play.update_track(args["package_name"], edit_id, args["track"], {"track": args["track"], "releases": releases})
    if result.get("error"):
        return failure(result["error"], result.get("reason", "halt failed"))
    commit = await play.commit(args["package_name"], edit_id)
    if commit.get("error"):
        return failure(commit["error"], commit.get("reason", "commit failed"))
    return {"ok": True, "approval_id": args["approval_id"], "reason": args["reason"], "halted": [r.get("name") for r in releases if r.get("status") == "halted"]}


async def artifact_size_delta(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not (safe_path(args["before_path"]) and safe_path(args["after_path"])):
        return failure("invalid_args", "paths must be repo-relative")
    before = repo.dir / args["before_path"]
    after = repo.dir / args["after_path"]
    for p in (before, after):
        if not p.is_file() or p.suffix.lower() not in {".apk", ".aab"}:
            return failure("not_found", f"{p.name} is not an APK/AAB in the checkout")
    b, a = before.stat().st_size, after.stat().st_size
    return {"before_bytes": b, "after_bytes": a, "delta_bytes": a - b, "delta_pct": round((a - b) / b * 100, 2) if b else None}


async def lint_baseline_diff(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not safe_path(args["baseline_path"]):
        return failure("invalid_args", "baseline_path must be repo-relative")
    base = await repo.show(args["baseline_path"], args["base_ref"]) or ""
    head = await repo.show(args["baseline_path"], args["head_ref"]) or ""
    base_ids = set(re.findall(r'id="([^"]+)"', base))
    head_ids = set(re.findall(r'id="([^"]+)"', head))
    base_issues = base.count("<issue")
    head_issues = head.count("<issue")
    return {
        "baseline": args["baseline_path"],
        "issues_before": base_issues,
        "issues_after": head_issues,
        "grew": head_issues > base_issues,
        "new_ids": sorted(head_ids - base_ids),
        "verdict": "a baseline that grows hides a finding" if head_issues > base_issues else "baseline did not grow",
    }


async def _resolve_app_id(asc: Any, bundle_id: str) -> tuple[str | None, dict[str, Any] | None]:
    """App Store Connect id for a bundle id. Returns (app_id, error) — exactly one is set.

    Every version lookup must be scoped to an app: versionString is unique only within one
    app, so filtering on it alone can resolve to a different app's release entirely.
    """
    apps = await asc.request("GET", "/apps", params={"filter[bundleId]": bundle_id, "limit": 1})
    if apps.get("error"):
        return None, apps
    data = (apps.get("body") or {}).get("data") or []
    if not data:
        return None, failure("not_found", "no app with that bundle id")
    return data[0]["id"], None


async def testflight_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    asc = ctx.services.asc.client()
    if not asc.configured:
        return {"builds": [], **failure("not_configured", "App Store Connect key is not configured on the gateway (or PyJWT is missing)")}
    app_id, error = await _resolve_app_id(asc, args["bundle_id"])
    if error is not None:
        return {"builds": [], **error}
    params: dict[str, Any] = {"filter[app]": app_id, "sort": "-uploadedDate", "limit": 10}
    if args.get("build"):
        params["filter[version]"] = args["build"]
    builds = await asc.request("GET", "/builds", params=params)
    if builds.get("error"):
        return {"builds": [], **builds}
    items = [
        {"id": b.get("id"), **{k: (b.get("attributes") or {}).get(k) for k in ("version", "processingState", "uploadedDate", "expired")}}
        for b in (builds.get("body") or {}).get("data") or []
    ]
    return {"app_id": app_id, "builds": items}


async def appstore_phased_release(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    asc = ctx.services.asc.client()
    if not asc.configured:
        return failure("not_configured", "App Store Connect key is not configured on the gateway")
    app_id, error = await _resolve_app_id(asc, args["bundle_id"])
    if error is not None:
        return error
    versions = await asc.request("GET", "/appStoreVersions", params={"filter[app]": app_id, "filter[versionString]": args["version"], "limit": 1})
    if versions.get("error"):
        return failure(versions["error"], versions.get("reason", "version lookup failed"))
    data = (versions.get("body") or {}).get("data") or []
    if not data:
        return failure("not_found", "no App Store version with that string for that bundle id")
    version_id = data[0]["id"]
    body = {"data": {"type": "appStoreVersionPhasedReleases", "attributes": {"phasedReleaseState": "ACTIVE"}, "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}}}}
    result = await asc.request("POST", "/appStoreVersionPhasedReleases", json=body)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "phased release failed"))
    return {"ok": True, "approval_id": args["approval_id"], "halt_signal": args["halt_signal"], "phased_release": (result.get("body") or {}).get("data")}


async def appstore_pause_release(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    asc = ctx.services.asc.client()
    if not asc.configured:
        return failure("not_configured", "App Store Connect key is not configured on the gateway")
    app_id, error = await _resolve_app_id(asc, args["bundle_id"])
    if error is not None:
        return error
    versions = await asc.request("GET", "/appStoreVersions", params={"filter[app]": app_id, "filter[versionString]": args["version"], "include": "appStoreVersionPhasedRelease", "limit": 1})
    if versions.get("error"):
        return failure(versions["error"], versions.get("reason", "version lookup failed"))
    included = (versions.get("body") or {}).get("included") or []
    phased = next((i for i in included if i.get("type") == "appStoreVersionPhasedReleases"), None)
    if not phased:
        return failure("nothing_to_pause", "that version has no phased release")
    body = {"data": {"type": "appStoreVersionPhasedReleases", "id": phased["id"], "attributes": {"phasedReleaseState": "PAUSED"}}}
    result = await asc.request("PATCH", f"/appStoreVersionPhasedReleases/{phased['id']}", json=body)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "pause failed"))
    return {"ok": True, "approval_id": args["approval_id"], "reason": args["reason"], "phased_release_id": phased["id"]}


async def entitlements_diff(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    target = args.get("target_dir") or "ios"
    names = await repo.diff_names(args["base_ref"], args["head_ref"])
    relevant = [n for n in names if n.startswith(target + "/") and (n.endswith(".entitlements") or n.endswith("Info.plist") or n.endswith(".plist"))]
    diff = await repo.diff(args["base_ref"], args["head_ref"], relevant) if relevant else ""
    added_usage = sorted(set(re.findall(r"^\+.*?(NS[A-Za-z]+UsageDescription)", diff, re.M)))
    removed_usage = sorted(set(re.findall(r"^-.*?(NS[A-Za-z]+UsageDescription)", diff, re.M)))
    added_ent = sorted(set(re.findall(r"^\+\s*<key>(com\.apple\.[A-Za-z0-9.-]+)</key>", diff, re.M)))
    removed_ent = sorted(set(re.findall(r"^-\s*<key>(com\.apple\.[A-Za-z0-9.-]+)</key>", diff, re.M)))
    return {
        "files": relevant,
        "usage_descriptions_added": added_usage,
        "usage_descriptions_removed": removed_usage,
        "entitlements_added": added_ent,
        "entitlements_removed": removed_ent,
        "paragraph": "no entitlement change" if not relevant else "entitlement or usage-description files changed; list them in the report",
    }


async def review_risk_check(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    names = await repo.diff_names(args["base_ref"], args["head_ref"])
    swift = [n for n in names if n.endswith(".swift") or n.endswith(".m") or n.endswith(".plist") or n.endswith(".entitlements")]
    diff = await repo.diff(args["base_ref"], args["head_ref"], swift) if swift else ""
    added = "\n".join(line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    risks = []
    if USAGE_KEYS.search(added):
        risks.append({"risk": "permission", "detail": "a usage description was added or changed; confirm the string matches the code path and the prompt appears in context"})
    if any(m in added for m in PRIVATE_API_MARKERS):
        risks.append({"risk": "private_api", "detail": "dynamic selector or dlopen usage added; a compile that succeeds does not prove the symbol is public"})
    if any(m in added for m in STOREKIT_MARKERS):
        risks.append({"risk": "purchases", "detail": "StoreKit code changed; digital goods must go through StoreKit and the flow needs LEAD's attention"})
    if any(m in added for m in ACCOUNT_MARKERS):
        risks.append({"risk": "account_deletion", "detail": "account UI changed; account deletion must stay reachable"})
    if "NSLocationAlwaysAndWhenInUseUsageDescription" in added or "NSLocationAlwaysUsageDescription" in added:
        risks.append({"risk": "always_location", "detail": "always-on location needs a justification a reviewer can read"})
    return {"files_checked": swift, "risks": risks, "verdict": "none" if not risks else "flag before submission"}
