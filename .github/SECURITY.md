# Security policy

## Supported versions

This repository has no releases. The latest `master` is the only supported
version; fixes land there.

## Reporting a vulnerability

Report privately through GitHub security advisories: open the Security tab of
this repository and use "Report a vulnerability". That opens a private thread
with the maintainers.

Do not open a public issue for a bug that is exploitable. This repository is a
benchmark suite, so the likely cases are the harness or `run.sh` executing
attacker-controlled input, or a build script reaching outside the checkout.

A vulnerability in one of the measured frameworks belongs with that project, not
here.
