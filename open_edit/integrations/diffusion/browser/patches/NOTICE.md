The unchanged koota+0.6.6.patch comes from diffusionstudio/editor commit
fefcde9df7198466bd7cc9f3a9d7eae1575b5b12, patches/koota+0.6.6.patch:
https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/patches/koota%2B0.6.6.patch

Retained under the upstream MPL-2.0 license (see ../vendor/LICENSE). The patch
fixes koota static Or queries across trait generations. OpenEdit's MIT setup
helper applies the same changes without running npm lifecycle scripts; its
output is checked against this upstream patch. Koota itself retains its MIT
license in the separately installed npm dependency.
