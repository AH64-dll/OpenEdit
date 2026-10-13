# Think it. Edit it.

[Ten-second preview](preview.mp4), with original motion graphics and synthesized
stereo music. `scene.jsx` is editable literal graphics source; `score.wav` is the
original audio. OpenEdit's live canvas and export UI produced the checked preview.

Using the installed environment's Python, create a new project:

```bash
/path/to/OpenEdit/.venv/bin/python create_project.py --project ~/OpenEditProjects/explainer
```

On Windows use `C:\path\to\OpenEdit\.venv\Scripts\python.exe` and an absolute
project folder. The script uses real MCP import/commit calls, requires the
installed graphics runtime, and refuses to reinitialize an existing project.
Open the project in the editor, select **Graphics** to inspect its animated layers,
and use **Export** for a new video. All clips and graphic layers stay editable.

The source/audio are original assets under the repository's MIT license. Font
rendering uses the package's OFL font. The [workflow log](../../docs/OPENEDIT_EXPLAINER_WORKFLOW.md)
records actual tests, authoring mistakes, fixes and the unverified live model turn.
