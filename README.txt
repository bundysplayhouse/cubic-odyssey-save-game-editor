Cubic Odyssey Save Editor v1.34
================================

Guided Capture action dropdown
------------------------------
Select a common action from the dropdown before Capture Before. Choices cover
Qbits, recipes, ship blueprints, skills, equipment, ship modules, containers
and quests. You can also type a custom action or add details such as an amount
or item name. These are experiment suggestions, not verified field mappings.
The action remains locked after Before and is restored when you resume.
Existing sessions with custom descriptions remain compatible. New Experiment
clears the selection so you can choose the next action deliberately.

Extract the Windows ZIP and run Cubic_Odyssey_Save_Editor.exe with its runtime
folder beside it. Previous documentation follows.

Cubic Odyssey Save Editor v1.33
================================

Guided before/after capture
---------------------------
Open Save Difference Lab > Guided Capture. Select your slot, describe one
action, and click Capture Before with the game saved and fully closed. Play
the game, perform that action, save and close it, then click Capture After.
The same slot is captured automatically and the Difference Lab shows results.

The slot is locked after Before. The session survives closing the editor.
New Experiment resets the workflow but keeps all completed capture files.
Captures and action records are stored in .editor_data/guided_captures; the
current session is in .editor_data/guided_session.json beside the editor.
Capture After can be repeated. Completed captures survive a comparison error;
reopen the guide to resume, or select their folders in Difference Lab.

All game files within the chosen slot are captured and verified. Files outside
the slot, including account-wide data, are not captured. Editor backups and
history are excluded. Captures read disk files, not staged editor changes.
Keep the game closed during captures so its files remain stable.
These captures provide evidence; they do not enable unproven gameplay writes.
The existing Guided Experiment window can record Qbits balances and detailed
observations using the automatically selected A/B captures.

Extract the Windows ZIP and run Cubic_Odyssey_Save_Editor.exe with its runtime
folder beside it. Previous documentation follows.

Cubic Odyssey Save Editor v1.32
================================

Save Inspector: Scan All Files restored
--------------------------------------
Select your slot and click Scan All Files. The scan includes .sav, world files
and other game files within that slot, including nested folders. Editor backup
and history files are excluded. Unknown formats show a warning, and damaged
files show an error without stopping the remaining scan. No saves are changed.
Export Inspection Report now includes the scan results and full source paths.
The existing single-file inspector, pending edits and backups remain available.

Extract the Windows ZIP and run Cubic_Odyssey_Save_Editor.exe. Keep its runtime
folder beside it. The source ZIP is also supplied.

Previous documentation follows.

Cubic Odyssey Save Editor v1.31
================================

Difference Lab: direct file comparison and folder-picker fix
------------------------------------------------------------
Extract the Windows ZIP and run Cubic_Odyssey_Save_Editor.exe, or use the source
ZIP with Python as before. Keep the runtime folder beside the Windows editor.

TO COMPARE SAVE FILES
1. Click Choose File A and select the BEFORE save file.
2. Click Choose File B and select the AFTER save file.
3. Click Compare A / B.

You can select .sav, .vx and .vw3 files directly. All files is also available
in the picker for metadata, backup copies or other file types. Before/after
files may have different filenames; they are compared as one pair, rather than
being misreported as one removed file and one added file. A recognized original
filename supplies schema labels when the other copy has been renamed.
Different known save types are rejected to avoid confusing their schemas.

Use separate before/after copies. Selecting the same live file twice cannot
recover its earlier contents and is rejected with an explanation. Source files
are never modified by comparison. Identical copies show No differences found.

FOLDER COMPARISON FIX
Choose Folder A/B accepts ordinary save folders OR editor snapshot folders.
Previously it allowed choosing any folder but then required snapshot.json;
that mismatch caused the missing-folder/file error on ordinary save folders.
Ordinary folders are now captured automatically before comparison. Existing
snapshot folders and their snapshot.json files remain supported. Choose either
two files or two folders/snapshots; mixed file/folder pairs get a clear message.
Missing inputs are identified as A or B and show the exact missing path.

Imported comparison copies are retained in .editor_data/comparisons beside the
editor. This keeps bookmarks and Field Mapping evidence tied to the bytes that
were compared, even if the original files later change. Snapshot evidence stays
read-only. Complete folder captures must be stored outside the source folder.
Guided Experiment uses the same input handling and records the retained copies.

VALIDATION
Tests cover the original ordinary-folder failure, direct and renamed save files,
existing snapshots/manifests, voxel files, unchanged inputs, missing/mixed/same
inputs, file-picker callbacks, immutable bookmark evidence, snapshot write
prevention and compact layout. The Windows bundled-runtime startup is checked.

Previous documentation follows. v1.31 Choose File / Choose Folder controls
supersede older instructions that require snapshots for every comparison.

Cubic Odyssey Save Editor v1.30
================================

Difference Lab refinement and guided validation
-----------------------------------------------
Windows: extract the complete ZIP and run Cubic_Odyssey_Save_Editor.exe.
Python, Tk and Zstandard are bundled. The source ZIP remains available.

DIFFERENCE LAB
Use Known fields, Unknown fields, Added objects / fields, Numeric changes or
Bookmarked to narrow the evidence. Search searches evidence values as well as
names/paths. Only changed files is on by default; turn it off to see all files.
Warnings remain visible regardless of the evidence filter. Numeric candidates
remain unproven; raw bytes that resemble floats/integers are not field mappings.

Select an evidence row and Toggle Bookmark to retain/remove it. Open Bookmarks
reopens its snapshot pair and selects the relevant file. Bookmarks persist in
.editor_data/bookmarks.json and retain snapshot references. Keep those snapshot
folders available; moving/deleting them prevents reopening the comparison.

Open in Field Mapping inspects the actual snapshot bytes, locates the matching
field and attaches the source snapshots and before/after evidence to the note.
These rows are read-only even if the corresponding live field has a writer.
Save Mapping Evidence to retain the note. Scan Fields Across Slots explicitly
reloads live data before supported editing can resume.

GUIDED EXPERIMENTS — IN-GAME WORK STILL REQUIRED
No real Qbits, recipe-unlock, ship-blueprint or clone-validation captures were
supplied for this release. Their actual gameplay validation is NOT complete.
New Qbits/blueprint writers remain disabled; clone registration is unverified.
The Guided Experiment dialog records the observations needed for those tasks:

1. Qbits: choose the complete account save root, save/close the game, and capture
   A. Note the exact visible balance. Earn or spend a known amount, save and
   close the game, then capture B and note the new balance. Compare A/B, open
   Guided Experiment, select Qbits, describe the action and enter both balances.
   Save Experiment Record lists matching numeric evidence as unproven candidates.
   Repeat with a second independent amount before treating a field as mapped.
2. Recipe: capture before/after unlocking exactly one recipe. Record its name or
   identifier and the action. Do not combine it with the ship-blueprint test.
3. Ship blueprint: separately capture before/after saving or unlocking one ship
   blueprint. Record which action occurred and its blueprint identifier/name.
4. Clone: record the clone path and tick only checks actually observed in-game:
   appears, loads, saves independently, survives restarting the game, and leaves
   the original slot unchanged. This records user observations, not automatic
   certification or a change to the editor's supported writer list.

Each record is saved under .editor_data/experiments with its snapshot paths,
changed files, action, observations and (for Qbits) exact-balance candidates.
Both snapshots are revalidated and compared before the record is stored.
Provide the snapshot directories and experiment JSON when continuing mapping.
Captures read disk, not pending edits; keep the game closed for each capture.

GUI / LANGUAGE
New navigation, core instructions, filters, experiment controls, headings and
operation states have expanded translations across all 13 supported languages.
Raw game identifiers, serializer tokens, detailed technical diagnostics and
some About/status text remain English. Arabic/Urdu layout is not fully mirrored.
Save-edit controls now say Stage or Review / Stage when queuing an edit. Apply
Pending remains the final action that writes files. Appearance settings still
apply immediately, as before.

Capture, comparison and clone jobs report file counts and phases in a global
progress bar. Field scans run in the background with per-file progress. During
work, progress messages stay on the GUI thread; closing waits for completion.

VALIDATION
Automated tests cover capture progress, filters, bookmark persistence, snapshot
mapping provenance and write prevention, live field scans, guided records,
candidate matching, all 13 languages, and normal/compact window layouts.
Synthetic balance matches are tests of the helper, not discoveries of Qbits.
Existing pending edits, backup history and recovery journal behavior are retained.

Previous documentation follows; v1.30 labels and investigation controls supersede
their older descriptions below.

Cubic Odyssey Save Editor v1.29
================================

WINDOWS PACKAGE
Extract the complete Windows ZIP into a writable folder, then run
Cubic_Odyssey_Save_Editor.exe. Keep its runtime folder and Python modules beside
it. Python, Tk and Zstandard are included; no separate installation is needed.
This is a portable Windows x64 folder build, not a single-file executable.
The source ZIP remains available with the original .bat launcher.

SAVE DIFFERENCE LAB
Choose the complete account save root (the folder containing global stats and
the numbered-slot tree). Capture Snapshot A with the game closed. Perform one
action in-game, save and close the game, then capture Snapshot B and Compare.
The capture includes all game files, including .sav, .vx, .vw3 and metadata.
Editor history, journals and .bak/.prev files are excluded. Capture reads disk,
not pending edits. It verifies the file list and hashes again before publishing
the snapshot manifest. A changing source causes capture to fail.
Snapshots are stored under .editor_data/snapshots beside the editor. Open A/B
can reload those directories later. Captures must be outside the source tree.
Compare reports added/removed/changed/unchanged files, raw/decoded sizes,
serializer paths, known skill/vital/item values, byte ranges and candidate
strings/numbers. Double-click evidence to see full text; export the report as
JSON. Corrupt or unmapped payloads retain byte evidence with warnings.
Array paths are positional: a shifted index is not proof of a new object ID.
Large reports are bounded (4,000 evidence rows per file; 1,000 byte ranges),
with limit notices. Complete original files remain in the snapshot blobs.

SAVE HEALTH / INTEGRITY
The legacy Qbits offset was found to overlap an economy array header in the
supplied saves. That control is now disabled until currency is correctly mapped.
The selected slot is checked at load/refresh and after applying edits. Manual
Scan Save Health also checks global stats/blueprints/account metadata, expected
slot files, associated .bak/.prev files, dated backup hashes, stale pending
baselines and interrupted journals. Known schemas validate their trees/types;
custom structures and opaque world data get Warning, not a false Healthy.
Duplicate field/entity IDs and unusual skill/vital values are flagged. Repeated
item identifiers are legitimate stacks and are not treated as corruption.
Failed validation of a proposed file blocks its transaction before writing.
Healthy means available checks passed, not proof of every in-game invariant.

PERSISTENT TRANSACTIONS
Apply Pending stores originals and expected hashes in .editor_data/transactions
before replacing files. Each replacement is flushed and journalled. On Windows,
replacement uses write-through rename. Startup detects incomplete journals and
offers restoration of the originals, showing the affected paths first.
Recovery preflights all current hashes; outside changes prevent automatic
recovery. Apply is blocked until unresolved journals are handled. Ordinary
write failures attempt rollback immediately; failed recovery retains the journal.
This improves crash recovery but cannot guarantee against hardware/filesystem
failure or corrupted/missing journal storage. Keep .editor_data with the editor
when moving/upgrading it. Journals, snapshots and dated backups are not pruned
automatically and consume disk space.

SCHEMA REGISTRY / FIELD MAPPING
save_schema.py centralizes known file definitions, field types/names/decoders,
validators and explicit writer bindings. Existing proven parsers are retained
as adapters rather than rewritten all at once. Save Inspector now displays
registered names automatically. The mapping page scans a chosen save filename
across all discovered slots, displaying field paths, offsets, types and values.
Save Unknown/Suspected/Verified notes with executable/config references,
experiment report paths and in-game observations. Notes persist in
.editor_data/field_notes.json. Suspected/Verified requires evidence text.
Edit Known Field is generated from explicit validated skill/vital bindings and
uses the existing setters, bounds and pending workflow. Marking an unknown field
Verified does not create a writer or bypass validation. Unknown paths, especially
array indices, may change meaning after structural edits; recheck the evidence.

WORLD ENTITIES
Scan/filter groups objects by world file and exposes saved IDs, type strings,
positions and their contained items. Category labels are identifier-based hints,
not verified behavioral types. Contained quantity and supported float condition
edits reuse the existing world-item writer and stage changes for review.
Coordinates, NPC state, portal state and other unmapped entity state are not
newly writable in this release.

CLONE SELECTED SLOT
Choose a destination parent folder. The editor uses the first free numbered
folder, copies the selected slot's game files, validates supported saves and
verifies source/copy hashes before publishing the clone. It never overwrites an
existing slot or changes global/account files. Pending edits must be applied or
discarded first. An interrupted clone may leave a hidden .clone-* working copy.
Metadata is copied unchanged because no slot-number rewrite has been proven.
This provides an editor sandbox. In-game registration/selection of cloned slots
still needs validation; the editor does not invent global account registrations.

ADD ITEM
Select a simple item in the desired Player/Ship cargo inventory, then Add Item.
The wizard offers identifiers of the same known config class. It duplicates the
validated template element, substitutes the identifier and sets quantity while
fixing array counts and enclosing lengths. Empty mod arrays are retained;
installed mods and other nested objects are rejected. Condition is inherited
from the template because config durability is not proven to use the same saved
unit. No guessed state stripping or from-scratch item synthesis is performed.
World-container structural insertion is not enabled; existing contained scalar
edits are supported through World Entities.

BLUEPRINT / RECIPE NEXT EXPERIMENTS
The tools are now ready for controlled before/after captures. Capture unlocking
exactly one crafting recipe separately from saving/unlocking one ship blueprint.
The supplied empty BlueprintEntry collection still cannot establish a populated
entry format. No new blueprint/unlock/performance writer has been guessed.
See GAMEPLAY_RESEARCH.txt for prior config evidence and validation steps.

ABOUT / LANGUAGE
About shows editor/runtime versions, supported format coverage, config root,
catalog count and investigation storage. Existing themes and languages remain;
new investigation pages currently use English technical controls and notes.

VALIDATION
All supplied .sav files pass available health checks (some remain Warning where
coverage is partial). Tests cover schema names/writers, complete captures,
decoded and opaque differences, corrupt-payload fallback, persistent apply,
interrupted/conflicted recovery, injected second-file rollback, clone hashes,
template item addition and world objects. GUI checks cover mapping/evidence,
contained-item writes and 22 pages at two window sizes. The isolated bundled
runtime starts Tk/Zstandard and the complete editor. No new gameplay behavior
or cloned-slot registration has been tested in-game.

Previous release documentation follows; v1.29 transaction behavior supersedes
the older non-journalled write implementation.

Cubic Odyssey Save Editor v1.28
================================

Save review, recovery and inventory update
-----------------------------------------
Start with Run_Cubic_Odyssey_Save_Editor.bat (Python with tkinter and the
zstandard package, or the existing zstd command-line fallback, is required).
Select the same save folder and optional extracted configs folder as before.

1. SAVE OVERVIEW shows the selected slot's character name, level, location,
   playtime and full folder path. Values reflect staged edits where applicable.
   Character level prefers the client skill record; metadata is the fallback.
2. Make edits using the existing page controls. They now STAGE changes in
   memory, including config edits and .bak/.prev recovery actions.
3. Open PENDING CHANGES (Ctrl+S). Select each file to see before/after values.
   Select Apply Pending to write the batch, or discard one file/all files.
   Unsubmitted form values are separate from staged edits: use their page's
   Apply or Review / Save button first. Settings and report exports still save
   immediately. Pending edits do not survive closing or a process crash.

The existing single-slot loading workflow remains. Pending rows retain their
full target paths when switching slots. Global stats and configs are identified
separately. Review every listed path before applying a batch that spans slots.
Outside changes to a queued file block apply; discard that file and reload.
Other pages' typed form values survive normal refresh after staging an edit.
Ctrl+R explicitly discards unsubmitted form values after confirmation.

BACKUP MANAGER
Each Apply Pending captures the previous on-disk file in a dated snapshot
beside it, under .cubic_editor_history. Browse the selected slot's history,
global stats history and the configured config tree. Inspect the proposed
changes associated with a snapshot, then Stage Selected Restore and review it
in Pending Changes. Restoration is itself backed up when applied.
Snapshots have SHA-256 integrity checks. Invalid snapshots are skipped/reported.
History starts with this version; old .bak/.prev files are not dated retroactively.
Original .bak files are retained; .prev records the file before the applied
batch. Within a staging session, existing undo controls can also undo staged
steps. Final on-disk .prev represents the pre-batch file.
Failed attempts may leave valid pre-write snapshots describing proposed changes.
Snapshots are retained without automatic pruning. Each file uses a temporary
replacement and read-back verification; reported batch failures attempt to roll
back replaced files. A whole-folder transaction across a power loss is not
guaranteed. Keep the game closed while applying edits, as before.

INVENTORY
Click a column heading to sort ascending/descending. Search across item rows,
filter by config category or container, and use Ctrl/Shift selection followed
by Set Selected Quantities. Group by Container orders rows by their enclosing
inventory array. Container numbers distinguish arrays within the current scan;
they are not permanent in-game IDs. World Items retains its object/location view.

GUI
Window size and main table column widths persist when closing normally.
The title's * and bottom status flag staged files and unsubmitted form edits.
Ctrl+S: review pending; Ctrl+R: reload data; Ctrl+F: inventory search on that
page, otherwise config search. In config dialogs Ctrl+S stages the dialog edit.
Closing with staged changes or dirty forms prompts before discarding them.
23 new navigation/control/overview labels have translations in all 13 supported
languages. Technical notes, detailed status/error messages, config tokens and
some controls still use English; Arabic/Urdu layout is not fully mirrored.

GAMEPLAY RESEARCH
A searchable evidence table shows actual config operations, values, ship flags
and source paths for ship components, equipment bonuses and crafting discovery.
See GAMEPLAY_RESEARCH.txt for findings and the next controlled in-game checks.
New direct performance/bonus/unlock writers remain disabled pending mapping and
in-game validation. Existing proven editing functions remain available.

VALIDATION
Tested using copies of all 11 supplied slots: skill editing, staging/applying,
discard, history integrity, stale-file rejection and injected failure rollback.
World-item quantity/condition regression checks cover 44 world files.
GUI checks cover config stage/apply/undo, inventory batch/filter/sort, restoration,
draft preservation, layout persistence, 17 pages at 3 sizes, and 13 languages
with 4 built-in themes. Gameplay research checks match supplied source values.
These are automated data/widget checks; this release has not been tested in-game.

Earlier release notes follow. Their immediate-save wording is superseded by
the staging workflow above; the underlying fields and editor controls remain.

Cubic Odyssey Save Editor v1.27
================================

Structured item config editing
------------------------------
Double-click an item in Config Lookup, or click Edit Selected Config, to open
labelled fields for maximum stack size, item tier, base price, durability and
recycle value. Only properties already present as unambiguous root numeric
values are enabled. Missing, duplicate or unsupported properties are left for
the Advanced Text Editor; the form does not guess or insert game defaults.

Review / Save shows a before/after diff before writing. Changes retain comments,
spacing, unrelated fields, file encoding and newline convention. Integer and
finite non-negative number checks run before saving. The form's numeric limits
are editor input bounds, not a claim that every value is meaningful in-game.

Undo Last Save and Restore Original share the config's existing .bak/.prev
backups with the text editor. Reload handles external changes; stale saves are
rejected. Advanced Text Editor opens the complete file. Switching to it prompts
before discarding unsaved form changes. The item catalog refreshes after writes.

Config changes affect the selected configs folder. They do not directly rewrite
saved inventory quantities or item condition, and editing an extracted config
copy does not install it into the game. Close the game before editing installed
configs. New form explanations may use English under other interface languages.

Validation
----------
Checked parsing and token-only edits across all 1,340 supplied item configs.
Recognized fields: stack size in 1,337, tier in 1,339, price in 850, durability
in 388 and recycle value in 992 files. Tested nested fields, comments, quoted
text, duplicate properties, invalid numbers and no-op changes. GUI checks passed
for edit/review/cancel/save, disabled missing fields, backup generations,
undo/redo/restore, stale-file rejection and opening the advanced text editor.
Existing text-editor regression checks also passed. No installed configs or
live game saves were changed during development.

Extract and run Run_Cubic_Odyssey_Save_Editor.bat. Copy editor_settings.json
from your previous editor folder to retain themes and language preferences.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.26
================================

Six additional language choices
--------------------------------
Settings > Interface language now also offers:
- Mandarin Chinese, using Simplified Chinese: 中文（简体）
- Hindi: हिन्दी
- Portuguese: Português
- Urdu: اردو
- Bengali: বাংলা
- Modern Standard Arabic: العربية الفصحى

There are now 13 language choices including English. The same 89 translation
keys are populated for all 12 non-English languages. Coverage remains navigation,
Settings labels and common controls/headings; technical explanations, detailed
status/error messages and untranslated controls remain English. Game data and
identifiers are unchanged.

Arabic and Urdu use the existing layout, not a fully mirrored right-to-left
interface. Font availability and complex-script rendering depend on the local
Windows/Tk installation; visual rendering has not been verified on your display.

Tested switching through all 13 languages, retaining pending edits and themes,
preference saving and restart restoration, and Settings scrolling at 960x600.
Verified that every translation key has all 12 non-English entries.

Extract the ZIP and launch Run_Cubic_Odyssey_Save_Editor.bat. Copy your existing
editor_settings.json into the new editor folder to retain your preferences.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.25
================================

Settings page
-------------
A new Settings entry appears at the bottom of the scrolling sidebar.

Appearance:
- Select Light, Dark, Midnight, Cubic Odyssey or your saved Custom theme.
- Start from a built-in palette, edit hex colors or use Choose to open a color
  picker, then click Apply Custom Theme.
- Customize page/input/table backgrounds, text, alternating rows, buttons,
  hover colors, borders, headings, selected text and sidebar colors.
- Restore Base Colors reloads the chosen palette into the form. Click Apply
  Custom Theme to save it. Built-in palettes remain unchanged.

Language:
- English, French, German, Italian, Spanish, Russian and Japanese are available.
- Select the language using its native name; changes apply immediately.
- Initial translation coverage includes navigation, Settings labels and common
  controls/table headings. Technical explanations, detailed status/error
  messages and untranslated controls fall back to English. Game identifiers,
  configuration text, player data and theme names are not translated.
- No external translation service or network connection is used.

Preferences are stored in editor_settings.json beside the editor. It retains
both the custom palette and language independently of the active theme.
Copy that file into a new release folder to keep your preferences. Invalid
preferences fall back to defaults; a write error is reported if the editor
folder is not writable. Settings do not modify game configs or save files.

Validation:
Tested all seven language selections, switching without losing pending edits,
custom palette creation, rejection of invalid colors, preservation of built-in
palettes, independent preference persistence, restart loading and Settings
scrolling at 960x600. Config editing, review/save/cancel, reload, catalog refresh,
stale-file rejection and backup recovery regression checks passed.
Native desktop screenshot capture remains unavailable; font appearance and
translation wording benefit from checking on your display.

Extract this ZIP and run Run_Cubic_Odyssey_Save_Editor.bat as before.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.24
================================

Clearer Save Inspector labels
----------------------------
Experiment Lab is now named Save Inspector, including sidebar navigation,
page title, prompts and references from other pages.

Analyze Save -> Inspect Selected File
Scan All Files -> Scan Selected Slot
Export JSON -> Export Inspection Report

This is a naming update only. Inspection, JSON exports, editing, themes and
backup behavior are unchanged. The export remains a JSON file.

Extract and run Run_Cubic_Odyssey_Save_Editor.bat as before. To retain your
chosen theme in a new folder, copy editor_settings.json from your old editor.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.23
================================

Selectable themes
-----------------
Use the Theme dropdown in the top bar on any page:
- Light: the existing pale interface with navy and teal accents.
- Dark: charcoal panels with soft teal highlights.
- Midnight: deep blue panels with periwinkle highlights.
- Cubic Odyssey: dark metallic panels, bright cyan selection, and amber
  headings inspired by the supplied in-game screenshot.

Themes switch immediately without reloading saves, changing the selected slot,
resetting table selection or discarding unsaved edits. Tables, alternating rows,
forms, sidebars, scrollbars, dropdown lists and config text/review windows follow
the selected palette. Native Windows message boxes/file pickers may continue
to follow Windows settings.

Your choice is saved to editor_settings.json beside the editor script and loaded
on the next launch. Keep this file when moving/upgrading the editor to retain the
preference. Missing or invalid preferences default to Light. If the folder is
not writable, the selected theme still applies to this session and a message
explains that it could not be remembered.

Validation: all four palettes tested on existing and newly opened widgets,
including config text windows and dropdown lists; verified that unsaved config
and skill edits, slot and table selection survive theme switching. Preference
persistence, restart loading and invalid-preference fallback passed. Existing
editing and backup behavior is unchanged. Theme appearance has not been visually
verified on the user's display; native desktop screenshot capture is unavailable
in this environment.

Extract and run Run_Cubic_Odyssey_Save_Editor.bat as before.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.22
================================

GUI refresh, based on v1.21
--------------------------
- Sidebar navigation replaces the crowded tab strip; the sidebar scrolls when
  window height is limited.
- The active save-slot selector and Refresh data button are available on every
  page. The Experiment Lab selector stays synchronized with them.
- A navy/teal theme, Segoe UI typography, consistent button and input spacing,
  clearer headings, taller table rows and alternating row colors.
- Every data table, including selection dialogs, now has vertical and horizontal
  scrollbars. Column widths remain readable instead of squeezing to fit.
- Every main page has horizontal and vertical scrolling for overflowing forms,
  instructions and action rows. Use Shift + mouse wheel to scroll horizontally.
- Inventory instructions and action buttons occupy separate, aligned rows.
- Initial window size adapts to the screen; the minimum is 960 x 600.

Existing save editing, config editing and .bak/.prev behavior are retained.
GUI tests checked all 12 pages at 1480x900, 1100x700 and 960x600, table scrolling,
sidebar scrolling and slot synchronization. The config edit/review/save/cancel,
reload, catalog refresh and backup recovery tests passed with the new UI.
Desktop screenshot capture was unavailable; visual appearance still benefits
from checking on your display, particularly with custom Windows scaling.

Extract the ZIP and run Run_Cubic_Odyssey_Save_Editor.bat as before.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.21
===============================

Editable Config Lookup (built from the working v1.20)
----------------------------------------------------
Select an item in Config Lookup, then click Edit Selected Config or double-click
the row. The window shows the complete ItemCfg text and its exact file path.
Edit any properties, click Review / Save, inspect the diff, then Save Changes
with Backups. Cancel returns to your unsaved edits. Reload File discards edits
only after confirmation. Closing an edited window also asks before discarding.

The editor writes to the configs folder you selected when launching it. Changes
to a live game config affect all saves using that installation, not just the
selected save slot. Close the game before editing its installed configs.
Editing an extracted copy does not install it into the game. Keep the folder
structure when copying modified configs into the appropriate game location.

Each config gets its own .cfg.bak original baseline and .cfg.prev previous
version. Undo Last Save swaps back to the previous version; repeating it redoes
the change. Restore Original restores .bak. Both actions show a diff first.
These backups are separate from the save-file backups. Existing .bak files
are retained. File changes made externally require Reload File before saving.

Basic validation checks the ItemCfg block, balanced braces, closed quoted
strings and comments, and null characters. This is not full game-schema
validation: values, identifiers, asset paths and cross-file references remain
your responsibility. Use the game's existing syntax. UTF-8 files (with or
without a BOM) and their original LF/CRLF line endings are preserved.

The item catalog and dependent item metadata refresh after saving or restoring.
Reload Catalog also picks up external changes. Config Lookup still lists item
configs; this release does not add other configuration categories.

Validation
----------
- All 1,340 supplied item configs passed validation and byte-identical encoding
  round trips.
- Tested invalid text, quoted/commented braces, BOM/CRLF, stale-file rejection,
  no-op writes, original/previous backups, undo/redo and original restore.
- Tested the GUI edit, review, save, cancel, reload and catalog-refresh flow on
  an isolated config copy.
- Re-ran character-skill editing checks across all 11 supplied save slots.
- No installed game configs or live saves were changed during development.

Extract this ZIP and launch Run_Cubic_Odyssey_Save_Editor.bat as before.
Python/Tkinter and Zstandard requirements are unchanged.

Earlier release notes follow.

Cubic Odyssey Save Editor v1.20
===============================

New in v1.20: editable character skills
---------------------------------------
The Character Skills tab edits the selected slot's character level and nine
individual skills: Knighthood, Building, Mining, Crafting, Melee, Ranged,
Corruption, Trading and Space Combat. Each has an editable level and progress
percentage toward the next level. These are the character's own skills;
the existing global account class levels are separate.

Select your slot in Experiment Lab, open Character Skills, change the values,
and click Apply Character Skills. Review the proposed changes, then save.
Progress 50 means halfway to the next level, not 50 total XP. Enter a percentage
from 0 to below 100. Levels are limited to 1-30, matching the supplied executable
and its default skill cap. Setting a skill to level 30 clears its progress,
as the game does. This version does not support a modded level cap.

Changing Character level updates both its skill record and the runtime-level
copy in the same client-state save. The level shown in the game's save-selection
metadata updates when the game next saves. The editor does not simulate gameplay
level-up events, rewards, achievement unlocks or account-stat updates.

All writes retain the working single-slot workflow, .bak original baseline and
.prev previous version. Backups are shared with inventory, ships and vitals
because these values live in the same 93_client_state.sav. Recovery restores the
entire file; undo again redoes the change. Reload after editing externally.

Correction to earlier story interpretation
-------------------------------------------
93_meta.sav field 13 is a character-level snapshot, not a TaskCfg story ID.
The Save Slot Details label is corrected, and Quests / Story now presents the
story catalog without claiming that a matching number is the active task.
Generated quest reward/removal editing remains available. Any older release
notes below describing that field as story progression are superseded here.

Validation
-----------
Mapped the ten skill records, skill names, level cap and fractional progress
through the supplied executable's serializers, enum table and level-up code.
Edited all 20 values on copies of all 11 supplied client-state saves; checked
the character-level mirror, complete serialized validation, unchanged file
length, bytes outside the intended fields, inventory/vitals preservation and
Zstandard compression round trips. Tested invalid values/types, cap progress
normalization, GUI Apply, no-op/stale writes, shared backups, undo/redo, restore,
slot switching and missing files, including use without the configs folder.
Source saves were not modified. In-game behavior awaits user testing.

Run Run_Cubic_Odyssey_Save_Editor.bat as before. Extract the ZIP first.
Existing Python/Tkinter and Zstandard requirements are unchanged.

Historical release notes follow (v1.20 corrections above take precedence).

Cubic Odyssey Save Editor v1.19
===============================

New in v1.19
------------
Character Vitals is a new tab for the selected save slot. It edits:
- Current health
- Current stamina / energy
- Saved maximum stamina / energy
- Current shield
- Saved maximum shield

Fill Stamina and Shield copies the displayed maximums into the current-value
boxes. Click Apply Character Vitals to save the changes. These controls work
without the optional configs folder and refresh when you switch save slots.

Edits use the complete client-state validator, reject invalid/non-finite
values and stale saves, preserve .bak/.prev recovery copies, and verify the
compressed file after writing. Current stamina/shield cannot be set above
their saved maximums. Maximums may be recalculated by the game from equipment
or other bonuses; this is not a permanent maximum-stat override. Maximum
health and additional skill/XP editing are not included in this release.

The recovery buttons restore the entire 93_client_state.sav, including
inventory and ships. Its .bak and .prev files are shared with those editors.
Undo can be used again to redo; original restore leaves the replaced file
in .prev.

Validation for v1.19
--------------------
- Mapped the stamina/shield pairs through the supplied executable's character
  and resource serializers, including current-versus-maximum ordering.
- Parsed and edited all five values on copies of all 11 supplied slots.
- Checked unchanged decoded length, preservation of bytes outside the edited
  fields, complete structural validation, and Zstandard round trips.
- Checked invalid values, stale-save rejection, and no-op writes.
- Tested GUI Apply/Fill, .bak/.prev generations, undo/redo, original restore,
  slot switching, missing client-state handling, and use without configs.
- Original source saves were not modified. In-game behavior still needs the
  user's confirmation, particularly whether saved maximums are retained.

Earlier release notes follow.

New in v1.18
------------
The World Items tab now includes a Location / container column. It reads the
world entity that owns each item record and shows its saved object identifier,
entity ID, and 3D position. This distinguishes separate chests or boxes that
contain the same item. One supplied entity has no deployable identifier, so
the editor labels it by its saved entity tag and position.

Location mapping was checked on all 8,340 world item records in the 44 world
saves across the 11 supplied slots. The GUI search, slot refresh, quantity and
condition edits, .bak/.prev backups, undo, and original restore were checked
again on an isolated copy. The supplied saves were not modified.

The v1.17 editing features and earlier notes below are retained.

New in v1.17
------------
World Items can now edit two fixed-size InventoryItem fields in the selected
slot's numbered world saves:
- Set Quantity (field 3, unsigned 32-bit integer)
- Edit Condition / Charge (field 5, only when stored as a 32-bit float)

Each edit reloads the chosen world save, confirms that the item's identifier,
offset and original value still match, changes only the selected four-byte
field, reparses the item, checks top-level save framing, writes through the
existing .bak/.prev backup path, and verifies the compressed save by reading
it back. It also refuses to overwrite a world save that changed while the edit
dialog was open. The World Items tab has dedicated undo (.prev) and original restore
(.bak) buttons; choose an item or a specific world file before using them.

In v1.17 the World Items tab did not yet display each record's owning world
object. v1.18 adds that location information. Item ID
replacement, duplication, and deletion in world saves remain unavailable
because they would resize outer structures that have not been fully mapped.

Validation for v1.17
--------------------
- Tested quantity edits and float condition edits in memory on every one of
  the 44 numbered world saves across all 11 supplied slots.
- Verified exact byte changes, unchanged decoded length, reparsing, and
  Zstandard round trips on each test edit.
- Tested GUI editing, two backup generations, undo, and original restore on
  an isolated copy of a supplied world save. Original source saves were not
  edited.
- Confirmed the stale-save guard rejects an overwrite and leaves the file
  unchanged.

The v1.16 and earlier features and notes below are retained.

New in v1.16
------------
1. World Items tab
   - Reads item records in the selected slot's numbered 93_3*.sav world files.
   - Shows source file, item identifier, quantity, condition/charge, decoded
     byte offset, and config type/tier when configs are available.
   - Includes item search and a source-file filter.
   - In v1.16 this tab was read-only. v1.17 adds the fixed-size edits above.

2. Inventory safety correction
   - Inventory / Equipment only displays records from 93_client_state.sav.
     If that file is absent or cannot be decoded, world records are no longer
     used as a fallback in the editing tab.

Validation for v1.16
--------------------
- Parsed all four numbered world saves in each of the 11 supplied slots:
  731 to 777 item records per slot.
- Confirmed the editor GUI loads slot 0 with 770 world records and 32 player
  inventory records; tested search, source-file filtering, and slot refresh.
- Confirmed a slot missing 93_client_state.sav shows no editable player items,
  while its world records remain visible in the read-only tab.
- On an isolated copy, confirmed quantity editing preserves the original
  .bak and updates .prev to the immediately preceding save after each edit.
- Syntax checked the complete editor and confirmed Zstandard round trips for
  all 44 supplied world saves.
- World scanning never writes to save files or creates recovery copies.

The v1.15 features and notes below are retained.

New in v1.15
------------
1. Quests / Story tab
   - Parses the selected slot's 93_quests.sav as a PlayerQuest array.
   - Maps the generated quest-type enum:
       0 RESOURCE_REQUEST
       1 PLANET_CHART
       2 SYSTEM_CHART
       3 NPC_PIRATE_BOUNTY
       4 NPC_PIRATE_SHIP_BOUNTY
       5 HUNT_DARKNESS_CREATURE
       6 DARKNESS_CLEANUP
       7 PROPS_REQUEST
       8 FRUIT_REQUEST
       9 HUNT_CREATURE
   - Shows nested task/target data, quest position, reward fields, and raw IDs/state.

2. Edit Raw Reward Values
   - PlayerQuest fields 9 and 10 are fixed uint32 reward values.
   - The editor can change them without resizing the quest.
   - Their exact Qbits-versus-XP ordering is intentionally NOT claimed yet.
   - The entire known serialized save tree is validated before writing.

3. Abandon Selected Quest
   - Removes one complete PlayerQuest array element.
   - Decrements the quest-array count.
   - Updates the serialized array length.
   - Validates the complete file before writing.
   - This is an experimental save-level equivalent of removing/abandoning a
     generated side quest.

4. Quest-specific recovery
   - Undo Last Quest Edit (.prev)
   - Restore Original Quests (.bak)

5. Story progression catalog
   - Reads the current progression TaskCfg ID from the already mapped
     93_meta.sav progression field.
   - Loads and searches the extracted game's configs/progression/*.cfg files.
   - Shows Task ID, storyStep, chapter, category, description token, argument,
     needed items, and config rewards.
   - The current task is marked in the catalog.
   - Direct story advancement remains read-only because story/world state is
     distributed across multiple save files and subsystems.

Reverse-engineering findings used by v1.15
------------------------------------------
The supplied 93_quests.sav is:
  top-level field 1 -> type 0x17 PlayerQuest array

The supplied save contains three generated quests:
  FRUIT_REQUEST
  HUNT_CREATURE
  FRUIT_REQUEST

The HUNT_CREATURE record contains one nested task whose target string is:
  dino_tl_l_a

This matches quest type value 9 to HUNT_CREATURE and lines up the complete
0-9 enum with QuestsDistributionConfig.

The supplied slot metadata uses progression TaskCfg IDs 14, 15, or 16
depending on the slot. Those IDs map directly to configs/progression/*.cfg.

Testing performed
-----------------
All 11 supplied save slots were tested.

For every slot:
- Parsed all 3 PlayerQuest entries.
- Confirmed quest types and nested task records.
- Changed raw reward fields 9 and 10 in memory and reparsed successfully.
- Removed the middle HUNT_CREATURE quest structurally.
- Verified quest count changed from 3 to 2.
- Revalidated the full serialized save tree.
- Performed Zstandard recompression/decompression round trips.
- Parsed 93_meta.sav and matched its current progression value to TaskCfg.

The supplied config archive contains 148 TaskCfg progression definitions.

Existing features retained
--------------------------
- Inventory quantity editing
- Set Max Stack from ItemCfg
- Condition / Charge editing
- Different-length Replace Item ID
- Duplicate / Remove inventory items
- Quickslot move/swap, copy, and clear
- Qbits editor
- Player class-level editor
- Save-slot metadata and variable-length display-name editor
- Ship / vehicle inspection and component replacement
- Blueprint collection inspection and blueprint config catalog
- Config item catalog
- Experiment Lab
- Structural save validation
- .bak + .prev recovery

Requirements
------------
Python 3.x and the 'zstandard' package.

Install zstandard:
    py -m pip install zstandard

Usage
-----
Run:
    Cubic_Odyssey_Save_Editor.py

When prompted for the save folder, you may select:
- the normal Cubic Odyssey save folder
- the nested "0" save container
- an individual slot folder containing 93_client_state.sav

Select the extracted game's "configs" folder to enable item/component catalogs
and the new story TaskCfg progression catalog.

Safety
------
Keep a separate copy of your saves and disable Steam Cloud while testing.
The editor maintains an original .bak baseline and a one-step .prev copy for
files it edits.
