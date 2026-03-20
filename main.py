"""
deep_research.py
────────────────────────────────────────────────────────────────
Runs the Gemini Deep Research Agent on a given topic and saves
the resulting report to a local text file.

Usage:
    # 1. Install the required library
    pip install google-genai --upgrade

    # 2. Set your API key as an environment variable (never hard-code it)
    export GEMINI_API_KEY="your_api_key_here"   # Mac/Linux
    set    GEMINI_API_KEY=your_api_key_here      # Windows

    # 3. Run (topic is optional; falls back to DEFAULT_TOPIC)
    python deep_research.py "Competitive analysis of the EV battery market"
    python deep_research.py
────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import datetime


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

DEFAULT_TOPIC = "Please provide a simple overview of the EV battery market competitive landscape."
TOPIC = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOPIC

# Output directory: a "results" folder next to this script
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# Polling settings
POLL_INTERVAL_INITIAL  = 15   # Initial polling interval in seconds
POLL_INTERVAL_MAX      = 60   # Maximum polling interval in seconds (exponential back-off ceiling)
TIMEOUT_MINUTES        = 65   # Abort if research has not completed within this many minutes
MAX_CONSECUTIVE_ERRORS = 10   # Abort after this many consecutive polling errors


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    # ── Dependency check ─────────────────────────────────────
    try:
        from google import genai
    except ImportError:
        sys.exit(
            "Error: google-genai is not installed.\n"
            "  Run: pip install google-genai --upgrade"
        )

    # ── API key check ────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "Error: environment variable GEMINI_API_KEY is not set.\n"
            "  Run: export GEMINI_API_KEY='your_api_key'"
        )

    client = genai.Client(api_key=api_key)

    # ── Step 1: Launch Deep Research (async) ─────────────────
    print("=" * 60)
    print(f"Topic : {TOPIC}")
    print("=" * 60)
    print("[1/3] Starting Deep Research Agent...")

    interaction = client.interactions.create(
        agent="deep-research-pro-preview-12-2025",
        input=TOPIC,
        background=True,  # Required for async execution
        store=True,       # Required when background=True
    )
    research_id = interaction.id
    print(f"      Interaction ID : {research_id}")
    print( "      Note: research typically takes 5-20 minutes (up to 60 minutes for complex topics).")

    # ── Step 2: Poll until complete ───────────────────────────
    print("[2/3] Waiting for research to complete...")

    wait             = float(POLL_INTERVAL_INITIAL)
    elapsed          = 0.0
    max_sec          = TIMEOUT_MINUTES * 60
    consecutive_errs = 0  # Must be initialised before the loop
    report           = None

    while elapsed < max_sec:
        time.sleep(wait)
        elapsed += wait
        mins, secs = divmod(int(elapsed), 60)  # int() prevents %d format errors with floats

        # Poll for status; transient server errors are retried automatically
        try:
            result = client.interactions.get(research_id)
            consecutive_errs = 0  # Reset on success

        except Exception as e:
            consecutive_errs += 1
            print(
                f"      [{mins:02d}:{secs:02d} elapsed] "
                f"Transient error ({consecutive_errs}/{MAX_CONSECUTIVE_ERRORS}), retrying: {e}"
            )
            if consecutive_errs >= MAX_CONSECUTIVE_ERRORS:
                sys.exit(
                    f"Error: {MAX_CONSECUTIVE_ERRORS} consecutive errors — aborting.\n"
                    f"Last error: {e}"
                )
            wait = min(wait * 1.5, POLL_INTERVAL_MAX)
            continue  # Skip status check and retry

        # ── Status check ─────────────────────────────────────
        print(f"      [{mins:02d}:{secs:02d} elapsed] Status: {result.status}")

        if result.status == "completed":
            # Extract the last text output from the agent
            for output in reversed(result.outputs):
                if output.type == "text":
                    report = output.text
                    break
            if report is None:
                sys.exit("Error: status is 'completed' but no text output was found.")
            print("[2/3] Research complete!")
            break

        elif result.status == "failed":
            sys.exit(f"Error: research failed.\nDetails: {result.error}")

        elif result.status == "cancelled":
            sys.exit("Error: research was cancelled.")

        # Exponential back-off (capped at POLL_INTERVAL_MAX seconds)
        wait = min(wait * 1.5, POLL_INTERVAL_MAX)

    else:
        # Reached when the while condition becomes False (timeout)
        sys.exit(f"Error: research did not complete within {TIMEOUT_MINUTES} minutes.")

    # ── Step 3: Save report to a local file ──────────────────
    print("[3/3] Saving report to file...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(
        c if c.isalnum() or c in ("-", "_") else "_"
        for c in TOPIC[:20]
    )
    filename    = f"{timestamp}_{safe_topic}.txt"
    output_path = os.path.join(OUTPUT_DIR, filename)

    header = (
        f"# Deep Research Report\n"
        f"# Generated     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# Topic         : {TOPIC}\n"
        f"# Interaction ID: {research_id}\n"
        f"{'=' * 60}\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(report)

    print(f"      Saved to : {output_path}")
    print(f"      Size     : {len(report):,} characters")
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()