"""Loaded automatically by every Python process that scripts/guarded starts (it puts this
folder on PYTHONPATH). Turns on the in-process network guard; the sandbox profile still
applies if the package can't be imported."""

try:
    from filing_update_evals.netguard import install_from_env
except ImportError:
    pass
else:
    install_from_env()
