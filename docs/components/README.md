# Components

Each document here specifies one stage of the pipeline. They are listed in execution
order, but they can be built and tested somewhat independently.

| # | Component | File | Responsibility |
|---|---|---|---|
| 1 | Watcher | [watcher.md](watcher.md) | Observe `inbox/`, debounce, queue work durably |
| 2 | Extraction | [extraction.md](extraction.md) | Turn any file into text (OCR / native / ASR) |
| 3 | Classification | [classification.md](classification.md) | laya Router, shortlist, confidence gates |
| 4 | Novelty & Emergence | [novelty-and-emergence.md](novelty-and-emergence.md) | Discover and name new categories |
| 5 | Category Management | [category-management.md](category-management.md) | User edits + re-classification triggers |
| 6 | Organizer & Naming | [organizer-and-naming.md](organizer-and-naming.md) | Move and rename files consistently |
| 7 | Review Loop | [review-loop.md](review-loop.md) | Correct misfiles, collect ground truth |
