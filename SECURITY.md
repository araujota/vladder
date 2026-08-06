# Security Policy

## Supported Versions

Security fixes are applied to the latest published vLadder release candidate or stable release.
Older research snapshots are not supported.

## Reporting A Vulnerability

Use GitHub's private vulnerability reporting for
[`araujota/vladder`](https://github.com/araujota/vladder/security/advisories/new). Do not open a
public issue containing an exploit, private source, credentials, or contribution capabilities.

Include the affected version, operating system, reproduction conditions, and the smallest safe
proof of impact. Maintainers will acknowledge a report within seven days and will coordinate a
fix and disclosure timeline based on severity.

## Security Boundaries

vLadder executes compilers, solvers, generated candidates, benchmark harnesses, and optional
project adapters on the user's machine. Treat untrusted source and generated executables as
untrusted code and isolate them appropriately. Formal proof evidence applies only to its recorded
semantic envelope; it is not a sandbox or a supply-chain attestation.

Optional training and review contribution paths are disabled until the user explicitly opts in.
Their scoped installation capabilities are sensitive local credentials and must not be committed,
logged, or included in release artifacts.
