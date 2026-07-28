# Remotion Licensing for Open Edit

Open Edit can optionally render React motion graphics with
[Remotion](https://www.remotion.dev/). Remotion uses a custom two-tier license.

## Free license (no signup)

Eligible when you are:

- an individual
- a for-profit organization with **up to 3 employees**
- a non-profit / not-for-profit (as defined by Remotion)
- evaluating Remotion (non-production)

Commercial video creation is allowed under the free license when eligible.
See https://www.remotion.dev/docs/license and `LICENSE.md` in the Remotion repo.

## Company / Automators license

If your organization has **4 or more employees** (including contractors in
collaborations that push the combined headcount ≥ 4), you must purchase a
Company License from Remotion.

Open Edit is an **automated video editor**. For orgs that ship Open Edit as a
product or run automated Remotion renders at scale, Remotion’s **Automators**
pricing tier is the relevant commercial product. See:

- https://www.remotion.dev/docs/license/faq
- https://www.remotion.pro/license

## Open Edit policy

1. Remotion is an **optional** dependency. Core timeline editing works without it.
2. CI Remotion smoke tests that download Chromium are gated behind
   `OPEN_EDIT_REMOTION_SMOKE=1`.
3. Do not hide or strip Remotion license notices from bundled starter templates.
4. Operators deploying Open Edit for larger companies must obtain their own
   Remotion license; Open Edit does not grant one.
