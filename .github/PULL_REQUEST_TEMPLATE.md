# Summary

What this changes, and why. If it touches a benchmark app, say what the same
change needs in the other frameworks to keep the comparison fair.

# Verification

How you checked it: the commands you ran, the machine, and whether you did a
full measurement round.

- [ ] `python3 harness/test_stats.py`
- [ ] `python3 harness/bench.py report` leaves `results.json` unchanged
- [ ] the affected framework apps build (`./run.sh build`)
- [ ] `README.md` or the caveats in `results.md` updated, where relevant

Committed numbers change only in a run that measured them. Say which machine
produced them.
