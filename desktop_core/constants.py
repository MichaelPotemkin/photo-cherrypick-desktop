"""Shared tuning constants used by more than one module — single source of truth."""

# In a multi-shot burst — or a scene — when the top-2 picks are within this overall margin the choice
# is a near-tie; flag it so the UI can tell the photographer "too close to call, you decide". 0.05
# was calibrated on the audit shoot: picks below it are ~coin-flips vs the reference panel (it more
# than halves confidently-wrong unflagged picks). See docs/SCORING-ITERATION-LOG.md.
CLOSE_GAP = 0.05
