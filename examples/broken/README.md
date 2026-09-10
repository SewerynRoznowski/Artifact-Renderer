# Deliberately broken examples

Everything in this folder is wrong on purpose. Nothing here is a model to
copy — these exist to show what a page does when something is missing,
mistyped, or not supported, because the alternative to showing it is
silence, and a silently absent artifact is the failure this whole design
is trying to avoid.

The working examples are one level up, and none of them are broken.

| Folder | What is wrong |
|---|---|
| `Missing-Files` | Every section names a file that isn't there |
| `Unknown-Types` | A type nobody implements, and one that isn't built yet |
| `Bad-Options` | Options that are wrong, unknown, or out of range |

Run `mav check examples/broken/Missing-Files` to see the same problems as
text — it exits non-zero, which is what makes it usable in CI.
