# Publishing CENSO

Two steps, in this order. The second is pointless before the first: a FAIR
assessment marks an ontology unfindable if its IRI does not dereference,
however well built the file is.

## 1. Serve the files somewhere stable

Anything with a permanent HTTPS URL. Two options, both fine:

**GitHub Pages** — conventional for a paper artefact.
Push `ontology/dist/censo-full.{ttl,owl}`, `ontology/reg/*.ttl` and
`ontology/censo-shapes.ttl` to a repository, enable Pages, and the base is
`https://<user>.github.io/<repo>`.

**A university page** — if Boğaziçi provides one with a stable HTTPS URL, that
works too. Avoid any address tied to a department or a personal account that
may be withdrawn: a w3id redirect is permanent, and pointing it at a URL that
later disappears is worse than not registering it.

## 2. Register the w3id redirect

1. Fork <https://github.com/perma-id/w3id.org>
2. Create a directory `censo/`
3. Copy `w3id-censo/.htaccess` into it, replacing every `{{BASE}}` with the
   base URL from step 1
4. Open a pull request. Their guidance asks for a short description and a
   contact address; both are already in the file header.

Once merged, check it:

```bash
curl -sIL -H "Accept: text/turtle" https://w3id.org/censo/ | grep -i location
curl -sIL -H "Accept: application/rdf+xml" https://w3id.org/censo/ | grep -i location
```

## 3. Then run FOOPS!

<https://foops.linkeddata.es/> — paste `https://w3id.org/censo/`, not a file
upload. Uploading a file cannot score Findability or Accessibility, so the
result would understate the ontology and tell you nothing you can act on.

## Publishing a new release

The site is a checkout of the repository GitHub Pages serves, in
`publish/site`. `scripts/97_assemble_publish.py` writes into it; it does not
commit, because a push is a publication and should be one deliberate act:

```bash
python scripts/97_assemble_publish.py          # rebuild
python scripts/97_assemble_publish.py --check  # exit 1 if the site is stale
cd publish/site && git add -A && git commit && git push
```

The script refuses to overwrite a release directory git already tracks. That
guard is the whole point: `https://w3id.org/censo/2.3.0` must keep returning
the 2.3.0 axioms after 2.4.0 is published, and the same holds for the modules'
own version IRIs — `shapes/2.4.0`, `reg/2.4.0`, `alignment/2.0.0` — which are
frozen under `releases/<module>/<version>/`. If a build differs from a tracked
release, the version is what has to change, not the archive.

## Changing the w3id rules

`w3id-censo/.htaccess` in this repository is the source; the file the redirect
actually uses lives in the w3id.org repository, so **editing it here changes
nothing until a pull request carries it over**. That is the manual step:

1. Fork <https://github.com/perma-id/w3id.org> (or pull your existing fork)
2. Replace `censo/.htaccess` with this one
3. Open the pull request, and check the new rules once it is merged:

```bash
for u in shapes/2.4.0 reg/2.4.0 alignment alignment/2.0.0; do
  curl -sIL -o /dev/null -w "%{http_code} $u\n" "https://w3id.org/censo/$u"
done
```

Until it is merged those four IRIs return 404 through w3id, while the files
themselves are already served at
`https://recepcanaltinbag.github.io/censo/releases/...`.
