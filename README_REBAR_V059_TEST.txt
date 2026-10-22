GO Structural Workspace + IngeTrazo v0.5.9 + Rebar LOD integration test
=========================================================================

This integration branch bundles Thai BIM Toolkit 0.21.0 as
plugins\thai_bim. IngeTrazo loads bundled plugins before the user plugin
directory, so this test uses the branch copy without overwriting
%APPDATA%\ingetrazo\plugins\thai_bim.

Extension API compatibility: Thai BIM uses API 2; IngeTrazo v0.5.9 exposes
API_VERSION = 2.

Recommended launcher:
    Start_GO_v059_Rebar_Test.cmd

IngeTrazo v0.5.9 + GO Rebar LOD source test
================================================

BASE
----
This branch starts from the exact upstream IngeTrazo v0.5.9 release commit:
24e7ada6df9f0b4f5f761f287aaade9e40e6728c

It is NOT the older 0.5.7 source-test base.

RUN ON WINDOWS
--------------
1. Extract the complete branch ZIP to a writable folder, for example:
   C:\GO-Dev\IngeTrazo-v059-Rebar
2. Double-click Start_Rebar_v059_Test.cmd.
3. The first run creates .venv-rebar and installs the limited test dependencies.
4. A separate source window starts with --new-window. It does not replace
   C:\Program Files\IngeTrazo and does not uninstall the packaged v0.5.9.
5. In the new window open a NEW document.
6. Extensions > Python Console > Run script file:
      scripts\GO_RB9_Stirrup_Fix.py
7. Then run:
      scripts\GO_RB9_LOD_Check.py
8. Return focus to the viewport and orbit/pan/zoom or preview-move a bar.

EXPECTED CHECK
--------------
HOST_LINE_RENDERER: AVAILABLE
CENTERLINE_DATA: 24/24 bars with at least 2 stored points
SIGNED_PATHS: 24/24
ELIGIBLE_FOR_LINES: 24/24
INTERACTION_BLOCKERS: none
FROZEN_APPLICATION: False

The application itself should report version 0.5.9.

ENTITY INFO
-----------
A blue RB9 should report about 68 centreline points and 9 mm diameter.
A DB12 should report 2 centreline points and 12 mm diameter.
Line display should say Ready for interaction.

SCOPE
-----
The limited test requirements omit the Git-based OpenSKP package and pytest.
This launcher is for native modelling and the rebar/viewport test. It does not
claim full release packaging coverage. Use the repository's normal requirements
and release build process for a complete distribution.

The line LOD is display-only. Picking, BIM quantities, undo, native persistence
and export retain the solid mesh. Repeated bars share prototype meshes and use
per-instance transforms.
