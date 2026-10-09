"""Unified Command Line Interface for Programming Desk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .assertions.milestone_verifier import MilestoneVerifier
from .diagnostics.doctor_engine import CheckStatus, DoctorEngine
from .session.session_store import SessionFrame, SessionStore
from .supervision.process_supervisor import ProcessSupervisor
from .telemetry.audit_tracer import AuditTracer


def handle_doctor(args: argparse.Namespace) -> int:
    engine = DoctorEngine()
    results = engine.run_all()
    overall = engine.overall_status(results)
    if args.json:
        payload = {
            "overall_status": overall.value,
            "checks": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        verbose = getattr(args, "verbose", False)
        print(engine.format_report(results, verbose=verbose))
    return engine.exit_code(results)


def handle_audit(args: argparse.Namespace) -> int:
    tracer = AuditTracer()
    events = tracer.read_events(phase=args.phase, limit=args.tail)
    if args.json:
        print(json.dumps(events, indent=2))
    else:
        if not events:
            print("No audit events found.")
            return 0
        for ev in events:
            ts = ev.get("timestamp", "")
            action = ev.get("action", "")
            actor = ev.get("actor", "")
            dur = ev.get("duration_ms")
            dur_str = f"({dur:.1f}ms)" if dur is not None else ""
            print(f"[{ts}] {actor} -> {action} {dur_str}")
    return 0


def handle_verify(args: argparse.Namespace) -> int:
    verifier = MilestoneVerifier(roadmap_path=args.roadmap)
    test_cmd = None
    if args.run_tests:
        test_cmd = [sys.executable, "-m", "pytest", "tests/desk"]

    report = verifier.verify_milestone(test_command=test_cmd)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(verifier.format_summary(report))

    return 0 if report.all_phases_complete else 1


def handle_session(args: argparse.Namespace) -> int:
    store = SessionStore()
    if args.init:
        existing_frame = store.load_session()
        active_tasks = existing_frame.active_tasks if existing_frame else []
        completed_tasks = existing_frame.completed_tasks if existing_frame else []
        frame = SessionFrame(
            session_id=args.init,
            milestone=args.milestone,
            phase=args.phase,
            status="active",
            active_tasks=active_tasks,
            completed_tasks=completed_tasks,
        )
        store.save_session(frame)
        # Preserve existing STATE.md progress if already present
        if not store.state_md_path.exists() or store.state_md_path.stat().st_size == 0:
            store.sync_to_markdown_state(frame)
        print(f"Initialized session '{args.init}'.")
        return 0

    frame = store.load_session()
    if not frame:
        print("No active session found.")
        return 1

    if args.json:
        print(json.dumps(frame.to_dict(), indent=2))
    else:
        print(f"Session ID: {frame.session_id}")
        print(f"Milestone: {frame.milestone} | Phase: {frame.phase}")
        print(f"Status: {frame.status} | Updated: {frame.updated_at}")
        print(f"Active Tasks: {len(frame.active_tasks)} | Completed Tasks: {len(frame.completed_tasks)}")
    return 0


def handle_run(args: argparse.Namespace) -> int:
    tracer = AuditTracer()
    supervisor = ProcessSupervisor(default_timeout=args.timeout)

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        print("Error: No command specified to run.", file=sys.stderr)
        tracer.emit(action="run_error", error="No command specified", exit_code=2)
        return 2

    try:
        res = supervisor.run(cmd, timeout=args.timeout)
        tracer.emit(
            action="supervised_run",
            cmd=cmd[0],
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
            timed_out=res.timed_out,
        )

        if res.stdout:
            print(res.stdout, end="")
        if res.stderr:
            print(res.stderr, file=sys.stderr, end="")

        return res.exit_code
    except Exception as exc:
        print(f"Error executing command: {exc}", file=sys.stderr)
        tracer.emit(
            action="run_failure",
            cmd=cmd[0] if cmd else "unknown",
            error=str(exc),
            exit_code=1,
        )
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="desk", description="Programming Desk Workbench CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Inspect workspace health")
    p_doctor.add_argument("--json", action="store_true", help="Output JSON")
    p_doctor.add_argument("-v", "--verbose", action="store_true", help="Verbose details")
    p_doctor.set_defaults(handler=handle_doctor)

    # audit
    p_audit = subparsers.add_parser("audit", help="Inspect audit telemetry logs")
    p_audit.add_argument("--tail", type=int, default=20, help="Number of trailing events")
    p_audit.add_argument("--phase", type=str, default=None, help="Filter by phase")
    p_audit.add_argument("--json", action="store_true", help="Output JSON")
    p_audit.set_defaults(handler=handle_audit)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify roadmap milestones and assertions")
    p_verify.add_argument("--roadmap", default=".planning/ROADMAP.md", help="Path to ROADMAP.md")
    p_verify.add_argument("--run-tests", action="store_true", help="Execute test suite")
    p_verify.add_argument("--json", action="store_true", help="Output JSON")
    p_verify.set_defaults(handler=handle_verify)

    # session
    p_session = subparsers.add_parser("session", help="Session state inspections and sync")
    p_session.add_argument("--init", type=str, help="Initialize a new session ID")
    p_session.add_argument("--milestone", default="v8.0", help="Milestone label")
    p_session.add_argument("--phase", default="Phase 1", help="Phase label")
    p_session.add_argument("--json", action="store_true", help="Output JSON")
    p_session.set_defaults(handler=handle_session)

    # run
    p_run = subparsers.add_parser("run", help="Supervised process execution")
    p_run.add_argument("--timeout", type=float, default=30.0, help="Execution timeout in seconds")
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="Command array to run")
    p_run.set_defaults(handler=handle_run)

    try:
        args = parser.parse_args(argv)
        if not hasattr(args, "handler"):
            parser.print_help()
            return 0
        return args.handler(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        try:
            AuditTracer().emit(action="cli_panic", error=str(exc), exit_code=1)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
