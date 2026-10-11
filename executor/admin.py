import argparse
import sys
from executor.credits import generate_code, list_codes, revoke_code, verify_code


def cmd_generate(args):
    record = generate_code(note=args.note or "")
    print(f"==================================================")
    print(f"Generated One-Time Access Code: {record['code']}")
    print(f"Status:                         UNUSED (Single-use)")
    print(f"Note:                           {record['note'] or 'None'}")
    print(f"==================================================")
    print("Share this code with the user to execute their job.")


def cmd_list(args):
    records = list_codes()
    if not records:
        print("No access codes found.")
        return

    print(f"{'CODE':<16} {'STATUS':<10} {'CREATED AT':<24} {'USED BY JOB':<18} {'NOTE'}")
    print("-" * 80)
    for r in records:
        status = r.get("status", "unused").upper()
        used_by = r.get("used_by_job") or "-"
        created = r.get("created_at", "")[:19]
        print(f"{r['code']:<16} {status:<10} {created:<24} {used_by:<18} {r.get('note', '')}")


def cmd_check(args):
    valid, reason, record = verify_code(args.code)
    if record:
        status = record.get("status", "unused").upper()
        print(f"Code:        {record['code']}")
        print(f"Status:      {status}")
        print(f"Used by:     {record.get('used_by_job') or 'Not yet used'}")
        print(f"Valid to use:{' YES' if valid else ' NO (' + reason + ')'}")
    else:
        print(f"Invalid Code: {reason}")


def cmd_revoke(args):
    success = revoke_code(args.code)
    if success:
        print(f"Access code {args.code} has been revoked.")
    else:
        print(f"Error: Code {args.code} not found.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Admin Tool: Generate and Manage One-Time Access Codes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate a new single-use access code")
    p_gen.add_argument("--note", type=str, default="", help="Optional recipient note/tag")

    # list
    subparsers.add_parser("list", help="List all one-time access codes")

    # check
    p_chk = subparsers.add_parser("check", help="Check status of an access code")
    p_chk.add_argument("code", type=str, help="Access code to inspect")

    # revoke
    p_rev = subparsers.add_parser("revoke", help="Revoke an unused access code")
    p_rev.add_argument("code", type=str, help="Access code to revoke")

    args = parser.parse_args()
    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "revoke":
        cmd_revoke(args)


if __name__ == "__main__":
    main()
