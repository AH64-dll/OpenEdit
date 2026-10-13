# Public website

The source is this directory. `scripts/build_site.py` adds the verified video,
poster and editable ZIP from `examples/openedit-explainer`, so the website and
repository use the same demo without maintaining duplicate binary files.

```bash
python scripts/build_site.py --output /tmp/openedit-site
python -m http.server 8080 --directory /tmp/openedit-site
```

`Publish website` runs on relevant main-branch changes or manual dispatch. It
updates the existing `gh-pages` branch and explicitly requests a Pages build;
GitHub-token pushes alone do not trigger those builds. Keep the repository's
Pages source configured as `gh-pages` / root. The deployed URL is
https://ah64-dll.github.io/OpenEdit/.

The guide distinguishes the current 1.4 source from earlier public releases.
When publishing a new app version, update its visible version/setup details.
The MP4 and project ZIP are same-origin downloads. Video has native controls,
captions and no autoplay; it does not load until requested. The guide uses
system fonts and works without JavaScript; JS only adds clipboard buttons.
