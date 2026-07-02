# Local research materials

Drop your own background materials for a research question into a **subfolder**
of this directory, one subfolder per topic. For example:

```
question/
├── rhythm-and-reward/
│   ├── review.md
│   ├── notes.txt
│   └── background.rst
└── temporal-asymmetry/
    └── summary.md
```

During **Stage 0 (question clarification)**, cogTIDE scans these subfolders,
scores their names against your research question by simple token overlap, and
offers to ingest the best-matching folder. All `.md`, `.txt`, `.rst`, and
`.markdown` files in the selected subfolder are concatenated (up to a character
budget) and handed to the clarifier as background context.

Notes:

- Only text files (`.md`, `.txt`, `.rst`, `.markdown`) are ingested. PDFs and
  other binaries are ignored — convert them to text first if you want them used.
- The context is **advisory background**, not authoritative evidence. The
  clarifier will not treat it as ground truth or copy it verbatim.
- Everything you add here (other than this `README.md` and `.gitkeep`) is
  **git-ignored** by default, so your private materials are not committed. See
  the repository `.gitignore`.
