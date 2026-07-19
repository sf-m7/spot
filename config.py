"""Spot configuration. Nothing secret lives here - only env plumbing."""
import os

SUPABASE_URL = os.environ.get("SPOT_SUPABASE_URL", "https://wlnjdhgighoudrzoddyq.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SPOT_SUPABASE_SERVICE_KEY", "")

R2_BUCKET = os.environ.get("SPOT_R2_BUCKET", "spot-archive")
R2_ACCOUNT_ID = os.environ.get("SPOT_R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("SPOT_R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("SPOT_R2_SECRET_ACCESS_KEY", "")

# Politeness: the first-movers scrape Etimad openly but quietly. We do the same.
# Never raise these without a reason recorded in the decision log.
REQUEST_DELAY_SECONDS = float(os.environ.get("SPOT_REQUEST_DELAY", "3.0"))
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = os.environ.get(
    "SPOT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

# Stage 0 scope: one sector only. Everything is gated on this staying narrow.
STAGE0_SECTOR = os.environ.get("SPOT_SECTOR", "construction")
