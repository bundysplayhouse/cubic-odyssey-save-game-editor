# cubic-odyssey-save-game-editor

a cubic odyssey save game editor

This is built using AI it is highly experimental!
Use at your own risk!
You have been warned!

Current features
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
