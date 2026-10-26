"""VibeEdit Windows MVP core package (stdlib only; FFmpeg is the only
external tool, used for probing and rendering).

This is a Windows re-implementation of the BashCut/VibeEdit timeline
model. It is NOT the original Swift code: SwiftUI/AppKit/AVFoundation
cannot run on Windows, so the timeline, project format and edit
operations are re-implemented here in Python, and rendering is done
with FFmpeg. See VibeEdit/docs/windows-port.md for the mapping.
"""

__version__ = "0.1.0"
