"""
DH Rugby Stats — Clip Exporter v3
====================================
Reads a saved session JSON (from DH Rugby Stats app) and uses FFmpeg
to cut clips for tagged events.

Clip timings are read automatically from the active template that was
saved with the session — so Backs Coach, Forwards Coach or Full Match
timings are applied without any manual adjustment.

Requirements:
  - Python 3.7+  (python.org)
  - FFmpeg        (ffmpeg.org — or: brew install ffmpeg on Mac)

Usage:
  python3 clip_exporter.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── FALLBACK TIMINGS ──────────────────────────────────────────────────
# Used only if no template data is found in the session file.
# (Sessions saved before v3 of the app won't have templateTimings.)
FALLBACK_TIMINGS = {
    'Try':        (30,  5),
    'Linebreak':  (15, 15),
    'Lineout':    ( 7, 15),
    'Scrum':      ( 8, 15),
    'Turnover':   ( 8, 12),
    'Breakdown':  ( 7, 10),
    'Tackle':     ( 5, 10),
    'Penalty':    (10, 15),
    'Kick':       (10, 15),
}
DEFAULT_TIMING = (8, 12)   # fallback if event not in any list


def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    print("\n❌  FFmpeg not found.")
    print("    Mac:     brew install ffmpeg")
    print("    Windows: https://ffmpeg.org/download.html\n")
    return False


def fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def sanitise(s):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in str(s)).strip()


def parse_timestamp(ts):
    parts = str(ts).split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return float(ts)


def cut_clip(video_path, start_sec, end_sec, output_path):
    start    = max(0, start_sec)
    duration = end_sec - start
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start),
        '-i', str(video_path),
        '-t', str(duration),
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-crf', '23',
        '-preset', 'fast',
        '-movflags', '+faststart',
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def pick_from_list(prompt, options, allow_all=True):
    print(f"\n  {prompt}")
    if allow_all:
        print(f"    0. All")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    while True:
        raw = input("\n  Enter number: ").strip()
        if raw == '0' and allow_all:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Please enter a valid number.")


def get_timing(event_label, template_timings):
    """
    Look up pre/post roll for an event label.
    1. Check template timings from session (highest priority)
    2. Fall back to built-in defaults
    3. Fall back to DEFAULT_TIMING
    """
    if event_label in template_timings:
        t = template_timings[event_label]
        return (t['pre'], t['post'])
    return FALLBACK_TIMINGS.get(event_label, DEFAULT_TIMING)


def main():
    print("\n╔══════════════════════════════════════════════╗")
    print("║   DH Rugby Stats — Clip Exporter  v3         ║")
    print("╚══════════════════════════════════════════════╝\n")

    if not check_ffmpeg():
        input("Press Enter to exit...")
        sys.exit(1)

    # ── Session JSON ──────────────────────────────────────────────────
    print("Step 1: Session JSON file")
    json_path = input("  Drag your .json session file here: ").strip().strip('"').strip("'")
    if not os.path.isfile(json_path):
        print(f"  ❌  File not found: {json_path}")
        input("Press Enter to exit...")
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        session = json.load(f)

    all_tags        = session.get('tags', [])
    match           = session.get('match', {})
    home            = match.get('home', 'Home')
    away            = match.get('away', 'Away')
    date            = match.get('date', '')
    template_name   = session.get('templateName', 'Unknown')
    template_timings = session.get('templateTimings', {})

    print(f"\n  ✅  {home} v {away} ({date}) — {len(all_tags)} tags loaded")
    if template_timings:
        print(f"  📋  Template: {template_name}")
        print(f"  ⏱   Timings loaded from template ({len(template_timings)} events):")
        for label, t in sorted(template_timings.items()):
            print(f"        {label:<22} {t['pre']}s before → {t['post']}s after")
    else:
        print(f"  ⚠️   No template timings in this session — using built-in defaults.")
        print(f"       (Re-save your session in the app to include template timings.)")
    print()

    # ── Video file ────────────────────────────────────────────────────
    print("Step 2: Video file")
    video_path = input("  Drag your video file here: ").strip().strip('"').strip("'")
    if not os.path.isfile(video_path):
        print(f"  ❌  File not found: {video_path}")
        input("Press Enter to exit...")
        sys.exit(1)
    print(f"  ✅  {os.path.basename(video_path)}\n")

    # ── Loop: run filters again with same files ───────────────────────
    while True:
        run_filters(all_tags, video_path, home, away, date, template_timings)
        again = input("\n  Run again with same files? (y / Enter to exit): ").strip().lower()
        if again != 'y':
            print("\n  Goodbye!\n")
            break
        print("\n" + "─" * 50)
        print("  New filter run — same session & video")
        print("─" * 50)


def run_filters(all_tags, video_path, home, away, date, template_timings):

    # ── Filter: Team ──────────────────────────────────────────────────
    print("─" * 50)
    print("Step 3: Filters\n")

    teams = sorted(set(t.get('teamLabel', '') for t in all_tags if t.get('teamLabel')))
    selected_team = pick_from_list("Filter by team:", teams, allow_all=True)
    filtered = all_tags if not selected_team else [t for t in all_tags if t.get('teamLabel') == selected_team]
    print(f"  → {len(filtered)} tags after team filter")

    # ── Filter: Category ──────────────────────────────────────────────
    cats = sorted(set(t.get('eventLabel', '') for t in filtered if t.get('eventLabel')))
    selected_cat = pick_from_list("Filter by event category:", cats, allow_all=True)
    filtered = filtered if not selected_cat else [t for t in filtered if t.get('eventLabel') == selected_cat]
    print(f"  → {len(filtered)} tags after category filter")

    # ── Filter: Detail outcome ────────────────────────────────────────
    selected_detail = None
    details = sorted(set(t.get('detail', '') for t in filtered if t.get('detail')))
    if details:
        selected_detail = pick_from_list("Filter by detail/outcome:", details, allow_all=True)
        if selected_detail:
            filtered = [t for t in filtered if t.get('detail') == selected_detail]
            print(f"  → {len(filtered)} tags after detail filter")

    if not filtered:
        print("\n  ⚠️  No tags match your filters. Nothing to export.")
        return

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n  ✅  Exporting {len(filtered)} clips:")
    print(f"      Team:   {selected_team or 'All teams'}")
    print(f"      Event:  {selected_cat or 'All events'}")
    print(f"      Detail: {selected_detail or 'All outcomes'}")

    print(f"\n  Clip timings that will be used:")
    cats_to_export = sorted(set(t.get('eventLabel', '') for t in filtered))
    for cat in cats_to_export:
        pre, post = get_timing(cat, template_timings)
        source = '(from template)' if cat in template_timings else '(default)'
        print(f"    {cat:<24} {pre}s before → {post}s after  {source}")

    override = input("\n  Override all timings? (y / Enter to keep): ").strip().lower()
    override_timing = None
    if override == 'y':
        pre_in  = input("  Pre-roll seconds for all clips:  ").strip()
        post_in = input("  Post-roll seconds for all clips: ").strip()
        if pre_in.isdigit() and post_in.isdigit():
            override_timing = (int(pre_in), int(post_in))
            print(f"  ✅  Override set: {override_timing[0]}s / {override_timing[1]}s")
        else:
            print("  Invalid — using template/default timings.")

    # ── Output folder ─────────────────────────────────────────────────
    video_dir    = os.path.dirname(os.path.abspath(video_path))
    match_folder = sanitise(f"{home}_v_{away}_{date}") or "clips"
    sub_folder   = "_".join(filter(None, [
        sanitise(selected_team  or ''),
        sanitise(selected_cat   or 'All'),
        sanitise(selected_detail or '')
    ])) or "All_Clips"
    output_dir = os.path.join(video_dir, 'DHRugby_Clips', match_folder, sub_folder)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n  Output folder:\n  {output_dir}\n")

    # ── Export ────────────────────────────────────────────────────────
    print("─" * 50)
    success = 0
    fail    = 0

    for i, tag in enumerate(filtered, 1):
        cat      = tag.get('eventLabel', 'Unknown')
        ts       = parse_timestamp(tag.get('videoSec', 0))
        detail   = sanitise(tag.get('detail', ''))[:40]
        player   = tag.get('player', '')
        zone     = sanitise(tag.get('zone', ''))
        team_lbl = sanitise(tag.get('teamLabel', ''))
        ts_str   = tag.get('timestamp', '').replace(':', '.')
        note     = sanitise(tag.get('note', ''))[:30]

        pre, post = override_timing if override_timing else get_timing(cat, template_timings)

        # Filename
        parts = [f"{i:03d}", ts_str, sanitise(cat), detail]
        if player: parts.append(f"No{player}")
        if zone:   parts.append(zone)
        filename = "_".join(p for p in parts if p) + ".mp4"
        filename = filename.replace(' ', '_')[:120]
        output_path = os.path.join(output_dir, filename)

        print(f"  [{i:02d}/{len(filtered)}] {tag.get('timestamp')} {team_lbl} — {cat} — {tag.get('detail','')[:40]}")
        if note:
            print(f"           📝  {note}")

        if cut_clip(video_path, ts - pre, ts + post, output_path):
            print(f"           ✅  {filename}")
            success += 1
        else:
            print(f"           ❌  Failed")
            fail += 1

    # ── Done ──────────────────────────────────────────────────────────
    print("\n" + "─" * 50)
    print(f"\n  ✅  {success} clips exported successfully")
    if fail:
        print(f"  ❌  {fail} clips failed")
    print(f"\n  Saved to:\n  {output_dir}\n")


if __name__ == '__main__':
    main()
